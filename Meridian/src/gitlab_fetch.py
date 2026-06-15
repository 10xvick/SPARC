#!/usr/bin/env python3
"""
GitLab Commits Fetcher
Fetches commit details from GitLab repositories and exports output-compatible CSVs.

Output compatibility target (same commit/file column names as github_fetch.py):
- output/github_commits.csv
- output/github_commit_files.csv
"""

import csv
import json
import os
import sys
import time
import fcntl
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote
from contextlib import contextmanager

import pandas as pd
import requests


# ============================================================================
# PATHS / CONFIG
# ============================================================================

def _resolve_project_root() -> str:
    env_root = os.getenv("TEAMSIGHT_HOME")
    if env_root:
        return os.path.abspath(os.path.expanduser(env_root))

    source_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isdir(os.path.join(source_root, "config")):
        return source_root

    cwd_root = os.getcwd()
    if os.path.isdir(os.path.join(cwd_root, "config")):
        return cwd_root

    return source_root


PROJECT_ROOT = _resolve_project_root()
CONFIG_FILE = os.path.join(PROJECT_ROOT, "config", "gitlab_config.json")
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "output", "github_commits.csv")
CHECKPOINT_FILE = os.path.join(PROJECT_ROOT, "data", "gitlab_fetch_checkpoint.json")
FETCH_LOCK_FILE = os.path.join(PROJECT_ROOT, "data", "scm_fetch.lock")
REPO_FETCH_DELAY = 2
COMMIT_BATCH_SIZE = 100
MIN_COMMIT_DATE = "2025-04-01"
CHECKPOINT_OVERLAP_DAYS = 15
REPOSITORY_LIST_FILE: Optional[str] = None


class GitLabFetchError(RuntimeError):
    """Raised when one or more GitLab repositories cannot be fetched."""


def _ensure_parent_dir(file_path: str) -> None:
    parent_dir = os.path.dirname(file_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)


def _derive_commit_files_output(commits_output: str) -> str:
    """Derive file-level CSV output path from commit-level CSV path."""
    name = os.path.basename(commits_output)
    directory = os.path.dirname(commits_output)

    if name.endswith("_commits.csv"):
        file_name = name.replace("_commits.csv", "_commit_files.csv")
    elif name.endswith(".csv"):
        file_name = name.replace(".csv", "_files.csv")
    else:
        file_name = f"{name}_files.csv"

    return os.path.join(directory, file_name)


@contextmanager
def acquire_fetch_lock(lock_file: str = FETCH_LOCK_FILE):
    """Acquire shared lock to prevent concurrent SCM fetch jobs."""
    _ensure_parent_dir(lock_file)
    lock_handle = open(lock_file, "w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_handle.close()
        raise RuntimeError("Another SCM fetch job is already running")

    try:
        lock_handle.write(str(os.getpid()))
        lock_handle.flush()
        yield
    finally:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_UN)
        finally:
            lock_handle.close()


def _resolve_path(path_value: str) -> str:
    if os.path.isabs(path_value):
        return path_value
    return os.path.join(PROJECT_ROOT, path_value)


def load_config_file(config_file: str = CONFIG_FILE) -> Dict[str, Any]:
    if not os.path.exists(config_file):
        print(f"Warning: Config file '{config_file}' not found. Using defaults.")
        return {}

    try:
        with open(config_file, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        if "outputFile" in config and not os.path.isabs(config["outputFile"]):
            config["outputFile"] = _resolve_path(config["outputFile"])
        if "checkpointFile" in config and not os.path.isabs(config["checkpointFile"]):
            config["checkpointFile"] = _resolve_path(config["checkpointFile"])
        return config
    except Exception as exc:
        print(f"Warning: Could not load config file: {exc}")
        return {}


GLOBAL_CONFIG_DATA = load_config_file()
GITLAB_TOKEN = GLOBAL_CONFIG_DATA.get("default", {}).get("gitlabToken", "") or os.getenv("GITLAB_TOKEN", "")
GITLAB_API_BASE_URL = GLOBAL_CONFIG_DATA.get("default", {}).get("gitlabApiBaseUrl", "http://172.20.0.7:4156/api/v4")
OUTPUT_FILE = GLOBAL_CONFIG_DATA.get("outputFile", OUTPUT_FILE)
CHECKPOINT_FILE = GLOBAL_CONFIG_DATA.get("checkpointFile", CHECKPOINT_FILE)
try:
    COMMIT_BATCH_SIZE = int(GLOBAL_CONFIG_DATA.get("default", {}).get("batchSize", COMMIT_BATCH_SIZE))
except (TypeError, ValueError):
    COMMIT_BATCH_SIZE = 100
if COMMIT_BATCH_SIZE <= 0:
    COMMIT_BATCH_SIZE = 100

CHECKPOINT_OVERLAP_DAYS = int(
    GLOBAL_CONFIG_DATA.get("default", {}).get(
        "checkpointOverlapDays",
        GLOBAL_CONFIG_DATA.get("default", {}).get("overlapDays", CHECKPOINT_OVERLAP_DAYS),
    )
)
if CHECKPOINT_OVERLAP_DAYS < 0:
    CHECKPOINT_OVERLAP_DAYS = 0


def _load_valid_jira_projects() -> List[str]:
    try:
        jira_config_path = os.path.join(PROJECT_ROOT, "config", "jira_config.json")
        with open(jira_config_path, "r", encoding="utf-8") as handle:
            jira_cfg = json.load(handle)
        return list(jira_cfg.get("projects", {}).keys())
    except Exception:
        return []


VALID_JIRA_PROJECTS = _load_valid_jira_projects()


# Reuse categorization + JIRA parsing logic from github_fetch for exact compatibility.
try:
    from github_fetch import categorize_file, extract_jira_ids  # type: ignore
except Exception:
    def extract_jira_ids(text: str) -> str:
        return ""

    def categorize_file(filename: str, filepath: str) -> Dict[str, Any]:
        return {
            "category": "Source",
            "subcategory": "Other",
            "is_screen": "false",
            "confidence": 0.5,
        }


# ============================================================================
# API HELPERS
# ============================================================================

def get_headers(token: Optional[str] = None) -> Dict[str, str]:
    auth_token = token if token else GITLAB_TOKEN
    return {
        "PRIVATE-TOKEN": auth_token,
        "Accept": "application/json",
        "User-Agent": "TeamSight-GitLab-Fetcher",
    }


def make_request(url: str, params: Optional[Dict[str, Any]] = None, token: Optional[str] = None) -> Any:
    try:
        response = requests.get(url, headers=get_headers(token), params=params, timeout=30)
        if response.status_code != 200:
            msg = f"GitLab API returned status {response.status_code}"
            try:
                detail = response.json()
                if isinstance(detail, dict):
                    msg += f": {detail.get('message', response.text)}"
                else:
                    msg += f": {response.text}"
            except Exception:
                msg += f": {response.text}"
            raise Exception(msg)
        return response.json()
    except requests.exceptions.RequestException as exc:
        raise Exception(f"Request failed: {exc}")


def parse_gitlab_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    val = value.strip()
    if val.endswith("Z"):
        val = val.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(val)
        return dt.replace(tzinfo=None)
    except Exception:
        return None


def _count_unified_diff_line_stats(diff_text: Any) -> Tuple[int, int]:
    """Count added/deleted lines from a unified diff body.

    GitLab commit diff entries often do not provide additions/deletions fields,
    so we derive per-file LOC directly from the diff text.
    """
    if not diff_text:
        return 0, 0

    added = 0
    deleted = 0
    for raw_line in str(diff_text).splitlines():
        if not raw_line:
            continue
        # Skip diff metadata/header lines.
        if raw_line.startswith(("+++", "---", "@@", "diff --git", "index ")):
            continue
        if raw_line.startswith("+"):
            added += 1
        elif raw_line.startswith("-"):
            deleted += 1
    return added, deleted


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    txt = str(value).strip()
    if txt in ("", "nan", "None"):
        return default
    try:
        return int(float(txt))
    except Exception:
        return default


def _is_xhaul_repo(repo_path: str, repo_config: Dict[str, Any]) -> bool:
    team = str(repo_config.get("team", "") or "").strip().lower()
    if team == "xhaul":
        return True
    return "xhaul" in str(repo_path or "").strip().lower()


def _dedupe_commit_files(file_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not file_rows:
        return []

    deduped: List[Dict[str, Any]] = []
    seen: set = set()
    for row in file_rows:
        key = (
            str(row.get("commit_sha", "")).strip(),
            str(row.get("repository", "")).strip(),
            str(row.get("filepath", "")).strip(),
            str(row.get("status", "")).strip().lower(),
            _safe_int(row.get("lines_added")),
            _safe_int(row.get("lines_deleted")),
            _safe_int(row.get("lines_changed")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _get_min_commit_date() -> Optional[datetime]:
    if not MIN_COMMIT_DATE:
        return None
    return datetime.strptime(MIN_COMMIT_DATE, "%Y-%m-%d")


def _get_min_commit_api_since() -> Optional[datetime]:
    min_commit_date = _get_min_commit_date()
    if min_commit_date is None:
        return None
    if CHECKPOINT_OVERLAP_DAYS <= 0:
        return min_commit_date
    return min_commit_date - timedelta(days=CHECKPOINT_OVERLAP_DAYS)


# ============================================================================
# CONFIG / REPOSITORY HELPERS
# ============================================================================

def get_repository_config(config_data: Dict[str, Any], repo_path: str) -> Optional[Dict[str, Any]]:
    repo_config = {
        "gitlabToken": GITLAB_TOKEN,
        "gitlabApiBaseUrl": GITLAB_API_BASE_URL,
        "projectId": None,
        "team": "",
        "fetchAllBranches": True,
        "refName": "",
    }

    if "default" in config_data:
        default_cfg = config_data["default"]
        if "gitlabToken" in default_cfg:
            repo_config["gitlabToken"] = default_cfg["gitlabToken"]
        if "gitlabApiBaseUrl" in default_cfg:
            repo_config["gitlabApiBaseUrl"] = default_cfg["gitlabApiBaseUrl"]
        if "fetchAllBranches" in default_cfg:
            repo_config["fetchAllBranches"] = bool(default_cfg["fetchAllBranches"])
        if "refName" in default_cfg:
            repo_config["refName"] = str(default_cfg["refName"] or "")

    repo_specific = config_data.get("repositories", {}).get(repo_path, {})
    if "gitlabToken" in repo_specific:
        repo_config["gitlabToken"] = repo_specific["gitlabToken"]
    if "gitlabApiBaseUrl" in repo_specific:
        repo_config["gitlabApiBaseUrl"] = repo_specific["gitlabApiBaseUrl"]
    if "projectId" in repo_specific:
        repo_config["projectId"] = repo_specific["projectId"]
    if "team" in repo_specific:
        repo_config["team"] = repo_specific["team"]
    if "fetchAllBranches" in repo_specific:
        repo_config["fetchAllBranches"] = bool(repo_specific["fetchAllBranches"])
    if "refName" in repo_specific:
        repo_config["refName"] = str(repo_specific["refName"] or "")

    if not repo_config["gitlabToken"]:
        return None
    return repo_config


def get_repository_list(config_data: Dict[str, Any]) -> List[str]:
    if not config_data or "repositories" not in config_data:
        return []
    return list(config_data.get("repositories", {}).keys())


REPOSITORY_LIST = get_repository_list(GLOBAL_CONFIG_DATA)


def resolve_project_id(repo_path: str, repo_config: Dict[str, Any]) -> str:
    if repo_config.get("projectId"):
        return str(repo_config["projectId"])

    api_base = repo_config["gitlabApiBaseUrl"]
    token = repo_config["gitlabToken"]
    encoded = quote(repo_path, safe="")
    url = f"{api_base}/projects/{encoded}"
    project = make_request(url, token=token)
    project_id = project.get("id")
    if project_id is None:
        raise GitLabFetchError(f"Unable to resolve project id for {repo_path}")
    return str(project_id)


def load_checkpoint() -> Dict[str, str]:
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:
            print(f"Warning: Could not load checkpoint file: {exc}")
    return {}


def save_checkpoint(checkpoint_data: Dict[str, str]) -> None:
    try:
        _ensure_parent_dir(CHECKPOINT_FILE)
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as handle:
            json.dump(checkpoint_data, handle, indent=2)
        print(f"Checkpoint saved to {CHECKPOINT_FILE}")
    except Exception as exc:
        print(f"Warning: Could not save checkpoint: {exc}")


# ============================================================================
# REVIEW HELPERS (MR-based mapping to GitHub-like columns)
# ============================================================================

def _count_mr_comments(notes: List[Dict[str, Any]]) -> str:
    commenter_counts: Dict[str, int] = {}
    for note in notes:
        body = str(note.get("body", "")).strip()
        if not body:
            continue
        if note.get("system"):
            continue
        author = note.get("author", {}) or {}
        commenter = author.get("username") or author.get("name") or "unknown"
        commenter_counts[commenter] = commenter_counts.get(commenter, 0) + 1
    if not commenter_counts:
        return ""
    return ";".join([f"{k}:{v}" for k, v in sorted(commenter_counts.items())])


def get_mr_review_info(project_id: str, commit_sha: str, repo_config: Dict[str, Any]) -> Tuple[str, str, str]:
    api_base = repo_config["gitlabApiBaseUrl"]
    token = repo_config["gitlabToken"]

    try:
        mrs_url = f"{api_base}/projects/{project_id}/repository/commits/{commit_sha}/merge_requests"
        mrs = make_request(mrs_url, token=token)
        if not isinstance(mrs, list) or not mrs:
            return ("", "", "")

        mr = mrs[0]
        mr_iid = str(mr.get("iid", ""))
        if not mr_iid:
            return ("", "", "")

        approver = ""
        try:
            approvals_url = f"{api_base}/projects/{project_id}/merge_requests/{mr_iid}/approvals"
            approvals = make_request(approvals_url, token=token)
            approved_by = approvals.get("approved_by", []) if isinstance(approvals, dict) else []
            if approved_by:
                last = approved_by[-1]
                user = last.get("user", {}) if isinstance(last, dict) else {}
                approver = user.get("username") or user.get("name") or ""
        except Exception:
            approver = ""

        review_comments = ""
        try:
            notes_url = f"{api_base}/projects/{project_id}/merge_requests/{mr_iid}/notes"
            notes = make_request(notes_url, params={"per_page": 100}, token=token)
            if isinstance(notes, list):
                review_comments = _count_mr_comments(notes)
        except Exception:
            review_comments = ""

        return (mr_iid, approver, review_comments)

    except Exception:
        return ("", "", "")


# ============================================================================
# FETCH / EXPORT
# ============================================================================

def get_all_branches(project_id: str, repo_config: Dict[str, Any]) -> List[str]:
    """Fetch all branch names for a project."""
    api_base = repo_config["gitlabApiBaseUrl"]
    token = repo_config["gitlabToken"]
    branches_url = f"{api_base}/projects/{project_id}/repository/branches"

    all_branches: List[str] = []
    page = 1
    per_page = 100

    while True:
        try:
            branches_data = make_request(
                branches_url,
                params={"per_page": per_page, "page": page},
                token=token,
            )
        except Exception as exc:
            print(f"    Warning: Could not fetch branches for project {project_id}: {exc}")
            break

        if not isinstance(branches_data, list) or not branches_data:
            break

        all_branches.extend([
            str(branch.get("name", "")).strip()
            for branch in branches_data
            if str(branch.get("name", "")).strip()
        ])

        if len(branches_data) < per_page:
            break

        page += 1

    # Preserve order while removing duplicates.
    deduped_branches = list(dict.fromkeys(all_branches))
    return deduped_branches


def get_repository_commits_batch(
    repo_path: str,
    project_id: str,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    repo_config: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    if repo_config is None:
        repo_config = get_repository_config(GLOBAL_CONFIG_DATA, repo_path)
        if not repo_config:
            return [], True

    api_base = repo_config["gitlabApiBaseUrl"]
    token = repo_config["gitlabToken"]

    all_commits: List[Dict[str, Any]] = []
    had_error = False
    fetch_all_branches = bool(repo_config.get("fetchAllBranches", True))
    ref_name = str(repo_config.get("refName", "") or "").strip()
    # Guard against the same SHA appearing on multiple branches
    seen_shas: set = set()

    # Determine which branches to fetch from
    if ref_name:
        branches_to_fetch = [ref_name]
    elif fetch_all_branches:
        branches_to_fetch = get_all_branches(project_id, repo_config)
    else:
        branches_to_fetch = []

    if not branches_to_fetch:
        return [], False

    min_commit_date = _get_min_commit_date()
    is_xhaul_repo = _is_xhaul_repo(repo_path, repo_config)
    api_since = since if since is not None else _get_min_commit_api_since()

    for branch_name in branches_to_fetch:
        page = 1
        per_page = min(100, COMMIT_BATCH_SIZE)

        while True:
            commits_url = f"{api_base}/projects/{project_id}/repository/commits"
            params: Dict[str, Any] = {
                "per_page": per_page,
                "page": page,
                "ref_name": branch_name,
            }
            if api_since:
                params["since"] = api_since.isoformat() + "Z"
            if until:
                params["until"] = until.isoformat() + "Z"

            try:
                commits_data = make_request(commits_url, params=params, token=token)
            except Exception as exc:
                print(f"    Error fetching {branch_name} page {page}: {exc}")
                had_error = True
                break

            if not isinstance(commits_data, list) or not commits_data:
                break

            stop_fetching = False
            batch_commits: List[Dict[str, Any]] = []

            for commit in commits_data:
                sha = str(commit.get("id", ""))
                if not sha or sha in seen_shas:
                    continue
                seen_shas.add(sha)

                detail_url = f"{api_base}/projects/{project_id}/repository/commits/{sha}"
                diff_url = f"{api_base}/projects/{project_id}/repository/commits/{sha}/diff"

                try:
                    commit_detail = make_request(detail_url, params={"stats": "true"}, token=token)
                    commit_diff = make_request(diff_url, token=token)
                except Exception as exc:
                    print(f"    Error fetching commit details for {sha[:8]}: {exc}")
                    had_error = True
                    continue

                commit_date = (
                    parse_gitlab_datetime(commit.get("authored_date"))
                    or parse_gitlab_datetime(commit.get("committed_date"))
                    or parse_gitlab_datetime(commit.get("created_at"))
                )
                if not commit_date:
                    continue

                if since and commit_date < since:
                    stop_fetching = True
                    break
                if until and commit_date >= until:
                    continue

                if min_commit_date is not None:
                    if commit_date < min_commit_date:
                        stop_fetching = True
                        break

                full_message = str(commit_detail.get("message", commit.get("message", "")))
                commit_message = full_message.split("\n")[0] if full_message else ""
                jira_ids = extract_jira_ids(full_message)

                pr_number, approver, review_comments = get_mr_review_info(project_id, sha, repo_config)

                # Skip merge commits — they carry files from both sides of the
                # merge and would double-count lines already recorded in the
                # individual feature commits.
                # Primary signal: GitLab's parent_ids list (merge = 2+ parents).
                # Fallback: commit message prefix for repos where parent_ids is absent.
                parent_ids = commit_detail.get("parent_ids", []) if isinstance(commit_detail, dict) else []
                if not isinstance(parent_ids, list):
                    parent_ids = []
                is_merge = len(parent_ids) > 1
                if not is_merge:
                    _merge_re = re.compile(r'^Merge (pull request|branch)\b', re.IGNORECASE)
                    is_merge = bool(_merge_re.match(commit_message))
                if is_merge:
                    continue

                count_review_flag = "true" if pr_number else "false"

                stats = commit_detail.get("stats", {}) if isinstance(commit_detail, dict) else {}
                diff_files = commit_diff if isinstance(commit_diff, list) else []

                commit_files: List[Dict[str, Any]] = []
                for file_info in diff_files:
                    old_path = str(file_info.get("old_path") or "").strip()
                    new_path = str(file_info.get("new_path") or "").strip()
                    filepath = new_path or old_path
                    filename = os.path.basename(filepath) if filepath else ""

                    additions = _safe_int(file_info.get("additions"))
                    deletions = _safe_int(file_info.get("deletions"))
                    if additions == 0 and deletions == 0:
                        additions, deletions = _count_unified_diff_line_stats(file_info.get("diff"))
                    changes = _safe_int(file_info.get("changes"))
                    if changes == 0:
                        changes = additions + deletions

                    if file_info.get("new_file"):
                        status = "added"
                    elif file_info.get("deleted_file"):
                        status = "removed"
                    elif file_info.get("renamed_file"):
                        status = "renamed"
                    else:
                        status = "modified"

                    file_category = categorize_file(filename, filepath)
                    commit_files.append({
                        "commit_sha": sha,
                        "date": commit_date,
                        "author": commit_detail.get("author_name") or commit.get("author_name") or "",
                        "author_email": commit_detail.get("author_email") or commit.get("author_email") or "",
                        "repository": repo_path,
                        "jira_id": jira_ids,
                        "filename": filename,
                        "filepath": filepath,
                        "file_extension": os.path.splitext(filename)[1] if filename else "",
                        "status": status,
                        "lines_added": additions,
                        "lines_deleted": deletions,
                        "lines_changed": changes,
                        "category": file_category["category"],
                        "subcategory": file_category["subcategory"],
                        "is_screen": file_category["is_screen"],
                        "confidence": file_category["confidence"],
                    })

                deduped_commit_files = _dedupe_commit_files(commit_files)
                if is_xhaul_repo:
                    # For XHAUL, trust deduped file-level diff totals over merge-inflated commit stats.
                    files_changed = len(deduped_commit_files)
                    lines_added = sum(_safe_int(f.get("lines_added")) for f in deduped_commit_files)
                    lines_deleted = sum(_safe_int(f.get("lines_deleted")) for f in deduped_commit_files)
                    lines_changed = sum(_safe_int(f.get("lines_changed")) for f in deduped_commit_files)
                else:
                    files_changed = len(diff_files)
                    lines_added = int(stats.get("additions") or 0)
                    lines_deleted = int(stats.get("deletions") or 0)
                    lines_changed = int(stats.get("total") or 0)

                batch_commits.append({
                    "commit_sha": sha,
                    "date": commit_date,
                    "author": commit_detail.get("author_name") or commit.get("author_name") or "",
                    "author_email": commit_detail.get("author_email") or commit.get("author_email") or "",
                    "repository": repo_path,
                    "message": commit_message,
                    "jira_id": jira_ids,
                    "files_changed": files_changed,
                    "lines_added": lines_added,
                    "lines_deleted": lines_deleted,
                    "lines_changed": lines_changed,
                    "pr_number": pr_number,
                    "approver": approver,
                    "review_comments": review_comments,
                    "count_review_flag": count_review_flag,
                    "commit_files": deduped_commit_files,
                })

            all_commits.extend(batch_commits)
            if batch_commits:
                print(f"    Fetched batch {page} from {branch_name}: {len(batch_commits)} commits")

            if stop_fetching or len(commits_data) < per_page:
                break

            page += 1
            time.sleep(0.5)

        if had_error:
            break

    return all_commits, had_error

def export_to_csv(commits: List[Dict[str, Any]], filename: str = "gitlab_commits.csv", append: bool = False) -> None:
    if not commits:
        return

    commits_for_export: List[Dict[str, Any]] = []
    for commit in commits:
        item = commit.copy()
        item.pop("commit_files", None)
        commits_for_export.append(item)

    fieldnames = list(commits_for_export[0].keys())
    file_exists = os.path.exists(filename) and append

    # Dedup: when appending, filter out commits already present.
    # Prefer commit_sha as the dedup key; fall back to
    # (date, author_email, message, lines_added, lines_deleted, lines_changed).
    if file_exists:
        try:
            read_cols = ["date", "author_email", "message", "lines_added", "lines_deleted", "lines_changed"]
            existing_df_cols = list(pd.read_csv(filename, nrows=0).columns)
            has_sha_col = "commit_sha" in existing_df_cols
            if has_sha_col:
                read_cols.append("commit_sha")
            read_cols = [c for c in read_cols if c in existing_df_cols]
            existing_df = pd.read_csv(filename, usecols=read_cols)
            existing_shas: set = set()
            existing_fallback_keys: set = set()
            if has_sha_col:
                existing_shas = set(existing_df["commit_sha"].dropna().astype(str))
            existing_fallback_keys = set(
                zip(
                    existing_df["date"].astype(str),
                    existing_df["author_email"].astype(str),
                    existing_df["message"].astype(str),
                    existing_df.get("lines_added", pd.Series(dtype=str)).fillna("").astype(str),
                    existing_df.get("lines_deleted", pd.Series(dtype=str)).fillna("").astype(str),
                    existing_df.get("lines_changed", pd.Series(dtype=str)).fillna("").astype(str),
                )
            )
            before = len(commits_for_export)
            filtered = []
            for c in commits_for_export:
                sha_val = str(c.get("commit_sha", ""))
                if sha_val and has_sha_col:
                    if sha_val not in existing_shas:
                        filtered.append(c)
                else:
                    key = (
                        str(c.get("date", "")),
                        str(c.get("author_email", "")),
                        str(c.get("message", "")),
                        str(c.get("lines_added", "")),
                        str(c.get("lines_deleted", "")),
                        str(c.get("lines_changed", "")),
                    )
                    if key not in existing_fallback_keys:
                        filtered.append(c)
            commits_for_export = filtered
            skipped = before - len(commits_for_export)
            if skipped:
                print(f"  Skipped {skipped} duplicate commits")
        except Exception:
            pass

    if not commits_for_export:
        print("  No new commits to append")
        return

    mode = "a" if file_exists else "w"
    _ensure_parent_dir(filename)

    # Schema-upgrade guard: if the existing file has fewer columns than the new
    # commits (e.g. commit_sha was added), rewrite the file with the union schema.
    if file_exists:
        existing_cols = list(pd.read_csv(filename, nrows=0).columns)
        new_cols = [c for c in fieldnames if c not in existing_cols]
        if new_cols:
            # Rewrite existing rows with new columns prepended/appended as empty.
            existing_df = pd.read_csv(filename)
            for col in new_cols:
                insert_pos = 0 if col == "commit_sha" else len(existing_df.columns)
                existing_df.insert(insert_pos, col, "")
            # Reorder fieldnames to match the upgraded schema
            fieldnames = list(existing_df.columns)
            existing_df.to_csv(filename, index=False)
            print(f"  Schema upgraded: added columns {new_cols} to {filename}")
            # Now append in normal "a" mode (header already written by to_csv)

    with open(filename, mode, newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(commits_for_export)

    action = "Appended" if file_exists else "Exported"
    print(f"  {action} {len(commits_for_export)} commits to {filename}")


def export_files_to_csv(commits: List[Dict[str, Any]], filename: str = "gitlab_commit_files.csv", append: bool = False) -> None:
    all_files: List[Dict[str, Any]] = []
    for commit in commits:
        all_files.extend(commit.get("commit_files", []))

    all_files = _dedupe_commit_files(all_files)

    if not all_files:
        return

    fieldnames = [
        "commit_sha", "date", "author", "author_email", "repository", "jira_id",
        "filename", "filepath", "file_extension", "status",
        "lines_added", "lines_deleted", "lines_changed",
        "category", "subcategory", "is_screen", "confidence",
    ]

    file_exists = os.path.exists(filename) and append

    if file_exists:
        try:
            existing_df_cols = list(pd.read_csv(filename, nrows=0).columns)
            read_cols = [
                c for c in [
                    "commit_sha", "repository", "filepath", "status",
                    "lines_added", "lines_deleted", "lines_changed"
                ]
                if c in existing_df_cols
            ]
            if read_cols:
                existing_df = pd.read_csv(filename, usecols=read_cols)
                existing_keys = set(
                    zip(
                        existing_df.get("commit_sha", pd.Series(dtype=str)).fillna("").astype(str),
                        existing_df.get("repository", pd.Series(dtype=str)).fillna("").astype(str),
                        existing_df.get("filepath", pd.Series(dtype=str)).fillna("").astype(str),
                        existing_df.get("status", pd.Series(dtype=str)).fillna("").astype(str).str.lower(),
                        existing_df.get("lines_added", pd.Series(dtype=object)).apply(_safe_int),
                        existing_df.get("lines_deleted", pd.Series(dtype=object)).apply(_safe_int),
                        existing_df.get("lines_changed", pd.Series(dtype=object)).apply(_safe_int),
                    )
                )

                before = len(all_files)
                filtered: List[Dict[str, Any]] = []
                for row in all_files:
                    key = (
                        str(row.get("commit_sha", "")).strip(),
                        str(row.get("repository", "")).strip(),
                        str(row.get("filepath", "")).strip(),
                        str(row.get("status", "")).strip().lower(),
                        _safe_int(row.get("lines_added")),
                        _safe_int(row.get("lines_deleted")),
                        _safe_int(row.get("lines_changed")),
                    )
                    if key in existing_keys:
                        continue
                    filtered.append(row)
                all_files = filtered
                skipped = before - len(all_files)
                if skipped:
                    print(f"  Skipped {skipped} duplicate file records")
        except Exception:
            pass

    if not all_files:
        print("  No new file records to append")
        return
    mode = "a" if file_exists else "w"
    _ensure_parent_dir(filename)

    with open(filename, mode, newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(all_files)

    action = "Appended" if file_exists else "Exported"
    print(f"  {action} {len(all_files)} file records to {filename}")


def fetch_all_commits(use_checkpoint: bool = True) -> List[Dict[str, Any]]:
    if not REPOSITORY_LIST:
        print("No repositories configured in gitlab_config.json")
        return []

    checkpoint_data = load_checkpoint() if use_checkpoint else {}
    all_commits: List[Dict[str, Any]] = []
    failed_repositories: List[str] = []
    # Cross-repo guard: prevent the same commit SHA from being written twice
    # (can happen when repos share history or the same repo appears in config
    # under different paths).
    global_seen_shas: set = set()

    print(f"\nStarting GitLab fetch for {len(REPOSITORY_LIST)} repositories")

    commits_output = OUTPUT_FILE
    files_output = _derive_commit_files_output(OUTPUT_FILE)

    first_write_done = os.path.exists(commits_output)
    first_files_write_done = os.path.exists(files_output)

    for idx, repo_path in enumerate(REPOSITORY_LIST, 1):
        print(f"\n[{idx}/{len(REPOSITORY_LIST)}] Processing {repo_path}")

        repo_config = get_repository_config(GLOBAL_CONFIG_DATA, repo_path)
        if repo_config is None:
            print("  Skipping repository - missing gitlab token")
            failed_repositories.append(repo_path)
            continue

        try:
            project_id = resolve_project_id(repo_path, repo_config)
        except Exception as exc:
            print(f"  Error resolving project id: {exc}")
            failed_repositories.append(repo_path)
            continue

        since_date = None
        if use_checkpoint and repo_path in checkpoint_data:
            try:
                since_date = parse_gitlab_datetime(checkpoint_data[repo_path])
            except Exception:
                since_date = None

        if since_date:
            fetch_since = since_date
            if CHECKPOINT_OVERLAP_DAYS > 0:
                fetch_since = since_date - timedelta(days=CHECKPOINT_OVERLAP_DAYS)
                print(
                    f"  Fetching commits since {fetch_since.isoformat()} "
                    f"(checkpoint overlap: {CHECKPOINT_OVERLAP_DAYS} days; checkpoint={since_date.isoformat()})"
                )
            else:
                print(f"  Fetching commits since {since_date.isoformat()} (no overlap)")
        else:
            min_commit_api_since = _get_min_commit_api_since()
            if min_commit_api_since is not None and CHECKPOINT_OVERLAP_DAYS > 0:
                print(
                    f"  Fetching full history since {min_commit_api_since.isoformat()} "
                    f"(MIN_COMMIT_DATE={MIN_COMMIT_DATE}; overlap={CHECKPOINT_OVERLAP_DAYS} days)"
                )
            elif MIN_COMMIT_DATE:
                print(f"  Fetching full history since {MIN_COMMIT_DATE} (no overlap)")
            else:
                print("  Fetching full history (no MIN_COMMIT_DATE)")
            fetch_since = None

        repo_commits, repo_had_error = get_repository_commits_batch(
            repo_path=repo_path,
            project_id=project_id,
            since=fetch_since,
            repo_config=repo_config,
        )

        if repo_had_error:
            failed_repositories.append(repo_path)

        if repo_commits:
            # Filter out any SHAs already written in this session (cross-repo guard)
            new_commits = []
            for c in repo_commits:
                sha = str(c.get("commit_sha", ""))
                if sha and sha in global_seen_shas:
                    continue
                if sha:
                    global_seen_shas.add(sha)
                new_commits.append(c)
            skipped_cross_repo = len(repo_commits) - len(new_commits)
            if skipped_cross_repo:
                print(f"  Skipped {skipped_cross_repo} cross-repo duplicate commit(s)")
            if new_commits:
                export_to_csv(new_commits, commits_output, append=first_write_done)
                export_files_to_csv(new_commits, files_output, append=first_files_write_done)
                first_write_done = True
                first_files_write_done = True

                latest_commit = max(new_commits, key=lambda c: c["date"])
                checkpoint_data[repo_path] = latest_commit["date"].isoformat() + "Z"
                all_commits.extend(new_commits)
            print(f"  Fetched {len(new_commits)} new commits ({len(repo_commits)} raw)")
        else:
            print("  No commits found")

        if idx < len(REPOSITORY_LIST):
            time.sleep(REPO_FETCH_DELAY)

    if use_checkpoint:
        save_checkpoint(checkpoint_data)

    print(f"\nCompleted. Total commits fetched: {len(all_commits)}")
    if failed_repositories:
        unique_failed_repositories = sorted(set(failed_repositories))
        raise GitLabFetchError(
            "GitLab fetch failed for repositories: " + ", ".join(unique_failed_repositories)
        )
    return all_commits


def list_repositories() -> None:
    if not GITLAB_TOKEN:
        print("No gitlab token configured.")
        return

    print("Fetching accessible projects from GitLab...")
    page = 1
    per_page = 100
    total = 0

    while True:
        url = f"{GITLAB_API_BASE_URL}/projects"
        params = {"per_page": per_page, "page": page, "membership": True, "simple": True}
        data = make_request(url, params=params)
        if not isinstance(data, list) or not data:
            break
        for project in data:
            total += 1
            print(f"  {project.get('path_with_namespace')} (id={project.get('id')})")
        if len(data) < per_page:
            break
        page += 1

    print(f"Total projects: {total}")


def test_connection() -> None:
    if not GITLAB_TOKEN:
        print("No gitlab token configured.")
        return
    try:
        url = f"{GITLAB_API_BASE_URL}/user"
        user = make_request(url)
        print("Connection successful")
        print(f"User: {user.get('name')} ({user.get('username')})")
    except Exception as exc:
        print(f"Connection failed: {exc}")


def show_checkpoint() -> None:
    checkpoint = load_checkpoint()
    if not checkpoint:
        print("No checkpoint data found")
        return
    print("Checkpoint status:")
    for repo_path, dt in sorted(checkpoint.items()):
        print(f"  {repo_path}: {dt}")


def reset_checkpoint() -> None:
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        print(f"Removed checkpoint file: {CHECKPOINT_FILE}")
    else:
        print("No checkpoint file to remove")


def parse_config_args(args: List[str]) -> Dict[str, str]:
    config_overrides: Dict[str, str] = {}
    for arg in args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            config_overrides[key.strip().lower()] = value.strip()
    return config_overrides


def apply_config_overrides(config_overrides: Dict[str, str]) -> None:
    global GITLAB_TOKEN, GITLAB_API_BASE_URL, OUTPUT_FILE, CHECKPOINT_FILE
    global REPO_FETCH_DELAY, COMMIT_BATCH_SIZE, MIN_COMMIT_DATE, CHECKPOINT_OVERLAP_DAYS
    global REPOSITORY_LIST_FILE, REPOSITORY_LIST

    if "token" in config_overrides:
        GITLAB_TOKEN = config_overrides["token"]
    if "api_url" in config_overrides:
        GITLAB_API_BASE_URL = config_overrides["api_url"].rstrip("/")
    if "output_file" in config_overrides:
        OUTPUT_FILE = _resolve_path(config_overrides["output_file"])
    if "checkpoint_file" in config_overrides:
        CHECKPOINT_FILE = _resolve_path(config_overrides["checkpoint_file"])
    if "repo_delay" in config_overrides:
        REPO_FETCH_DELAY = int(config_overrides["repo_delay"])
    if "batch_size" in config_overrides:
        COMMIT_BATCH_SIZE = int(config_overrides["batch_size"])
    if "min_date" in config_overrides:
        MIN_COMMIT_DATE = None if config_overrides["min_date"].lower() == "none" else config_overrides["min_date"]
    if "overlap_days" in config_overrides:
        CHECKPOINT_OVERLAP_DAYS = max(0, int(config_overrides["overlap_days"]))

    if "repo_list_file" in config_overrides:
        REPOSITORY_LIST_FILE = _resolve_path(config_overrides["repo_list_file"])
        with open(REPOSITORY_LIST_FILE, "r", encoding="utf-8") as handle:
            repo_items = json.load(handle)
        parsed: List[str] = []
        for item in repo_items:
            if isinstance(item, str):
                parsed.append(item)
            elif isinstance(item, dict) and "owner" in item and "repo" in item:
                parsed.append(f"{item['owner']}/{item['repo']}")
            elif isinstance(item, dict) and "path_with_namespace" in item:
                parsed.append(str(item["path_with_namespace"]))
        REPOSITORY_LIST = parsed


def main() -> None:
    if len(sys.argv) < 2:
        print(
            """
GitLab Commits Fetcher

Usage:
  python gitlab_fetch.py <command> [config_options] [flags]

Commands:
  test                Test GitLab API connection
  list                List accessible projects
  fetch [--full]      Fetch commits (incremental by default, --full for complete fetch)
  recent [days]       Fetch commits from last N days (default: 7)
  checkpoint          Show checkpoint status
  reset-checkpoint    Reset checkpoint file

Config options (key=value):
  token=<token>
  api_url=<url>
  output_file=<file>
  checkpoint_file=<file>
  repo_delay=<seconds>
  batch_size=<number>
  min_date=<YYYY-MM-DD|none>
    overlap_days=<non-negative integer>
  repo_list_file=<json>
            """
        )
        sys.exit(1)

    command = sys.argv[1].lower()
    overrides = parse_config_args(sys.argv[2:])
    if overrides:
        apply_config_overrides(overrides)

    if command == "test":
        test_connection()
    elif command == "list":
        list_repositories()
    elif command == "fetch":
        use_checkpoint = "--full" not in sys.argv
        try:
            with acquire_fetch_lock():
                fetch_all_commits(use_checkpoint=use_checkpoint)
        except GitLabFetchError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)
        except RuntimeError as exc:
            print(f"Warning: {exc}. Skipping this run.")
    elif command == "recent":
        days = 7
        if len(sys.argv) > 2 and sys.argv[2].isdigit():
            days = int(sys.argv[2])
        try:
            with acquire_fetch_lock():
                since_date = datetime.utcnow() - timedelta(days=days)
                all_recent: List[Dict[str, Any]] = []
                failed_repositories: List[str] = []
                for repo_path in REPOSITORY_LIST:
                    repo_config = get_repository_config(GLOBAL_CONFIG_DATA, repo_path)
                    if not repo_config:
                        failed_repositories.append(repo_path)
                        continue
                    try:
                        project_id = resolve_project_id(repo_path, repo_config)
                    except Exception as exc:
                        print(f"  Error resolving project id for {repo_path}: {exc}")
                        failed_repositories.append(repo_path)
                        continue
                    repo_commits, repo_had_error = get_repository_commits_batch(
                        repo_path=repo_path,
                        project_id=project_id,
                        since=since_date,
                        repo_config=repo_config,
                    )
                    if repo_had_error:
                        failed_repositories.append(repo_path)
                    all_recent.extend(repo_commits)
                if all_recent:
                    recent_output = os.path.join(PROJECT_ROOT, "output", f"gitlab_recent_commits_{days}days.csv")
                    export_to_csv(all_recent, recent_output, append=False)
                    export_files_to_csv(all_recent, _derive_commit_files_output(recent_output), append=False)
                if failed_repositories:
                    unique_failed_repositories = sorted(set(failed_repositories))
                    raise GitLabFetchError(
                        "GitLab recent fetch failed for repositories: " + ", ".join(unique_failed_repositories)
                    )
        except GitLabFetchError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)
        except RuntimeError as exc:
            print(f"Warning: {exc}. Skipping this run.")
    elif command == "checkpoint":
        show_checkpoint()
    elif command == "reset-checkpoint":
        reset_checkpoint()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
