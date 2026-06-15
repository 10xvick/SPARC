#!/usr/bin/env python3
"""
Git Activity Report Cache Job

Generates a pre-computed Git Activity monthly cache to speed up API response times.
Caches the aggregated commit data for the current month alongside metadata filters.

Invoked by scheduler daily. Can also be run on-demand.

Related files:
  - input: output/github_commits.csv, config/Resources.csv
  - output: output/git_activity_cache_YYYYMM.json, output/git_activity_cache_latest.json
"""

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional
import calendar

import pandas as pd


# Add src/ to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

GIT_ACTIVITY_SCORE_WEIGHTS = {
    'productivity': 0.40,
    'consistency': 0.35,
    'collaboration': 0.25,
}
GIT_ACTIVITY_STRICTNESS_MULTIPLIER = 1.20

ACTIVITY_TYPES = (
    'total_commits',
    'merges',
    'commits',
    'lines_added',
    'lines_deleted',
    'lines_changed',
    'files_changed',
    'repos_touched',
)


def _load_month_indexed_cache(latest_file: Path) -> tuple[dict[str, dict[str, Any]], str]:
    """Load month-indexed cache store from latest cache file.

    Supports both legacy single-month payloads and the new envelope format.
    Returns (months_map, latest_month).
    """
    if not latest_file.exists():
        return {}, ''

    try:
        payload = json.loads(latest_file.read_text(encoding='utf-8'))
    except Exception:
        return {}, ''

    if not isinstance(payload, dict):
        return {}, ''

    months_payload = payload.get('months')
    if isinstance(months_payload, dict):
        months_map: dict[str, dict[str, Any]] = {}
        for month_key, month_value in months_payload.items():
            clean_month = _clean_text(month_key)
            if clean_month and isinstance(month_value, dict):
                months_map[clean_month] = month_value
        latest_month = _clean_text(payload.get('latest_month'))
        return months_map, latest_month

    legacy_month = _clean_text(payload.get('selected_month'))
    if legacy_month:
        return {legacy_month: payload}, legacy_month

    return {}, ''


def _load_dated_month_caches(output_dir: Path) -> dict[str, dict[str, Any]]:
    """Load any existing git_activity_cache_YYYYMM.json payloads keyed by selected_month."""
    month_payloads: dict[str, dict[str, Any]] = {}
    for cache_file in sorted(output_dir.glob('git_activity_cache_*.json')):
        if cache_file.name == 'git_activity_cache_latest.json':
            continue
        try:
            payload = json.loads(cache_file.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        month_key = _clean_text(payload.get('selected_month'))
        if not month_key:
            continue
        month_payloads[month_key] = payload
    return month_payloads


def _build_employee_commit_details_cache(month_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build month-scoped commit details cache keyed by person identity."""
    people: dict[str, dict[str, Any]] = {}
    index_by_sapid: dict[str, str] = {}
    index_by_email: dict[str, str] = {}

    for record in month_records:
        sapid = _clean_sapid(record.get('sapid'))
        author_email = _clean_text(record.get('author_email')).lower()
        person_key = f"sapid::{sapid}" if sapid else (f"email::{author_email}" if author_email else '')
        if not person_key:
            continue

        if person_key not in people:
            people[person_key] = {
                'person': {
                    'name': _clean_text(record.get('name')),
                    'sapid': sapid,
                    'author_email': author_email,
                    'team': _clean_text(record.get('team')),
                    'scrum': _clean_text(record.get('scrum')),
                },
                'summary': {
                    'total_commits': 0,
                    'merge_commits': 0,
                    'non_merge_commits': 0,
                    'total_lines_changed': 0,
                    'total_files_changed': 0,
                },
                'commits': [],
            }

        commit_entry = {
            'commit_sha': _clean_text(record.get('commit_sha')),
            'date': record['date'].strftime('%Y-%m-%d') if record.get('date') is not None else '',
            'author': _clean_text(record.get('author')),
            'author_email': author_email,
            'repository': _clean_text(record.get('repository')),
            'message': _clean_text(record.get('message')),
            'jira_id': _clean_text(record.get('jira_id')),
            'files_changed': int(_as_float(record.get('files_changed'))),
            'lines_added': int(_as_float(record.get('lines_added'))),
            'lines_deleted': int(_as_float(record.get('lines_deleted'))),
            'lines_changed': int(_as_float(record.get('lines_changed'))),
            'pr_number': _clean_text(record.get('pr_number')),
            'approver': _clean_text(record.get('approver')),
            'review_comments': int(_as_float(record.get('review_comments'))),
            'is_merge': bool(record.get('is_merge')),
        }

        person_bucket = people[person_key]
        person_bucket['commits'].append(commit_entry)
        person_bucket['summary']['total_commits'] += 1
        person_bucket['summary']['merge_commits'] += 1 if commit_entry['is_merge'] else 0
        person_bucket['summary']['non_merge_commits'] += 0 if commit_entry['is_merge'] else 1
        person_bucket['summary']['total_lines_changed'] += int(commit_entry['lines_changed'])
        person_bucket['summary']['total_files_changed'] += int(commit_entry['files_changed'])

        if sapid:
            index_by_sapid[sapid] = person_key
        if author_email:
            index_by_email[author_email] = person_key

    for person_bucket in people.values():
        person_bucket['commits'].sort(
            key=lambda item: (
                _clean_text(item.get('date')),
                _clean_text(item.get('repository')),
                _clean_text(item.get('commit_sha')),
            ),
            reverse=True,
        )

    return {
        'people': people,
        'index': {
            'by_sapid': index_by_sapid,
            'by_author_email': index_by_email,
        },
    }


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _clean_text(value: Any, default: str = "") -> str:
    """Clean and normalize text values."""
    if value is None or str(value).strip().lower() in ('nan', 'none', ''):
        return default
    cleaned = str(value).strip()
    return cleaned


def _clean_sapid(value: Any) -> str:
    """Clean and normalize SAPID."""
    if not value or str(value).strip() in ('', 'nan', 'None'):
        return ""
    try:
        # Try to parse as number to remove decimals
        return str(int(float(str(value).strip())))
    except (ValueError, TypeError):
        return str(value).strip()


def _as_float(value: Any, default: float = 0.0) -> float:
    """Convert value to float safely."""
    if value is None or str(value).strip() in ('', 'nan', 'None'):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _find_column_by_normalized_name(columns: list[str], expected: str) -> Optional[str]:
    """Find a column by comparing stripped/lowercased names."""
    expected_norm = expected.strip().lower()
    for column in columns:
        if column.strip().lower() == expected_norm:
            return column
    return None


def _parse_optional_date(value: Any) -> Optional[date]:
    if value is None or str(value).strip().lower() in ('', 'nan', 'none', 'nat'):
        return None
    parsed = pd.to_datetime(value, errors='coerce')
    if pd.isna(parsed):
        return None
    return parsed.date()


# ---------------------------------------------------------------------------
# Helper functions (mirrored from reports.py)
# ---------------------------------------------------------------------------

def _normalize_person_name(name: str) -> str:
    """Normalize name for person identification."""
    return _clean_text(name).lower().replace(" ", "_")


def _business_days_for_month(month_key: str, start_date: Optional[date], as_of: Optional[date] = None) -> int:
    try:
        year_value, month_value = month_key.split('-')
        year = int(year_value)
        month = int(month_value)
    except Exception:
        return 0

    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])

    if as_of is not None and as_of < month_end:
        month_end = as_of

    active_start = month_start
    if start_date and start_date > active_start:
        active_start = start_date
    if active_start > month_end:
        return 0

    total = 0
    current = active_start
    while current <= month_end:
        if current.weekday() < 5:
            total += 1
        current += timedelta(days=1)
    return total


def _select_baseline_months(available_months: list[str], selected_month: str, max_months: int = 3) -> list[str]:
    if selected_month in available_months:
        selected_index = available_months.index(selected_month)
        return available_months[selected_index + 1:selected_index + 1 + max_months]
    return available_months[:max_months]


def _safe_average(values: list[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _score_from_ratio(actual_value: float, target_value: float) -> int:
    if target_value <= 0:
        return 100 if actual_value > 0 else 0
    score = min(100.0, (actual_value / target_value) * 100.0)
    return int(round(score))


def _empty_git_activity_scorecard(selected_month: str, baseline_months: Optional[list[str]] = None) -> dict[str, Any]:
    return {
        'overall_score': 0,
        'productivity_score': 0,
        'consistency_score': 0,
        'collaboration_score': 0,
        'weights': {
            'productivity': int(GIT_ACTIVITY_SCORE_WEIGHTS['productivity'] * 100),
            'consistency': int(GIT_ACTIVITY_SCORE_WEIGHTS['consistency'] * 100),
            'collaboration': int(GIT_ACTIVITY_SCORE_WEIGHTS['collaboration'] * 100),
        },
        'strictness': 'balanced',
        'display_format': 'integer',
        'baseline_months': baseline_months or [],
        'selected_month': selected_month,
        'gauge_layout': 'overall+3-components',
        'rows_scored': 0,
    }


def _load_employee_start_date_maps() -> tuple[dict[str, date], dict[str, date]]:
    resources_file = PROJECT_ROOT / "config" / "Resources.csv"
    if not resources_file.exists():
        return {}, {}

    try:
        resources_df = pd.read_csv(resources_file)
    except Exception:
        return {}, {}

    columns = list(resources_df.columns)
    sapid_col = _find_column_by_normalized_name(columns, 'SAPID')
    mail_col = _find_column_by_normalized_name(columns, 'EMail')
    git_mail_col = _find_column_by_normalized_name(columns, 'GIT Email')
    start_date_col = _find_column_by_normalized_name(columns, 'Start Date')
    if not start_date_col:
        return {}, {}

    by_sapid: dict[str, date] = {}
    by_email: dict[str, date] = {}

    for _, row in resources_df.iterrows():
        start_date = _parse_optional_date(row.get(start_date_col))
        if not start_date:
            continue

        sapid = _clean_sapid(row.get(sapid_col)) if sapid_col else ''
        if sapid:
            by_sapid[sapid] = start_date

        email_values = []
        if mail_col:
            email_values.append(_clean_text(row.get(mail_col)).lower())
        if git_mail_col:
            email_values.append(_clean_text(row.get(git_mail_col)).lower())

        for email in email_values:
            if email:
                by_email[email] = start_date

    return by_sapid, by_email


def _build_git_activity_monthly_stats(
    records: list[dict[str, Any]],
    months_of_interest: set[str],
    keys_of_interest: set[str],
) -> dict[str, dict[str, dict[str, int]]]:
    if not records or not months_of_interest or not keys_of_interest:
        return {}

    stats: dict[str, dict[str, dict[str, Any]]] = {}
    for record in records:
        month_key = record.get('month')
        if month_key not in months_of_interest:
            continue

        key = _clean_sapid(record.get('sapid')) or _clean_text(record.get('author_email')).lower()
        if key not in keys_of_interest:
            continue

        month_bucket = stats.setdefault(key, {}).setdefault(
            month_key,
            {
                'total_commits': 0,
                'merge_commits': 0,
                'active_days_set': set(),
            }
        )
        month_bucket['total_commits'] += 1
        if record.get('is_merge'):
            month_bucket['merge_commits'] += 1
        parsed_date = record.get('date')
        if parsed_date is not None:
            month_bucket['active_days_set'].add(parsed_date.strftime('%Y-%m-%d'))

    normalized_stats: dict[str, dict[str, dict[str, int]]] = {}
    for key, month_map in stats.items():
        normalized_stats[key] = {}
        for month_key, values in month_map.items():
            normalized_stats[key][month_key] = {
                'total_commits': int(values.get('total_commits', 0)),
                'merge_commits': int(values.get('merge_commits', 0)),
                'active_days': len(values.get('active_days_set', set())),
            }

    return normalized_stats


def _compute_git_activity_scorecard(
    rows: list[dict[str, Any]],
    selected_month: str,
    available_months: list[str],
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    baseline_months = _select_baseline_months(available_months, selected_month, max_months=3)
    if not rows:
        return rows, _empty_git_activity_scorecard(selected_month, baseline_months)

    row_keys: set[str] = set()
    for row in rows:
        key = _clean_sapid(row.get('sapid')) or _clean_text(row.get('author_email')).lower()
        if key:
            row_keys.add(key)

    months_of_interest = set(baseline_months + [selected_month])
    monthly_stats = _build_git_activity_monthly_stats(records, months_of_interest, row_keys)
    start_date_by_sapid, start_date_by_email = _load_employee_start_date_maps()

    default_targets = {
        'productivity': 0.60,
        'consistency': 0.45,
        'collaboration': 0.25,
    }

    cohort_productivity_rates: list[float] = []
    cohort_consistency_rates: list[float] = []
    cohort_collaboration_rates: list[float] = []

    for row in rows:
        row_key = _clean_sapid(row.get('sapid')) or _clean_text(row.get('author_email')).lower()
        if not row_key:
            continue
        start_date = start_date_by_sapid.get(_clean_sapid(row.get('sapid'))) or start_date_by_email.get(_clean_text(row.get('author_email')).lower())

        for month_key in baseline_months:
            working_days = _business_days_for_month(month_key, start_date)
            if working_days <= 0:
                continue

            month_stat = monthly_stats.get(row_key, {}).get(month_key, {'total_commits': 0, 'merge_commits': 0, 'active_days': 0})
            total_commits = float(month_stat.get('total_commits', 0))
            merge_commits = float(month_stat.get('merge_commits', 0))
            active_days = float(month_stat.get('active_days', 0))

            cohort_productivity_rates.append(total_commits / float(working_days))
            cohort_consistency_rates.append(active_days / float(working_days))
            if total_commits > 0:
                cohort_collaboration_rates.append(merge_commits / total_commits)

    cohort_targets = {
        'productivity': _safe_average(cohort_productivity_rates) or default_targets['productivity'],
        'consistency': _safe_average(cohort_consistency_rates) or default_targets['consistency'],
        'collaboration': _safe_average(cohort_collaboration_rates) or default_targets['collaboration'],
    }

    scored_rows: list[dict[str, Any]] = []
    overall_scores: list[int] = []
    productivity_scores: list[int] = []
    consistency_scores: list[int] = []
    collaboration_scores: list[int] = []

    for row in rows:
        row_key = _clean_sapid(row.get('sapid')) or _clean_text(row.get('author_email')).lower()
        if not row_key:
            scored_rows.append(row)
            continue

        start_date = start_date_by_sapid.get(_clean_sapid(row.get('sapid'))) or start_date_by_email.get(_clean_text(row.get('author_email')).lower())
        selected_working_days = _business_days_for_month(selected_month, start_date, as_of=date.today())
        fallback_active_days = sum(1 for value in row.get('daily_counts', {}).values() if int(_as_float(value)) > 0)
        selected_stat = monthly_stats.get(row_key, {}).get(selected_month, {
            'total_commits': int(row.get('metric_total', 0)),
            'merge_commits': 0,
            'active_days': fallback_active_days,
        })

        selected_total_commits = float(selected_stat.get('total_commits', 0))
        selected_merge_commits = float(selected_stat.get('merge_commits', 0))
        selected_active_days = float(selected_stat.get('active_days', 0))

        if selected_working_days > 0:
            actual_productivity = selected_total_commits / float(selected_working_days)
            actual_consistency = selected_active_days / float(selected_working_days)
        else:
            actual_productivity = 0.0
            actual_consistency = 0.0
        actual_collaboration = (selected_merge_commits / selected_total_commits) if selected_total_commits > 0 else 0.0

        productivity_targets: list[float] = []
        consistency_targets: list[float] = []
        collaboration_targets: list[float] = []
        for month_key in baseline_months:
            month_working_days = _business_days_for_month(month_key, start_date)
            if month_working_days <= 0:
                continue

            month_stat = monthly_stats.get(row_key, {}).get(month_key, {'total_commits': 0, 'merge_commits': 0, 'active_days': 0})
            month_total_commits = float(month_stat.get('total_commits', 0))
            month_merge_commits = float(month_stat.get('merge_commits', 0))
            month_active_days = float(month_stat.get('active_days', 0))

            productivity_targets.append(month_total_commits / float(month_working_days))
            consistency_targets.append(month_active_days / float(month_working_days))
            if month_total_commits > 0:
                collaboration_targets.append(month_merge_commits / month_total_commits)

        target_productivity = _safe_average(productivity_targets) or cohort_targets['productivity']
        target_consistency = _safe_average(consistency_targets) or cohort_targets['consistency']
        target_collaboration = _safe_average(collaboration_targets) or cohort_targets['collaboration']

        productivity_score = _score_from_ratio(actual_productivity, target_productivity * GIT_ACTIVITY_STRICTNESS_MULTIPLIER)
        consistency_score = _score_from_ratio(actual_consistency, target_consistency * GIT_ACTIVITY_STRICTNESS_MULTIPLIER)
        collaboration_score = _score_from_ratio(actual_collaboration, target_collaboration * GIT_ACTIVITY_STRICTNESS_MULTIPLIER)

        weighted_score = (
            productivity_score * GIT_ACTIVITY_SCORE_WEIGHTS['productivity']
            + consistency_score * GIT_ACTIVITY_SCORE_WEIGHTS['consistency']
            + collaboration_score * GIT_ACTIVITY_SCORE_WEIGHTS['collaboration']
        )
        overall_score = int(round(weighted_score))

        row_with_score = {
            **row,
            'git_activity_score': {
                'overall_score': overall_score,
                'productivity_score': productivity_score,
                'consistency_score': consistency_score,
                'collaboration_score': collaboration_score,
                'actual': {
                    'productivity_per_working_day': round(actual_productivity, 4),
                    'consistency_ratio': round(actual_consistency, 4),
                    'collaboration_merge_ratio': round(actual_collaboration, 4),
                },
                'target': {
                    'productivity_per_working_day': round(target_productivity, 4),
                    'consistency_ratio': round(target_consistency, 4),
                    'collaboration_merge_ratio': round(target_collaboration, 4),
                },
                'active_working_days': int(selected_working_days),
            }
        }

        scored_rows.append(row_with_score)
        overall_scores.append(overall_score)
        productivity_scores.append(productivity_score)
        consistency_scores.append(consistency_score)
        collaboration_scores.append(collaboration_score)

    summary_scorecard = _empty_git_activity_scorecard(selected_month, baseline_months)
    summary_scorecard.update({
        'overall_score': int(round(_safe_average([float(score) for score in overall_scores]))),
        'productivity_score': int(round(_safe_average([float(score) for score in productivity_scores]))),
        'consistency_score': int(round(_safe_average([float(score) for score in consistency_scores]))),
        'collaboration_score': int(round(_safe_average([float(score) for score in collaboration_scores]))),
        'rows_scored': len(overall_scores),
    })

    return scored_rows, summary_scorecard


def _load_employee_git_identity_map() -> dict[str, dict[str, str]]:
    """Load email→profile mapping from Resources.csv."""
    RESOURCES_FILE = PROJECT_ROOT / "config" / "Resources.csv"
    if not RESOURCES_FILE.exists():
        return {}

    resources_df = pd.read_csv(RESOURCES_FILE)
    columns = list(resources_df.columns)

    name_col = _find_column_by_normalized_name(columns, 'Name')
    sapid_col = _find_column_by_normalized_name(columns, 'SAPID')
    team_col = _find_column_by_normalized_name(columns, 'Team')
    scrum_col = _find_column_by_normalized_name(columns, 'Scrum')
    primary_role_col = _find_column_by_normalized_name(columns, 'Primary Role')
    secondary_role_col = _find_column_by_normalized_name(columns, 'Secondary Role')
    mail_col = _find_column_by_normalized_name(columns, 'EMail')
    git_mail_col = _find_column_by_normalized_name(columns, 'GIT Email')
    github_mail_col = _find_column_by_normalized_name(columns, 'GitHub Email')
    gitlab_mail_col = _find_column_by_normalized_name(columns, 'GitLab Email')

    identity_map = {}

    for _, row in resources_df.iterrows():
        emails = [
            _clean_text(row.get(mail_col)).lower() if mail_col else '',
            _clean_text(row.get(git_mail_col)).lower() if git_mail_col else '',
            _clean_text(row.get(github_mail_col)).lower() if github_mail_col else '',
            _clean_text(row.get(gitlab_mail_col)).lower() if gitlab_mail_col else '',
        ]

        for email in emails:
            if email:
                identity_map[email] = {
                    "name": _clean_text(row.get(name_col)) if name_col else '',
                    "sapid": _clean_sapid(row.get(sapid_col)) if sapid_col else '',
                    "team": _clean_text(row.get(team_col)) if team_col else '',
                    "scrum": _clean_text(row.get(scrum_col)) if scrum_col else '',
                    "primary_role": _clean_text(row.get(primary_role_col)) if primary_role_col else '',
                    "secondary_role": _clean_text(row.get(secondary_role_col)) if secondary_role_col else '',
                    "author_email": email,
                }

    return identity_map


def _load_employee_git_roster() -> list[dict[str, str]]:
    """Load employee roster from Resources.csv."""
    RESOURCES_FILE = PROJECT_ROOT / "config" / "Resources.csv"
    if not RESOURCES_FILE.exists():
        return []

    resources_df = pd.read_csv(RESOURCES_FILE)
    columns = list(resources_df.columns)

    name_col = _find_column_by_normalized_name(columns, 'Name')
    sapid_col = _find_column_by_normalized_name(columns, 'SAPID')
    team_col = _find_column_by_normalized_name(columns, 'Team')
    scrum_col = _find_column_by_normalized_name(columns, 'Scrum')
    mail_col = _find_column_by_normalized_name(columns, 'EMail')
    git_mail_col = _find_column_by_normalized_name(columns, 'GIT Email')
    github_mail_col = _find_column_by_normalized_name(columns, 'GitHub Email')
    gitlab_mail_col = _find_column_by_normalized_name(columns, 'GitLab Email')

    roster = []

    for _, row in resources_df.iterrows():
        email = ''
        for value in [
            _clean_text(row.get(git_mail_col)).lower() if git_mail_col else '',
            _clean_text(row.get(github_mail_col)).lower() if github_mail_col else '',
            _clean_text(row.get(gitlab_mail_col)).lower() if gitlab_mail_col else '',
            _clean_text(row.get(mail_col)).lower() if mail_col else '',
        ]:
            if value:
                email = value
                break

        roster.append({
            "name": _clean_text(row.get(name_col)) if name_col else '',
            "sapid": _clean_sapid(row.get(sapid_col)) if sapid_col else '',
            "team": _clean_text(row.get(team_col)) if team_col else '',
            "scrum": _clean_text(row.get(scrum_col)) if scrum_col else '',
            "author_email": email,
        })

    return roster


# ---------------------------------------------------------------------------
# Cache generation
# ---------------------------------------------------------------------------

def generate_git_activity_cache(
    project_root: Path,
    month: Optional[str] = None,
) -> dict[str, Any]:
    """
    Generate pre-computed Git Activity data for a given month.
    
    month format: YYYY-MM (e.g., '2026-04')
    If month is None, uses the latest available month from commits.
    
    Returns a dict with:
      - date_columns: list of dates
      - rows: pre-computed activity rows
      - available_months: list of all available months
      - selected_month: the computed month
      - available_filters: teams, scrums
      - metadata: timestamp, etc.
    """
    commits_file = project_root / 'output' / 'github_commits.csv'
    if not commits_file.exists():
        raise FileNotFoundError(f"github_commits.csv not found at {commits_file}")

    commits_df = pd.read_csv(commits_file)
    required_columns = {'date', 'author', 'author_email', 'repository', 'message'}
    missing = [col for col in required_columns if col not in commits_df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    identity_by_email = _load_employee_git_identity_map()
    employee_roster = _load_employee_git_roster()

    merge_regex = re.compile(r'^\s*merge(d)?\b', re.IGNORECASE)
    records: list[dict[str, Any]] = []

    for _, row in commits_df.iterrows():
        parsed_date = pd.to_datetime(row.get('date'), errors='coerce')
        if pd.isna(parsed_date):
            continue

        author_email = _clean_text(row.get('author_email')).lower()
        author_name = _clean_text(row.get('author'))
        repository = _clean_text(row.get('repository'))
        message = _clean_text(row.get('message'))

        resolved = identity_by_email.get(author_email, {})
        resolved_name = _clean_text(resolved.get('name')) or author_name
        resolved_sapid = _clean_sapid(resolved.get('sapid'))
        resolved_team = _clean_text(resolved.get('team'))
        resolved_scrum = _clean_text(resolved.get('scrum'))

        records.append({
            'date': parsed_date,
            'month': parsed_date.strftime('%Y-%m'),
            'commit_sha': _clean_text(row.get('commit_sha')),
            'author': author_name,
            'author_email': author_email,
            'name': resolved_name,
            'sapid': resolved_sapid,
            'team': resolved_team,
            'scrum': resolved_scrum,
            'repository': repository,
            'message': message,
            'jira_id': _clean_text(row.get('jira_id')),
            'pr_number': _clean_text(row.get('pr_number')),
            'approver': _clean_text(row.get('approver')),
            'review_comments': int(_as_float(row.get('review_comments'))),
            'is_merge': bool(merge_regex.match(message)),
            'files_changed': int(_as_float(row.get('files_changed'))),
            'lines_added': int(_as_float(row.get('lines_added'))),
            'lines_deleted': int(_as_float(row.get('lines_deleted'))),
            'lines_changed': int(_as_float(row.get('lines_changed'))),
        })

    available_months = sorted({record['month'] for record in records}, reverse=True)
    if not available_months:
        raise ValueError("No commits found to cache")

    selected_month = month if month in available_months else available_months[0]

    # Aggregate data
    year_str, month_str = selected_month.split('-')
    year_val = int(year_str)
    month_val = int(month_str)
    total_days = calendar.monthrange(year_val, month_val)[1]
    date_columns = [f"{selected_month}-{day:02d}" for day in range(1, total_days + 1)]

    month_records = [record for record in records if record['month'] == selected_month]
    employee_details_cache = _build_employee_commit_details_cache(month_records)

    aggregate: dict[str, dict[str, Any]] = {}

    for employee in employee_roster:
        employee_key = employee['sapid'] or employee['author_email'] or f"name::{_normalize_person_name(employee['name'])}"
        activity_metrics = {
            activity: {
                'daily_counts': {day_key: 0 for day_key in date_columns},
                'metric_total': 0,
            }
            for activity in ACTIVITY_TYPES
        }
        aggregate[employee_key] = {
            'name': employee['name'],
            'author_email': employee['author_email'],
            'sapid': employee['sapid'],
            'team': employee['team'],
            'scrum': employee['scrum'],
            'activity_metrics': activity_metrics,
            'daily_repositories': {day_key: set() for day_key in date_columns},
            'merge_commits': 0,
            'non_merge_commits': 0,
        }

    for record in month_records:
        key = record['sapid'] or record['author_email'] or f"name::{_normalize_person_name(record['name'])}"
        if key not in aggregate:
            activity_metrics = {
                activity: {
                    'daily_counts': {day_key: 0 for day_key in date_columns},
                    'metric_total': 0,
                }
                for activity in ACTIVITY_TYPES
            }
            aggregate[key] = {
                'name': record['name'],
                'author_email': record['author_email'],
                'sapid': record['sapid'],
                'team': record['team'],
                'scrum': record['scrum'],
                'activity_metrics': activity_metrics,
                'daily_repositories': {day_key: set() for day_key in date_columns},
                'merge_commits': 0,
                'non_merge_commits': 0,
            }

        row = aggregate[key]
        day_key = record['date'].strftime('%Y-%m-%d')
        if day_key not in row['activity_metrics']['total_commits']['daily_counts']:
            continue

        if record['is_merge']:
            row['merge_commits'] += 1
        else:
            row['non_merge_commits'] += 1

        row['activity_metrics']['total_commits']['daily_counts'][day_key] += 1
        row['activity_metrics']['total_commits']['metric_total'] += 1

        merge_value = 1 if record['is_merge'] else 0
        non_merge_value = 0 if record['is_merge'] else 1
        lines_added = int(record['lines_added'])
        lines_deleted = int(record['lines_deleted'])
        lines_changed = int(record['lines_changed'])
        files_changed = int(record['files_changed'])

        row['activity_metrics']['merges']['daily_counts'][day_key] += merge_value
        row['activity_metrics']['merges']['metric_total'] += merge_value

        row['activity_metrics']['commits']['daily_counts'][day_key] += non_merge_value
        row['activity_metrics']['commits']['metric_total'] += non_merge_value

        row['activity_metrics']['lines_added']['daily_counts'][day_key] += lines_added
        row['activity_metrics']['lines_added']['metric_total'] += lines_added

        row['activity_metrics']['lines_deleted']['daily_counts'][day_key] += lines_deleted
        row['activity_metrics']['lines_deleted']['metric_total'] += lines_deleted

        row['activity_metrics']['lines_changed']['daily_counts'][day_key] += lines_changed
        row['activity_metrics']['lines_changed']['metric_total'] += lines_changed

        row['activity_metrics']['files_changed']['daily_counts'][day_key] += files_changed
        row['activity_metrics']['files_changed']['metric_total'] += files_changed

        repository_name = _clean_text(record['repository'])
        if repository_name:
            row['daily_repositories'][day_key].add(repository_name)

    for row in aggregate.values():
        repos_daily = {
            day_key: len(row['daily_repositories'][day_key])
            for day_key in date_columns
        }
        row['activity_metrics']['repos_touched']['daily_counts'] = repos_daily
        row['activity_metrics']['repos_touched']['metric_total'] = sum(repos_daily.values())

    data_rows = []
    for row in aggregate.values():
        total_commits_metrics = row['activity_metrics']['total_commits']
        data_rows.append({
            'date': selected_month,
            'name': row['name'],
            'author_email': row['author_email'],
            'sapid': row['sapid'],
            'team': row['team'],
            'scrum': row['scrum'],
            # Keep total_commits at top-level for scorecard compatibility.
            'daily_counts': total_commits_metrics['daily_counts'],
            'metric_total': total_commits_metrics['metric_total'],
            'merge_commits': row['merge_commits'],
            'non_merge_commits': row['non_merge_commits'],
            'activity_metrics': row['activity_metrics'],
        })

    data_rows.sort(key=lambda item: (item['name'].lower(), item['team'].lower(), item['scrum'].lower(), item['author_email']))

    available_filters = {
        'teams': sorted({row['team'] for row in data_rows if row['team']}),
        'scrums': sorted({row['scrum'] for row in data_rows if row['scrum']}),
    }

    scored_rows, scorecard = _compute_git_activity_scorecard(
        rows=data_rows,
        selected_month=selected_month,
        available_months=available_months,
        records=records,
    )

    return {
        'success': True,
        'data': scored_rows,
        'date_columns': date_columns,
        'available_months': available_months,
        'selected_month': selected_month,
        'available_filters': available_filters,
        'summary': {
            'total_rows': len(scored_rows),
            'metric_total': sum(int(row.get('metric_total', 0)) for row in scored_rows),
            'git_activity_scorecard': scorecard,
        },
        'metadata': {
            'cached_at': datetime.now().isoformat(),
            'cache_version': 4,
        },
        'employee_details_cache': {
            'selected_month': selected_month,
            **employee_details_cache,
        },
    }


def main():
    """Main entry point."""
    try:
        print("⏳ Generating Git Activity cache...")
        
        cache_data = generate_git_activity_cache(PROJECT_ROOT)
        selected_month = cache_data['selected_month']
        
        output_dir = PROJECT_ROOT / 'output'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save dated cache file
        cache_file = output_dir / f"git_activity_cache_{selected_month.replace('-', '')}.json"
        cache_file.write_text(json.dumps(cache_data, indent=2), encoding='utf-8')
        print(f"✅ Saved cache: {cache_file.name} ({len(cache_data['data'])} rows)")
        
        # Save latest pointer with month-indexed retention so previous months remain available.
        latest_file = output_dir / "git_activity_cache_latest.json"
        existing_months, _ = _load_month_indexed_cache(latest_file)
        # Backfill month map from existing dated cache files so older months remain accessible.
        for month_key, month_payload in _load_dated_month_caches(output_dir).items():
            existing_months.setdefault(month_key, month_payload)
        existing_months[selected_month] = cache_data

        latest_payload = {
            'cache_version': 5,
            'latest_month': selected_month,
            'months': dict(sorted(existing_months.items(), reverse=True)),
            'metadata': {
                'updated_at': datetime.now().isoformat(),
                'month_count': len(existing_months),
            },
        }
        latest_file.write_text(json.dumps(latest_payload, indent=2), encoding='utf-8')
        print(f"✅ Updated cache pointer: {latest_file.name} (months retained={len(existing_months)})")
        
        print(f"✅ Cache generation complete for month {selected_month}")
        return 0
        
    except Exception as e:
        print(f"❌ Cache generation failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
