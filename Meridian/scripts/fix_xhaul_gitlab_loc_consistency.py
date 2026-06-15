#!/usr/bin/env python3
"""Repair XHAUL GitLab LOC consistency in output CSVs.

What it fixes:
1. Deduplicates XHAUL GitLab file rows in output/github_commit_files.csv
2. Recomputes XHAUL commit summary LOC in output/github_commits.csv from deduped file rows

Scope guard:
- Only repositories mapped to team "XHAUL" in config/gitlab_config.json are touched.
- Non-XHAUL rows are preserved as-is.

Usage:
  .venv/bin/python scripts/fix_xhaul_gitlab_loc_consistency.py
  .venv/bin/python scripts/fix_xhaul_gitlab_loc_consistency.py --dry-run
  .venv/bin/python scripts/fix_xhaul_gitlab_loc_consistency.py --project-root /opt/teamsight/teamsight
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


COMMITS_COLUMNS = [
    "commit_sha",
    "date",
    "author",
    "author_email",
    "repository",
    "message",
    "jira_id",
    "files_changed",
    "lines_added",
    "lines_deleted",
    "lines_changed",
    "pr_number",
    "approver",
    "review_comments",
    "count_review_flag",
]

FILES_COLUMNS = [
    "commit_sha",
    "date",
    "author",
    "author_email",
    "repository",
    "jira_id",
    "filename",
    "filepath",
    "file_extension",
    "status",
    "lines_added",
    "lines_deleted",
    "lines_changed",
    "category",
    "subcategory",
    "is_screen",
    "confidence",
]


@dataclass
class FixStats:
    xhaul_repos: int = 0
    xhaul_file_rows_before: int = 0
    xhaul_file_rows_after: int = 0
    xhaul_file_rows_removed: int = 0
    xhaul_commits_touched: int = 0
    xhaul_commit_rows_updated: int = 0
    xhaul_commit_rows_missing: int = 0


def _safe_int(v) -> int:
    if pd.isna(v):
        return 0
    s = str(v).strip()
    if s in ("", "nan", "None"):
        return 0
    try:
        return int(float(s))
    except Exception:
        return 0


def _load_xhaul_repositories(config_file: Path) -> List[str]:
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    data = json.loads(config_file.read_text(encoding="utf-8"))
    repos = []
    for repo, cfg in (data.get("repositories") or {}).items():
        if str((cfg or {}).get("team", "")).strip().lower() == "xhaul":
            repos.append(str(repo).strip())
    return sorted(set(repos))


def _dedupe_file_rows(df: pd.DataFrame) -> pd.DataFrame:
    keys = ["commit_sha", "repository", "filepath", "status", "lines_added", "lines_deleted", "lines_changed"]
    for col in keys:
        if col not in df.columns:
            df[col] = ""
    for col in ["commit_sha", "repository", "filepath", "status"]:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["status"] = df["status"].str.lower()
    for col in ["lines_added", "lines_deleted", "lines_changed"]:
        df[col] = df[col].apply(_safe_int)
    return df.drop_duplicates(subset=keys, keep="last")


def _aggregate_commit_metrics(file_df: pd.DataFrame) -> Dict[Tuple[str, str], Dict[str, int]]:
    grouped: Dict[Tuple[str, str], Dict[str, int]] = {}
    by_commit = file_df.groupby(["commit_sha", "repository"], dropna=False)
    for (sha, repo), g in by_commit:
        grouped[(str(sha), str(repo))] = {
            "files_changed": int(len(g)),
            "lines_added": int(g["lines_added"].apply(_safe_int).sum()),
            "lines_deleted": int(g["lines_deleted"].apply(_safe_int).sum()),
            "lines_changed": int(g["lines_changed"].apply(_safe_int).sum()),
        }
    return grouped


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix XHAUL GitLab LOC consistency")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    output_dir = project_root / "output"
    config_file = project_root / "config" / "gitlab_config.json"
    commits_file = output_dir / "github_commits.csv"
    files_file = output_dir / "github_commit_files.csv"

    if not commits_file.exists():
        raise FileNotFoundError(f"Missing commits CSV: {commits_file}")
    if not files_file.exists():
        raise FileNotFoundError(f"Missing commit files CSV: {files_file}")

    xhaul_repos = _load_xhaul_repositories(config_file)
    if not xhaul_repos:
        print("No XHAUL repositories found in gitlab_config.json; nothing to do.")
        return 0

    print(f"XHAUL repositories: {xhaul_repos}")

    commits_df = pd.read_csv(commits_file, dtype=str)
    files_df = pd.read_csv(files_file, dtype=str)

    for col in COMMITS_COLUMNS:
        if col not in commits_df.columns:
            commits_df[col] = ""
    for col in FILES_COLUMNS:
        if col not in files_df.columns:
            files_df[col] = ""

    commits_df = commits_df[COMMITS_COLUMNS]
    files_df = files_df[FILES_COLUMNS]

    xhaul_files_mask = files_df["repository"].fillna("").astype(str).isin(xhaul_repos)
    xhaul_commits_mask = commits_df["repository"].fillna("").astype(str).isin(xhaul_repos)

    xhaul_files_before = files_df[xhaul_files_mask].copy()
    non_xhaul_files = files_df[~xhaul_files_mask].copy()

    xhaul_files_dedup = _dedupe_file_rows(xhaul_files_before)
    commit_metrics = _aggregate_commit_metrics(xhaul_files_dedup)

    stats = FixStats()
    stats.xhaul_repos = len(xhaul_repos)
    stats.xhaul_file_rows_before = int(len(xhaul_files_before))
    stats.xhaul_file_rows_after = int(len(xhaul_files_dedup))
    stats.xhaul_file_rows_removed = stats.xhaul_file_rows_before - stats.xhaul_file_rows_after
    stats.xhaul_commits_touched = int(len(commit_metrics))

    updates = 0
    missing = 0

    commits_work = commits_df.copy()
    for (sha, repo), m in commit_metrics.items():
        mask = (commits_work["commit_sha"].fillna("").astype(str) == sha) & (
            commits_work["repository"].fillna("").astype(str) == repo
        )
        count = int(mask.sum())
        if count == 0:
            missing += 1
            continue
        commits_work.loc[mask, "files_changed"] = str(m["files_changed"])
        commits_work.loc[mask, "lines_added"] = str(m["lines_added"])
        commits_work.loc[mask, "lines_deleted"] = str(m["lines_deleted"])
        commits_work.loc[mask, "lines_changed"] = str(m["lines_changed"])
        updates += count

    stats.xhaul_commit_rows_updated = updates
    stats.xhaul_commit_rows_missing = missing

    fixed_files_df = pd.concat([non_xhaul_files, xhaul_files_dedup], ignore_index=True)
    fixed_files_df = fixed_files_df[FILES_COLUMNS]
    fixed_commits_df = commits_work[COMMITS_COLUMNS]

    ts = _timestamp()
    report_dir = output_dir / "data_quality"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"xhaul_gitlab_loc_fix_report_{ts}.json"

    report = {
        "timestamp_utc": ts,
        "dry_run": bool(args.dry_run),
        "project_root": str(project_root),
        "files_csv": str(files_file),
        "commits_csv": str(commits_file),
        "stats": stats.__dict__,
        "xhaul_repositories": xhaul_repos,
    }

    if args.dry_run:
        report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        print(f"Dry-run report: {report_file}")
        return 0

    backup_commits = commits_file.with_suffix(commits_file.suffix + f".bak_xhaul_locfix_{ts}")
    backup_files = files_file.with_suffix(files_file.suffix + f".bak_xhaul_locfix_{ts}")

    commits_file.replace(backup_commits)
    files_file.replace(backup_files)

    fixed_commits_df.to_csv(commits_file, index=False)
    fixed_files_df.to_csv(files_file, index=False)

    report.update(
        {
            "backup_commits_csv": str(backup_commits),
            "backup_files_csv": str(backup_files),
            "status": "applied",
        }
    )
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"Applied fix report: {report_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
