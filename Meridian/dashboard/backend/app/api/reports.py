"""Reports API endpoints."""
from collections import Counter
from datetime import date, datetime, timedelta
import calendar
import csv
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from typing import Any, Optional
import json
import logging
import re
import shutil
import threading
import pandas as pd
import sys
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4
from app.api.kpi_utils import get_prorated_target, parse_ref_date

_logger = logging.getLogger(__name__)

# Add src directory to path to import KppEvaluator
project_root = Path(__file__).parent.parent.parent.parent.parent
src_path = project_root / 'src'
sys.path.insert(0, str(src_path))

from KppEvaluator import KppEvaluator
from employee_score_comparison_report import (
    flatten_employee_score_rows,
    generate_employee_score_comparison,
)
from app.services import roles_service
from app.models.user import TokenData
from app.dependencies import require_report_access
from app.services.user_service import UserService
from app.services.role_service import RoleService
from app.services.rbac_service import RBACService
from app.services.scoring_service import get_scoring_service
from app.services.audit_trail_service import AuditTrailService


def _sanitize_report_payload(payload: Any) -> Any:
    if payload is None:
        return None
    if isinstance(payload, dict):
        safe: dict[str, Any] = {}
        for key, value in list(payload.items())[:50]:
            safe[str(key)] = _sanitize_report_payload(value)
        return safe
    if isinstance(payload, list):
        return [_sanitize_report_payload(item) for item in payload[:50]]
    if isinstance(payload, str):
        return payload[:500]
    if isinstance(payload, (int, float, bool)):
        return payload
    return str(payload)


audit_trail_service = AuditTrailService()


async def _audit_report_access(request: Request, current_user: TokenData = Depends(require_report_access)):
    details = {
        "path": request.url.path,
        "query": _sanitize_report_payload(dict(request.query_params)),
    }

    audit_trail_service.record_report_access_event(
        sapid=current_user.sapid,
        user_id=current_user.user_id,
        user_name=current_user.name,
        role=current_user.role,
        method=request.method,
        path=request.url.path,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details=details,
    )

    return current_user

router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
    dependencies=[Depends(_audit_report_access)]
)

rbac_user_service = UserService()
rbac_role_service = RoleService()
rbac_service = RBACService(rbac_role_service, rbac_user_service)

GLOBAL_ROLE_BUCKETS = ("Common", "All", "Metric", "Metrics")
ALL_KPIS_ROLE_LABEL = "All KPIs"
NON_REPORTABLE_ROLE_BUCKETS = {
    *GLOBAL_ROLE_BUCKETS,
    "Weekly Score",
    "Quarterly Score",
    "Annual Score",
    "Parameter",
    "Message",
    "Critical KPI"
}

JIRA_ISSUES_FILE = project_root / 'output' / 'JIRAIssues.csv'
JIRA_HISTORY_FILE = project_root / 'output' / 'JIRAIssues_History.csv'
RESOURCES_FILE = project_root / 'config' / 'Resources.csv'
EPIC_TREE_OUTPUT_DIR = project_root / 'output' / 'EpicTree'
EPIC_TREE_EPICS_FILE = EPIC_TREE_OUTPUT_DIR / 'epics.csv'
EMPLOYEE_SCORE_LATEST_FILE = project_root / 'output' / 'employee_score_comparison_latest.csv'
GIT_ACTIVITY_CACHE_LATEST_FILE = project_root / 'output' / 'git_activity_cache_latest.json'
GIT_ACTIVITY_EXPORTS_DIR = project_root / 'output' / 'git_activity_exports'
UDE_INSTALLATIONS_FILE = project_root / 'output' / 'ude_installations.json'
UDE_CONFIG_FILE = project_root / 'config' / 'ude_config.json'
TIME_CONFIG_FILE = project_root / 'config' / 'time_config.json'

GIT_ACTIVITY_SCORE_WEIGHTS = {
    'productivity': 0.40,
    'consistency': 0.35,
    'collaboration': 0.25,
}
GIT_ACTIVITY_STRICTNESS_MULTIPLIER = 1.20

# Concurrency protection for employee score report generation
_employee_score_generation_lock = threading.Lock()
_employee_score_generation_in_progress: dict[str, bool] = {}  # Maps day_key -> True if generation in progress
_git_activity_detail_export_lock = threading.Lock()
_git_activity_detail_export_jobs: dict[str, dict[str, Any]] = {}
_git_activity_detail_export_active_by_user: dict[str, str] = {}


def _resolve_snapshot_day(as_of_date: Optional[str]) -> str:
    """Resolve snapshot day key in YYYYMMDD format."""
    if as_of_date and len(as_of_date) == 8 and as_of_date.isdigit():
        return as_of_date

    latest_date = _get_latest_available_kpi_date()
    if latest_date:
        return latest_date

    return pd.Timestamp.now().strftime('%Y%m%d')


def _get_latest_available_kpi_date() -> Optional[str]:
    """Return latest CurrentDate found across output/k*-data.csv files."""
    output_dir = project_root / 'output'
    if not output_dir.exists():
        return None

    latest: Optional[str] = None
    for kpi_file in sorted(output_dir.glob('k*-data.csv')):
        try:
            with open(kpi_file, 'r', encoding='utf-8') as handle:
                import csv

                reader = csv.DictReader(handle)
                if 'CurrentDate' not in (reader.fieldnames or []):
                    continue
                for row in reader:
                    current_date = _clean_text(row.get('CurrentDate'))
                    if len(current_date) == 8 and current_date.isdigit():
                        if latest is None or current_date > latest:
                            latest = current_date
        except Exception:
            continue
    return latest


def _employee_score_daily_snapshot_file(day_key: str) -> Path:
    return project_root / 'output' / f'employee_score_comparison_{day_key}.csv'


def _has_any_kpi_data_for_day(day_key: str) -> bool:
    """Return True when at least one KPI file has data for the requested day."""
    evaluator = _create_evaluator()
    for kpi in evaluator.list_kpis():
        kpi_data = evaluator.read_kpi_data(kpi, period='Annual', as_of_date=day_key)
        if kpi_data:
            return True
    return False


def _ensure_employee_score_snapshot_file(as_of_date: Optional[str]) -> Path:
    """Return day-specific output snapshot; generate it once if missing.
    
    Protects against concurrent generation by using a module-level lock
    and in-progress tracker. Multiple concurrent requests for the same day
    will wait for the first request to complete generation.
    """
    day_key = _resolve_snapshot_day(as_of_date)
    snapshot_file = _employee_score_daily_snapshot_file(day_key)

    # Fast path: file exists, return immediately (no lock needed)
    if snapshot_file.exists():
        return snapshot_file

    # Acquire lock to check/set in-progress flag
    with _employee_score_generation_lock:
        # Check if file was just created by another thread
        if snapshot_file.exists():
            return snapshot_file
        
        # Check if another thread is already generating for this day
        if _employee_score_generation_in_progress.get(day_key, False):
            # Another thread is generating; wait and retry
            _logger.info(f'[score-report] Generation for {day_key} already in progress, waiting...')
    
    # Wait for concurrent generation to complete (with timeout)
    max_wait_seconds = 600  # 10 minute timeout
    wait_interval = 1.0  # Check every 1 second
    elapsed = 0.0
    
    while elapsed < max_wait_seconds:
        with _employee_score_generation_lock:
            if snapshot_file.exists():
                _logger.info(f'[score-report] Generation completed by concurrent request for {day_key}')
                return snapshot_file
            
            if not _employee_score_generation_in_progress.get(day_key, False):
                # We can proceed with generation
                _employee_score_generation_in_progress[day_key] = True
                break
        
        threading.Event().wait(wait_interval)
        elapsed += wait_interval
    else:
        # Timeout waiting for generation
        raise HTTPException(
            status_code=503,
            detail='Employee score report generation is taking longer than expected (timeout after 10 minutes).',
        )

    try:
        # Perform the generation (outside the lock, so other requests can still check status)
        _logger.info(f'[score-report] Starting generation for {day_key}')
        
        # If today's KPI outputs are not present yet, run KPI computation first.
        if not _has_any_kpi_data_for_day(day_key):
            _logger.info(f'[score-report] KPI data missing for {day_key}, running KPI computation...')
            evaluator = _create_evaluator()
            current_day = datetime.strptime(day_key, '%Y%m%d').date()
            run_results = evaluator.run_all_kpis(current_date=current_day)
            if not any(run_results.values()):
                raise HTTPException(
                    status_code=500,
                    detail='KPI computation failed while preparing employee score snapshot.',
                )

        _logger.info(f'[score-report] Generating score comparison report for {day_key}')
        report_payload = generate_employee_score_comparison(
            resources_file=project_root / 'config' / 'Resources.csv',
            roles_file=project_root / 'config' / 'Roles.csv',
            output_dir=project_root / 'output',
            scoring_config_file=project_root / 'config' / 'scoring_config.json',
            jira_issues_file=project_root / 'output' / 'JIRAIssues.csv',
            github_commits_file=project_root / 'output' / 'github_commits.csv',
            fiscal_start_month=4,
            as_of_date=day_key,
        )
        rows = flatten_employee_score_rows(report_payload.get('rows', []))

        fieldnames = [
            'Name', 'SAPID', 'Team', 'Scrum', 'PrimaryRole', 'SecondaryRole',
            'Weekly_Overall', 'Weekly_Input', 'Weekly_Output', 'Weekly_Quality', 'Weekly_Hygiene',
            'Quarterly_Overall', 'Quarterly_Input', 'Quarterly_Output', 'Quarterly_Quality', 'Quarterly_Hygiene',
            'Annual_Overall', 'Annual_Input', 'Annual_Output', 'Annual_Quality', 'Annual_Hygiene',
        ]

        snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        import csv
        with open(snapshot_file, 'w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        shutil.copy2(snapshot_file, EMPLOYEE_SCORE_LATEST_FILE)
        _logger.info(f'[score-report] Generation completed for {day_key}: {len(rows)} employees')
        
    finally:
        # Always clear the in-progress flag
        with _employee_score_generation_lock:
            _employee_score_generation_in_progress[day_key] = False
    
    return snapshot_file


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def warm_transitions_cache_in_background() -> None:
    """Launch a daemon thread that pre-populates all in-memory and on-disk caches.

    1. Calls _load_jira_issue_data() to warm the module-level _jira_data_cache,
       so the first user request to any endpoint that uses JIRA issue data is fast.
    2. Reads JIRAIssues_History.csv once and writes per-issue JSON transition cache
       files for every issue that does not already have one.

    The thread is daemonised so it never blocks startup or shutdown.
    """
    def _run() -> None:
        # --- Step 1: warm the JIRA issue data in-memory cache ---
        try:
            _logger.info('[jira-data-warm] Pre-warming JIRA issue data cache...')
            _load_jira_issue_data()
            _logger.info('[jira-data-warm] JIRA issue data cache ready.')
        except Exception as exc:
            _logger.warning('[jira-data-warm] Failed to pre-warm JIRA data cache: %s', exc)

        # --- Step 2: warm per-issue transition JSON files ---
        if not JIRA_HISTORY_FILE.exists():
            _logger.info('[transitions-warm] History file not found, skipping pre-warm.')
            return

        transitions_dir = EPIC_TREE_OUTPUT_DIR / 'transitions'
        try:
            transitions_dir.mkdir(parents=True, exist_ok=True)
            history_df = pd.read_csv(JIRA_HISTORY_FILE)
        except Exception as exc:
            _logger.warning('[transitions-warm] Failed to read history file: %s', exc)
            return

        required_columns = {'Key', 'Field', 'ChangeDate'}
        if not required_columns.issubset(history_df.columns):
            _logger.warning('[transitions-warm] History file missing required columns.')
            return

        history_df['Key'] = history_df['Key'].fillna('').astype(str).str.strip()
        history_df['Field'] = history_df['Field'].fillna('').astype(str).str.strip()
        history_df['FromValue'] = (
            history_df['FromValue'].fillna('').astype(str).str.strip()
            if 'FromValue' in history_df.columns else ''
        )
        history_df['ToValue'] = (
            history_df['ToValue'].fillna('').astype(str).str.strip()
            if 'ToValue' in history_df.columns else ''
        )
        history_df['ChangedBy'] = (
            history_df['ChangedBy'].fillna('').astype(str).str.strip()
            if 'ChangedBy' in history_df.columns else ''
        )
        history_df['ChangeDate'] = pd.to_datetime(history_df['ChangeDate'], errors='coerce', utc=True)
        history_df = history_df.dropna(subset=['ChangeDate'])
        history_df = history_df.sort_values('ChangeDate')

        written = 0
        skipped = 0
        for issue_key, group in history_df.groupby('Key', sort=False):
            if not issue_key:
                continue
            # _issue_transitions_cache_path appends /transitions/ internally,
            # so pass the parent EpicTree dir, not the already-resolved transitions_dir.
            cache_path = _issue_transitions_cache_path(str(issue_key))
            if cache_path.exists():
                skipped += 1
                continue
            try:
                rows = [
                    {
                        'change_date': _format_timestamp(row.get('ChangeDate')),
                        'field': _clean_text(row.get('Field')),
                        'from_value': _clean_text(row.get('FromValue')),
                        'to_value': _clean_text(row.get('ToValue')),
                        'changed_by': _clean_text(row.get('ChangedBy')),
                    }
                    for _, row in group.iterrows()
                ]
                cache_path.write_text(json.dumps(rows), encoding='utf-8')
                written += 1
            except Exception as exc:
                _logger.debug('[transitions-warm] Could not write cache for %s: %s', issue_key, exc)

        _logger.info(
            '[transitions-warm] Complete — written=%d, already-cached=%d', written, skipped
        )

        # --- Step 3: warm the Replan Tracker in-memory cache ---
        try:
            import app.api.replan_tracker as _replan_mod
            _logger.info('[replan-warm] Pre-warming Replan Tracker cache...')
            _replan_mod.load_replan_data()
            _logger.info('[replan-warm] Replan Tracker cache ready.')
        except Exception as exc:
            _logger.warning('[replan-warm] Failed to pre-warm Replan Tracker cache: %s', exc)

        # --- Step 4: warm the Assignee Delay in-memory cache ---
        try:
            import app.api.assignee_delay_report as _adr_mod
            _logger.info('[assignee-delay-warm] Pre-warming Assignee Delay cache...')
            _adr_mod._load_assignee_delay_data()
            _logger.info('[assignee-delay-warm] Assignee Delay cache ready.')
        except Exception as exc:
            _logger.warning('[assignee-delay-warm] Failed to pre-warm Assignee Delay cache: %s', exc)

    thread = threading.Thread(target=_run, name='transitions-cache-warm', daemon=True)
    thread.start()


EPIC_TREE_WORKSPACE_COLUMNS = [
    'Key',
    'Parent',
    'Issue Type',
    'Summary',
    'Status',
    'Priority',
    'Story Points',
    'Assignee',
    'Team',
    'Sprint',
    'Created',
    'Updated',
    '_created_dt',
    '_updated_dt',
    '_sprint_end_dt',
    '_completion_dt',
    '_initial_sprint',
    '_initial_allocated_dt',
    '_planned_duration_days',
    '_actual_duration_days',
    '_slippage_days',
    '_delay_days',
    '_age_days',
    '_is_done',
    '_is_in_progress',
    '_is_todo',
    '_is_overdue',
    '_assignee_norm',
    '_next_transition_field',
    '_next_transition_from',
    '_next_transition_to',
    '_next_transition_by',
    '_next_transition_dt',
]

DONE_STATUSES = {
    'done',
    'closed',
    'resolved',
    'removed',
    'completed'
}

IN_PROGRESS_STATUSES = {
    'in progress',
    'approved',
    'code review',
    'review',
    'testing',
    'ready for qa',
    'in test'
}

FIRST_ACTIVE_STATUSES = IN_PROGRESS_STATUSES | DONE_STATUSES

ISSUE_TYPE_ORDER = {
    'epic': 0,
    'story': 1,
    'task': 2,
    'bug': 3,
    'sub-task': 4
}

FORCED_TEAM_BY_KEY_PREFIX = {
    'ERXTX-': 'XHAUL'
}

MIN_DELAY_THRESHOLD_DAYS = 1.0

# Module-level cache for the processed JIRA issues DataFrame.
# Keyed by a tuple of (issues_mtime, history_mtime) so it auto-invalidates
# whenever either source file changes on disk.
_jira_data_cache: dict[str, Any] = {
    'mtimes': None,
    'df': None
}


def _create_evaluator() -> KppEvaluator:
    """Create a KPI evaluator instance for report generation."""
    resources_file = project_root / 'config' / 'Resources.csv'
    jira_issues_file = project_root / 'output' / 'JIRAIssues.csv'
    github_commits_file = project_root / 'output' / 'github_commits.csv'
    output_dir = project_root / 'output'

    return KppEvaluator(
        resources_file=str(resources_file),
        jira_issues_file=str(jira_issues_file),
        github_commits_file=str(github_commits_file),
        output_dir=str(output_dir),
        fiscal_start_month=4
    )


def _format_sheet_value(value) -> str:
    """Format Roles.csv values for report display without losing non-numeric targets."""
    if pd.isna(value):
        return ""

    if isinstance(value, (int, float)):
        return f"{value:g}"

    return str(value).strip()


def _get_reportable_roles(roles_df: pd.DataFrame) -> list[str]:
    """Return user-facing roles derived from Roles.csv, excluding shared/system buckets."""
    unique_roles = (
        roles_df['Role']
        .fillna('')
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    return sorted(
        role
        for role in unique_roles
        if role and role not in NON_REPORTABLE_ROLE_BUCKETS
    )


def _get_shared_role_buckets(roles_df: pd.DataFrame) -> list[str]:
    """Return shared applicability buckets that exist in Roles.csv."""
    available_roles = set(
        roles_df['Role']
        .fillna('')
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    return [role for role in GLOBAL_ROLE_BUCKETS if role in available_roles]


def _clean_sapid(value: Any) -> str:
    """Normalize a SAPID value to a plain integer string (strips '.0' from pandas floats)."""
    if pd.isna(value):
        return ""
    try:
        return str(int(float(str(value).strip())))
    except (ValueError, TypeError):
        return str(value).strip()


def _clean_text(value: Any, default: str = "") -> str:
    """Normalize text values from CSV cells."""
    if pd.isna(value):
        return default

    text = str(value).strip()
    if not text:
        return default

    if text.lower() in {"nan", "none", "null"}:
        return default

    return text


def _git_activity_detail_export_user_key(current_user: TokenData) -> str:
    return (
        _clean_text(getattr(current_user, 'user_id', ''))
        or _clean_text(getattr(current_user, 'sapid', ''))
        or _clean_text(getattr(current_user, 'name', ''))
        or 'anonymous'
    )


def _cleanup_git_activity_detail_export_jobs() -> None:
    expiry_cutoff = datetime.now() - timedelta(hours=12)

    with _git_activity_detail_export_lock:
        active_job_ids = set(_git_activity_detail_export_active_by_user.values())
        removable_job_ids: list[str] = []
        for job_id, job in _git_activity_detail_export_jobs.items():
            status = _clean_text(job.get('status')).lower()
            completed_at_str = _clean_text(job.get('completed_at'))
            if status in {'pending', 'running'} or job_id in active_job_ids:
                continue
            if not completed_at_str:
                removable_job_ids.append(job_id)
                continue
            try:
                completed_at = datetime.fromisoformat(completed_at_str)
            except Exception:
                removable_job_ids.append(job_id)
                continue
            if completed_at < expiry_cutoff:
                removable_job_ids.append(job_id)

        for job_id in removable_job_ids:
            job = _git_activity_detail_export_jobs.pop(job_id, None)
            file_path_str = _clean_text((job or {}).get('file_path')) if job else ''
            file_path = Path(file_path_str) if file_path_str else None
            if file_path and file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass

        active_users_to_clear: list[str] = []
        for user_key, job_id in _git_activity_detail_export_active_by_user.items():
            job = _git_activity_detail_export_jobs.get(job_id)
            if not job or _clean_text(job.get('status')).lower() not in {'pending', 'running'}:
                active_users_to_clear.append(user_key)

        for user_key in active_users_to_clear:
            _git_activity_detail_export_active_by_user.pop(user_key, None)


def _git_activity_detail_export_snapshot(job: dict[str, Any]) -> dict[str, Any]:
    return {
        'success': True,
        'job_id': _clean_text(job.get('job_id')),
        'status': _clean_text(job.get('status')).lower() or 'pending',
        'progress_percent': int(_as_float(job.get('progress_percent'))),
        'message': _clean_text(job.get('message')),
        'current_step': _clean_text(job.get('current_step')),
        'started_at': _clean_text(job.get('started_at')),
        'completed_at': _clean_text(job.get('completed_at')),
        'error_message': _clean_text(job.get('error_message')),
        'download_ready': bool(job.get('download_ready')),
        'download_filename': _clean_text(job.get('download_filename')),
        'selected_month': _clean_text(job.get('selected_month')),
        'team': _clean_text(job.get('team')),
        'scrum': _clean_text(job.get('scrum')),
        'activity_type': _clean_text(job.get('activity_type')),
        'employee_scope': _clean_text(job.get('employee_scope')),
        'rows_written': int(_as_float(job.get('rows_written'))),
    }


def _update_git_activity_detail_export_job(job_id: str, **updates: Any) -> None:
    with _git_activity_detail_export_lock:
        job = _git_activity_detail_export_jobs.get(job_id)
        if not job:
            return
        job.update(updates)


def _get_git_activity_detail_export_job(job_id: str) -> Optional[dict[str, Any]]:
    with _git_activity_detail_export_lock:
        job = _git_activity_detail_export_jobs.get(job_id)
        return dict(job) if isinstance(job, dict) else None


def _get_active_git_activity_detail_export_job_for_user(user_key: str) -> Optional[dict[str, Any]]:
    with _git_activity_detail_export_lock:
        job_id = _git_activity_detail_export_active_by_user.get(user_key)
        job = _git_activity_detail_export_jobs.get(job_id) if job_id else None
        if not isinstance(job, dict):
            return None
        if _clean_text(job.get('status')).lower() not in {'pending', 'running'}:
            return None
        return dict(job)


def _json_list_dumps(values: set[str] | list[str]) -> str:
    """Serialize a set/list of strings to deterministic JSON array text."""
    normalized_values = sorted({
        _clean_text(value)
        for value in values
        if _clean_text(value)
    })
    return json.dumps(normalized_values, ensure_ascii=False)


def _json_list_loads(value: Any) -> list[str]:
    """Parse JSON array text to normalized string list."""
    if value is None or pd.isna(value):
        return []

    raw_text = _clean_text(value)
    if not raw_text:
        return []

    try:
        parsed = json.loads(raw_text)
    except Exception:
        return [item for item in [_clean_text(token) for token in raw_text.split('|')] if item]

    if not isinstance(parsed, list):
        return []

    return [item for item in [_clean_text(token) for token in parsed] if item]


def _extract_components(value: Any) -> list[str]:
    """Parse components cell into normalized component tokens."""
    raw_text = _clean_text(value)
    if not raw_text:
        return []

    tokens: list[str] = []
    for separator in ['|', ';']:
        raw_text = raw_text.replace(separator, ',')

    for token in raw_text.split(','):
        cleaned = _clean_text(token)
        if cleaned:
            tokens.append(cleaned)

    return sorted(set(tokens))


def _epic_workspace_file_name(epic_key: str) -> str:
    """Return deterministic per-epic workspace filename."""
    return f"epic_{quote(epic_key, safe='')}.csv"


def _issue_transitions_cache_path(issue_key: str, target_dir: Optional[Path] = None) -> Path:
    """Return path to the per-issue transitions cache file inside the EpicTree folder."""
    base = target_dir if target_dir is not None else EPIC_TREE_OUTPUT_DIR
    return base / 'transitions' / f"issue_{quote(str(issue_key), safe='')}.json"


def _resolve_epic_tree_output_dir(
    output_dir: Optional[Path] = None,
    project_root_override: Optional[Path] = None
) -> Path:
    """Resolve EpicTree output folder path."""
    if output_dir is None:
        if project_root_override is not None:
            return Path(project_root_override).expanduser().resolve() / 'output' / 'EpicTree'
        return EPIC_TREE_OUTPUT_DIR
    return Path(output_dir).expanduser().resolve()


def _emit_epic_tree_cache_progress(step: int, total_steps: int, message: str, enabled: bool) -> None:
    """Print progress lines for long-running EpicTree cache generation."""
    if not enabled:
        return

    safe_total = max(1, total_steps)
    bounded_step = max(0, min(step, safe_total))
    percent = int(round((bounded_step / safe_total) * 100))
    print(f"[EpicTreeCache] step {bounded_step}/{safe_total} ({percent}%) {message}", flush=True)


def _normalize_person_name(value: Any) -> str:
    """Normalize person names for reliable joins across CSV exports."""
    name = _clean_text(value)
    if not name:
        return ""

    normalized = name.replace('[External]', '').strip()
    normalized = " ".join(normalized.split())
    return normalized.lower()


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert values to float safely."""
    try:
        if pd.isna(value):
            return default
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return default

            cleaned = cleaned.replace(',', '')
            if cleaned.endswith('%'):
                cleaned = cleaned[:-1].strip()

            match = re.search(r'-?\d+(?:\.\d+)?', cleaned)
            if not match:
                return default
            return float(match.group(0))

        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_delay_days(value: Any) -> float:
    """Normalize delay to zero when below threshold and never return negatives."""
    normalized = max(0.0, _safe_float(value, default=0.0))
    if normalized < MIN_DELAY_THRESHOLD_DAYS:
        return 0.0
    return normalized


def _optional_rounded_float(value: Any, digits: int = 2) -> Optional[float]:
    """Return rounded float or None when value is missing/invalid."""
    if value is None or pd.isna(value):
        return None

    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _extract_first_sprint_token(value: Any) -> str:
    """Extract the first sprint token from comma-separated sprint history values."""
    sprint_value = _clean_text(value)
    if not sprint_value:
        return ""

    tokens = [token.strip() for token in sprint_value.split(',') if token.strip()]
    return tokens[0] if tokens else ""


def _format_timestamp(value: Any) -> str:
    """Format timestamp values for JSON responses."""
    if value is None or pd.isna(value):
        return ""

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    parsed = pd.to_datetime(value, errors='coerce', utc=True)
    if pd.isna(parsed):
        return _clean_text(value)

    return parsed.isoformat()


def _load_assignee_team_map() -> dict[str, str]:
    """Build a normalized assignee-name to team mapping from Resources.csv."""
    if not RESOURCES_FILE.exists():
        return {}

    try:
        resources_df = _load_normalized_resources_df()
    except Exception:
        return {}

    if 'Team' not in resources_df.columns:
        return {}

    team_map: dict[str, str] = {}
    for _, row in resources_df.iterrows():
        team = _clean_text(row.get('Team'), 'Unknown') or 'Unknown'

        for column in ('JIRA Name', 'Name'):
            normalized_name = _normalize_person_name(row.get(column))
            if normalized_name:
                team_map[normalized_name] = team

    return team_map


def _load_employee_team_map() -> tuple[dict[str, str], dict[str, str], dict[str, str], list[tuple[str, str, str]], list[str]]:
    """Build SAPID-keyed maps and a full employee list from Resources.csv.

    Returns:
        team_map:            SAPID -> team
        sapid_name_map:      SAPID -> display name (as spelled in Resources.csv)
        norm_name_to_sapid:  normalized_lowercase_name -> SAPID (only unique names)
        employees:           list of (sapid, display_name, team) for every row in Resources
        available_teams:     sorted list of all team names
    """
    if not RESOURCES_FILE.exists():
        return {}, {}, {}, [], []

    try:
        resources_df = _load_normalized_resources_df()
    except Exception:
        return {}, {}, {}, [], []

    if 'Team' not in resources_df.columns:
        return {}, {}, {}, [], []

    team_map: dict[str, str] = {}            # SAPID -> team
    sapid_name_map: dict[str, str] = {}      # SAPID -> display name (proper casing)
    norm_name_to_sapids: dict[str, list[str]] = {}  # normalized_name -> [SAPIDs]
    employees: list[tuple[str, str, str]] = []
    available_teams = sorted({
        _clean_text(value)
        for value in resources_df['Team'].tolist()
        if _clean_text(value)
    })

    for _, row in resources_df.iterrows():
        sapid = _clean_sapid(row.get('SAPID'))
        display_name = _clean_text(row.get('Name'))   # keep original casing from Resources
        norm_name = _normalize_person_name(row.get('Name'))  # lowercase, for matching only
        team = _clean_text(row.get('Team'))
        if not sapid:
            continue
        if team:
            team_map[sapid] = team
        if display_name:
            sapid_name_map[sapid] = display_name
        if norm_name:
            norm_name_to_sapids.setdefault(norm_name, []).append(sapid)
        employees.append((sapid, display_name or sapid, team or ""))

    # Only keep name→SAPID for names that belong to exactly one employee (unambiguous)
    norm_name_to_sapid: dict[str, str] = {
        name: sapids[0]
        for name, sapids in norm_name_to_sapids.items()
        if len(sapids) == 1
    }

    return team_map, sapid_name_map, norm_name_to_sapid, employees, available_teams


def _find_column_by_normalized_name(columns: list[str], expected: str) -> Optional[str]:
    """Find a column by comparing stripped/lowercased names."""
    expected_norm = expected.strip().lower()
    for column in columns:
        if column.strip().lower() == expected_norm:
            return column
    return None

def _load_normalized_resources_df() -> pd.DataFrame:
    """Load Resources.csv with normalized headers and key string fields."""
    resources_df = pd.read_csv(RESOURCES_FILE)
    resources_df.columns = [str(column).strip() for column in resources_df.columns]
    for column in ['Name', 'SAPID', 'Team', 'Scrum', 'Primary Role', 'Secondary Role', 'JIRA Name', 'EMail', 'GIT Email', 'Employment Status', 'Start Date']:
        if column in resources_df.columns:
            resources_df[column] = resources_df[column].apply(
                lambda value: str(value).strip() if pd.notna(value) else value
            )
    return resources_df


def _load_employee_git_identity_map() -> dict[str, dict[str, str]]:
    """Return email->employee profile map using Resources.csv data."""
    if not RESOURCES_FILE.exists():
        return {}

    try:
        resources_df = _load_normalized_resources_df()
    except Exception:
        return {}

    columns = list(resources_df.columns)
    name_col = _find_column_by_normalized_name(columns, 'Name')
    sapid_col = _find_column_by_normalized_name(columns, 'SAPID')
    team_col = _find_column_by_normalized_name(columns, 'Team')
    scrum_col = _find_column_by_normalized_name(columns, 'Scrum')
    primary_role_col = _find_column_by_normalized_name(columns, 'Primary Role')
    secondary_role_col = _find_column_by_normalized_name(columns, 'Secondary Role')
    mail_col = _find_column_by_normalized_name(columns, 'EMail')
    git_mail_col = _find_column_by_normalized_name(columns, 'GIT Email')

    email_map: dict[str, dict[str, str]] = {}
    for _, row in resources_df.iterrows():
        name = _clean_text(row.get(name_col)) if name_col else ''
        sapid = _clean_sapid(row.get(sapid_col)) if sapid_col else ''
        team = _clean_text(row.get(team_col)) if team_col else ''
        scrum = _clean_text(row.get(scrum_col)) if scrum_col else ''
        primary_role = _clean_text(row.get(primary_role_col)) if primary_role_col else ''
        secondary_role = _clean_text(row.get(secondary_role_col)) if secondary_role_col else ''

        profile = {
            'name': name,
            'sapid': sapid,
            'team': team,
            'scrum': scrum,
            'primary_role': primary_role,
            'secondary_role': secondary_role,
        }

        raw_emails = []
        if mail_col:
            raw_emails.append(_clean_text(row.get(mail_col)).lower())
        if git_mail_col:
            raw_emails.append(_clean_text(row.get(git_mail_col)).lower())

        for raw_email in raw_emails:
            cleaned_email = raw_email.strip()
            if cleaned_email:
                email_map[cleaned_email] = profile

    return email_map


def _load_employee_git_roster() -> list[dict[str, str]]:
    """Return employee roster rows from Resources.csv for git activity reports."""
    if not RESOURCES_FILE.exists():
        return []

    try:
        resources_df = _load_normalized_resources_df()
    except Exception:
        return []

    columns = list(resources_df.columns)
    name_col = _find_column_by_normalized_name(columns, 'Name')
    sapid_col = _find_column_by_normalized_name(columns, 'SAPID')
    team_col = _find_column_by_normalized_name(columns, 'Team')
    scrum_col = _find_column_by_normalized_name(columns, 'Scrum')
    mail_col = _find_column_by_normalized_name(columns, 'EMail')
    git_mail_col = _find_column_by_normalized_name(columns, 'GIT Email')

    roster: list[dict[str, str]] = []
    for _, row in resources_df.iterrows():
        roster.append({
            'name': _clean_text(row.get(name_col)) if name_col else '',
            'sapid': _clean_sapid(row.get(sapid_col)) if sapid_col else '',
            'team': _clean_text(row.get(team_col)) if team_col else '',
            'scrum': _clean_text(row.get(scrum_col)) if scrum_col else '',
            'author_email': (
                _clean_text(row.get(git_mail_col)).lower()
                if git_mail_col and _clean_text(row.get(git_mail_col))
                else _clean_text(row.get(mail_col)).lower() if mail_col else ''
            ),
        })

    return roster


def _parse_optional_date(value: Any) -> Optional[date]:
    parsed = pd.to_datetime(value, errors='coerce')
    if pd.isna(parsed):
        return None
    return parsed.date()


def _normalize_ude_version(value: Any) -> str:
    version = _clean_text(value)
    # Normalize optional leading 'v' (e.g. v1.8.3 -> 1.8.3) for consistent filtering.
    if version.lower().startswith('v') and len(version) > 1 and version[1].isdigit():
        return version[1:]
    return version


def _business_days_for_month(month_key: str, start_date: Optional[date], as_of: Optional[date] = None) -> int:
    try:
        year_value, month_value = month_key.split('-')
        year = int(year_value)
        month = int(month_value)
    except Exception:
        return 0

    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])

    # For an in-progress month, cap at today so actuals aren't deflated
    # by future days the employee hasn't had a chance to work yet.
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


def _score_from_ratio(actual_value: float, target_value: float) -> int:
    if target_value <= 0:
        return 100 if actual_value > 0 else 0
    score = min(100.0, (actual_value / target_value) * 100.0)
    return int(round(score))


def _safe_average(values: list[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _load_employee_start_date_maps() -> tuple[dict[str, date], dict[str, date]]:
    if not RESOURCES_FILE.exists():
        return {}, {}

    try:
        resources_df = _load_normalized_resources_df()
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


def _get_configured_annual_start(ref_date: Optional[date] = None) -> date:
    target_date = ref_date or date.today()
    fiscal_start_month = 4
    fiscal_start_day = 1

    try:
        if TIME_CONFIG_FILE.exists():
            with open(TIME_CONFIG_FILE, 'r', encoding='utf-8') as handle:
                payload = json.load(handle) or {}
            calendar_config = payload.get('kpi_calendar') or {}
            fiscal_start_month = int(calendar_config.get('fiscal_start_month', fiscal_start_month))
            fiscal_start_day = int(calendar_config.get('fiscal_start_day', fiscal_start_day))
    except Exception:
        fiscal_start_month = 4
        fiscal_start_day = 1

    try:
        start_this_year = date(target_date.year, fiscal_start_month, fiscal_start_day)
    except Exception:
        start_this_year = date(target_date.year, 4, 1)

    if target_date >= start_this_year:
        return start_this_year

    try:
        return date(target_date.year - 1, fiscal_start_month, fiscal_start_day)
    except Exception:
        return date(target_date.year - 1, 4, 1)


def _build_git_activity_monthly_stats(
    commits_file: Path,
    months_of_interest: set[str],
    keys_of_interest: set[str],
) -> dict[str, dict[str, dict[str, int]]]:
    if not commits_file.exists() or not months_of_interest or not keys_of_interest:
        return {}

    try:
        commits_df = pd.read_csv(
            commits_file,
            usecols=['date', 'author_email', 'message'],
        )
    except Exception:
        return {}

    identity_by_email = _load_employee_git_identity_map()
    merge_regex = re.compile(r'^\s*merge(d)?\b', re.IGNORECASE)
    stats: dict[str, dict[str, dict[str, Any]]] = {}

    for _, row in commits_df.iterrows():
        parsed_date = pd.to_datetime(row.get('date'), errors='coerce')
        if pd.isna(parsed_date):
            continue

        month_key = parsed_date.strftime('%Y-%m')
        if month_key not in months_of_interest:
            continue

        author_email = _clean_text(row.get('author_email')).lower()
        resolved = identity_by_email.get(author_email, {})
        key = _clean_sapid(resolved.get('sapid')) or author_email
        if key not in keys_of_interest:
            continue

        message = _clean_text(row.get('message'))
        month_bucket = stats.setdefault(key, {}).setdefault(
            month_key,
            {
                'total_commits': 0,
                'merge_commits': 0,
                'active_days_set': set(),
            }
        )
        month_bucket['total_commits'] += 1
        if merge_regex.match(message):
            month_bucket['merge_commits'] += 1
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
    commits_file: Path,
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
    monthly_stats = _build_git_activity_monthly_stats(commits_file, months_of_interest, row_keys)
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
        selected_stat = monthly_stats.get(row_key, {}).get(selected_month, {
            'total_commits': int(row.get('merge_commits', 0)) + int(row.get('non_merge_commits', 0)),
            'merge_commits': int(row.get('merge_commits', 0)),
            'active_days': 0,
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


def _summarize_cached_git_activity_scorecard(
    rows: list[dict[str, Any]],
    selected_month: str,
    baseline_months: Optional[list[str]] = None,
) -> dict[str, Any]:
    summary_scorecard = _empty_git_activity_scorecard(selected_month, baseline_months)
    overall_scores: list[float] = []
    productivity_scores: list[float] = []
    consistency_scores: list[float] = []
    collaboration_scores: list[float] = []

    for row in rows:
        score = row.get('git_activity_score')
        if not isinstance(score, dict):
            continue

        overall_scores.append(float(score.get('overall_score', 0)))
        productivity_scores.append(float(score.get('productivity_score', 0)))
        consistency_scores.append(float(score.get('consistency_score', 0)))
        collaboration_scores.append(float(score.get('collaboration_score', 0)))

    if overall_scores:
        summary_scorecard.update({
            'overall_score': int(round(_safe_average(overall_scores))),
            'productivity_score': int(round(_safe_average(productivity_scores))),
            'consistency_score': int(round(_safe_average(consistency_scores))),
            'collaboration_score': int(round(_safe_average(collaboration_scores))),
            'rows_scored': len(overall_scores),
        })

    return summary_scorecard


def _git_activity_metric_label(activity_type: str) -> str:
    return {
        'total_commits': 'Total Commits',
        'merges': 'Merges',
        'commits': 'Commits',
        'lines_added': 'Lines Added',
        'lines_deleted': 'Lines Deleted',
        'lines_changed': 'Lines Changed',
        'files_changed': 'Files Changed',
        'repos_touched': 'Repos Touched',
    }[activity_type]


def _safe_median(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    count = len(sorted_values)
    middle = count // 2
    if count % 2 == 1:
        return float(sorted_values[middle])
    return float((sorted_values[middle - 1] + sorted_values[middle]) / 2.0)


def _format_week_label(reference_date: date) -> str:
    iso_year, iso_week, _ = reference_date.isocalendar()
    return f"{iso_year}{iso_week:02d}"


def _format_month_label(reference_date: date) -> str:
    return reference_date.strftime('%b%Y')


def _format_quarter_label(reference_date: date) -> str:
    quarter_to_code = {
        1: 'JFM',
        2: 'AMJ',
        3: 'JAS',
        4: 'OND',
    }
    quarter = ((reference_date.month - 1) // 3) + 1
    return f"{quarter_to_code.get(quarter, f'Q{quarter}')}{reference_date.year}"


def _load_ude_config() -> dict:
    """Load UDE version-to-team configuration."""
    if not UDE_CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(UDE_CONFIG_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _compute_effective_version_teams(
    release_by_version: 'dict[str, date]',
    ude_config: dict,
) -> 'dict[str, list[str]]':
    """
    For each version, compute its effective team assignment using propagation.
    A version's effective teams = its explicitly configured teams, or the last
    configured teams (inherited from prior version in ascending release order).
    An empty list means the version is available to ALL teams.
    """
    raw_version_team_mapping = ude_config.get('version_team_mapping', {})
    version_team_mapping: dict[str, list[str]] = {}
    if isinstance(raw_version_team_mapping, dict):
        for version_key, teams in raw_version_team_mapping.items():
            normalized_version = _normalize_ude_version(version_key)
            if not normalized_version:
                continue
            if isinstance(teams, list):
                version_team_mapping[normalized_version] = [
                    _clean_text(team) for team in teams if _clean_text(team)
                ]
            else:
                version_team_mapping[normalized_version] = []
    sorted_versions = sorted(release_by_version.keys(), key=lambda v: release_by_version[v])

    effective: dict[str, list[str]] = {}
    current_teams: list[str] = []
    for v in sorted_versions:
        if v in version_team_mapping:
            current_teams = list(version_team_mapping[v])
        effective[v] = list(current_teams)
    return effective


def _get_applicable_versions_for_team(
    team: str,
    release_by_version: 'dict[str, date]',
    effective_version_teams: 'dict[str, list[str]]',
) -> 'list[str]':
    """
    Return versions applicable to a given team, ascending by release date.
    - Versions with no team assignment (ALL) are always applicable.
    - Versions assigned to specific teams are only applicable to those teams.
    - If a team has at least one team-specific version, only ALL + team-specific
      versions apply (versions assigned to OTHER teams are excluded).
    Falls back to all versions if none are applicable.
    """
    applicable: list[str] = []
    team_has_specific = any(team in teams for v, teams in effective_version_teams.items() if teams)

    for v, teams in effective_version_teams.items():
        if not teams:
            # ALL bucket: applicable to every team
            applicable.append(v)
        elif team in teams:
            # Team-specific and this team is included
            applicable.append(v)
        # else: specific to other teams — skip

    if not applicable:
        # Safety fallback: if no applicable versions found, use all
        applicable = sorted(release_by_version.keys(), key=lambda v: release_by_version[v])

    return sorted(applicable, key=lambda v: release_by_version[v])


def _load_ude_installation_records() -> list[dict[str, Any]]:
    if not UDE_INSTALLATIONS_FILE.exists():
        return []

    try:
        payload = json.loads(UDE_INSTALLATIONS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return []

    if isinstance(payload, dict):
        records = []
        for key, value in payload.items():
            if isinstance(value, dict):
                record = dict(value)
                if not _clean_text(record.get('install_event_id')):
                    record['install_event_id'] = _clean_text(key)
                records.append(record)
        return records

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    return []


def _load_employee_roster_for_ude(employee_scope: str) -> list[dict[str, str]]:
    if not RESOURCES_FILE.exists():
        return []

    try:
        resources_df = _load_normalized_resources_df()
    except Exception:
        return []

    columns = list(resources_df.columns)
    sapid_col = _find_column_by_normalized_name(columns, 'SAPID')
    name_col = _find_column_by_normalized_name(columns, 'Name')
    team_col = _find_column_by_normalized_name(columns, 'Team')
    scrum_col = _find_column_by_normalized_name(columns, 'Scrum')
    status_col = _find_column_by_normalized_name(columns, 'Employment Status')

    roster: list[dict[str, str]] = []
    for _, row in resources_df.iterrows():
        sapid = _clean_sapid(row.get(sapid_col)) if sapid_col else ''
        if not sapid:
            continue

        employment_status = _clean_text(row.get(status_col)).lower() if status_col else ''
        if employee_scope == 'active' and employment_status and employment_status != 'active':
            continue

        roster.append({
            'sapid': sapid,
            'name': _clean_text(row.get(name_col)) if name_col else sapid,
            'team': _clean_text(row.get(team_col)) if team_col else '',
            'scrum': _clean_text(row.get(scrum_col)) if scrum_col else '',
        })

    return roster


def _build_ude_installation_snapshot() -> tuple[list[dict[str, Any]], dict[str, date]]:
    raw_records = _load_ude_installation_records()

    parsed_records: list[dict[str, Any]] = []
    release_by_version: dict[str, date] = {}
    for record in raw_records:
        if _clean_text(record.get('status'), 'installed').lower() != 'installed':
            continue

        sapid = _clean_sapid(record.get('sapid'))
        device_id = _clean_text(record.get('device_id'))
        ude_version = _normalize_ude_version(record.get('version'))
        if not sapid or not device_id or not ude_version:
            continue

        release_date = _parse_optional_date(record.get('release_date'))
        installed_date = _parse_optional_date(record.get('installed_date'))
        if release_date is None:
            continue

        existing_release = release_by_version.get(ude_version)
        if existing_release is None or release_date < existing_release:
            release_by_version[ude_version] = release_date

        parsed_records.append({
            'sapid': sapid,
            'device_id': device_id,
            'device_label': _clean_text(record.get('device_label')),
            'version': ude_version,
            'release_date': release_date,
            'installed_date': installed_date,
        })

    return parsed_records, release_by_version


@router.get("/ude-installations/filters")
def get_ude_installations_filters(
    employee_scope: str = Query("active", description="active|all"),
    current_user: TokenData = Depends(require_report_access),
):
    """Return filter options (teams, scrums, versions) without running full report."""
    try:
        normalized_employee_scope = _clean_text(employee_scope).lower() or 'active'
        if normalized_employee_scope not in {'active', 'all'}:
            raise HTTPException(status_code=400, detail='employee_scope must be one of: active, all')

        _, release_by_version = _build_ude_installation_snapshot()
        all_versions = sorted(release_by_version.keys(), key=lambda v: release_by_version[v], reverse=True)

        roster = _load_employee_roster_for_ude(normalized_employee_scope)
        employee_team_map, _, _, _, all_teams = _load_employee_team_map()
        accessible_sapids, accessible_teams = _get_accessible_matrix_scope(
            current_user=current_user,
            employee_team_map=employee_team_map,
            all_teams=all_teams,
        )
        accessible_team_set = set(accessible_teams)
        team_manager_team_scope = {
            _clean_text(team_id)
            for team_id in (current_user.team_ids or [])
            if _clean_text(team_id)
        } if current_user.role == "Team Manager" else set()

        teams: set[str] = set()
        scrums: set[str] = set()
        for employee in roster:
            emp_sapid = employee['sapid']
            emp_team = employee.get('team', '')
            if accessible_sapids is not None:
                visible_by_sapid = bool(emp_sapid and emp_sapid in accessible_sapids)
                visible_by_team = bool(emp_team and emp_team in accessible_team_set)
                if not (visible_by_sapid or visible_by_team):
                    continue
            if emp_team:
                teams.add(emp_team)
            emp_scrum = employee.get('scrum', '')
            if emp_scrum:
                scrums.add(emp_scrum)

        return {
            'teams': sorted(teams),
            'scrums': sorted(scrums),
            'versions': all_versions,
            'compliance': ['all', 'compliant', 'non_compliant'],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/ude-installations")
def get_ude_installations_report(
    team: Optional[str] = Query(None, description="Optional team filter"),
    scrum: Optional[str] = Query(None, description="Optional scrum filter"),
    version: Optional[str] = Query(None, description="Optional UDE version filter; defaults to latest release"),
    compliance_filter: str = Query("non_compliant", description="all|compliant|non_compliant"),
    employee_scope: str = Query("active", description="active|all"),
    current_user: TokenData = Depends(require_report_access),
):
    """UDE installation compliance report with employee summary and device exception rows."""
    try:
        normalized_employee_scope = _clean_text(employee_scope).lower() or 'active'
        if normalized_employee_scope not in {'active', 'all'}:
            raise HTTPException(status_code=400, detail='employee_scope must be one of: active, all')

        normalized_compliance_filter = _clean_text(compliance_filter).lower() or 'non_compliant'
        if normalized_compliance_filter not in {'all', 'compliant', 'non_compliant'}:
            raise HTTPException(status_code=400, detail='compliance_filter must be one of: all, compliant, non_compliant')

        team_filter = _clean_text(team)
        scrum_filter = _clean_text(scrum)
        version_filter = _normalize_ude_version(version)

        parsed_records, release_by_version = _build_ude_installation_snapshot()
        ude_config = _load_ude_config()
        effective_version_teams = _compute_effective_version_teams(release_by_version, ude_config)

        if not release_by_version:
            return {
                'success': True,
                'data': [],
                'summary': {
                    'total_rows': 0,
                    'filtered_rows': 0,
                    'total_employees': 0,
                    'fully_compliant_employees': 0,
                    'employee_compliance_percent': 0.0,
                    'total_devices': 0,
                    'compliant_devices': 0,
                    'device_compliance_percent': 0.0,
                },

                'available_filters': {
                    'teams': [],
                    'scrums': [],
                    'versions': [],
                    'compliance': ['all', 'compliant', 'non_compliant'],
                },
                'applied_filters': {
                    'team': team_filter,
                    'scrum': scrum_filter,
                    'version': version_filter,
                    'compliance_filter': normalized_compliance_filter,
                    'employee_scope': normalized_employee_scope,
                },
                'default_compliance_filter': 'non_compliant',
            }

        all_versions = sorted(release_by_version.keys(), key=lambda v: release_by_version[v], reverse=True)
        # Global latest version (for filter display and fallback)
        global_latest_version = all_versions[0] if all_versions else ''

        roster = _load_employee_roster_for_ude(normalized_employee_scope)
        employee_team_map, _, _, _, all_teams = _load_employee_team_map()
        accessible_sapids, accessible_teams = _get_accessible_matrix_scope(
            current_user=current_user,
            employee_team_map=employee_team_map,
            all_teams=all_teams,
        )
        accessible_team_set = set(accessible_teams)
        team_manager_team_scope = {
            _clean_text(team_id)
            for team_id in (current_user.team_ids or [])
            if _clean_text(team_id)
        } if current_user.role == "Team Manager" else set()

        visible_roster: list[dict[str, str]] = []
        for employee in roster:
            sapid = employee['sapid']
            employee_team = employee.get('team', '')
            if accessible_sapids is not None:
                visible_by_sapid = bool(sapid and sapid in accessible_sapids)
                visible_by_team = bool(employee_team and employee_team in accessible_team_set)
                if not (visible_by_sapid or visible_by_team):
                    continue
            visible_roster.append(employee)

        if team_filter:
            visible_roster = [employee for employee in visible_roster if employee.get('team') == team_filter]
        if scrum_filter:
            visible_roster = [employee for employee in visible_roster if employee.get('scrum') == scrum_filter]

        records_by_sapid: dict[str, list[dict[str, Any]]] = {}
        for record in parsed_records:
            records_by_sapid.setdefault(record['sapid'], []).append(record)

        today = datetime.now().date()
        current_date_label = today.strftime('%Y%m%d')
        week_label = _format_week_label(today)
        month_label = _format_month_label(today)
        quarter_label = _format_quarter_label(today)
        year_label = f"FY{today.year}" if today.month >= 4 else f"FY{today.year - 1}"

        rows: list[dict[str, Any]] = []
        all_employee_stats: list[dict[str, Any]] = []
        total_devices = 0
        compliant_devices = 0

        for employee in visible_roster:
            sapid = employee['sapid']
            name = employee['name']
            emp_team = employee.get('team', '')
            emp_scrum = employee.get('scrum', '')
            employee_records = records_by_sapid.get(sapid, [])

            # Determine version set applicable to this employee's team
            emp_applicable_versions = _get_applicable_versions_for_team(
                emp_team, release_by_version, effective_version_teams
            )
            emp_release_by_version = {v: release_by_version[v] for v in emp_applicable_versions}
            emp_latest_version = emp_applicable_versions[-1] if emp_applicable_versions else global_latest_version
            emp_target_version = version_filter if version_filter in emp_release_by_version else emp_latest_version
            emp_target_release_date = emp_release_by_version.get(emp_target_version, release_by_version.get(emp_target_version, date.today()))

            devices: dict[str, dict[str, Any]] = {}
            for record in employee_records:
                device_id = record['device_id']
                device_entry = devices.setdefault(device_id, {
                    'device_id': device_id,
                    'device_label': record.get('device_label', ''),
                    'events': [],
                })
                if not device_entry.get('device_label') and record.get('device_label'):
                    device_entry['device_label'] = record.get('device_label')
                device_entry['events'].append(record)

            device_rows: list[dict[str, Any]] = []

            for device in devices.values():
                events = sorted(
                    device['events'],
                    key=lambda item: (item.get('installed_date') or date.min, item['release_date'])
                )

                # Use first install per version on a device to avoid reinstall skew.
                first_install_by_version: dict[str, Optional[date]] = {}
                for event in events:
                    version_name = _clean_text(event.get('version'))
                    if not version_name:
                        continue
                    installed_on = event.get('installed_date')
                    if version_name not in first_install_by_version:
                        first_install_by_version[version_name] = installed_on
                    elif installed_on is not None:
                        existing = first_install_by_version.get(version_name)
                        if existing is None or installed_on < existing:
                            first_install_by_version[version_name] = installed_on

                latest_event = events[-1] if events else None
                current_device_version = _clean_text(latest_event.get('version')) if latest_event else ''

                target_install_date = first_install_by_version.get(emp_target_version)
                if target_install_date:
                    device_delay = max(0, (target_install_date - emp_target_release_date).days)
                else:
                    device_delay = max(0, (today - emp_target_release_date).days)

                is_compliant = bool(current_device_version == emp_target_version)
                total_devices += 1
                if is_compliant:
                    compliant_devices += 1

                device_rows.append({
                    'device_id': device['device_id'],
                    'device_label': _clean_text(device.get('device_label')),
                    'device_version': current_device_version,
                    'device_delay': float(device_delay),
                    'is_compliant': is_compliant,
                    'events': events,
                    'first_install_by_version': first_install_by_version,
                })

            total_employee_devices = len(device_rows)
            if total_employee_devices == 0:
                # Keep report actionable: skip employees with no registered UDE devices.
                continue

            non_compliant_devices = [row for row in device_rows if not row['is_compliant']]
            compliant_device_count = total_employee_devices - len(non_compliant_devices)
            employee_compliance_status = 'COMPLIANT' if len(non_compliant_devices) == 0 else 'NON_COMPLIANT'

            current_delay = max([device['device_delay'] for device in device_rows], default=0.0)

            all_employee_stats.append({
                'compliance_status': employee_compliance_status,
            })

            if total_employee_devices > 1:
                rows.append({
                    'current_date': current_date_label,
                    'week': week_label,
                    'month': month_label,
                    'quarter': quarter_label,
                    'year': year_label,
                    'sapid': sapid,
                    'name': name,
                    'team': emp_team,
                    'scrum': emp_scrum,
                    'row_type': 'EMPLOYEE_SUMMARY',
                    'compliance_status': employee_compliance_status,
                    'current_version': emp_target_version,
                    'current_delay_days': round(current_delay, 2),
                    'total_devices': total_employee_devices,
                    'compliant_devices': compliant_device_count,
                    'non_compliant_devices': len(non_compliant_devices),
                    'device_id': '',
                    'device_label': '',
                    'device_version': '',
                    'device_delay_days': 0.0,
                })

            for device in device_rows:
                rows.append({
                    'current_date': current_date_label,
                    'week': week_label,
                    'month': month_label,
                    'quarter': quarter_label,
                    'year': year_label,
                    'sapid': sapid,
                    'name': name,
                    'team': emp_team,
                    'scrum': emp_scrum,
                    'row_type': 'DEVICE',
                    'compliance_status': 'COMPLIANT' if device['is_compliant'] else 'NON_COMPLIANT',
                    'current_version': emp_target_version,
                    'current_delay_days': round(current_delay, 2),
                    'total_devices': total_employee_devices,
                    'compliant_devices': compliant_device_count,
                    'non_compliant_devices': len(non_compliant_devices),
                    'device_id': device['device_id'],
                    'device_label': device['device_label'],
                    'device_version': device['device_version'],
                    'device_delay_days': round(float(device['device_delay']), 2),
                })

        rows.sort(key=lambda item: (item['name'].lower(), item['sapid'], 0 if item['row_type'] == 'EMPLOYEE_SUMMARY' else 1, item['device_id']))

        if normalized_compliance_filter == 'compliant':
            filtered_rows = [row for row in rows if row['compliance_status'] == 'COMPLIANT']
        elif normalized_compliance_filter == 'non_compliant':
            filtered_rows = [row for row in rows if row['compliance_status'] == 'NON_COMPLIANT']
        else:
            filtered_rows = rows

        fully_compliant_employees = sum(1 for row in all_employee_stats if row['compliance_status'] == 'COMPLIANT')
        total_employees = len(all_employee_stats)
        employee_compliance_percent = (fully_compliant_employees / total_employees * 100.0) if total_employees else 0.0
        device_compliance_percent = (compliant_devices / total_devices * 100.0) if total_devices else 0.0

        return {
            'success': True,
            'data': filtered_rows,
            'summary': {
                'total_rows': len(rows),
                'filtered_rows': len(filtered_rows),
                'total_employees': total_employees,
                'fully_compliant_employees': fully_compliant_employees,
                'employee_compliance_percent': round(employee_compliance_percent, 2),
                'total_devices': total_devices,
                'compliant_devices': compliant_devices,
                'device_compliance_percent': round(device_compliance_percent, 2),
            },
            'available_filters': {
                'teams': sorted({employee.get('team', '') for employee in visible_roster if employee.get('team', '')}),
                'scrums': sorted({employee.get('scrum', '') for employee in visible_roster if employee.get('scrum', '')}),
                'versions': all_versions,
                'compliance': ['all', 'compliant', 'non_compliant'],
            },
            'applied_filters': {
                'team': team_filter,
                'scrum': scrum_filter,
                'version': version_filter or global_latest_version,
                'compliance_filter': normalized_compliance_filter,
                'employee_scope': normalized_employee_scope,
            },
            'default_compliance_filter': 'non_compliant',
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/ude-installations/{sapid}/details")
def get_ude_installations_employee_details(
    sapid: str,
    employee_scope: str = Query("active", description="active|all"),
    current_user: TokenData = Depends(require_report_access),
):
    try:
        normalized_employee_scope = _clean_text(employee_scope).lower() or 'active'
        if normalized_employee_scope not in {'active', 'all'}:
            raise HTTPException(status_code=400, detail='employee_scope must be one of: active, all')

        normalized_sapid = _clean_sapid(sapid)
        if not normalized_sapid:
            raise HTTPException(status_code=400, detail='Invalid SAPID')

        parsed_records, release_by_version = _build_ude_installation_snapshot()
        ude_config = _load_ude_config()
        effective_version_teams = _compute_effective_version_teams(release_by_version, ude_config)
        today = datetime.now().date()

        roster = _load_employee_roster_for_ude(normalized_employee_scope)
        employee_team_map, _, _, _, all_teams = _load_employee_team_map()
        accessible_sapids, accessible_teams = _get_accessible_matrix_scope(
            current_user=current_user,
            employee_team_map=employee_team_map,
            all_teams=all_teams,
        )
        accessible_team_set = set(accessible_teams)

        visible_roster: list[dict[str, str]] = []
        for employee in roster:
            employee_sapid = employee['sapid']
            employee_team = employee.get('team', '')
            if accessible_sapids is not None:
                visible_by_sapid = bool(employee_sapid and employee_sapid in accessible_sapids)
                visible_by_team = bool(employee_team and employee_team in accessible_team_set)
                if not (visible_by_sapid or visible_by_team):
                    continue
            visible_roster.append(employee)

        employee = next((item for item in visible_roster if item['sapid'] == normalized_sapid), None)
        if employee is None:
            raise HTTPException(status_code=404, detail='Employee not found or not accessible')

        emp_team = employee.get('team', '')
        employee_start_date_by_sapid, _ = _load_employee_start_date_maps()
        employee_start_date = employee_start_date_by_sapid.get(normalized_sapid)
        annual_start_date = _get_configured_annual_start(today)
        version_cutoff_date = max(employee_start_date, annual_start_date) if employee_start_date else annual_start_date

        emp_applicable_versions = _get_applicable_versions_for_team(emp_team, release_by_version, effective_version_teams)
        emp_release_by_version = {v: release_by_version[v] for v in emp_applicable_versions}
        sorted_emp_versions = sorted(emp_release_by_version.items(), key=lambda item: item[1])
        emp_latest_version = sorted_emp_versions[-1][0] if sorted_emp_versions else ''

        employee_records = [record for record in parsed_records if record['sapid'] == normalized_sapid]

        devices: dict[str, dict[str, Any]] = {}
        for record in employee_records:
            device_id = _clean_text(record.get('device_id'))
            version_name = _clean_text(record.get('version'))
            if not device_id or not version_name:
                continue

            device_entry = devices.setdefault(device_id, {
                'device_id': device_id,
                'device_label': _clean_text(record.get('device_label')),
                'first_install_by_version': {},
            })

            if not device_entry.get('device_label') and _clean_text(record.get('device_label')):
                device_entry['device_label'] = _clean_text(record.get('device_label'))

            installed_date = record.get('installed_date')
            existing_installed = device_entry['first_install_by_version'].get(version_name)
            if existing_installed is None:
                device_entry['first_install_by_version'][version_name] = installed_date
            elif installed_date is not None and installed_date < existing_installed:
                device_entry['first_install_by_version'][version_name] = installed_date

        # Apply the annual/start-date cutoff, but always keep the latest applicable
        # version visible so the drawer can explain current installation state.
        versions_by_release = [
            (version_name, release_date)
            for version_name, release_date in sorted_emp_versions
            if release_date >= version_cutoff_date or version_name == emp_latest_version
        ]

        detail_rows: list[dict[str, Any]] = []
        for device in sorted(devices.values(), key=lambda item: item.get('device_id', '')):
            first_install_by_version = device.get('first_install_by_version', {})
            device_id = _clean_text(device.get('device_id'))
            device_label = _clean_text(device.get('device_label'))

            for version_index, (version_name, release_date) in enumerate(versions_by_release):
                installed_date = first_install_by_version.get(version_name)

                if installed_date is not None:
                    delay_end_date = installed_date
                else:
                    delay_end_date = today
                    for next_version, _ in versions_by_release[version_index + 1:]:
                        next_installed = first_install_by_version.get(next_version)
                        if next_installed is not None:
                            delay_end_date = next_installed
                            break

                computed_delay_days = max(0, (delay_end_date - release_date).days)

                detail_rows.append({
                    'sapid': normalized_sapid,
                    'name': employee.get('name', normalized_sapid),
                    'team': employee.get('team', ''),
                    'scrum': employee.get('scrum', ''),
                    'device_id': device_id,
                    'device_label': device_label,
                    'ude_version': version_name,
                    'installed_date': installed_date.isoformat() if installed_date else '',
                    'release_date': release_date.isoformat(),
                    'computed_delay_days': float(computed_delay_days),
                    'is_latest_target_version': bool(emp_latest_version and version_name == emp_latest_version),
                })

        detail_rows.sort(
            key=lambda item: (
                item.get('device_id', ''),
                item.get('release_date', ''),
            ),
            reverse=True,
        )

        return {
            'success': True,
            'employee': {
                'sapid': normalized_sapid,
                'name': employee.get('name', normalized_sapid),
                'team': employee.get('team', ''),
                'scrum': employee.get('scrum', ''),
            },
            'employee_start_date': employee_start_date.isoformat() if employee_start_date else '',
            'annual_start_date': annual_start_date.isoformat(),
            'version_cutoff_date': version_cutoff_date.isoformat(),
            'latest_target_version': emp_latest_version,
            'data': detail_rows,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _get_accessible_matrix_scope(
    current_user: TokenData,
    employee_team_map: dict[str, str],
    all_teams: list[str]
) -> tuple[Optional[set[str]], list[str]]:
    """Return accessible SAPIDs and team filter options for the matrix report."""
    if current_user.role in ["Admin", "API User"]:
        return None, all_teams

    accessible_sapids: set[str] = set()
    accessible_teams: set[str] = set()

    for accessible_user_id in rbac_service.get_accessible_users(current_user.user_id):
        accessible_user = rbac_user_service.get_user_by_id(accessible_user_id)
        if not accessible_user:
            continue

        sapid = _clean_sapid(accessible_user.sapid)
        if sapid:
            accessible_sapids.add(sapid)
            mapped_team = employee_team_map.get(sapid)
            if mapped_team:
                accessible_teams.add(mapped_team)

        for team_id in accessible_user.team_ids or []:
            cleaned_team = _clean_text(team_id)
            if cleaned_team:
                accessible_teams.add(cleaned_team)

    return accessible_sapids, sorted(accessible_teams)


def _get_accessible_epic_scope(
    current_user: TokenData,
    issues_df: Optional[pd.DataFrame] = None
) -> tuple[Optional[set[str]], list[str]]:
    """Return accessible teams for JIRA epic filtering based on descendant issues."""
    if current_user.role in ["Admin", "API User"]:
        all_teams: list[str] = []
        if issues_df is not None and 'Team' in issues_df.columns:
            all_teams = sorted({
                _clean_text(value, 'Unknown')
                for value in issues_df['Team'].tolist()
                if _clean_text(value, 'Unknown')
            })
        return None, all_teams

    accessible_assignees: set[str] = set()
    accessible_teams: set[str] = set()

    # Get accessible users for current user
    for accessible_user_id in rbac_service.get_accessible_users(current_user.user_id):
        accessible_user = rbac_user_service.get_user_by_id(accessible_user_id)
        if not accessible_user:
            continue

        # Add user's name (normalized)
        normalized_name = _normalize_person_name(accessible_user.name)
        if normalized_name:
            accessible_assignees.add(normalized_name)

        # Add teams from user's team_ids
        for team_id in accessible_user.team_ids or []:
            cleaned_team = _clean_text(team_id)
            if cleaned_team:
                accessible_teams.add(cleaned_team)

    return accessible_assignees, sorted(accessible_teams)


def _load_completion_dates() -> dict[str, pd.Timestamp]:
    """Load first transition-to-done timestamp per issue from changelog history."""
    if not JIRA_HISTORY_FILE.exists():
        return {}

    try:
        history_df = pd.read_csv(JIRA_HISTORY_FILE)
    except Exception:
        return {}

    required_columns = {'Key', 'Field', 'ToValue', 'ChangeDate'}
    if not required_columns.issubset(history_df.columns):
        return {}

    history_df['Field'] = history_df['Field'].fillna('').astype(str).str.strip().str.lower()
    history_df['ToValue'] = history_df['ToValue'].fillna('').astype(str).str.strip().str.lower()
    history_df = history_df[
        (history_df['Field'] == 'status')
        & (history_df['ToValue'].isin(DONE_STATUSES))
    ].copy()

    if history_df.empty:
        return {}

    history_df['ChangeDate'] = pd.to_datetime(history_df['ChangeDate'], errors='coerce', utc=True)
    history_df = history_df.dropna(subset=['ChangeDate'])
    history_df['Key'] = history_df['Key'].fillna('').astype(str).str.strip()
    history_df = history_df[history_df['Key'] != '']

    if history_df.empty:
        return {}

    history_df = history_df.sort_values(['Key', 'ChangeDate'])
    first_done_df = history_df.groupby('Key', as_index=False).first()

    return {
        _clean_text(row['Key']): row['ChangeDate']
        for _, row in first_done_df.iterrows()
        if _clean_text(row['Key'])
    }


def _load_initial_sprint_allocations() -> dict[str, dict[str, Any]]:
    """Load first sprint allocation timestamp and sprint for each issue from history."""
    if not JIRA_HISTORY_FILE.exists():
        return {}

    try:
        history_df = pd.read_csv(JIRA_HISTORY_FILE)
    except Exception:
        return {}

    required_columns = {'Key', 'Field', 'ToValue', 'ChangeDate'}
    if not required_columns.issubset(history_df.columns):
        return {}

    history_df['Field'] = history_df['Field'].fillna('').astype(str).str.strip().str.lower()
    history_df = history_df[history_df['Field'] == 'sprint'].copy()
    if history_df.empty:
        return {}

    history_df['Key'] = history_df['Key'].fillna('').astype(str).str.strip()
    history_df['ToValue'] = history_df['ToValue'].fillna('').astype(str).str.strip()
    history_df['ChangeDate'] = pd.to_datetime(history_df['ChangeDate'], errors='coerce', utc=True)
    history_df = history_df[
        (history_df['Key'] != '')
        & history_df['ChangeDate'].notna()
        & (history_df['ToValue'] != '')
    ].copy()

    if history_df.empty:
        return {}

    history_df['first_sprint_token'] = history_df['ToValue'].apply(_extract_first_sprint_token)
    history_df = history_df[history_df['first_sprint_token'] != '']
    if history_df.empty:
        return {}

    history_df = history_df.sort_values(['Key', 'ChangeDate'])

    initial_allocations: dict[str, dict[str, Any]] = {}
    for issue_key, issue_history in history_df.groupby('Key'):
        first_row = issue_history.iloc[0]
        initial_allocations[_clean_text(issue_key)] = {
            'allocated_at': first_row['ChangeDate'],
            'initial_sprint': _clean_text(first_row['first_sprint_token'])
        }

    return initial_allocations


def _load_first_active_dates() -> dict[str, pd.Timestamp]:
    """Load first active-status timestamp per issue from changelog history."""
    if not JIRA_HISTORY_FILE.exists():
        return {}

    try:
        history_df = pd.read_csv(JIRA_HISTORY_FILE)
    except Exception:
        return {}

    required_columns = {'Key', 'Field', 'ToValue', 'ChangeDate'}
    if not required_columns.issubset(history_df.columns):
        return {}

    history_df['Field'] = history_df['Field'].fillna('').astype(str).str.strip().str.lower()
    history_df['ToValue'] = history_df['ToValue'].fillna('').astype(str).str.strip().str.lower()
    history_df = history_df[
        (history_df['Field'] == 'status')
        & (history_df['ToValue'].isin(FIRST_ACTIVE_STATUSES))
    ].copy()

    if history_df.empty:
        return {}

    history_df['ChangeDate'] = pd.to_datetime(history_df['ChangeDate'], errors='coerce', utc=True)
    history_df = history_df.dropna(subset=['ChangeDate'])
    history_df['Key'] = history_df['Key'].fillna('').astype(str).str.strip()
    history_df = history_df[history_df['Key'] != '']

    if history_df.empty:
        return {}

    history_df = history_df.sort_values(['Key', 'ChangeDate'])
    first_active_df = history_df.groupby('Key', as_index=False).first()

    return {
        _clean_text(row['Key']): row['ChangeDate']
        for _, row in first_active_df.iterrows()
        if _clean_text(row['Key'])
    }


def _load_next_transition_details(initial_allocations: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Load first transition after initial allocation (or first transition if unavailable)."""
    if not JIRA_HISTORY_FILE.exists():
        return {}

    try:
        history_df = pd.read_csv(JIRA_HISTORY_FILE)
    except Exception:
        return {}

    required_columns = {'Key', 'Field', 'ToValue', 'ChangeDate'}
    if not required_columns.issubset(history_df.columns):
        return {}

    history_df['Key'] = history_df['Key'].fillna('').astype(str).str.strip()
    history_df['Field'] = history_df['Field'].fillna('').astype(str).str.strip()
    history_df['FromValue'] = history_df['FromValue'].fillna('').astype(str).str.strip() if 'FromValue' in history_df.columns else ''
    history_df['ToValue'] = history_df['ToValue'].fillna('').astype(str).str.strip()
    history_df['ChangedBy'] = history_df['ChangedBy'].fillna('').astype(str).str.strip() if 'ChangedBy' in history_df.columns else ''
    history_df['ChangeDate'] = pd.to_datetime(history_df['ChangeDate'], errors='coerce', utc=True)

    history_df = history_df[
        (history_df['Key'] != '')
        & history_df['ChangeDate'].notna()
        & (history_df['Field'] != '')
    ].copy()

    if history_df.empty:
        return {}

    history_df = history_df.sort_values(['Key', 'ChangeDate'])

    transition_map: dict[str, dict[str, Any]] = {}
    for issue_key, issue_history in history_df.groupby('Key'):
        clean_issue_key = _clean_text(issue_key)
        if not clean_issue_key:
            continue

        start_dt = initial_allocations.get(clean_issue_key, {}).get('allocated_at')
        candidate_history = issue_history

        if start_dt is not None and not pd.isna(start_dt):
            candidate_history = issue_history[issue_history['ChangeDate'] > start_dt]

        if candidate_history.empty:
            candidate_history = issue_history

        if candidate_history.empty:
            continue

        first_transition = candidate_history.iloc[0]
        transition_map[clean_issue_key] = {
            'field': _clean_text(first_transition.get('Field')),
            'from_value': _clean_text(first_transition.get('FromValue')),
            'to_value': _clean_text(first_transition.get('ToValue')),
            'changed_by': _clean_text(first_transition.get('ChangedBy')),
            'changed_at': first_transition.get('ChangeDate')
        }

    return transition_map


def _load_issue_transition_rows(issue_key: str) -> list[dict[str, Any]]:
    """Load full transition history rows for a single issue key."""
    clean_issue_key = _clean_text(issue_key)
    if not clean_issue_key or not JIRA_HISTORY_FILE.exists():
        return []

    try:
        history_df = pd.read_csv(JIRA_HISTORY_FILE)
    except Exception:
        return []

    required_columns = {'Key', 'Field', 'ChangeDate'}
    if not required_columns.issubset(history_df.columns):
        return []

    history_df['Key'] = history_df['Key'].fillna('').astype(str).str.strip()
    history_df = history_df[history_df['Key'] == clean_issue_key].copy()
    if history_df.empty:
        return []

    history_df['Field'] = history_df['Field'].fillna('').astype(str).str.strip()
    history_df['FromValue'] = history_df['FromValue'].fillna('').astype(str).str.strip() if 'FromValue' in history_df.columns else ''
    history_df['ToValue'] = history_df['ToValue'].fillna('').astype(str).str.strip() if 'ToValue' in history_df.columns else ''
    history_df['ChangedBy'] = history_df['ChangedBy'].fillna('').astype(str).str.strip() if 'ChangedBy' in history_df.columns else ''
    history_df['ChangeDate'] = pd.to_datetime(history_df['ChangeDate'], errors='coerce', utc=True)
    history_df = history_df.dropna(subset=['ChangeDate'])
    history_df = history_df.sort_values('ChangeDate')

    transitions: list[dict[str, Any]] = []
    for _, row in history_df.iterrows():
        transitions.append({
            'change_date': _format_timestamp(row.get('ChangeDate')),
            'field': _clean_text(row.get('Field')),
            'from_value': _clean_text(row.get('FromValue')),
            'to_value': _clean_text(row.get('ToValue')),
            'changed_by': _clean_text(row.get('ChangedBy'))
        })

    return transitions


def _build_issue_assignee_timeline(
    transitions: list[dict[str, Any]],
    issue_assignee: Any,
    created_dt: Any,
    effective_end_dt: Any,
    delay_baseline_dt: Any
) -> list[dict[str, Any]]:
    """Build assignee ownership timeline with duration and attributable delay."""
    end_ts = pd.to_datetime(effective_end_dt, errors='coerce', utc=True)
    if end_ts is None or pd.isna(end_ts):
        return []

    start_ts = pd.to_datetime(created_dt, errors='coerce', utc=True)
    baseline_ts = pd.to_datetime(delay_baseline_dt, errors='coerce', utc=True)

    assignee_events: list[dict[str, Any]] = []
    for transition in transitions:
        if _clean_text(transition.get('field')).lower() != 'assignee':
            continue

        change_ts = pd.to_datetime(transition.get('change_date'), errors='coerce', utc=True)
        if change_ts is None or pd.isna(change_ts):
            continue

        assignee_events.append({
            'change_date': change_ts,
            'from_assignee': _clean_text(transition.get('from_value'), 'Unassigned'),
            'to_assignee': _clean_text(transition.get('to_value'), 'Unassigned')
        })

    assignee_events.sort(key=lambda event: event['change_date'])

    if start_ts is None or pd.isna(start_ts):
        if assignee_events:
            start_ts = assignee_events[0]['change_date']
        else:
            start_ts = end_ts

    if start_ts is None or pd.isna(start_ts):
        return []

    if start_ts > end_ts:
        start_ts = end_ts

    current_assignee = _clean_text(issue_assignee, 'Unassigned')
    if assignee_events:
        first_from_assignee = _clean_text(assignee_events[0].get('from_assignee'))
        if first_from_assignee:
            current_assignee = first_from_assignee

    total_delay_days_raw = 0.0
    delay_attribution_enabled = False
    if baseline_ts is not None and not pd.isna(baseline_ts):
        total_delay_days_raw = max(0.0, (end_ts - baseline_ts).total_seconds() / 86400)
        delay_attribution_enabled = total_delay_days_raw >= MIN_DELAY_THRESHOLD_DAYS

    timeline_rows: list[dict[str, Any]] = []

    def append_segment(assignee_name: str, segment_start: pd.Timestamp, segment_end: pd.Timestamp) -> None:
        if (
            segment_start is None
            or segment_end is None
            or pd.isna(segment_start)
            or pd.isna(segment_end)
            or segment_end <= segment_start
        ):
            return

        duration_days = max(0.0, (segment_end - segment_start).total_seconds() / 86400)

        attributable_delay_days = 0.0
        if delay_attribution_enabled and baseline_ts is not None and not pd.isna(baseline_ts):
            overlap_start = max(segment_start, baseline_ts)
            overlap_end = min(segment_end, end_ts)
            if overlap_end > overlap_start:
                attributable_delay_days = max(0.0, (overlap_end - overlap_start).total_seconds() / 86400)

        timeline_rows.append({
            'assignee': _clean_text(assignee_name, 'Unassigned'),
            'period_start': _format_timestamp(segment_start),
            'period_end': _format_timestamp(segment_end),
            'duration_days': round(duration_days, 2),
            'delay_days': round(attributable_delay_days, 2)
        })

    period_start = start_ts

    for event in assignee_events:
        event_ts = event['change_date']
        if event_ts is None or pd.isna(event_ts):
            continue

        if event_ts < period_start:
            next_assignee = _clean_text(event.get('to_assignee'))
            if next_assignee:
                current_assignee = next_assignee
            continue

        bounded_event_ts = min(event_ts, end_ts)
        append_segment(current_assignee, period_start, bounded_event_ts)

        period_start = bounded_event_ts
        next_assignee = _clean_text(event.get('to_assignee'))
        if next_assignee:
            current_assignee = next_assignee

        if period_start >= end_ts:
            break

    append_segment(current_assignee, period_start, end_ts)

    return timeline_rows


def _get_jira_file_mtimes() -> tuple[float, float]:
    """Return (issues_mtime, history_mtime) for cache invalidation."""
    issues_mtime = JIRA_ISSUES_FILE.stat().st_mtime if JIRA_ISSUES_FILE.exists() else 0.0
    history_mtime = JIRA_HISTORY_FILE.stat().st_mtime if JIRA_HISTORY_FILE.exists() else 0.0
    return (issues_mtime, history_mtime)


def _load_jira_issue_data() -> pd.DataFrame:
    """Load JIRA issue data enriched with team, completion, and delay metrics.
    
    Results are cached in memory and only reloaded when the source CSV files
    change on disk, making repeated calls within the same data cycle very fast.
    """
    if not JIRA_ISSUES_FILE.exists():
        raise HTTPException(status_code=404, detail='JIRAIssues.csv not found')

    current_mtimes = _get_jira_file_mtimes()
    if _jira_data_cache['mtimes'] == current_mtimes and _jira_data_cache['df'] is not None:
        return _jira_data_cache['df'].copy()

    try:
        issues_df = pd.read_csv(JIRA_ISSUES_FILE)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'Failed to read JIRAIssues.csv: {exc}')

    required_columns = [
        'Issue Type', 'Key', 'Parent', 'Priority', 'Status', 'Story Points',
        'Assignee', 'Summary', 'Updated', 'Created', 'Sprint.endDate', 'Sprint'
    ]
    for column in required_columns:
        if column not in issues_df.columns:
            issues_df[column] = ''

    for column in ['Issue Type', 'Key', 'Parent', 'Priority', 'Status', 'Assignee', 'Summary', 'Sprint', 'Updated', 'Created']:
        issues_df[column] = issues_df[column].fillna('').astype(str).str.strip()

    issues_df['Story Points'] = pd.to_numeric(issues_df['Story Points'], errors='coerce').fillna(0)
    issues_df['_created_dt'] = pd.to_datetime(issues_df['Created'], errors='coerce', utc=True)
    issues_df['_updated_dt'] = pd.to_datetime(issues_df['Updated'], errors='coerce', utc=True)
    issues_df['_sprint_end_dt'] = pd.to_datetime(issues_df['Sprint.endDate'], errors='coerce', utc=True)

    issues_df['_status_norm'] = issues_df['Status'].str.lower().str.strip()
    issues_df['_is_done'] = issues_df['_status_norm'].isin(DONE_STATUSES)
    issues_df['_is_in_progress'] = (~issues_df['_is_done']) & issues_df['_status_norm'].isin(IN_PROGRESS_STATUSES)
    issues_df['_is_todo'] = (~issues_df['_is_done']) & (~issues_df['_is_in_progress'])

    issues_df['_assignee_norm'] = issues_df['Assignee'].apply(_normalize_person_name)
    assignee_team_map = _load_assignee_team_map()
    issues_df['Team'] = issues_df['_assignee_norm'].map(assignee_team_map).fillna('Unknown')
    for key_prefix, forced_team in FORCED_TEAM_BY_KEY_PREFIX.items():
        forced_team_mask = issues_df['Key'].str.startswith(key_prefix, na=False)
        issues_df.loc[forced_team_mask, 'Team'] = forced_team

    issues_df['Assignee'] = issues_df['Assignee'].where(issues_df['Assignee'] != '', 'Unassigned')

    completion_dates = _load_completion_dates()
    issues_df['_completion_dt'] = pd.to_datetime(
        issues_df['Key'].map(completion_dates),
        errors='coerce',
        utc=True
    )

    first_active_dates = _load_first_active_dates()
    issues_df['_first_active_dt'] = pd.to_datetime(
        issues_df['Key'].map(first_active_dates),
        errors='coerce',
        utc=True
    )
    issues_df['_delay_reference_dt'] = issues_df['_first_active_dt'].fillna(issues_df['_created_dt'])
    issues_df['_delay_reference_source'] = 'created_date'
    issues_df.loc[issues_df['_first_active_dt'].notna(), '_delay_reference_source'] = 'first_active_date'

    issues_df['_delay_baseline_dt'] = issues_df['_sprint_end_dt']
    reference_after_sprint = (
        issues_df['_sprint_end_dt'].notna()
        & issues_df['_delay_reference_dt'].notna()
        & (issues_df['_delay_reference_dt'] > issues_df['_sprint_end_dt'])
    )
    issues_df.loc[reference_after_sprint, '_delay_baseline_dt'] = issues_df.loc[reference_after_sprint, '_delay_reference_dt']

    issues_df['_delay_baseline_source'] = 'sprint_end_date'
    issues_df.loc[reference_after_sprint, '_delay_baseline_source'] = issues_df.loc[reference_after_sprint, '_delay_reference_source']
    issues_df.loc[issues_df['_sprint_end_dt'].isna(), '_delay_baseline_source'] = 'no_sprint_end_date'

    completed_without_history = issues_df['_completion_dt'].isna() & issues_df['_is_done']
    # Note: full build continues below; cache is stored after final column is added at end of function.
    issues_df.loc[completed_without_history, '_completion_dt'] = issues_df.loc[completed_without_history, '_updated_dt']

    initial_allocations = _load_initial_sprint_allocations()
    issues_df['_initial_allocated_dt'] = pd.to_datetime(
        issues_df['Key'].map(lambda issue_key: initial_allocations.get(issue_key, {}).get('allocated_at')),
        errors='coerce',
        utc=True
    )
    issues_df['_initial_sprint'] = issues_df['Key'].map(
        lambda issue_key: _clean_text(initial_allocations.get(issue_key, {}).get('initial_sprint'))
    )

    issues_df['_initial_allocated_dt'] = issues_df['_initial_allocated_dt'].fillna(issues_df['_created_dt'])
    issues_df['_initial_sprint'] = issues_df['_initial_sprint'].where(
        issues_df['_initial_sprint'] != '',
        issues_df['Sprint']
    )

    next_transitions = _load_next_transition_details(initial_allocations)
    issues_df['_next_transition_field'] = issues_df['Key'].map(
        lambda issue_key: _clean_text(next_transitions.get(issue_key, {}).get('field'))
    )
    issues_df['_next_transition_from'] = issues_df['Key'].map(
        lambda issue_key: _clean_text(next_transitions.get(issue_key, {}).get('from_value'))
    )
    issues_df['_next_transition_to'] = issues_df['Key'].map(
        lambda issue_key: _clean_text(next_transitions.get(issue_key, {}).get('to_value'))
    )
    issues_df['_next_transition_by'] = issues_df['Key'].map(
        lambda issue_key: _clean_text(next_transitions.get(issue_key, {}).get('changed_by'))
    )
    issues_df['_next_transition_dt'] = pd.to_datetime(
        issues_df['Key'].map(lambda issue_key: next_transitions.get(issue_key, {}).get('changed_at')),
        errors='coerce',
        utc=True
    )

    sprint_end_by_name = (
        issues_df[
            (issues_df['Sprint'] != '')
            & issues_df['_sprint_end_dt'].notna()
        ]
        .sort_values('_sprint_end_dt')
        .groupby('Sprint')['_sprint_end_dt']
        .first()
        .to_dict()
    )

    issues_df['_initial_sprint_end_dt'] = pd.to_datetime(
        issues_df['_initial_sprint'].map(sprint_end_by_name),
        errors='coerce',
        utc=True
    )

    now_ts = pd.Timestamp.now(tz='UTC')
    effective_end = issues_df['_completion_dt'].where(issues_df['_is_done'], now_ts)

    planned_duration_days = (
        (issues_df['_initial_sprint_end_dt'] - issues_df['_initial_allocated_dt'])
        .dt.total_seconds()
        / 86400
    )
    issues_df['_planned_duration_days'] = planned_duration_days.where(planned_duration_days > 0)

    actual_duration_days = (
        (effective_end - issues_df['_initial_allocated_dt'])
        .dt.total_seconds()
        / 86400
    )
    issues_df['_actual_duration_days'] = actual_duration_days.where(actual_duration_days >= 0)
    issues_df['_slippage_days'] = issues_df['_actual_duration_days'] - issues_df['_planned_duration_days']

    age_days = (effective_end - issues_df['_created_dt']).dt.total_seconds() / 86400
    issues_df['_age_days'] = age_days.fillna(0).clip(lower=0)

    delay_days = (effective_end - issues_df['_delay_baseline_dt']).dt.total_seconds() / 86400
    delay_days = delay_days.where(issues_df['_delay_baseline_dt'].notna(), 0)
    issues_df['_delay_days'] = delay_days.fillna(0).clip(lower=0)
    issues_df['_delay_days'] = issues_df['_delay_days'].apply(_normalize_delay_days)
    issues_df['_is_overdue'] = issues_df['_delay_days'] >= MIN_DELAY_THRESHOLD_DAYS

    # Store in cache before returning. We store a copy so mutations by callers
    # don't corrupt the cached version.
    _jira_data_cache['mtimes'] = current_mtimes
    _jira_data_cache['df'] = issues_df.copy()

    return issues_df


def _issue_sort_key(issue: pd.Series) -> tuple[int, str, str]:
    """Sort key used for deterministic tree ordering."""
    issue_type = _clean_text(issue.get('Issue Type')).lower()
    created = _clean_text(issue.get('Created'), '9999-12-31T23:59:59Z')
    key = _clean_text(issue.get('Key'))
    return (ISSUE_TYPE_ORDER.get(issue_type, 99), created, key)


def _build_children_map(issue_lookup: dict[str, pd.Series]) -> dict[str, list[str]]:
    """Build parent-to-children index for issue hierarchy traversal."""
    issue_keys = set(issue_lookup.keys())
    children_map: dict[str, list[str]] = {}

    for issue_key, issue in issue_lookup.items():
        parent_key = _clean_text(issue.get('Parent'))
        if parent_key and parent_key in issue_keys and parent_key != issue_key:
            children_map.setdefault(parent_key, []).append(issue_key)

    for parent_key, child_keys in children_map.items():
        child_keys.sort(key=lambda child_key: _issue_sort_key(issue_lookup[child_key]))

    return children_map


def _collect_descendant_keys(root_key: str, children_map: dict[str, list[str]]) -> list[str]:
    """Collect all descendants for a root issue key."""
    descendants: list[str] = []
    seen: set[str] = set()
    stack = list(reversed(children_map.get(root_key, [])))

    while stack:
        current_key = stack.pop()
        if current_key in seen:
            continue

        seen.add(current_key)
        descendants.append(current_key)

        for child_key in reversed(children_map.get(current_key, [])):
            if child_key not in seen:
                stack.append(child_key)

    return descendants


def _build_issue_tree_node(
    issue_key: str,
    issue_lookup: dict[str, pd.Series],
    children_map: dict[str, list[str]],
    lineage: Optional[set[str]] = None
) -> dict[str, Any]:
    """Build nested tree node for a given issue and its descendants."""
    issue = issue_lookup[issue_key]
    active_lineage = set() if lineage is None else set(lineage)

    node = {
        'key': _clean_text(issue.get('Key')),
        'parent': _clean_text(issue.get('Parent')),
        'issue_type': _clean_text(issue.get('Issue Type')),
        'summary': _clean_text(issue.get('Summary')),
        'status': _clean_text(issue.get('Status'), 'Unknown'),
        'priority': _clean_text(issue.get('Priority')),
        'story_points': round(_safe_float(issue.get('Story Points')), 2),
        'assignee': _clean_text(issue.get('Assignee'), 'Unassigned'),
        'team': _clean_text(issue.get('Team'), 'Unknown'),
        'sprint': _clean_text(issue.get('Sprint'), 'NA'),
        'created': _clean_text(issue.get('Created')),
        'updated': _clean_text(issue.get('Updated')),
        'sprint_end_date': _format_timestamp(issue.get('_sprint_end_dt')),
        'initial_sprint': _clean_text(issue.get('_initial_sprint'), _clean_text(issue.get('Sprint'), 'NA')),
        'initial_allocation_date': _format_timestamp(issue.get('_initial_allocated_dt')),
        'planned_duration_days': _optional_rounded_float(issue.get('_planned_duration_days')),
        'actual_duration_days': _optional_rounded_float(issue.get('_actual_duration_days')),
        'slippage_days': _optional_rounded_float(issue.get('_slippage_days')),
        'completion_date': _format_timestamp(issue.get('_completion_dt')),
        'age_days': round(_safe_float(issue.get('_age_days')), 2),
        'delay_days': round(_safe_float(issue.get('_delay_days')), 2),
        'is_done': bool(issue.get('_is_done', False)),
        'is_overdue': bool(issue.get('_is_overdue', False)),
        'children': []
    }

    if issue_key in active_lineage:
        return node

    active_lineage.add(issue_key)

    for child_key in children_map.get(issue_key, []):
        if child_key in issue_lookup:
            node['children'].append(
                _build_issue_tree_node(
                    issue_key=child_key,
                    issue_lookup=issue_lookup,
                    children_map=children_map,
                    lineage=active_lineage
                )
            )

    return node


def _build_epic_aggregates(
    issue_lookup: dict[str, pd.Series],
    epic_keys: list[str]
) -> dict[str, dict[str, Any]]:
    """Build hierarchy-aware aggregate metrics for each epic."""
    epic_key_set = set(epic_keys)
    root_epic_cache: dict[str, Optional[str]] = {}

    def resolve_root_epic(issue_key: str, lineage: Optional[set[str]] = None) -> Optional[str]:
        if issue_key in root_epic_cache:
            return root_epic_cache[issue_key]

        issue = issue_lookup.get(issue_key)
        if issue is None:
            root_epic_cache[issue_key] = None
            return None

        issue_type = _clean_text(issue.get('Issue Type')).lower()
        if issue_type == 'epic':
            root_epic_cache[issue_key] = issue_key
            return issue_key

        parent_key = _clean_text(issue.get('Parent'))
        if not parent_key or parent_key == issue_key or parent_key not in issue_lookup:
            root_epic_cache[issue_key] = None
            return None

        active_lineage = set(lineage or set())
        if issue_key in active_lineage:
            root_epic_cache[issue_key] = None
            return None

        active_lineage.add(issue_key)
        root_key = resolve_root_epic(parent_key, active_lineage)
        root_epic_cache[issue_key] = root_key
        return root_key

    epic_aggregates: dict[str, dict[str, Any]] = {
        epic_key: {
            'related_teams': set(),
            'related_states_norm': set(),
            'related_states_display': set(),
            'related_sprints': set(),
            'related_assignees': set(),
            'related_components': set(),
            'total_related_issues': 0,
            'total_descendants': 0,
            'done_descendants': 0,
            'open_descendants': 0,
            'overdue_descendants': 0,
            'delay_sum': 0.0,
            'delay_count': 0,
        }
        for epic_key in epic_keys
    }

    for issue_key, issue in issue_lookup.items():
        root_epic_key = resolve_root_epic(issue_key)
        if not root_epic_key or root_epic_key not in epic_key_set:
            continue

        aggregate = epic_aggregates[root_epic_key]

        team_value = _clean_text(issue.get('Team'), 'Unknown')
        if team_value:
            aggregate['related_teams'].add(team_value)

        state_value_display = _clean_text(issue.get('Status'))
        if state_value_display:
            aggregate['related_states_display'].add(state_value_display)
            aggregate['related_states_norm'].add(state_value_display.lower())

        sprint_value = _clean_text(issue.get('Sprint'))
        if sprint_value and sprint_value.upper() != 'NA':
            aggregate['related_sprints'].add(sprint_value)

        assignee_value = _clean_text(issue.get('Assignee'), 'Unassigned')
        if assignee_value:
            aggregate['related_assignees'].add(assignee_value)

        component_values = _extract_components(issue.get('Components'))
        for component_value in component_values:
            aggregate['related_components'].add(component_value)

        aggregate['total_related_issues'] += 1

        if issue_key == root_epic_key:
            continue

        aggregate['total_descendants'] += 1

        if bool(issue.get('_is_done', False)):
            aggregate['done_descendants'] += 1
        else:
            aggregate['open_descendants'] += 1

        if bool(issue.get('_is_overdue', False)):
            aggregate['overdue_descendants'] += 1

        delay_value = _safe_float(issue.get('_delay_days'))
        if delay_value > 0:
            aggregate['delay_sum'] += delay_value
            aggregate['delay_count'] += 1

    return epic_aggregates


def _to_bool_value(value: Any) -> bool:
    """Safely normalize booleans loaded from CSV."""
    if isinstance(value, bool):
        return value

    if value is None or pd.isna(value):
        return False

    return str(value).strip().lower() in {'true', '1', 'yes', 'y'}


def _load_epic_tree_epics_cache(
    output_dir: Optional[Path] = None,
    project_root_override: Optional[Path] = None
) -> pd.DataFrame:
    """Load precomputed EpicTree epics list cache."""
    target_dir = _resolve_epic_tree_output_dir(output_dir, project_root_override)
    epics_file = target_dir / 'epics.csv'
    if not epics_file.exists():
        return pd.DataFrame()

    try:
        epics_df = pd.read_csv(epics_file)
    except Exception:
        return pd.DataFrame()

    if epics_df.empty:
        return epics_df

    list_columns = [
        'related_teams',
        'related_states_norm',
        'related_states_display',
        'related_sprints',
        'related_assignees',
        'related_components',
    ]
    for column in list_columns:
        if column not in epics_df.columns:
            epics_df[column] = [[] for _ in range(len(epics_df))]
        else:
            epics_df[column] = epics_df[column].apply(_json_list_loads)

    numeric_columns = [
        'story_points',
        'total_related_issues',
        'total_descendants',
        'done_descendants',
        'open_descendants',
        'overdue_descendants',
        'avg_delay_days',
    ]
    for column in numeric_columns:
        if column not in epics_df.columns:
            epics_df[column] = 0
        epics_df[column] = pd.to_numeric(epics_df[column], errors='coerce').fillna(0)

    text_columns = [
        'epic_key', 'summary', 'status', 'priority', 'assignee', 'team', 'sprint',
        'created', 'updated', 'workspace_file'
    ]
    for column in text_columns:
        if column not in epics_df.columns:
            epics_df[column] = ''
        epics_df[column] = epics_df[column].fillna('').astype(str).str.strip()

    return epics_df


def _load_epic_workspace_cache(
    epic_key: str,
    output_dir: Optional[Path] = None,
    project_root_override: Optional[Path] = None
) -> pd.DataFrame:
    """Load precomputed per-epic workspace CSV."""
    clean_epic_key = _clean_text(epic_key)
    if not clean_epic_key:
        return pd.DataFrame()

    target_dir = _resolve_epic_tree_output_dir(output_dir, project_root_override)
    workspace_file = target_dir / _epic_workspace_file_name(clean_epic_key)
    if not workspace_file.exists():
        return pd.DataFrame()

    try:
        issue_df = pd.read_csv(workspace_file)
    except Exception:
        return pd.DataFrame()

    if issue_df.empty:
        return issue_df

    for column in EPIC_TREE_WORKSPACE_COLUMNS:
        if column not in issue_df.columns:
            issue_df[column] = ''

    text_columns = ['Issue Type', 'Key', 'Parent', 'Priority', 'Status', 'Assignee', 'Summary', 'Sprint', 'Updated', 'Created', 'Team']
    for column in text_columns:
        issue_df[column] = issue_df[column].fillna('').astype(str).str.strip()

    issue_df['Story Points'] = pd.to_numeric(issue_df['Story Points'], errors='coerce').fillna(0)
    issue_df['_delay_days'] = pd.to_numeric(issue_df['_delay_days'], errors='coerce').fillna(0)
    issue_df['_age_days'] = pd.to_numeric(issue_df['_age_days'], errors='coerce').fillna(0)
    issue_df['_planned_duration_days'] = pd.to_numeric(issue_df['_planned_duration_days'], errors='coerce')
    issue_df['_actual_duration_days'] = pd.to_numeric(issue_df['_actual_duration_days'], errors='coerce')
    issue_df['_slippage_days'] = pd.to_numeric(issue_df['_slippage_days'], errors='coerce')

    for column in ['_is_done', '_is_in_progress', '_is_todo', '_is_overdue']:
        issue_df[column] = issue_df[column].apply(_to_bool_value)

    datetime_columns = [
        '_created_dt', '_updated_dt', '_sprint_end_dt', '_completion_dt',
        '_initial_allocated_dt', '_next_transition_dt'
    ]
    for column in datetime_columns:
        issue_df[column] = pd.to_datetime(issue_df[column], errors='coerce', utc=True)

    if '_assignee_norm' not in issue_df.columns:
        issue_df['_assignee_norm'] = issue_df['Assignee'].apply(_normalize_person_name)
    else:
        issue_df['_assignee_norm'] = issue_df['_assignee_norm'].fillna('').astype(str).str.strip()

    issue_df['Assignee'] = issue_df['Assignee'].where(issue_df['Assignee'] != '', 'Unassigned')
    issue_df['Team'] = issue_df['Team'].where(issue_df['Team'] != '', 'Unknown')

    return issue_df


def generate_jira_epic_tree_cache(
    project_root: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    show_progress: bool = False
) -> dict[str, Any]:
    """Generate EpicTree cache files for list and per-epic workspace screens."""
    total_steps = 8
    _emit_epic_tree_cache_progress(1, total_steps, "Loading JIRA issue dataset", show_progress)
    issues_df = _load_jira_issue_data()

    _emit_epic_tree_cache_progress(2, total_steps, "Building hierarchy indexes and epic aggregates", show_progress)
    issue_lookup = {
        _clean_text(row['Key']): row
        for _, row in issues_df.iterrows()
        if _clean_text(row.get('Key'))
    }

    epic_keys = sorted(
        [
            issue_key
            for issue_key, issue in issue_lookup.items()
            if _clean_text(issue.get('Issue Type')).lower() == 'epic'
        ],
        key=lambda issue_key: _issue_sort_key(issue_lookup[issue_key])
    )

    children_map = _build_children_map(issue_lookup)
    epic_aggregates = _build_epic_aggregates(issue_lookup, epic_keys)

    _emit_epic_tree_cache_progress(3, total_steps, "Preparing EpicTree output folder", show_progress)
    target_dir = _resolve_epic_tree_output_dir(output_dir, project_root)
    timestamp = pd.Timestamp.now(tz='UTC').strftime('%Y%m%d_%H%M%S_%f')
    tmp_dir = target_dir.parent / f".{target_dir.name}_tmp_{timestamp}"

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    epic_rows: list[dict[str, Any]] = []
    total_epics = len(epic_keys)
    progress_interval = max(1, total_epics // 20) if total_epics > 0 else 1

    _emit_epic_tree_cache_progress(
        4,
        total_steps,
        f"Writing per-epic workspace CSV files ({total_epics} epics)",
        show_progress,
    )

    for epic_index, epic_key in enumerate(epic_keys, start=1):
        epic_issue = issue_lookup[epic_key]
        aggregate = epic_aggregates.get(epic_key, {})

        related_keys = [epic_key, *_collect_descendant_keys(epic_key, children_map)]
        related_df = issues_df[issues_df['Key'].isin(related_keys)].copy()

        for column in EPIC_TREE_WORKSPACE_COLUMNS:
            if column not in related_df.columns:
                related_df[column] = ''

        workspace_df = related_df[EPIC_TREE_WORKSPACE_COLUMNS].copy()
        datetime_columns = [
            '_created_dt', '_updated_dt', '_sprint_end_dt', '_completion_dt',
            '_initial_allocated_dt', '_next_transition_dt'
        ]
        for datetime_column in datetime_columns:
            workspace_df[datetime_column] = workspace_df[datetime_column].apply(_format_timestamp)

        workspace_file = _epic_workspace_file_name(epic_key)
        workspace_df.to_csv(tmp_dir / workspace_file, index=False)

        delay_count = int(aggregate.get('delay_count', 0))
        delay_sum = _safe_float(aggregate.get('delay_sum', 0.0))
        avg_delay_days = round(delay_sum / delay_count, 2) if delay_count > 0 else 0.0

        epic_rows.append({
            'epic_key': epic_key,
            'summary': _clean_text(epic_issue.get('Summary')),
            'status': _clean_text(epic_issue.get('Status'), 'Unknown'),
            'priority': _clean_text(epic_issue.get('Priority')),
            'assignee': _clean_text(epic_issue.get('Assignee'), 'Unassigned'),
            'team': _clean_text(epic_issue.get('Team'), 'Unknown'),
            'sprint': _clean_text(epic_issue.get('Sprint'), 'NA'),
            'story_points': round(_safe_float(epic_issue.get('Story Points')), 2),
            'created': _clean_text(epic_issue.get('Created')),
            'updated': _clean_text(epic_issue.get('Updated')),
            'total_related_issues': int(aggregate.get('total_related_issues', 0)),
            'total_descendants': int(aggregate.get('total_descendants', 0)),
            'done_descendants': int(aggregate.get('done_descendants', 0)),
            'open_descendants': int(aggregate.get('open_descendants', 0)),
            'overdue_descendants': int(aggregate.get('overdue_descendants', 0)),
            'avg_delay_days': avg_delay_days,
            'related_teams': _json_list_dumps(aggregate.get('related_teams', set())),
            'related_states_norm': _json_list_dumps(aggregate.get('related_states_norm', set())),
            'related_states_display': _json_list_dumps(aggregate.get('related_states_display', set())),
            'related_sprints': _json_list_dumps(aggregate.get('related_sprints', set())),
            'related_assignees': _json_list_dumps(aggregate.get('related_assignees', set())),
            'related_components': _json_list_dumps(aggregate.get('related_components', set())),
            'workspace_file': workspace_file,
        })

        if show_progress and (
            epic_index == 1
            or epic_index == total_epics
            or epic_index % progress_interval == 0
        ):
            loop_percent = int(round((epic_index / max(1, total_epics)) * 100))
            print(
                f"[EpicTreeCache] processing epics {loop_percent}% ({epic_index}/{total_epics}) current={epic_key}",
                flush=True,
            )

    _emit_epic_tree_cache_progress(5, total_steps, "Writing per-issue transition cache files", show_progress)
    transitions_dir = tmp_dir / 'transitions'
    transitions_dir.mkdir(parents=True, exist_ok=True)
    transition_file_count = 0
    if JIRA_HISTORY_FILE.exists():
        try:
            history_df = pd.read_csv(JIRA_HISTORY_FILE)
            required_hist_cols = {'Key', 'Field', 'ChangeDate'}
            if required_hist_cols.issubset(history_df.columns):
                history_df['Key'] = history_df['Key'].fillna('').astype(str).str.strip()
                history_df['Field'] = history_df['Field'].fillna('').astype(str).str.strip()
                history_df['FromValue'] = (
                    history_df['FromValue'].fillna('').astype(str).str.strip()
                    if 'FromValue' in history_df.columns else ''
                )
                history_df['ToValue'] = (
                    history_df['ToValue'].fillna('').astype(str).str.strip()
                    if 'ToValue' in history_df.columns else ''
                )
                history_df['ChangedBy'] = (
                    history_df['ChangedBy'].fillna('').astype(str).str.strip()
                    if 'ChangedBy' in history_df.columns else ''
                )
                history_df['ChangeDate'] = pd.to_datetime(
                    history_df['ChangeDate'], errors='coerce', utc=True
                )
                history_df = history_df.dropna(subset=['ChangeDate'])
                history_df = history_df.sort_values('ChangeDate')
                total_hist_issues = history_df['Key'].nunique()
                hist_progress_interval = max(1, total_hist_issues // 10)
                hist_index = 0
                for issue_key_raw, group in history_df.groupby('Key', sort=False):
                    issue_key_str = str(issue_key_raw).strip()
                    if not issue_key_str:
                        continue
                    transitions_list = [
                        {
                            'change_date': _format_timestamp(row.get('ChangeDate')),
                            'field': _clean_text(row.get('Field')),
                            'from_value': _clean_text(row.get('FromValue')),
                            'to_value': _clean_text(row.get('ToValue')),
                            'changed_by': _clean_text(row.get('ChangedBy')),
                        }
                        for _, row in group.iterrows()
                    ]
                    cache_file = transitions_dir / f"issue_{quote(issue_key_str, safe='')}.json"
                    cache_file.write_text(json.dumps(transitions_list), encoding='utf-8')
                    transition_file_count += 1
                    hist_index += 1
                    if show_progress and (
                        hist_index == 1
                        or hist_index == total_hist_issues
                        or hist_index % hist_progress_interval == 0
                    ):
                        hist_pct = int(round((hist_index / max(1, total_hist_issues)) * 100))
                        print(
                            f"[EpicTreeCache] transition files {hist_pct}%"
                            f" ({hist_index}/{total_hist_issues})",
                            flush=True,
                        )
        except Exception as exc:
            print(f"[EpicTreeCache] warning: could not write transition cache files: {exc}", flush=True)

    _emit_epic_tree_cache_progress(6, total_steps, "Writing epics.csv list cache", show_progress)
    epics_df = pd.DataFrame(epic_rows)
    epics_df.to_csv(tmp_dir / 'epics.csv', index=False)

    _emit_epic_tree_cache_progress(7, total_steps, "Writing metadata and publishing cache", show_progress)
    metadata = {
        'generated_at': pd.Timestamp.now(tz='UTC').isoformat(),
        'epic_count': len(epic_rows),
        'workspace_file_count': len(epic_rows),
        'transition_file_count': transition_file_count,
        'issues_source': str(JIRA_ISSUES_FILE),
        'history_source': str(JIRA_HISTORY_FILE),
        'issues_mtime': JIRA_ISSUES_FILE.stat().st_mtime if JIRA_ISSUES_FILE.exists() else 0.0,
        'history_mtime': JIRA_HISTORY_FILE.stat().st_mtime if JIRA_HISTORY_FILE.exists() else 0.0,
    }
    (tmp_dir / 'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')

    if target_dir.exists():
        shutil.rmtree(target_dir)
    tmp_dir.rename(target_dir)

    _emit_epic_tree_cache_progress(8, total_steps, "EpicTree cache generation completed", show_progress)

    return {
        **metadata,
        'output_dir': str(target_dir),
    }


@router.get("/matrix")
def get_matrix_report(
    period: str = Query("Annual", description="Period to display (Weekly, Monthly, Quarterly, Annual)"),
    kpis: Optional[str] = Query(None, description="Comma-separated list of KPIs (e.g., k3,k4,k7)"),
    sort_by: Optional[str] = Query(None, description="KPI to sort by (default: Name)"),
    team: Optional[str] = Query(None, description="Optional team filter; defaults to all accessible teams"),
    as_of_date: Optional[str] = Query(None, description="Optional date filter in YYYYMMDD format"),
    current_user: TokenData = Depends(require_report_access)
):
    """
    Get KPI matrix report data.
    
    Returns a matrix showing individuals and their KPI values.
    """
    try:
        evaluator = _create_evaluator()
        
        # Parse KPIs if provided
        kpi_list = None
        if kpis:
            kpi_list = [k.strip() for k in kpis.split(',')]
            # Validate KPIs
            invalid_kpis = [k for k in kpi_list if k not in evaluator.kpi_functions]
            if invalid_kpis:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid KPIs: {', '.join(invalid_kpis)}"
                )
        
        # Get all KPIs if not specified
        if kpi_list is None:
            kpi_list = evaluator.list_kpis()
        
        # Sort KPIs by numeric value
        kpi_list = sorted(kpi_list, key=lambda x: int(x[1:]))
        
        # Read data for all KPIs
        all_data = {}
        for kpi in kpi_list:
            all_data[kpi] = evaluator.read_kpi_data(kpi, period, as_of_date)

        # Source of truth for who appears in the matrix is Resources.csv (by SAPID).
        # all_data is only used for value lookups — never as the list of individuals.
        employee_team_map, sapid_name_map, norm_name_to_sapid, employees, all_teams = _load_employee_team_map()
        if not employees:
            raise HTTPException(
                status_code=404,
                detail="No employee data found in Resources.csv"
            )

        accessible_sapids, available_teams = _get_accessible_matrix_scope(
            current_user=current_user,
            employee_team_map=employee_team_map,
            all_teams=all_teams
        )
        team_filter = _clean_text(team)
        visible_team_set: set[str] = set()

        matrix_data = []
        for sapid, display_name, individual_team in employees:
            if accessible_sapids is not None and sapid not in accessible_sapids:
                continue

            if team_filter and individual_team != team_filter:
                continue

            if individual_team:
                visible_team_set.add(individual_team)

            row: dict = {'name': display_name, 'sapid': sapid, 'team': individual_team}
            norm_display = _normalize_person_name(display_name)
            # Name is unambiguous only when it maps to exactly this SAPID.
            # Ambiguous names (two people with identical name) never use name fallback
            # because we cannot tell which KPI row belongs to which person.
            name_is_unique = norm_name_to_sapid.get(norm_display) == sapid

            for kpi in kpi_list:
                kpi_values = all_data[kpi]
                # Modern KPI files: keyed by SAPID
                value = kpi_values.get(sapid)
                if value is None and name_is_unique:
                    # Older KPI files without SAPID column: key is the name as written
                    # in the KPI CSV. Match case-insensitively against display name.
                    for k, v in kpi_values.items():
                        if _normalize_person_name(k) == norm_display:
                            value = v
                            break
                row[kpi] = value if value is not None else 0
            matrix_data.append(row)
        
        # Sort the matrix
        if sort_by is None or sort_by.lower() == 'name':
            matrix_data.sort(key=lambda x: x['name'])
        elif sort_by in kpi_list:
            matrix_data.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
        else:
            # Invalid sort_by, default to name
            matrix_data.sort(key=lambda x: x['name'])

        # Build KPI metadata for colors and tooltips
        roles_df = roles_service.load_data().copy()
        roles_df['Index'] = roles_df['Index'].fillna('').astype(str).str.strip()
        period_target_col_map = {
            'Weekly': 'Weekly Target',
            'Monthly': 'Weekly Target',  # No Monthly column - approximate with Weekly
            'Quarterly': 'Quarterly Target',
            'Annual': 'Annual Target',
        }
        target_col = period_target_col_map.get(period, 'Annual Target')
        ref_date = parse_ref_date(as_of_date)
        kpi_meta: dict = {}
        for kpi in kpi_list:
            kpi_rows = roles_df[roles_df['Index'] == kpi]
            if kpi_rows.empty:
                base_kpi = evaluator.get_base_kpi(kpi)
                kpi_rows = roles_df[roles_df['Index'] == base_kpi]
            if kpi_rows.empty:
                kpi_meta[kpi] = None
                continue
            row = kpi_rows.iloc[0]
            type_code = str(row.get('Type', 'NG')).upper() if pd.notna(row.get('Type')) else 'NG'
            goal_direction = 'Minimize' if 'L' in type_code else 'Maximize'
            raw_target = row.get(target_col, 0)
            target_val = _safe_float(raw_target, default=0.0)
            prorate = str(row.get('Prorate', 'Yes')).strip().lower() != 'no'
            prorated_target_val = get_prorated_target(target_val, period, ref_date, prorate=prorate)
            kpi_meta[kpi] = {
                'kpp_goals': str(row.get('KPP Goals', '')) if pd.notna(row.get('KPP Goals')) else '',
                'measurement_criteria': str(row.get('Measurement Criteria', '')) if pd.notna(row.get('Measurement Criteria')) else '',
                'tool': str(row.get('Tool', '')) if pd.notna(row.get('Tool')) else '',
                'measure': str(row.get('Measure', '')) if pd.notna(row.get('Measure')) else '',
                'type_code': type_code,
                'goal_direction': goal_direction,
                'goal_type_category': str(row.get('Goal Type', 'Input')) if pd.notna(row.get('Goal Type')) else 'Input',
                'target': target_val,
                'prorated_target': prorated_target_val,
                'prorate': prorate,
                'weekly_target': _safe_float(row.get('Weekly Target', 0), default=0.0),
                'quarterly_target': _safe_float(row.get('Quarterly Target', 0), default=0.0),
                'annual_target': _safe_float(row.get('Annual Target', 0), default=0.0),
            }

        return {
            "success": True,
            "data": matrix_data,
            "kpis": kpi_list,
            "kpi_meta": kpi_meta,
            "period": period,
            "as_of_date": as_of_date,
            "sort_by": sort_by or "name",
            "applied_team": team_filter,
            "available_teams": available_teams if accessible_sapids is None else sorted(visible_team_set),
            "total_individuals": len(matrix_data),
            "total_kpis": len(kpi_list)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/employee-score-comparison")
def get_employee_score_comparison_report(
    team: Optional[str] = Query(None, description="Optional team filter"),
    scrum: Optional[str] = Query(None, description="Optional scrum filter"),
    primary_role: Optional[str] = Query(None, description="Optional primary role filter"),
    secondary_role: Optional[str] = Query(None, description="Optional secondary role filter"),
    as_of_date: Optional[str] = Query(None, description="Optional date filter in YYYYMMDD format"),
    current_user: TokenData = Depends(require_report_access),
):
    """Return Weekly/Quarterly/Annual employee scores from output snapshot data."""
    try:
        snapshot_file = _ensure_employee_score_snapshot_file(as_of_date)

        df = pd.read_csv(snapshot_file)
        expected_columns = {
            'Name', 'SAPID', 'Team', 'Scrum', 'PrimaryRole', 'SecondaryRole',
            'Weekly_Overall', 'Weekly_Input', 'Weekly_Output', 'Weekly_Quality', 'Weekly_Hygiene',
            'Quarterly_Overall', 'Quarterly_Input', 'Quarterly_Output', 'Quarterly_Quality', 'Quarterly_Hygiene',
            'Annual_Overall', 'Annual_Input', 'Annual_Output', 'Annual_Quality', 'Annual_Hygiene',
        }
        missing_columns = [column for column in expected_columns if column not in df.columns]
        if missing_columns:
            raise HTTPException(
                status_code=500,
                detail=f"Employee score snapshot is missing columns: {', '.join(sorted(missing_columns))}",
            )

        df['SAPID'] = df['SAPID'].apply(_clean_sapid)
        df['Name'] = df['Name'].apply(_clean_text)
        df['Team'] = df['Team'].apply(_clean_text)
        df['Scrum'] = df['Scrum'].apply(_clean_text)
        df['PrimaryRole'] = df['PrimaryRole'].apply(_clean_text)
        df['SecondaryRole'] = df['SecondaryRole'].apply(_clean_text)

        employee_team_map, _, _, _, all_teams = _load_employee_team_map()
        accessible_sapids, _ = _get_accessible_matrix_scope(
            current_user=current_user,
            employee_team_map=employee_team_map,
            all_teams=all_teams,
        )

        if accessible_sapids is not None:
            df = df[df['SAPID'].isin(accessible_sapids)].copy()

        available_filters = {
            'teams': sorted({value for value in df['Team'].tolist() if value}),
            'scrums': sorted({value for value in df['Scrum'].tolist() if value}),
            'primary_roles': sorted({value for value in df['PrimaryRole'].tolist() if value}),
            'secondary_roles': sorted({value for value in df['SecondaryRole'].tolist() if value}),
        }

        team_filter = _clean_text(team)
        scrum_filter = _clean_text(scrum)
        primary_filter = _clean_text(primary_role)
        secondary_filter = _clean_text(secondary_role)

        if team_filter:
            df = df[df['Team'] == team_filter]
        if scrum_filter:
            df = df[df['Scrum'] == scrum_filter]
        if primary_filter:
            df = df[df['PrimaryRole'] == primary_filter]
        if secondary_filter:
            df = df[df['SecondaryRole'] == secondary_filter]

        rows = []
        for _, row in df.iterrows():
            rows.append({
                'name': _clean_text(row.get('Name')),
                'sapid': _clean_sapid(row.get('SAPID')),
                'team': _clean_text(row.get('Team')),
                'scrum': _clean_text(row.get('Scrum')),
                'primary_role': _clean_text(row.get('PrimaryRole')),
                'secondary_role': _clean_text(row.get('SecondaryRole')),
                'scores': {
                    'Weekly': {
                        'overall': round(_as_float(row.get('Weekly_Overall')), 2),
                        'input': round(_as_float(row.get('Weekly_Input')), 2),
                        'output': round(_as_float(row.get('Weekly_Output')), 2),
                        'quality': round(_as_float(row.get('Weekly_Quality')), 2),
                        'hygiene': round(_as_float(row.get('Weekly_Hygiene')), 2),
                    },
                    'Quarterly': {
                        'overall': round(_as_float(row.get('Quarterly_Overall')), 2),
                        'input': round(_as_float(row.get('Quarterly_Input')), 2),
                        'output': round(_as_float(row.get('Quarterly_Output')), 2),
                        'quality': round(_as_float(row.get('Quarterly_Quality')), 2),
                        'hygiene': round(_as_float(row.get('Quarterly_Hygiene')), 2),
                    },
                    'Annual': {
                        'overall': round(_as_float(row.get('Annual_Overall')), 2),
                        'input': round(_as_float(row.get('Annual_Input')), 2),
                        'output': round(_as_float(row.get('Annual_Output')), 2),
                        'quality': round(_as_float(row.get('Annual_Quality')), 2),
                        'hygiene': round(_as_float(row.get('Annual_Hygiene')), 2),
                    },
                },
            })

        rows.sort(key=lambda item: (item['name'].lower(), item['sapid']))

        scoring_config = get_scoring_service().get_config()
        display_thresholds = scoring_config.get('score_display_thresholds', {
            'green_min': 70.0,
            'orange_min': 36.0,
            'red_max': 35.0,
        })
        category_weightages_raw = scoring_config.get('weightages', {})
        category_weightages = {
            'input': _as_float(category_weightages_raw.get('Input', 10.0), default=10.0),
            'output': _as_float(category_weightages_raw.get('Output', 50.0), default=50.0),
            'quality': _as_float(category_weightages_raw.get('Quality', 30.0), default=30.0),
            'hygiene': _as_float(category_weightages_raw.get('Hygiene', 10.0), default=10.0),
        }

        return {
            "success": True,
            "data": rows,
            "available_filters": available_filters,
            "applied_filters": {
                'team': team_filter,
                'scrum': scrum_filter,
                'primary_role': primary_filter,
                'secondary_role': secondary_filter,
            },
            "as_of_date": _resolve_snapshot_day(as_of_date),
            "score_display_thresholds": {
                'green_min': _as_float(display_thresholds.get('green_min', 70.0), default=70.0),
                'orange_min': _as_float(display_thresholds.get('orange_min', 36.0), default=36.0),
                'red_max': _as_float(display_thresholds.get('red_max', 35.0), default=35.0),
            },
            "category_weightages": category_weightages,
            "snapshot_file": str(snapshot_file),
            "total_employees": len(rows),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _load_git_activity_cache() -> Optional[dict[str, Any]]:
    """Load pre-computed Git Activity cache from latest file if available."""
    if not GIT_ACTIVITY_CACHE_LATEST_FILE.exists():
        return None
    
    try:
        cache_data = json.loads(GIT_ACTIVITY_CACHE_LATEST_FILE.read_text(encoding='utf-8'))
        if not isinstance(cache_data, dict):
            _logger.warning("Git Activity cache file is not a JSON object: %s", GIT_ACTIVITY_CACHE_LATEST_FILE)
            return None
        _logger.debug("Loaded Git Activity cache: %s", GIT_ACTIVITY_CACHE_LATEST_FILE)
        return cache_data
    except Exception as e:
        _logger.warning("Failed to load Git Activity cache: %s", e)
        return None


def _get_git_activity_cache_entry(
    cache_data: dict[str, Any],
    selected_month: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Return a month-scoped cache payload from either legacy or month-indexed format."""
    if not isinstance(cache_data, dict):
        return None

    requested_month = _clean_text(selected_month)

    # New format: envelope with per-month payloads.
    months_payload = cache_data.get('months')
    if isinstance(months_payload, dict):
        if requested_month:
            candidate = months_payload.get(requested_month)
            return candidate if isinstance(candidate, dict) else None

        latest_month = _clean_text(cache_data.get('latest_month'))
        if latest_month:
            latest_payload = months_payload.get(latest_month)
            if isinstance(latest_payload, dict):
                return latest_payload

        for candidate in months_payload.values():
            if isinstance(candidate, dict):
                return candidate
        return None

    # Legacy format: single month payload at root.
    root_month = _clean_text(cache_data.get('selected_month'))
    if not root_month:
        return None
    if requested_month and requested_month != root_month:
        return None
    return cache_data


def _extract_git_activity_cache_months(cache_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return a normalized month->payload map from cache envelope or legacy payload."""
    if not isinstance(cache_data, dict):
        return {}

    months_payload = cache_data.get('months')
    if isinstance(months_payload, dict):
        month_map: dict[str, dict[str, Any]] = {}
        for month_key, payload in months_payload.items():
            clean_month = _clean_text(month_key)
            if clean_month and isinstance(payload, dict):
                month_map[clean_month] = payload
        return month_map

    legacy_month = _clean_text(cache_data.get('selected_month'))
    if legacy_month:
        return {legacy_month: cache_data}
    return {}


def _persist_git_activity_cache_entry(cache_entry: dict[str, Any]) -> bool:
    """Persist a month cache payload to dated cache file and month-indexed latest cache."""
    if not isinstance(cache_entry, dict):
        return False

    selected_month = _clean_text(cache_entry.get('selected_month'))
    if not selected_month:
        return False

    try:
        output_dir = GIT_ACTIVITY_CACHE_LATEST_FILE.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        dated_cache_file = output_dir / f"git_activity_cache_{selected_month.replace('-', '')}.json"
        dated_cache_file.write_text(json.dumps(cache_entry, indent=2), encoding='utf-8')

        existing_cache_data = _load_git_activity_cache() or {}
        month_map = _extract_git_activity_cache_months(existing_cache_data)
        month_map[selected_month] = cache_entry

        envelope = {
            'cache_version': 5,
            'latest_month': selected_month,
            'months': dict(sorted(month_map.items(), reverse=True)),
            'metadata': {
                'updated_at': datetime.now().isoformat(),
                'month_count': len(month_map),
            },
        }
        GIT_ACTIVITY_CACHE_LATEST_FILE.write_text(json.dumps(envelope, indent=2), encoding='utf-8')
        return True
    except Exception as exc:
        _logger.warning("Failed to persist Git Activity month cache for %s: %s", selected_month, exc)
        return False


def _generate_git_activity_cache_for_month(selected_month: str) -> Optional[dict[str, Any]]:
    """Generate and persist Git Activity cache for a requested month on cache miss."""
    if not selected_month:
        return None

    try:
        from git_activity_cache_job import generate_git_activity_cache

        generated_cache = generate_git_activity_cache(project_root, month=selected_month)
        if not isinstance(generated_cache, dict):
            return None

        _persist_git_activity_cache_entry(generated_cache)
        _logger.info("Generated Git Activity cache on-demand for month %s", selected_month)
        return generated_cache
    except Exception as exc:
        _logger.warning("Failed to generate Git Activity cache for month %s: %s", selected_month, exc)
        return None


def _get_cached_git_activity_employee_details(
    cache_data: dict[str, Any],
    selected_month: str,
    requested_sapid: str,
    requested_email: str,
) -> Optional[dict[str, Any]]:
    """Resolve month-level employee commit details from git activity cache."""
    if not isinstance(cache_data, dict):
        return None

    cache_month = _clean_text(cache_data.get('selected_month'))
    if cache_month != selected_month:
        return None

    details_cache = cache_data.get('employee_details_cache')
    if not isinstance(details_cache, dict):
        return None

    if _clean_text(details_cache.get('selected_month')) != selected_month:
        return None

    index = details_cache.get('index') if isinstance(details_cache.get('index'), dict) else {}
    by_sapid = index.get('by_sapid') if isinstance(index.get('by_sapid'), dict) else {}
    by_email = index.get('by_author_email') if isinstance(index.get('by_author_email'), dict) else {}
    people = details_cache.get('people') if isinstance(details_cache.get('people'), dict) else {}

    person_key = ''
    if requested_sapid:
        person_key = _clean_text(by_sapid.get(requested_sapid))
    if not person_key and requested_email:
        person_key = _clean_text(by_email.get(requested_email.lower()))
    if not person_key:
        return None

    payload = people.get(person_key)
    if not isinstance(payload, dict):
        return None

    person = payload.get('person') if isinstance(payload.get('person'), dict) else {}
    summary = payload.get('summary') if isinstance(payload.get('summary'), dict) else {}
    commits = payload.get('commits') if isinstance(payload.get('commits'), list) else []

    return {
        'person': {
            'name': _clean_text(person.get('name')),
            'sapid': _clean_sapid(person.get('sapid')),
            'author_email': _clean_text(person.get('author_email')).lower(),
            'team': _clean_text(person.get('team')),
            'scrum': _clean_text(person.get('scrum')),
        },
        'summary': {
            'total_commits': int(_as_float(summary.get('total_commits'))),
            'merge_commits': int(_as_float(summary.get('merge_commits'))),
            'non_merge_commits': int(_as_float(summary.get('non_merge_commits'))),
            'total_lines_changed': int(_as_float(summary.get('total_lines_changed'))),
            'total_files_changed': int(_as_float(summary.get('total_files_changed'))),
        },
        'commits': [item for item in commits if isinstance(item, dict)],
    }


def _get_git_activity_cache_people_lookup(cache_entry: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    details_cache = cache_entry.get('employee_details_cache') if isinstance(cache_entry.get('employee_details_cache'), dict) else {}
    index = details_cache.get('index') if isinstance(details_cache.get('index'), dict) else {}
    people = details_cache.get('people') if isinstance(details_cache.get('people'), dict) else {}
    by_sapid = index.get('by_sapid') if isinstance(index.get('by_sapid'), dict) else {}
    by_email = index.get('by_author_email') if isinstance(index.get('by_author_email'), dict) else {}

    people_by_sapid: dict[str, dict[str, Any]] = {}
    for sapid_key, person_key in by_sapid.items():
        payload = people.get(_clean_text(person_key))
        if isinstance(payload, dict):
            people_by_sapid[_clean_sapid(sapid_key)] = payload

    people_by_email: dict[str, dict[str, Any]] = {}
    for email_key, person_key in by_email.items():
        payload = people.get(_clean_text(person_key))
        if isinstance(payload, dict):
            people_by_email[_clean_text(email_key).lower()] = payload

    return people_by_sapid, people_by_email


def _project_git_activity_cached_rows(
    cache_entry: dict[str, Any],
    team: str,
    scrum: str,
    activity_type: str,
    employee_scope: str,
    current_user: TokenData,
) -> tuple[list[dict[str, Any]], str]:
    employee_team_map, _, _, _, all_teams = _load_employee_team_map()
    accessible_sapids, _ = _get_accessible_matrix_scope(
        current_user=current_user,
        employee_team_map=employee_team_map,
        all_teams=all_teams,
    )
    team_manager_team_scope = {
        _clean_text(team_id)
        for team_id in (current_user.team_ids or [])
        if _clean_text(team_id)
    } if current_user.role == "Team Manager" else set()

    base_data = cache_entry.get('data') if isinstance(cache_entry.get('data'), list) else []
    scoped_rows: list[dict[str, Any]] = []
    if team_manager_team_scope:
        for row in base_data:
            if not isinstance(row, dict):
                continue
            row_team = _clean_text(row.get('team'))
            if row_team and row_team in team_manager_team_scope:
                scoped_rows.append(row)
    elif accessible_sapids is not None:
        for row in base_data:
            if not isinstance(row, dict):
                continue
            row_sapid = _clean_sapid(row.get('sapid'))
            if row_sapid and row_sapid in accessible_sapids:
                scoped_rows.append(row)
    else:
        scoped_rows = [row for row in base_data if isinstance(row, dict)]

    filtered_rows = scoped_rows
    if team:
        filtered_rows = [row for row in filtered_rows if _clean_text(row.get('team')) == team]
    if scrum:
        filtered_rows = [row for row in filtered_rows if _clean_text(row.get('scrum')) == scrum]

    projected_rows: list[dict[str, Any]] = []
    for row in filtered_rows:
        activity_metrics = row.get('activity_metrics') if isinstance(row.get('activity_metrics'), dict) else {}
        selected_metric = activity_metrics.get(activity_type) if isinstance(activity_metrics.get(activity_type), dict) else {}
        projected_rows.append({
            **row,
            'daily_counts': selected_metric.get('daily_counts', {}),
            'metric_total': int(_as_float(selected_metric.get('metric_total'))),
        })

    if employee_scope == 'active':
        projected_rows = [row for row in projected_rows if int(_as_float(row.get('metric_total'))) > 0]
    elif employee_scope == 'inactive':
        projected_rows = [row for row in projected_rows if int(_as_float(row.get('metric_total'))) <= 0]

    projected_rows.sort(
        key=lambda item: (
            _clean_text(item.get('name')).lower(),
            _clean_text(item.get('team')).lower(),
            _clean_text(item.get('scrum')).lower(),
            _clean_text(item.get('author_email')).lower(),
        )
    )
    return projected_rows, _clean_text(cache_entry.get('selected_month'))


def _write_git_activity_detail_export_csv(
    file_path: Path,
    cache_entry: dict[str, Any],
    projected_rows: list[dict[str, Any]],
    team: str,
    scrum: str,
    activity_type: str,
    employee_scope: str,
    metric_label: str,
    job_id: str,
) -> int:
    headers = [
        'report_month',
        'selected_team',
        'selected_scrum',
        'employee_scope',
        'activity_type',
        'metric_label',
        'employee_name',
        'employee_sapid',
        'employee_email',
        'employee_team',
        'employee_scrum',
        'employee_metric_total',
        'employee_total_commits',
        'employee_merge_commits',
        'employee_non_merge_commits',
        'employee_total_lines_changed',
        'employee_total_files_changed',
        'commit_date',
        'commit_type',
        'commit_sha',
        'repository',
        'jira_id',
        'pr_number',
        'approver',
        'review_comments',
        'files_changed',
        'lines_added',
        'lines_deleted',
        'lines_changed',
        'message',
    ]
    people_by_sapid, people_by_email = _get_git_activity_cache_people_lookup(cache_entry)
    selected_month = _clean_text(cache_entry.get('selected_month'))
    total_people = len(projected_rows)
    rows_written = 0

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)

        for index, person_row in enumerate(projected_rows, start=1):
            person_payload = None
            person_sapid = _clean_sapid(person_row.get('sapid'))
            person_email = _clean_text(person_row.get('author_email')).lower()
            if person_sapid:
                person_payload = people_by_sapid.get(person_sapid)
            if person_payload is None and person_email:
                person_payload = people_by_email.get(person_email)

            person = person_payload.get('person') if isinstance((person_payload or {}).get('person'), dict) else {}
            summary = person_payload.get('summary') if isinstance((person_payload or {}).get('summary'), dict) else {}
            commits = person_payload.get('commits') if isinstance((person_payload or {}).get('commits'), list) else []

            base_columns = [
                selected_month,
                team,
                scrum,
                employee_scope,
                activity_type,
                metric_label,
                _clean_text(person.get('name')) or _clean_text(person_row.get('name')),
                _clean_sapid(person.get('sapid')) or person_sapid,
                _clean_text(person.get('author_email')).lower() or person_email,
                _clean_text(person.get('team')) or _clean_text(person_row.get('team')),
                _clean_text(person.get('scrum')) or _clean_text(person_row.get('scrum')),
                int(_as_float(person_row.get('metric_total'))),
                int(_as_float(summary.get('total_commits'))),
                int(_as_float(summary.get('merge_commits'))),
                int(_as_float(summary.get('non_merge_commits'))),
                int(_as_float(summary.get('total_lines_changed'))),
                int(_as_float(summary.get('total_files_changed'))),
            ]

            if not commits:
                writer.writerow([*base_columns, '', '', '', '', '', '', '', '', '', '', '', '', ''])
                rows_written += 1
            else:
                for commit in commits:
                    if not isinstance(commit, dict):
                        continue
                    writer.writerow([
                        *base_columns,
                        _clean_text(commit.get('date')),
                        'MERGE' if bool(commit.get('is_merge')) else 'COMMIT',
                        _clean_text(commit.get('commit_sha')),
                        _clean_text(commit.get('repository')),
                        _clean_text(commit.get('jira_id')),
                        _clean_text(commit.get('pr_number')),
                        _clean_text(commit.get('approver')),
                        int(_as_float(commit.get('review_comments'))),
                        int(_as_float(commit.get('files_changed'))),
                        int(_as_float(commit.get('lines_added'))),
                        int(_as_float(commit.get('lines_deleted'))),
                        int(_as_float(commit.get('lines_changed'))),
                        _clean_text(commit.get('message')),
                    ])
                    rows_written += 1

            progress_percent = 55 if total_people <= 0 else min(95, 55 + int((index / total_people) * 40))
            _update_git_activity_detail_export_job(
                job_id,
                progress_percent=progress_percent,
                current_step=f'Writing employee rows ({index}/{total_people})',
                message=f'Writing detailed CSV for {index} of {total_people} employees',
                rows_written=rows_written,
            )

    return rows_written


def _run_git_activity_detail_export_job(
    job_id: str,
    user_key: str,
    current_user: TokenData,
    month: str,
    team: str,
    scrum: str,
    activity_type: str,
    employee_scope: str,
) -> None:
    try:
        _update_git_activity_detail_export_job(
            job_id,
            status='running',
            progress_percent=10,
            current_step='Loading Git Activity cache',
            message='Loading month cache for detailed export',
        )

        cache_data = _load_git_activity_cache() or {}
        cache_entry = _get_git_activity_cache_entry(cache_data, month)
        if not cache_entry:
            _update_git_activity_detail_export_job(
                job_id,
                progress_percent=25,
                current_step='Generating month cache',
                message=f'Generating Git Activity cache for {month}',
            )
            cache_entry = _generate_git_activity_cache_for_month(month)

        if not isinstance(cache_entry, dict):
            raise ValueError(f'Unable to build Git Activity cache for month {month}')

        projected_rows, selected_month = _project_git_activity_cached_rows(
            cache_entry=cache_entry,
            team=team,
            scrum=scrum,
            activity_type=activity_type,
            employee_scope=employee_scope,
            current_user=current_user,
        )

        _update_git_activity_detail_export_job(
            job_id,
            progress_percent=45,
            current_step='Preparing CSV file',
            message=f'Preparing detailed CSV for {len(projected_rows)} employees',
            selected_month=selected_month or month,
        )

        export_filename = (
            f'git-activity-{(selected_month or month).replace("/", "-")}-'
            f'{re.sub(r"[^A-Za-z0-9]+", "-", team).strip("-").lower() or "team"}-'
            f'{activity_type}-details.csv'
        )
        export_file_path = GIT_ACTIVITY_EXPORTS_DIR / f'{job_id}-{export_filename}'
        rows_written = _write_git_activity_detail_export_csv(
            file_path=export_file_path,
            cache_entry=cache_entry,
            projected_rows=projected_rows,
            team=team,
            scrum=scrum,
            activity_type=activity_type,
            employee_scope=employee_scope,
            metric_label=_git_activity_metric_label(activity_type),
            job_id=job_id,
        )

        _update_git_activity_detail_export_job(
            job_id,
            status='completed',
            progress_percent=100,
            current_step='Completed',
            message=f'Detailed CSV is ready with {rows_written} rows',
            completed_at=datetime.now().isoformat(),
            download_ready=True,
            download_filename=export_filename,
            file_path=str(export_file_path),
            rows_written=rows_written,
        )
    except Exception as exc:
        _logger.exception('Git Activity detailed export failed for job %s', job_id)
        _update_git_activity_detail_export_job(
            job_id,
            status='failed',
            progress_percent=100,
            current_step='Failed',
            message='Detailed CSV export failed',
            completed_at=datetime.now().isoformat(),
            error_message=str(exc),
            download_ready=False,
        )
    finally:
        with _git_activity_detail_export_lock:
            active_job_id = _git_activity_detail_export_active_by_user.get(user_key)
            if active_job_id == job_id:
                _git_activity_detail_export_active_by_user.pop(user_key, None)


@router.get("/git-activity")
def get_git_activity_report(
    month: Optional[str] = Query(None, description="Month in YYYY-MM; defaults to latest available month"),
    team: Optional[str] = Query(None, description="Optional team filter"),
    scrum: Optional[str] = Query(None, description="Optional scrum filter"),
    activity_type: str = Query("total_commits", description="total_commits|merges|commits|lines_added|lines_deleted|lines_changed|files_changed|repos_touched"),
    employee_scope: str = Query("active", description="active|inactive|all"),
    force_refresh: bool = Query(False, description="Force recompute instead of using cache"),
    current_user: TokenData = Depends(require_report_access),
):
    """Monthly Git activity summary per person from output/github_commits.csv.

    Includes both GitHub and GitLab records because both are collected into the
    same shared commits dataset.
    
    Uses pre-computed cache by default for faster response times. Set force_refresh=true
    to bypass cache and recompute with latest data.
    """
    try:
        cache_used = False
        scoring_config = get_scoring_service().get_config()
        display_thresholds = scoring_config.get('score_display_thresholds', {
            'green_min': 70.0,
            'orange_min': 36.0,
            'red_max': 35.0,
        })
        normalized_activity_type = _clean_text(activity_type).lower() or 'total_commits'
        if normalized_activity_type == 'all':
            normalized_activity_type = 'total_commits'
        if normalized_activity_type not in {
            'total_commits',
            'merges',
            'commits',
            'lines_added',
            'lines_deleted',
            'lines_changed',
            'files_changed',
            'repos_touched',
        }:
            raise HTTPException(
                status_code=400,
                detail=(
                    "activity_type must be one of: total_commits, merges, commits, "
                    "lines_added, lines_deleted, lines_changed, files_changed, repos_touched"
                )
            )

        normalized_employee_scope = _clean_text(employee_scope).lower() or 'active'
        if normalized_employee_scope not in {'active', 'inactive', 'all'}:
            raise HTTPException(status_code=400, detail="employee_scope must be one of: active, inactive, all")

        employee_team_map, sapid_name_map, norm_name_to_sapid, _, all_teams = _load_employee_team_map()
        accessible_sapids, accessible_teams = _get_accessible_matrix_scope(
            current_user=current_user,
            employee_team_map=employee_team_map,
            all_teams=all_teams,
        )
        accessible_team_set = set(accessible_teams)
        team_manager_team_scope = {
            _clean_text(team_id)
            for team_id in (current_user.team_ids or [])
            if _clean_text(team_id)
        } if current_user.role == "Team Manager" else set()

        # Try to use cache first unless force_refresh is requested
        if not force_refresh:
            cache_data = _load_git_activity_cache()
            cache_entry = _get_git_activity_cache_entry(cache_data or {}, month)
            requested_month = _clean_text(month)

            if not cache_entry and requested_month:
                # On cache miss for an explicitly requested month, build and persist cache now.
                cache_entry = _generate_git_activity_cache_for_month(requested_month)

            if cache_entry:
                # Cache exists, use it as the base and apply filters
                base_data = cache_entry['data']
                base_date_columns = cache_entry['date_columns']
                base_available_months = cache_entry['available_months']
                base_selected_month = cache_entry['selected_month']
                base_available_filters = cache_entry.get('available_filters', {'teams': [], 'scrums': []})
                cached_month = base_selected_month

                # If user requested a specific month, only use cache if it matches
                if month and month != cached_month:
                    _logger.info("Requested month %s != cached month %s, will recompute", month, cached_month)
                else:
                    cache_used = True
                    # Apply RBAC scope first for non-admin users using SAPID-only matching.
                    if team_manager_team_scope:
                        scoped_rows = []
                        for row in base_data:
                            row_team = _clean_text((row or {}).get('team'))
                            if row_team and row_team in team_manager_team_scope:
                                scoped_rows.append(row)
                        filtered_rows = scoped_rows
                    elif accessible_sapids is not None:
                        scoped_rows = []
                        for row in base_data:
                            row_sapid = _clean_sapid((row or {}).get('sapid'))
                            if row_sapid and row_sapid in accessible_sapids:
                                scoped_rows.append(row)
                        filtered_rows = scoped_rows
                    else:
                        filtered_rows = base_data

                    # Apply user filters to scoped cached data.
                    team_filter = _clean_text(team)
                    scrum_filter = _clean_text(scrum)
                    if team_filter:
                        filtered_rows = [r for r in filtered_rows if r['team'] == team_filter]
                    if scrum_filter:
                        filtered_rows = [r for r in filtered_rows if r['scrum'] == scrum_filter]

                    projected_rows = []
                    for row in filtered_rows:
                        activity_metrics = row.get('activity_metrics')
                        if not isinstance(activity_metrics, dict) or normalized_activity_type not in activity_metrics:
                            raise HTTPException(
                                status_code=500,
                                detail=(
                                    "Git Activity cache schema missing activity metrics; "
                                    "run git_activity_cache job to regenerate cache"
                                ),
                            )

                        selected_metric = activity_metrics.get(normalized_activity_type) or {}
                        projected_rows.append({
                            **row,
                            'daily_counts': selected_metric.get('daily_counts', {}),
                            'metric_total': int(selected_metric.get('metric_total', 0)),
                        })

                    # Filter by employee activity status based on selected metric.
                    if normalized_employee_scope == 'active':
                        projected_rows = [r for r in projected_rows if r['metric_total'] > 0]
                    elif normalized_employee_scope == 'inactive':
                        projected_rows = [r for r in projected_rows if r['metric_total'] <= 0]

                    cached_summary = cache_entry.get('summary', {}) if isinstance(cache_entry.get('summary'), dict) else {}
                    cached_scorecard = cached_summary.get('git_activity_scorecard', {}) if isinstance(cached_summary.get('git_activity_scorecard'), dict) else {}
                    scorecard = _summarize_cached_git_activity_scorecard(
                        rows=projected_rows,
                        selected_month=base_selected_month,
                        baseline_months=cached_scorecard.get('baseline_months', []),
                    )

                    metric_total = sum(r.get('metric_total', 0) for r in projected_rows)

                    available_filters = {
                        'teams': sorted({r.get('team', '') for r in filtered_rows if _clean_text(r.get('team'))}),
                        'scrums': sorted({r.get('scrum', '') for r in filtered_rows if _clean_text(r.get('scrum'))}),
                    }
                    if accessible_sapids is None:
                        available_filters = base_available_filters
                    else:
                        available_filters['teams'] = sorted(set(available_filters['teams']) | accessible_team_set)

                    return {
                        'success': True,
                        'data': projected_rows,
                        'date_columns': base_date_columns,
                        'metric_label': _git_activity_metric_label(normalized_activity_type),
                        'summary': {
                            'total_rows': len(projected_rows),
                            'metric_total': metric_total,
                            'git_activity_scorecard': scorecard,
                        },
                        'available_months': base_available_months,
                        'selected_month': base_selected_month,
                        'score_display_thresholds': {
                            'green_min': _as_float(display_thresholds.get('green_min', 70.0), default=70.0),
                            'orange_min': _as_float(display_thresholds.get('orange_min', 36.0), default=36.0),
                            'red_max': _as_float(display_thresholds.get('red_max', 35.0), default=35.0),
                        },
                        'available_filters': available_filters,
                        'applied_filters': {
                            'month': base_selected_month,
                            'team': team_filter,
                            'scrum': scrum_filter,
                            'activity_type': normalized_activity_type,
                            'employee_scope': normalized_employee_scope,
                        },
                        '_cache_used': cache_used,
                    }

        commits_file = project_root / 'output' / 'github_commits.csv'
        if not commits_file.exists():
            raise HTTPException(status_code=404, detail="github_commits.csv not found")

        try:
            commits_df = pd.read_csv(commits_file)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read github_commits.csv: {exc}")

        required_columns = {'date', 'author', 'author_email', 'repository', 'message'}
        missing = [column for column in required_columns if column not in commits_df.columns]
        if missing:
            raise HTTPException(
                status_code=500,
                detail=f"github_commits.csv missing required columns: {', '.join(sorted(missing))}"
            )

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
            resolved_primary_role = _clean_text(resolved.get('primary_role'))
            resolved_secondary_role = _clean_text(resolved.get('secondary_role'))

            if not resolved_sapid:
                mapped_sapid = norm_name_to_sapid.get(_normalize_person_name(author_name), '')
                if mapped_sapid:
                    resolved_sapid = mapped_sapid
                    resolved_name = sapid_name_map.get(mapped_sapid, resolved_name)
                    resolved_team = employee_team_map.get(mapped_sapid, resolved_team)

            if team_manager_team_scope:
                if not (resolved_team and resolved_team in team_manager_team_scope):
                    continue
            elif accessible_sapids is not None:
                if not (resolved_sapid and resolved_sapid in accessible_sapids):
                    continue

            records.append({
                'date': parsed_date,
                'month': parsed_date.strftime('%Y-%m'),
                'author_email': author_email,
                'name': resolved_name,
                'sapid': resolved_sapid,
                'team': resolved_team,
                'scrum': resolved_scrum,
                'primary_role': resolved_primary_role,
                'secondary_role': resolved_secondary_role,
                'repository': repository,
                'message': message,
                'is_merge': bool(merge_regex.match(message)),
                'files_changed': int(_as_float(row.get('files_changed'))),
                'lines_added': int(_as_float(row.get('lines_added'))),
                'lines_deleted': int(_as_float(row.get('lines_deleted'))),
                'lines_changed': int(_as_float(row.get('lines_changed'))),
            })

        available_months = sorted({record['month'] for record in records}, reverse=True)
        if not available_months:
            return {
                'success': True,
                'data': [],
                'date_columns': [],
                'metric_label': 'Total',
                'summary': {
                    'total_rows': 0,
                    'metric_total': 0,
                    'git_activity_scorecard': _empty_git_activity_scorecard(month or '', []),
                },
                'available_months': [],
                'selected_month': '',
                'available_filters': {
                    'teams': [],
                    'scrums': [],
                },
                'score_display_thresholds': {
                    'green_min': _as_float(display_thresholds.get('green_min', 70.0), default=70.0),
                    'orange_min': _as_float(display_thresholds.get('orange_min', 36.0), default=36.0),
                    'red_max': _as_float(display_thresholds.get('red_max', 35.0), default=35.0),
                },
                'applied_filters': {
                    'month': month or '',
                    'team': _clean_text(team),
                    'scrum': _clean_text(scrum),
                    'activity_type': activity_type,
                    'employee_scope': employee_scope,
                },
                '_cache_used': cache_used,
            }

        # Use the month of the most recent commit as the default, so that opening
        # the report on e.g. 1-May (when all data is from Apr 30) shows April, not
        # a sparse May with mostly zeros.
        if not month:
            max_record_date = max(r['date'] for r in records)
            last_data_month = max_record_date.strftime('%Y-%m')
            default_month = last_data_month if last_data_month in available_months else available_months[0]
        else:
            default_month = available_months[0]
        selected_month = month if month in available_months else default_month

        team_filter = _clean_text(team)
        scrum_filter = _clean_text(scrum)

        visible_roster = []
        for employee in employee_roster:
            employee_sapid = employee['sapid']

            if team_manager_team_scope:
                if not (employee.get('team') and employee['team'] in team_manager_team_scope):
                    continue
            elif accessible_sapids is not None:
                if not (employee_sapid and employee_sapid in accessible_sapids):
                    continue

            visible_roster.append(employee)

        available_filters = {
            'teams': sorted({employee['team'] for employee in visible_roster if employee['team']}),
            'scrums': sorted({employee['scrum'] for employee in visible_roster if employee['scrum']}),
        }

        filtered_roster = visible_roster
        if team_filter:
            filtered_roster = [employee for employee in filtered_roster if employee['team'] == team_filter]
        if scrum_filter:
            filtered_roster = [employee for employee in filtered_roster if employee['scrum'] == scrum_filter]

        month_records = [record for record in records if record['month'] == selected_month]
        if team_filter:
            month_records = [record for record in month_records if record['team'] == team_filter]
        if scrum_filter:
            month_records = [record for record in month_records if record['scrum'] == scrum_filter]

        year_str, month_str = selected_month.split('-')
        year_val = int(year_str)
        month_val = int(month_str)
        total_days = calendar.monthrange(year_val, month_val)[1]
        date_columns = [f"{selected_month}-{day:02d}" for day in range(1, total_days + 1)]

        aggregate: dict[str, dict[str, Any]] = {}

        for employee in filtered_roster:
            employee_key = employee['sapid'] or employee['author_email'] or f"name::{_normalize_person_name(employee['name'])}"
            aggregate[employee_key] = {
                'name': employee['name'],
                'author_email': employee['author_email'],
                'sapid': employee['sapid'],
                'team': employee['team'],
                'scrum': employee['scrum'],
                'daily_counts': {day_key: 0 for day_key in date_columns},
                'metric_total': 0,
                'merge_commits': 0,
                'non_merge_commits': 0,
                'daily_repositories': {day_key: set() for day_key in date_columns},
            }

        for record in month_records:
            key = record['sapid'] or record['author_email'] or f"name::{_normalize_person_name(record['name'])}"
            if key not in aggregate:
                aggregate[key] = {
                    'name': record['name'],
                    'author_email': record['author_email'],
                    'sapid': record['sapid'],
                    'team': record['team'],
                    'scrum': record['scrum'],
                    'daily_counts': {day_key: 0 for day_key in date_columns},
                    'metric_total': 0,
                    'merge_commits': 0,
                    'non_merge_commits': 0,
                    'daily_repositories': {day_key: set() for day_key in date_columns},
                }

            row = aggregate[key]
            if record['is_merge']:
                row['merge_commits'] += 1
            else:
                row['non_merge_commits'] += 1

            day_key = record['date'].strftime('%Y-%m-%d')
            if day_key not in row['daily_counts']:
                continue

            metric_value = 0
            if normalized_activity_type == 'total_commits':
                metric_value = 1
            elif normalized_activity_type == 'merges':
                metric_value = 1 if record['is_merge'] else 0
            elif normalized_activity_type == 'commits':
                metric_value = 0 if record['is_merge'] else 1
            elif normalized_activity_type == 'lines_added':
                metric_value = int(record['lines_added'])
            elif normalized_activity_type == 'lines_deleted':
                metric_value = int(record['lines_deleted'])
            elif normalized_activity_type == 'lines_changed':
                metric_value = int(record['lines_changed'])
            elif normalized_activity_type == 'files_changed':
                metric_value = int(record['files_changed'])
            elif normalized_activity_type == 'repos_touched':
                repository_name = _clean_text(record['repository'])
                if repository_name:
                    row['daily_repositories'][day_key].add(repository_name)

            if normalized_activity_type == 'repos_touched':
                continue

            row['daily_counts'][day_key] += metric_value
            row['metric_total'] += metric_value

        if normalized_activity_type == 'repos_touched':
            for row in aggregate.values():
                row['daily_counts'] = {
                    day_key: len(row['daily_repositories'][day_key])
                    for day_key in date_columns
                }
                row['metric_total'] = sum(row['daily_counts'].values())

        data_rows = []
        for row in aggregate.values():
            if normalized_employee_scope == 'active' and row['metric_total'] <= 0:
                continue
            if normalized_employee_scope == 'inactive' and row['metric_total'] > 0:
                continue
            data_rows.append({
                'date': selected_month,
                'name': row['name'],
                'author_email': row['author_email'],
                'sapid': row['sapid'],
                'team': row['team'],
                'scrum': row['scrum'],
                'daily_counts': row['daily_counts'],
                'metric_total': row['metric_total'],
                'merge_commits': row['merge_commits'],
                'non_merge_commits': row['non_merge_commits'],
            })

        data_rows.sort(key=lambda item: (item['name'].lower(), item['team'].lower(), item['scrum'].lower(), item['author_email']))

        scored_rows, scorecard = _compute_git_activity_scorecard(
            rows=data_rows,
            selected_month=selected_month,
            available_months=available_months,
            commits_file=commits_file,
        )

        metric_total = sum(item['metric_total'] for item in scored_rows)
        metric_label = _git_activity_metric_label(normalized_activity_type)

        return {
            'success': True,
            'data': scored_rows,
            'date_columns': date_columns,
            'metric_label': metric_label,
            'summary': {
                'total_rows': len(scored_rows),
                'metric_total': metric_total,
                'git_activity_scorecard': scorecard,
            },
            'available_months': available_months,
            'selected_month': selected_month,
            'score_display_thresholds': {
                'green_min': _as_float(display_thresholds.get('green_min', 70.0), default=70.0),
                'orange_min': _as_float(display_thresholds.get('orange_min', 36.0), default=36.0),
                'red_max': _as_float(display_thresholds.get('red_max', 35.0), default=35.0),
            },
            'available_filters': available_filters,
            'applied_filters': {
                'month': selected_month,
                'team': team_filter,
                'scrum': scrum_filter,
                'activity_type': normalized_activity_type,
                'employee_scope': normalized_employee_scope,
            },
            '_cache_used': cache_used,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/git-activity/employee-details")
def get_git_activity_employee_details(
    month: str = Query(..., description="Month in YYYY-MM"),
    sapid: Optional[str] = Query(None, description="Employee SAPID"),
    author_email: Optional[str] = Query(None, description="Employee author email"),
    current_user: TokenData = Depends(require_report_access),
):
    """Return month-level commit details for one employee in the Git activity report."""
    try:
        cache_used = False
        selected_month = _clean_text(month)
        if not re.match(r"^\d{4}-\d{2}$", selected_month):
            raise HTTPException(status_code=400, detail="month must be in YYYY-MM format")

        requested_sapid = _clean_sapid(sapid)
        requested_email = _clean_text(author_email).lower()
        if not requested_sapid and not requested_email:
            raise HTTPException(status_code=400, detail="Provide sapid or author_email")

        commits_file = project_root / 'output' / 'github_commits.csv'
        if not commits_file.exists():
            raise HTTPException(status_code=404, detail="github_commits.csv not found")

        try:
            commits_df = pd.read_csv(commits_file)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read github_commits.csv: {exc}")

        required_columns = {'commit_sha', 'date', 'author', 'author_email', 'repository', 'message'}
        missing = [column for column in required_columns if column not in commits_df.columns]
        if missing:
            raise HTTPException(
                status_code=500,
                detail=f"github_commits.csv missing required columns: {', '.join(sorted(missing))}"
            )

        employee_team_map, sapid_name_map, norm_name_to_sapid, _, all_teams = _load_employee_team_map()
        identity_by_email = _load_employee_git_identity_map()

        accessible_sapids, accessible_teams = _get_accessible_matrix_scope(
            current_user=current_user,
            employee_team_map=employee_team_map,
            all_teams=all_teams,
        )
        team_manager_team_scope = {
            _clean_text(team_id)
            for team_id in (current_user.team_ids or [])
            if _clean_text(team_id)
        } if current_user.role == "Team Manager" else set()

        cache_data = _load_git_activity_cache()
        cache_entry = _get_git_activity_cache_entry(cache_data or {}, selected_month)
        cached_details = _get_cached_git_activity_employee_details(
            cache_data=cache_entry or {},
            selected_month=selected_month,
            requested_sapid=requested_sapid,
            requested_email=requested_email,
        ) if cache_entry else None
        if cached_details:
            person = cached_details.get('person', {}) if isinstance(cached_details.get('person'), dict) else {}
            person_sapid = _clean_sapid(person.get('sapid'))
            person_team = _clean_text(person.get('team'))

            allowed = True
            if team_manager_team_scope:
                allowed = bool(person_team and person_team in team_manager_team_scope)
            elif accessible_sapids is not None:
                allowed = bool(person_sapid and person_sapid in accessible_sapids)

            if allowed:
                cache_used = True
                return {
                    'success': True,
                    'selected_month': selected_month,
                    'person': person,
                    'summary': cached_details.get('summary', {}),
                    'commits': cached_details.get('commits', []),
                    '_cache_used': cache_used,
                }

        merge_regex = re.compile(r'^\s*merge(d)?\b', re.IGNORECASE)
        commit_rows: list[dict[str, Any]] = []

        for _, row in commits_df.iterrows():
            parsed_date = pd.to_datetime(row.get('date'), errors='coerce')
            if pd.isna(parsed_date):
                continue
            if parsed_date.strftime('%Y-%m') != selected_month:
                continue

            row_author_email = _clean_text(row.get('author_email')).lower()
            row_author_name = _clean_text(row.get('author'))

            resolved = identity_by_email.get(row_author_email, {})
            resolved_name = _clean_text(resolved.get('name')) or row_author_name
            resolved_sapid = _clean_sapid(resolved.get('sapid'))
            resolved_team = _clean_text(resolved.get('team'))
            resolved_scrum = _clean_text(resolved.get('scrum'))

            if not resolved_sapid:
                mapped_sapid = norm_name_to_sapid.get(_normalize_person_name(row_author_name), '')
                if mapped_sapid:
                    resolved_sapid = mapped_sapid
                    resolved_name = sapid_name_map.get(mapped_sapid, resolved_name)
                    resolved_team = employee_team_map.get(mapped_sapid, resolved_team)

            if requested_sapid and resolved_sapid != requested_sapid:
                continue
            if requested_email and row_author_email != requested_email:
                continue

            if team_manager_team_scope:
                if not (resolved_team and resolved_team in team_manager_team_scope):
                    continue
            elif accessible_sapids is not None:
                if not (resolved_sapid and resolved_sapid in accessible_sapids):
                    continue

            message = _clean_text(row.get('message'))
            commit_rows.append({
                'commit_sha': _clean_text(row.get('commit_sha')),
                'date': parsed_date.strftime('%Y-%m-%d'),
                'author': row_author_name,
                'author_email': row_author_email,
                'repository': _clean_text(row.get('repository')),
                'message': message,
                'jira_id': _clean_text(row.get('jira_id')),
                'files_changed': int(_as_float(row.get('files_changed'))),
                'lines_added': int(_as_float(row.get('lines_added'))),
                'lines_deleted': int(_as_float(row.get('lines_deleted'))),
                'lines_changed': int(_as_float(row.get('lines_changed'))),
                'pr_number': _clean_text(row.get('pr_number')),
                'approver': _clean_text(row.get('approver')),
                'review_comments': int(_as_float(row.get('review_comments'))),
                'is_merge': bool(merge_regex.match(message)),
                '_resolved_name': resolved_name,
                '_resolved_sapid': resolved_sapid,
                '_resolved_team': resolved_team,
                '_resolved_scrum': resolved_scrum,
            })

        commit_rows.sort(key=lambda item: (item['date'], item['repository'], item['commit_sha']), reverse=True)

        person_name = ''
        person_sapid = requested_sapid
        person_email = requested_email
        person_team = ''
        person_scrum = ''
        if commit_rows:
            first = commit_rows[0]
            person_name = first.get('_resolved_name', '')
            person_sapid = first.get('_resolved_sapid', '')
            person_email = first.get('author_email', '')
            person_team = first.get('_resolved_team', '')
            person_scrum = first.get('_resolved_scrum', '')

        clean_commits = []
        for item in commit_rows:
            clean_item = dict(item)
            clean_item.pop('_resolved_name', None)
            clean_item.pop('_resolved_sapid', None)
            clean_item.pop('_resolved_team', None)
            clean_item.pop('_resolved_scrum', None)
            clean_commits.append(clean_item)

        return {
            'success': True,
            'selected_month': selected_month,
            'person': {
                'name': person_name,
                'sapid': person_sapid,
                'author_email': person_email,
                'team': person_team,
                'scrum': person_scrum,
            },
            'summary': {
                'total_commits': len(clean_commits),
                'merge_commits': sum(1 for item in clean_commits if item.get('is_merge')),
                'non_merge_commits': sum(1 for item in clean_commits if not item.get('is_merge')),
                'total_lines_changed': sum(int(item.get('lines_changed', 0)) for item in clean_commits),
                'total_files_changed': sum(int(item.get('files_changed', 0)) for item in clean_commits),
            },
            'commits': clean_commits,
            '_cache_used': cache_used,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/git-activity/export-details")
def start_git_activity_detailed_export(
    month: str = Query(..., description="Month in YYYY-MM"),
    team: str = Query(..., description="Team name; required for detailed export"),
    scrum: Optional[str] = Query(None, description="Optional scrum filter"),
    activity_type: str = Query("total_commits", description="total_commits|merges|commits|lines_added|lines_deleted|lines_changed|files_changed|repos_touched"),
    employee_scope: str = Query("active", description="active|inactive|all"),
    current_user: TokenData = Depends(require_report_access),
):
    _cleanup_git_activity_detail_export_jobs()

    selected_month = _clean_text(month)
    selected_team = _clean_text(team)
    selected_scrum = _clean_text(scrum)
    normalized_activity_type = _clean_text(activity_type).lower() or 'total_commits'
    normalized_employee_scope = _clean_text(employee_scope).lower() or 'active'

    if not re.match(r'^\d{4}-\d{2}$', selected_month):
        raise HTTPException(status_code=400, detail='month must be in YYYY-MM format')
    if not selected_team:
        raise HTTPException(status_code=400, detail='Detailed CSV export can be generated only on a per-team basis')
    if normalized_activity_type == 'all':
        normalized_activity_type = 'total_commits'
    if normalized_activity_type not in {
        'total_commits',
        'merges',
        'commits',
        'lines_added',
        'lines_deleted',
        'lines_changed',
        'files_changed',
        'repos_touched',
    }:
        raise HTTPException(status_code=400, detail='Invalid activity_type for detailed export')
    if normalized_employee_scope not in {'active', 'inactive', 'all'}:
        raise HTTPException(status_code=400, detail='employee_scope must be one of: active, inactive, all')

    user_key = _git_activity_detail_export_user_key(current_user)
    active_job = _get_active_git_activity_detail_export_job_for_user(user_key)
    if active_job:
        return JSONResponse(
            status_code=409,
            content={
                'detail': 'Detailed Git Activity export is already running',
                'job_id': _clean_text(active_job.get('job_id')),
                'status': _git_activity_detail_export_snapshot(active_job),
            },
        )

    job_id = f'git-activity-detail-export-{uuid4().hex}'
    now_iso = datetime.now().isoformat()
    job_payload = {
        'job_id': job_id,
        'owner_key': user_key,
        'status': 'pending',
        'progress_percent': 0,
        'current_step': 'Queued',
        'message': f'Queued detailed CSV export for team {selected_team}',
        'started_at': now_iso,
        'completed_at': '',
        'error_message': '',
        'download_ready': False,
        'download_filename': '',
        'file_path': '',
        'selected_month': selected_month,
        'team': selected_team,
        'scrum': selected_scrum,
        'activity_type': normalized_activity_type,
        'employee_scope': normalized_employee_scope,
        'rows_written': 0,
    }

    with _git_activity_detail_export_lock:
        _git_activity_detail_export_jobs[job_id] = job_payload
        _git_activity_detail_export_active_by_user[user_key] = job_id

    worker = threading.Thread(
        target=_run_git_activity_detail_export_job,
        kwargs={
            'job_id': job_id,
            'user_key': user_key,
            'current_user': current_user,
            'month': selected_month,
            'team': selected_team,
            'scrum': selected_scrum,
            'activity_type': normalized_activity_type,
            'employee_scope': normalized_employee_scope,
        },
        daemon=True,
        name=f'git-activity-detail-export-{job_id}',
    )
    worker.start()

    return {
        'success': True,
        'job_id': job_id,
        'status': _git_activity_detail_export_snapshot(job_payload),
    }


@router.get("/git-activity/export-details/status")
def get_git_activity_detailed_export_status(
    job_id: str = Query(..., description='Detailed export job id'),
    current_user: TokenData = Depends(require_report_access),
):
    _cleanup_git_activity_detail_export_jobs()

    job = _get_git_activity_detail_export_job(_clean_text(job_id))
    if not job:
        raise HTTPException(status_code=404, detail='Detailed export job not found')

    user_key = _git_activity_detail_export_user_key(current_user)
    if _clean_text(job.get('owner_key')) != user_key:
        raise HTTPException(status_code=403, detail='Not authorized to view this detailed export job')

    return _git_activity_detail_export_snapshot(job)


@router.get("/git-activity/export-details/download")
def download_git_activity_detailed_export(
    job_id: str = Query(..., description='Detailed export job id'),
    current_user: TokenData = Depends(require_report_access),
):
    _cleanup_git_activity_detail_export_jobs()

    job = _get_git_activity_detail_export_job(_clean_text(job_id))
    if not job:
        raise HTTPException(status_code=404, detail='Detailed export job not found')

    user_key = _git_activity_detail_export_user_key(current_user)
    if _clean_text(job.get('owner_key')) != user_key:
        raise HTTPException(status_code=403, detail='Not authorized to download this detailed export')

    status = _clean_text(job.get('status')).lower()
    if status in {'pending', 'running'}:
        raise HTTPException(status_code=409, detail='Detailed export is still running')
    if status != 'completed' or not job.get('download_ready'):
        raise HTTPException(status_code=409, detail=_clean_text(job.get('error_message')) or 'Detailed export is not available for download')

    file_path_str = _clean_text(job.get('file_path'))
    if not file_path_str:
        raise HTTPException(status_code=404, detail='Detailed export file is no longer available')

    file_path = Path(file_path_str)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail='Detailed export file is no longer available')

    return FileResponse(
        str(file_path),
        media_type='text/csv',
        filename=_clean_text(job.get('download_filename')) or file_path.name,
    )


@router.get("/git-activity/commit-file-details")
def get_git_activity_commit_file_details(
    month: str = Query(..., description="Month in YYYY-MM"),
    commit_sha: str = Query(..., description="Full commit SHA"),
    repository: Optional[str] = Query(None, description="Repository path to disambiguate duplicate SHAs"),
    sapid: Optional[str] = Query(None, description="Employee SAPID for access scoping"),
    author_email: Optional[str] = Query(None, description="Employee author email for access scoping"),
    current_user: TokenData = Depends(require_report_access),
):
    """Return deduped file-level LOC and component summary for one commit in a selected month."""
    try:
        selected_month = _clean_text(month)
        if not re.match(r"^\d{4}-\d{2}$", selected_month):
            raise HTTPException(status_code=400, detail="month must be in YYYY-MM format")

        requested_sha = _clean_text(commit_sha)
        if not requested_sha:
            raise HTTPException(status_code=400, detail="commit_sha is required")

        requested_repo = _clean_text(repository)
        requested_sapid = _clean_sapid(sapid)
        requested_email = _clean_text(author_email).lower()

        commits_file = project_root / 'output' / 'github_commits.csv'
        files_file = project_root / 'output' / 'github_commit_files.csv'
        if not commits_file.exists():
            raise HTTPException(status_code=404, detail="github_commits.csv not found")
        if not files_file.exists():
            raise HTTPException(status_code=404, detail="github_commit_files.csv not found")

        try:
            commits_df = pd.read_csv(commits_file)
            files_df = pd.read_csv(files_file)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read git activity CSV files: {exc}")

        commit_required_columns = {'commit_sha', 'date', 'author', 'author_email', 'repository', 'message'}
        missing_commit_cols = [column for column in commit_required_columns if column not in commits_df.columns]
        if missing_commit_cols:
            raise HTTPException(
                status_code=500,
                detail=f"github_commits.csv missing required columns: {', '.join(sorted(missing_commit_cols))}"
            )

        file_required_columns = {
            'commit_sha', 'repository', 'filepath', 'status',
            'lines_added', 'lines_deleted', 'lines_changed', 'filename', 'file_extension',
        }
        missing_file_cols = [column for column in file_required_columns if column not in files_df.columns]
        if missing_file_cols:
            raise HTTPException(
                status_code=500,
                detail=f"github_commit_files.csv missing required columns: {', '.join(sorted(missing_file_cols))}"
            )

        commit_months = pd.to_datetime(commits_df['date'], errors='coerce').dt.strftime('%Y-%m')
        sha_mask = commits_df['commit_sha'].astype(str).str.strip() == requested_sha
        month_mask = commit_months == selected_month
        repo_mask = commits_df['repository'].fillna('').astype(str).str.strip() == requested_repo if requested_repo else pd.Series([True] * len(commits_df))
        commit_matches = commits_df[sha_mask & month_mask & repo_mask].copy()
        if commit_matches.empty:
            raise HTTPException(status_code=404, detail="Commit not found for selected month")

        commit_row = commit_matches.iloc[0]

        employee_team_map, sapid_name_map, norm_name_to_sapid, _, all_teams = _load_employee_team_map()
        identity_by_email = _load_employee_git_identity_map()
        accessible_sapids, accessible_teams = _get_accessible_matrix_scope(
            current_user=current_user,
            employee_team_map=employee_team_map,
            all_teams=all_teams,
        )
        team_manager_team_scope = {
            _clean_text(team_id)
            for team_id in (current_user.team_ids or [])
            if _clean_text(team_id)
        } if current_user.role == "Team Manager" else set()

        row_author_email = _clean_text(commit_row.get('author_email')).lower()
        row_author_name = _clean_text(commit_row.get('author'))
        resolved = identity_by_email.get(row_author_email, {})
        resolved_name = _clean_text(resolved.get('name')) or row_author_name
        resolved_sapid = _clean_sapid(resolved.get('sapid'))
        resolved_team = _clean_text(resolved.get('team'))
        resolved_scrum = _clean_text(resolved.get('scrum'))

        if not resolved_sapid:
            mapped_sapid = norm_name_to_sapid.get(_normalize_person_name(row_author_name), '')
            if mapped_sapid:
                resolved_sapid = mapped_sapid
                resolved_name = sapid_name_map.get(mapped_sapid, resolved_name)
                resolved_team = employee_team_map.get(mapped_sapid, resolved_team)

        if requested_sapid and resolved_sapid != requested_sapid:
            raise HTTPException(status_code=404, detail="Commit not found for provided SAPID")
        if requested_email and row_author_email != requested_email:
            raise HTTPException(status_code=404, detail="Commit not found for provided author_email")

        if team_manager_team_scope:
            if not (resolved_team and resolved_team in team_manager_team_scope):
                raise HTTPException(status_code=403, detail="Insufficient permissions for this commit")
        elif accessible_sapids is not None:
            if not (resolved_sapid and resolved_sapid in accessible_sapids):
                raise HTTPException(status_code=403, detail="Insufficient permissions for this commit")

        files_mask = files_df['commit_sha'].astype(str).str.strip() == requested_sha
        if requested_repo:
            files_mask = files_mask & (files_df['repository'].fillna('').astype(str).str.strip() == requested_repo)
        commit_files_df = files_df[files_mask].copy()

        if commit_files_df.empty:
            summary_files = int(_as_float(commit_row.get('files_changed')))
            summary_added = int(_as_float(commit_row.get('lines_added')))
            summary_deleted = int(_as_float(commit_row.get('lines_deleted')))
            summary_changed = int(_as_float(commit_row.get('lines_changed')))
            return {
                'success': True,
                'selected_month': selected_month,
                'warning': (
                    'No file-level rows found for this commit in output/github_commit_files.csv. '
                    'Showing commit-level totals from output/github_commits.csv.'
                ),
                'commit': {
                    'commit_sha': requested_sha,
                    'repository': _clean_text(commit_row.get('repository')),
                    'date': pd.to_datetime(commit_row.get('date'), errors='coerce').strftime('%Y-%m-%d') if not pd.isna(pd.to_datetime(commit_row.get('date'), errors='coerce')) else '',
                    'author': row_author_name,
                    'author_email': row_author_email,
                    'message': _clean_text(commit_row.get('message')),
                    'jira_id': _clean_text(commit_row.get('jira_id')),
                    'person': {
                        'name': resolved_name,
                        'sapid': resolved_sapid,
                        'team': resolved_team,
                        'scrum': resolved_scrum,
                    },
                },
                'summary': {
                    'files_count': summary_files,
                    'lines_added': summary_added,
                    'lines_deleted': summary_deleted,
                    'lines_changed': summary_changed,
                },
                'components': [
                    {
                        'component': '[file-details-unavailable]',
                        'files_count': summary_files,
                        'lines_added': summary_added,
                        'lines_deleted': summary_deleted,
                        'lines_changed': summary_changed,
                    }
                ],
                'files': [
                    {
                        'component': '[file-details-unavailable]',
                        'filepath': '[file-level rows missing in github_commit_files.csv]',
                        'filename': '',
                        'file_extension': '',
                        'status': 'unknown',
                        'lines_added': summary_added,
                        'lines_deleted': summary_deleted,
                        'lines_changed': summary_changed,
                    }
                ],
            }

        def _component_from_path(filepath: str) -> str:
            path_value = _clean_text(filepath)
            if not path_value:
                return '[root]'
            parts = [part for part in path_value.split('/') if part]
            if not parts:
                return '[root]'
            if len(parts) == 1:
                return '[root]'
            if parts[0].startswith('.') and len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
            return parts[0]

        commit_files_df['repository'] = commit_files_df['repository'].fillna('').astype(str).str.strip()
        commit_files_df['filepath'] = commit_files_df['filepath'].fillna('').astype(str).str.strip()
        commit_files_df['status'] = commit_files_df['status'].fillna('').astype(str).str.strip().str.lower()
        commit_files_df['lines_added'] = commit_files_df['lines_added'].apply(_as_float).astype(int)
        commit_files_df['lines_deleted'] = commit_files_df['lines_deleted'].apply(_as_float).astype(int)
        commit_files_df['lines_changed'] = commit_files_df['lines_changed'].apply(_as_float).astype(int)

        dedupe_subset = ['commit_sha', 'repository', 'filepath', 'status', 'lines_added', 'lines_deleted', 'lines_changed']
        for column in dedupe_subset:
            if column not in commit_files_df.columns:
                commit_files_df[column] = ''
        commit_files_df = commit_files_df.drop_duplicates(subset=dedupe_subset, keep='last')

        commit_files_df['component'] = commit_files_df['filepath'].apply(_component_from_path)

        component_summary = (
            commit_files_df
            .groupby('component', dropna=False)
            .agg(
                files_count=('filepath', 'count'),
                lines_added=('lines_added', 'sum'),
                lines_deleted=('lines_deleted', 'sum'),
                lines_changed=('lines_changed', 'sum'),
            )
            .reset_index()
            .sort_values(by=['lines_changed', 'files_count', 'component'], ascending=[False, False, True])
        )

        files_payload = []
        ordered_files = commit_files_df.sort_values(by=['lines_changed', 'filepath'], ascending=[False, True])
        for _, row in ordered_files.iterrows():
            files_payload.append({
                'component': _clean_text(row.get('component')),
                'filepath': _clean_text(row.get('filepath')),
                'filename': _clean_text(row.get('filename')),
                'file_extension': _clean_text(row.get('file_extension')),
                'status': _clean_text(row.get('status')),
                'lines_added': int(row.get('lines_added', 0)),
                'lines_deleted': int(row.get('lines_deleted', 0)),
                'lines_changed': int(row.get('lines_changed', 0)),
            })

        components_payload = []
        for _, row in component_summary.iterrows():
            components_payload.append({
                'component': _clean_text(row.get('component')),
                'files_count': int(row.get('files_count', 0)),
                'lines_added': int(row.get('lines_added', 0)),
                'lines_deleted': int(row.get('lines_deleted', 0)),
                'lines_changed': int(row.get('lines_changed', 0)),
            })

        parsed_commit_date = pd.to_datetime(commit_row.get('date'), errors='coerce')

        return {
            'success': True,
            'selected_month': selected_month,
            'warning': '',
            'commit': {
                'commit_sha': requested_sha,
                'repository': _clean_text(commit_row.get('repository')),
                'date': parsed_commit_date.strftime('%Y-%m-%d') if not pd.isna(parsed_commit_date) else '',
                'author': row_author_name,
                'author_email': row_author_email,
                'message': _clean_text(commit_row.get('message')),
                'jira_id': _clean_text(commit_row.get('jira_id')),
                'person': {
                    'name': resolved_name,
                    'sapid': resolved_sapid,
                    'team': resolved_team,
                    'scrum': resolved_scrum,
                },
            },
            'summary': {
                'files_count': int(len(files_payload)),
                'lines_added': int(commit_files_df['lines_added'].sum()),
                'lines_deleted': int(commit_files_df['lines_deleted'].sum()),
                'lines_changed': int(commit_files_df['lines_changed'].sum()),
            },
            'components': components_payload,
            'files': files_payload,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/git-activity/metadata")
def get_git_activity_metadata(
    current_user: TokenData = Depends(require_report_access),
):
    """Return filter metadata for the Git activity report.

    Months come from commit data. Teams and scrums come from Resources.csv so
    dropdowns are populated even before a report is run.
    """
    try:
        available_months: list[str] = []
        commit_dates: pd.Series = pd.Series([], dtype='datetime64[ns]')
        commits_file = project_root / 'output' / 'github_commits.csv'
        if commits_file.exists():
            try:
                commits_df = pd.read_csv(commits_file, usecols=['date'])
                if 'date' in commits_df.columns:
                    commit_dates = pd.to_datetime(commits_df['date'], errors='coerce').dropna()
                    available_months = sorted({
                        parsed.strftime('%Y-%m')
                        for parsed in commit_dates
                    }, reverse=True)
            except Exception:
                available_months = []
        # Default to the month of the most recent commit, not available_months[0].
        # This avoids showing a sparse current month (e.g. 1-May with no data yet)
        # when the last nightly run collected data only through the previous month.
        if commit_dates is not None and len(commit_dates) > 0:
            last_data_month = commit_dates.max().strftime('%Y-%m')
            default_selected_month = last_data_month if last_data_month in available_months else (available_months[0] if available_months else '')
        else:
            default_selected_month = available_months[0] if available_months else ''

        team_map, _, _, _, all_teams = _load_employee_team_map()
        accessible_sapids, accessible_teams = _get_accessible_matrix_scope(
            current_user=current_user,
            employee_team_map=team_map,
            all_teams=all_teams,
        )
        team_manager_team_scope = {
            _clean_text(team_id)
            for team_id in (current_user.team_ids or [])
            if _clean_text(team_id)
        } if current_user.role == "Team Manager" else set()

        scrums: set[str] = set()
        teams: set[str] = set()
        if RESOURCES_FILE.exists():
            try:
                resources_df = _load_normalized_resources_df()
                scrum_col = _find_column_by_normalized_name(list(resources_df.columns), 'Scrum')
                sapid_col = _find_column_by_normalized_name(list(resources_df.columns), 'SAPID')
                team_col = _find_column_by_normalized_name(list(resources_df.columns), 'Team')

                for _, row in resources_df.iterrows():
                    team_value = _clean_text(row.get(team_col)) if team_col else ''
                    scrum_value = _clean_text(row.get(scrum_col)) if scrum_col else ''
                    sapid_value = _clean_sapid(row.get(sapid_col)) if sapid_col else ''

                    if team_manager_team_scope:
                        if not (team_value and team_value in team_manager_team_scope):
                            continue
                    elif accessible_sapids is not None:
                        if not (sapid_value and sapid_value in accessible_sapids):
                            continue

                    if team_value:
                        teams.add(team_value)
                    if scrum_value:
                        scrums.add(scrum_value)
            except Exception:
                teams = set(accessible_teams if accessible_sapids is not None else all_teams)

        if not teams:
            teams = set(accessible_teams if accessible_sapids is not None else all_teams)

        return {
            'success': True,
            'available_months': available_months,
            'selected_month': default_selected_month,
            'available_filters': {
                'teams': sorted(teams),
                'scrums': sorted(scrums),
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/role-kpi-applicability")
def get_role_kpi_applicability_report(
    role: Optional[str] = Query(None, description="Role from Roles.csv")
):
    """
    Get the KPIs applicable to a given role.

    Applicable KPIs include the selected role's KPIs plus shared buckets:
    Common, All, Metric/Metrics.
    """
    try:
        roles_df = roles_service.load_data().copy()
        roles_df['Role'] = roles_df['Role'].fillna('').astype(str).str.strip()
        roles_df['Index'] = roles_df['Index'].fillna('').astype(str).str.strip()

        reportable_roles = _get_reportable_roles(roles_df)
        if not reportable_roles:
            raise HTTPException(status_code=404, detail="No reportable roles found in Roles.csv")

        selected_role = role.strip() if role else reportable_roles[0]
        valid_roles = [*reportable_roles, ALL_KPIS_ROLE_LABEL]
        if selected_role not in valid_roles:
            raise HTTPException(
                status_code=400,
                detail=f"Role '{selected_role}' not found in reportable Roles.csv entries"
            )

        shared_role_buckets = _get_shared_role_buckets(roles_df)

        if selected_role == ALL_KPIS_ROLE_LABEL:
            applicable_df = roles_df[
                (~roles_df['Role'].isin(NON_REPORTABLE_ROLE_BUCKETS)) &
                (roles_df['Index'].astype(str).str.strip() != '')
            ].copy()
            applied_role_buckets = sorted(
                [bucket for bucket in applicable_df['Role'].dropna().astype(str).str.strip().unique().tolist() if bucket]
            )
            applicable_df['source_priority'] = 0
        else:
            applied_role_buckets = [selected_role, *shared_role_buckets]
            applicable_df = roles_df[roles_df['Role'].isin(applied_role_buckets)].copy()
            applicable_df['source_priority'] = applicable_df['Role'].apply(
                lambda value: applied_role_buckets.index(value) if value in applied_role_buckets else len(applied_role_buckets)
            )
        applicable_df['index_num'] = (
            applicable_df['Index']
            .str.extract(r'(\d+)')[0]
            .fillna('0')
            .astype(int)
        )
        applicable_df = applicable_df.sort_values(['source_priority', 'index_num', 'Index'])

        evaluator = _create_evaluator()
        source_counts = Counter()
        report_data = []
        implemented_kpis = 0
        pending_kpis = 0

        for _, row in applicable_df.iterrows():
            kpi_id = row['Index']
            source_role = row['Role']
            base_kpi = evaluator.get_base_kpi(kpi_id) if kpi_id else None
            implemented = kpi_id in evaluator.kpi_functions

            if implemented:
                implemented_kpis += 1
                if evaluator.is_equivalent_kpi(kpi_id):
                    implementation_type = 'Equivalent'
                    implementation_details = f"Uses {base_kpi.upper()} computation and data"
                else:
                    implementation_type = 'Direct'
                    implementation_details = 'Direct evaluator implementation is available'
            else:
                pending_kpis += 1
                if kpi_id in evaluator.kpi_equivalents:
                    implementation_type = 'Mapped / pending'
                    implementation_details = (
                        f"Mapped to {base_kpi.upper()} but that base KPI is not registered yet"
                    )
                else:
                    implementation_type = 'Pending'
                    implementation_details = 'No evaluator implementation is registered yet'

            source_counts[source_role] += 1

            report_data.append({
                'index': kpi_id,
                'name': _format_sheet_value(row.get('KPP Goals')),
                'source_role': source_role,
                'goal_type': _format_sheet_value(row.get('Goal Type')),
                'type_code': _format_sheet_value(row.get('Type')),
                'aggregation_type': _format_sheet_value(row.get('Aggregation Type')),
                'measurement_criteria': _format_sheet_value(row.get('Measurement Criteria')),
                'tool': _format_sheet_value(row.get('Tool')),
                'measure': _format_sheet_value(row.get('Measure')),
                'weekly_target': _format_sheet_value(row.get('Weekly Target')),
                'quarterly_target': _format_sheet_value(row.get('Quarterly Target')),
                'annual_target': _format_sheet_value(row.get('Annual Target')),
                'prorate': str(row.get('Prorate', 'Yes')).strip().lower() != 'no',
                'implemented': implemented,
                'implementation_status': 'Implemented' if implemented else 'Not yet implemented',
                'implementation_type': implementation_type,
                'implementation_details': implementation_details,
                'base_kpi': base_kpi.upper() if base_kpi else ''
            })

        return {
            'success': True,
            'roles': [*reportable_roles, ALL_KPIS_ROLE_LABEL],
            'selected_role': selected_role,
            'shared_role_buckets': shared_role_buckets,
            'applied_role_buckets': applied_role_buckets,
            'data': report_data,
            'total_kpis': len(report_data),
            'implemented_kpis': implemented_kpis,
            'pending_kpis': pending_kpis,
            'source_counts': {key: int(value) for key, value in source_counts.items()}
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/jira-epics')
def get_jira_epics_report(
    team: Optional[str] = Query(None, description='Filter by related issue team'),
    state: Optional[str] = Query(None, description='Filter by related issue status/state'),
    sprint: Optional[str] = Query(None, description='Filter by related issue sprint'),
    assignee: Optional[str] = Query(None, description='Filter by related issue assignee'),
    component: Optional[str] = Query(None, description='Filter by related issue component'),
    search: Optional[str] = Query(None, description='Search by epic key or summary'),
    page: int = Query(1, ge=1, description='1-based page number'),
    page_size: int = Query(25, ge=5, le=100, description='Number of epics per page'),
    current_user: TokenData = Depends(require_report_access)
):
    """List epics with hierarchy-aware filtering and delay rollups."""
    try:
        team_filter = _clean_text(team)
        state_filter = _clean_text(state).lower()
        sprint_filter = _clean_text(sprint)
        assignee_filter = _clean_text(assignee)
        component_filter = _clean_text(component)
        search_filter = _clean_text(search).lower()

        def build_empty_response(filters_payload: dict[str, list[str]], available_teams: list[str] = None):
            if available_teams is None:
                available_teams = []
            return {
                'success': True,
                'data': [],
                'total_epics': 0,
                'applied_filters': {
                    'team': team_filter,
                    'state': _clean_text(state),
                    'sprint': sprint_filter,
                    'assignee': assignee_filter,
                    'component': component_filter,
                    'search': _clean_text(search)
                },
                'filters': filters_payload,
                'available_teams': available_teams,
                'pagination': {
                    'page': 1,
                    'page_size': page_size,
                    'total_pages': 0,
                    'total_items': 0,
                    'has_next': False,
                    'has_previous': False
                }
            }

        cached_epics_df = _load_epic_tree_epics_cache()
        if not cached_epics_df.empty:
            accessible_assignees, all_accessible_teams = _get_accessible_epic_scope(current_user)

            scoped_epics_df = cached_epics_df.copy()
            if accessible_assignees is not None:
                accessible_team_set = set(all_accessible_teams)

                def is_epic_accessible(epic_row: pd.Series) -> bool:
                    related_teams = set(epic_row.get('related_teams', []) or [])
                    if related_teams & accessible_team_set:
                        return True

                    related_assignees = {
                        _normalize_person_name(value)
                        for value in (epic_row.get('related_assignees', []) or [])
                        if _normalize_person_name(value)
                    }
                    return bool(related_assignees & accessible_assignees)

                scoped_epics_df = scoped_epics_df[scoped_epics_df.apply(is_epic_accessible, axis=1)].copy()

                if scoped_epics_df.empty:
                    return build_empty_response(
                        {
                            'teams': sorted(all_accessible_teams),
                            'states': [],
                            'sprints': [],
                            'assignees': [],
                            'components': []
                        },
                        available_teams=sorted(all_accessible_teams)
                    )

            team_options = sorted({
                team_value
                for teams in scoped_epics_df['related_teams'].tolist()
                for team_value in teams
                if _clean_text(team_value)
            })
            state_options = sorted({
                state_value
                for states in scoped_epics_df['related_states_display'].tolist()
                for state_value in states
                if _clean_text(state_value)
            })
            sprint_options = sorted({
                sprint_value
                for sprints in scoped_epics_df['related_sprints'].tolist()
                for sprint_value in sprints
                if _clean_text(sprint_value)
            })
            assignee_options = sorted({
                assignee_value
                for assignees in scoped_epics_df['related_assignees'].tolist()
                for assignee_value in assignees
                if _clean_text(assignee_value)
            })
            component_options = sorted({
                component_value
                for components in scoped_epics_df['related_components'].tolist()
                for component_value in components
                if _clean_text(component_value)
            })

            filter_options = {
                'teams': team_options,
                'states': state_options,
                'sprints': sprint_options,
                'assignees': assignee_options,
                'components': component_options,
            }

            if team_filter:
                scoped_epics_df = scoped_epics_df[
                    scoped_epics_df['related_teams'].apply(lambda values: team_filter in (values or []))
                ].copy()
            if state_filter:
                scoped_epics_df = scoped_epics_df[
                    scoped_epics_df['related_states_norm'].apply(lambda values: state_filter in (values or []))
                ].copy()
            if sprint_filter:
                scoped_epics_df = scoped_epics_df[
                    scoped_epics_df['related_sprints'].apply(lambda values: sprint_filter in (values or []))
                ].copy()
            if assignee_filter:
                scoped_epics_df = scoped_epics_df[
                    scoped_epics_df['related_assignees'].apply(lambda values: assignee_filter in (values or []))
                ].copy()
            if component_filter:
                scoped_epics_df = scoped_epics_df[
                    scoped_epics_df['related_components'].apply(lambda values: component_filter in (values or []))
                ].copy()
            if search_filter:
                scoped_epics_df = scoped_epics_df[
                    scoped_epics_df.apply(
                        lambda epic_row: (
                            search_filter in _clean_text(epic_row.get('epic_key')).lower()
                            or search_filter in _clean_text(epic_row.get('summary')).lower()
                        ),
                        axis=1,
                    )
                ].copy()

            if scoped_epics_df.empty:
                available_teams = filter_options['teams'] if accessible_assignees is None else sorted(
                    set(filter_options['teams']) & set(all_accessible_teams)
                )
                return build_empty_response(filter_options, available_teams=available_teams)

            scoped_epics_df = scoped_epics_df.sort_values(
                ['overdue_descendants', 'open_descendants', 'epic_key'],
                ascending=[False, False, True]
            )

            total_epics = int(len(scoped_epics_df))
            total_pages = (total_epics + page_size - 1) // page_size if total_epics > 0 else 0
            effective_page = min(page, total_pages) if total_pages > 0 else 1
            start_index = (effective_page - 1) * page_size
            end_index = start_index + page_size

            page_epics_df = scoped_epics_df.iloc[start_index:end_index]
            epic_items = [
                {
                    'epic_key': _clean_text(epic_row.get('epic_key')),
                    'summary': _clean_text(epic_row.get('summary')),
                    'status': _clean_text(epic_row.get('status'), 'Unknown'),
                    'priority': _clean_text(epic_row.get('priority')),
                    'assignee': _clean_text(epic_row.get('assignee'), 'Unassigned'),
                    'team': _clean_text(epic_row.get('team'), 'Unknown'),
                    'sprint': _clean_text(epic_row.get('sprint'), 'NA'),
                    'story_points': round(_safe_float(epic_row.get('story_points')), 2),
                    'created': _clean_text(epic_row.get('created')),
                    'updated': _clean_text(epic_row.get('updated')),
                    'total_related_issues': int(_safe_float(epic_row.get('total_related_issues'))),
                    'total_descendants': int(_safe_float(epic_row.get('total_descendants'))),
                    'done_descendants': int(_safe_float(epic_row.get('done_descendants'))),
                    'open_descendants': int(_safe_float(epic_row.get('open_descendants'))),
                    'overdue_descendants': int(_safe_float(epic_row.get('overdue_descendants'))),
                    'avg_delay_days': round(_safe_float(epic_row.get('avg_delay_days')), 2),
                }
                for _, epic_row in page_epics_df.iterrows()
            ]

            final_available_teams = filter_options['teams'] if accessible_assignees is None else sorted(
                set(filter_options['teams']) & set(all_accessible_teams)
            )

            return {
                'success': True,
                'data': epic_items,
                'total_epics': total_epics,
                'applied_filters': {
                    'team': team_filter,
                    'state': _clean_text(state),
                    'sprint': sprint_filter,
                    'assignee': assignee_filter,
                    'component': component_filter,
                    'search': _clean_text(search)
                },
                'filters': filter_options,
                'available_teams': final_available_teams,
                'pagination': {
                    'page': effective_page,
                    'page_size': page_size,
                    'total_pages': total_pages,
                    'total_items': total_epics,
                    'has_next': total_pages > 0 and effective_page < total_pages,
                    'has_previous': total_pages > 0 and effective_page > 1
                }
            }

        issues_df = _load_jira_issue_data()
        if issues_df.empty:
            return build_empty_response({
                'teams': [],
                'states': [],
                'sprints': [],
                'assignees': [],
                'components': []
            })

        issue_lookup = {
            _clean_text(row['Key']): row
            for _, row in issues_df.iterrows()
            if _clean_text(row.get('Key'))
        }

        # Apply RBAC filtering
        accessible_assignees, all_accessible_teams = _get_accessible_epic_scope(current_user, issues_df)
        
        # Filter issues_df based on RBAC if user is not Admin/API User.
        # Use vectorized isin() – avoids a slow Python-level row loop.
        if accessible_assignees is not None:
            rbac_mask = (
                issues_df['_assignee_norm'].isin(accessible_assignees)
                | issues_df['Team'].isin(all_accessible_teams)
            )
            issues_df = issues_df[rbac_mask].copy()
            
            if issues_df.empty:
                return build_empty_response({
                    'teams': sorted(all_accessible_teams),
                    'states': [],
                    'sprints': [],
                    'assignees': [],
                    'components': []
                }, available_teams=all_accessible_teams)

        # Rebuild issue_lookup after RBAC filtering
        issue_lookup = {
            _clean_text(row['Key']): row
            for _, row in issues_df.iterrows()
            if _clean_text(row.get('Key'))
        }

        epic_keys = sorted(
            [
                issue_key
                for issue_key, issue in issue_lookup.items()
                if _clean_text(issue.get('Issue Type')).lower() == 'epic'
            ],
            key=lambda issue_key: _issue_sort_key(issue_lookup[issue_key])
        )
        epic_key_set = set(epic_keys)

        if not epic_keys:
            return build_empty_response({
                'teams': sorted(all_accessible_teams) if accessible_assignees is not None else [],
                'states': [],
                'sprints': [],
                'assignees': [],
                'components': []
            }, available_teams=all_accessible_teams if accessible_assignees is not None else [])

        filter_options = {
            'teams': sorted({
                _clean_text(value, 'Unknown')
                for value in issues_df['Team'].tolist()
                if _clean_text(value, 'Unknown')
            }),
            'states': sorted({
                _clean_text(value)
                for value in issues_df['Status'].tolist()
                if _clean_text(value)
            }),
            'sprints': sorted({
                _clean_text(value)
                for value in issues_df['Sprint'].tolist()
                if _clean_text(value) and _clean_text(value).upper() != 'NA'
            }),
            'assignees': sorted({
                _clean_text(value, 'Unassigned')
                for value in issues_df['Assignee'].tolist()
                if _clean_text(value, 'Unassigned')
            }),
            'components': sorted({
                component
                for raw_value in (issues_df['Components'].tolist() if 'Components' in issues_df.columns else [])
                for component in _extract_components(raw_value)
            })
        }

        root_epic_cache: dict[str, Optional[str]] = {}

        def resolve_root_epic(issue_key: str, lineage: Optional[set[str]] = None) -> Optional[str]:
            if issue_key in root_epic_cache:
                return root_epic_cache[issue_key]

            issue = issue_lookup.get(issue_key)
            if issue is None:
                root_epic_cache[issue_key] = None
                return None

            issue_type = _clean_text(issue.get('Issue Type')).lower()
            if issue_type == 'epic':
                root_epic_cache[issue_key] = issue_key
                return issue_key

            parent_key = _clean_text(issue.get('Parent'))
            if not parent_key or parent_key == issue_key or parent_key not in issue_lookup:
                root_epic_cache[issue_key] = None
                return None

            active_lineage = set(lineage or set())
            if issue_key in active_lineage:
                root_epic_cache[issue_key] = None
                return None

            active_lineage.add(issue_key)
            root_key = resolve_root_epic(parent_key, active_lineage)
            root_epic_cache[issue_key] = root_key
            return root_key

        epic_aggregates: dict[str, dict[str, Any]] = {
            epic_key: {
                'related_teams': set(),
                'related_states': set(),
                'related_sprints': set(),
                'related_assignees': set(),
                'related_components': set(),
                'total_related_issues': 0,
                'total_descendants': 0,
                'done_descendants': 0,
                'open_descendants': 0,
                'overdue_descendants': 0,
                'delay_sum': 0.0,
                'delay_count': 0
            }
            for epic_key in epic_keys
        }

        for issue_key, issue in issue_lookup.items():
            root_epic_key = resolve_root_epic(issue_key)
            if not root_epic_key or root_epic_key not in epic_key_set:
                continue

            aggregate = epic_aggregates[root_epic_key]

            aggregate['related_teams'].add(_clean_text(issue.get('Team'), 'Unknown'))

            status_value = _clean_text(issue.get('Status')).lower()
            if status_value:
                aggregate['related_states'].add(status_value)

            sprint_value = _clean_text(issue.get('Sprint'))
            if sprint_value and sprint_value.upper() != 'NA':
                aggregate['related_sprints'].add(sprint_value)

            aggregate['related_assignees'].add(_clean_text(issue.get('Assignee'), 'Unassigned'))
            for component_value in _extract_components(issue.get('Components')):
                aggregate['related_components'].add(component_value)
            aggregate['total_related_issues'] += 1

            if issue_key == root_epic_key:
                continue

            aggregate['total_descendants'] += 1

            if bool(issue.get('_is_done', False)):
                aggregate['done_descendants'] += 1
            else:
                aggregate['open_descendants'] += 1

            if bool(issue.get('_is_overdue', False)):
                aggregate['overdue_descendants'] += 1

            delay_value = _safe_float(issue.get('_delay_days'))
            if delay_value > 0:
                aggregate['delay_sum'] += delay_value
                aggregate['delay_count'] += 1

        matching_epic_keys: list[str] = []
        for epic_key in epic_keys:
            aggregate = epic_aggregates[epic_key]

            if team_filter and team_filter not in aggregate['related_teams']:
                continue
            if state_filter and state_filter not in aggregate['related_states']:
                continue
            if sprint_filter and sprint_filter not in aggregate['related_sprints']:
                continue
            if assignee_filter and assignee_filter not in aggregate['related_assignees']:
                continue
            if component_filter and component_filter not in aggregate['related_components']:
                continue

            epic_issue = issue_lookup[epic_key]
            epic_summary = _clean_text(epic_issue.get('Summary'))
            if search_filter and search_filter not in epic_key.lower() and search_filter not in epic_summary.lower():
                continue

            matching_epic_keys.append(epic_key)

        matching_epic_keys.sort(
            key=lambda epic_key: (
                -epic_aggregates[epic_key]['overdue_descendants'],
                -epic_aggregates[epic_key]['open_descendants'],
                epic_key
            )
        )

        total_epics = len(matching_epic_keys)
        total_pages = (total_epics + page_size - 1) // page_size if total_epics > 0 else 0
        effective_page = min(page, total_pages) if total_pages > 0 else 1
        start_index = (effective_page - 1) * page_size
        end_index = start_index + page_size

        visible_epic_keys = matching_epic_keys[start_index:end_index]
        epic_items = []
        for epic_key in visible_epic_keys:
            epic_issue = issue_lookup[epic_key]
            aggregate = epic_aggregates[epic_key]

            avg_delay_days = (
                round(aggregate['delay_sum'] / aggregate['delay_count'], 2)
                if aggregate['delay_count']
                else 0.0
            )

            epic_items.append({
                'epic_key': epic_key,
                'summary': _clean_text(epic_issue.get('Summary')),
                'status': _clean_text(epic_issue.get('Status'), 'Unknown'),
                'priority': _clean_text(epic_issue.get('Priority')),
                'assignee': _clean_text(epic_issue.get('Assignee'), 'Unassigned'),
                'team': _clean_text(epic_issue.get('Team'), 'Unknown'),
                'sprint': _clean_text(epic_issue.get('Sprint'), 'NA'),
                'story_points': round(_safe_float(epic_issue.get('Story Points')), 2),
                'created': _clean_text(epic_issue.get('Created')),
                'updated': _clean_text(epic_issue.get('Updated')),
                'total_related_issues': int(aggregate['total_related_issues']),
                'total_descendants': int(aggregate['total_descendants']),
                'done_descendants': int(aggregate['done_descendants']),
                'open_descendants': int(aggregate['open_descendants']),
                'overdue_descendants': int(aggregate['overdue_descendants']),
                'avg_delay_days': avg_delay_days
            })

        # Collect visible teams from epic_items
        visible_team_set = set()
        for item in epic_items:
            team = item.get('team', '')
            if team:
                visible_team_set.add(team)

        # For non-admin users, available_teams should only include teams visible in the results
        final_available_teams = all_accessible_teams if accessible_assignees is None else sorted(visible_team_set)

        return {
            'success': True,
            'data': epic_items,
            'total_epics': total_epics,
            'applied_filters': {
                'team': team_filter,
                'state': _clean_text(state),
                'sprint': sprint_filter,
                'assignee': assignee_filter,
                'component': component_filter,
                'search': _clean_text(search)
            },
            'filters': filter_options,
            'available_teams': final_available_teams,
            'pagination': {
                'page': effective_page,
                'page_size': page_size,
                'total_pages': total_pages,
                'total_items': total_epics,
                'has_next': total_pages > 0 and effective_page < total_pages,
                'has_previous': total_pages > 0 and effective_page > 1
            }
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get('/jira-epics/{epic_key}/details')
def get_jira_epic_details(
    epic_key: str,
    current_user: TokenData = Depends(require_report_access)
):
    """Get hierarchy tree and assignee/delay analytics for one selected epic."""
    try:
        selected_epic_key = _clean_text(epic_key)
        if not selected_epic_key:
            raise HTTPException(status_code=400, detail='Epic key is required')

        issues_df = _load_epic_workspace_cache(selected_epic_key)
        if issues_df.empty:
            issues_df = _load_jira_issue_data()

        # Apply RBAC filtering
        accessible_assignees, all_accessible_teams = _get_accessible_epic_scope(current_user, issues_df)

        # Filter issues_df based on RBAC if user is not Admin/API User.
        # Use vectorized isin() – avoids a slow Python-level row loop.
        if accessible_assignees is not None:
            rbac_mask = (
                issues_df['_assignee_norm'].isin(accessible_assignees)
                | issues_df['Team'].isin(all_accessible_teams)
            )
            issues_df = issues_df[rbac_mask].copy()

        issue_lookup = {
            _clean_text(row['Key']): row
            for _, row in issues_df.iterrows()
            if _clean_text(row.get('Key'))
        }

        if selected_epic_key not in issue_lookup:
            raise HTTPException(
                status_code=404,
                detail=f'Epic {selected_epic_key} not found in the current dataset. '
                       f'Please run the "JIRA Epic Tree Cache" scheduled job to sync the latest data.'
            )

        epic_issue = issue_lookup[selected_epic_key]
        if _clean_text(epic_issue.get('Issue Type')).lower() != 'epic':
            raise HTTPException(status_code=400, detail=f'Issue {selected_epic_key} is not an Epic')

        children_map = _build_children_map(issue_lookup)
        descendant_keys = _collect_descendant_keys(selected_epic_key, children_map)
        related_keys = [selected_epic_key, *descendant_keys]

        related_df = issues_df[issues_df['Key'].isin(related_keys)].copy()
        if related_df.empty:
            raise HTTPException(status_code=404, detail=f'No related issues found for Epic {selected_epic_key}')

        tree = _build_issue_tree_node(
            issue_key=selected_epic_key,
            issue_lookup=issue_lookup,
            children_map=children_map
        )

        delay_series = pd.to_numeric(related_df['_delay_days'], errors='coerce').fillna(0)
        positive_delays = delay_series[delay_series > 0]
        age_series = pd.to_numeric(related_df['_age_days'], errors='coerce').fillna(0)

        total_related_issues = int(len(related_df))
        done_issues = int(related_df['_is_done'].sum())
        open_issues = total_related_issues - done_issues
        delayed_issues = int(related_df['_is_overdue'].sum())

        assignee_breakdown = []
        assignee_df = related_df.copy()
        assignee_df['Assignee'] = assignee_df['Assignee'].replace('', 'Unassigned')
        assignee_df['Team'] = assignee_df['Team'].replace('', 'Unknown')

        for (assignee_name, team_name), assignee_group in assignee_df.groupby(['Assignee', 'Team'], dropna=False):
            group_delay = pd.to_numeric(assignee_group['_delay_days'], errors='coerce').fillna(0)
            group_positive_delay = group_delay[group_delay > 0]
            group_age = pd.to_numeric(assignee_group['_age_days'], errors='coerce').fillna(0)

            representative_group = assignee_group.copy()
            representative_group['_delay_sort'] = pd.to_numeric(representative_group['_delay_days'], errors='coerce').fillna(0)
            representative_group['_updated_sort'] = pd.to_datetime(representative_group['_updated_dt'], errors='coerce', utc=True)
            representative_group = representative_group.sort_values(
                ['_delay_sort', '_updated_sort'],
                ascending=[False, False]
            )
            representative_issue = representative_group.iloc[0] if not representative_group.empty else None

            initial_assigned_date = ''
            initial_sprint = 'NA'
            next_transition_field = ''
            next_transition_from = ''
            next_transition_to = ''
            next_transition_by = ''
            next_transition_date = ''

            if representative_issue is not None:
                initial_assigned_date = _format_timestamp(representative_issue.get('_initial_allocated_dt'))
                initial_sprint = _clean_text(
                    representative_issue.get('_initial_sprint'),
                    _clean_text(representative_issue.get('Sprint'), 'NA')
                )
                next_transition_field = _clean_text(representative_issue.get('_next_transition_field'))
                next_transition_from = _clean_text(representative_issue.get('_next_transition_from'))
                next_transition_to = _clean_text(representative_issue.get('_next_transition_to'))
                next_transition_by = _clean_text(representative_issue.get('_next_transition_by'))
                next_transition_date = _format_timestamp(representative_issue.get('_next_transition_dt'))

            transition_parts = []
            if next_transition_field:
                transition_parts.append(next_transition_field)
            if next_transition_from or next_transition_to:
                transition_parts.append(f"{next_transition_from or 'NA'} → {next_transition_to or 'NA'}")
            if next_transition_date:
                transition_parts.append(next_transition_date)
            if next_transition_by:
                transition_parts.append(f"by {next_transition_by}")

            next_transition_summary = ' | '.join(transition_parts)

            assignee_breakdown.append({
                'assignee': _clean_text(assignee_name, 'Unassigned'),
                'team': _clean_text(team_name, 'Unknown'),
                'total_issues': int(len(assignee_group)),
                'done_issues': int(assignee_group['_is_done'].sum()),
                'in_progress_issues': int(assignee_group['_is_in_progress'].sum()),
                'todo_issues': int(assignee_group['_is_todo'].sum()),
                'delayed_issues': int(assignee_group['_is_overdue'].sum()),
                'avg_age_days': round(float(group_age.mean()), 2) if not group_age.empty else 0.0,
                'avg_delay_days': round(float(group_positive_delay.mean()), 2) if not group_positive_delay.empty else 0.0,
                'max_delay_days': round(float(group_delay.max()), 2) if not group_delay.empty else 0.0,
                'initial_assigned_date': initial_assigned_date,
                'initial_sprint': initial_sprint,
                'next_transition_field': next_transition_field,
                'next_transition_from': next_transition_from,
                'next_transition_to': next_transition_to,
                'next_transition_by': next_transition_by,
                'next_transition_date': next_transition_date,
                'next_transition_summary': next_transition_summary
            })

        assignee_breakdown.sort(
            key=lambda item: (
                -item['delayed_issues'],
                -item['total_issues'],
                item['assignee']
            )
        )

        issue_type_breakdown = []
        for issue_type, issue_type_group in related_df.groupby('Issue Type', dropna=False):
            issue_type_delay = pd.to_numeric(issue_type_group['_delay_days'], errors='coerce').fillna(0)
            positive_issue_type_delay = issue_type_delay[issue_type_delay > 0]

            issue_type_breakdown.append({
                'issue_type': _clean_text(issue_type, 'Unknown'),
                'total_issues': int(len(issue_type_group)),
                'done_issues': int(issue_type_group['_is_done'].sum()),
                'open_issues': int((~issue_type_group['_is_done']).sum()),
                'delayed_issues': int(issue_type_group['_is_overdue'].sum()),
                'avg_delay_days': round(float(positive_issue_type_delay.mean()), 2) if not positive_issue_type_delay.empty else 0.0,
                'max_delay_days': round(float(issue_type_delay.max()), 2) if not issue_type_delay.empty else 0.0
            })

        issue_type_breakdown.sort(
            key=lambda item: (
                ISSUE_TYPE_ORDER.get(item['issue_type'].lower(), 99),
                item['issue_type']
            )
        )

        status_counts = (
            related_df['Status']
            .fillna('Unknown')
            .astype(str)
            .str.strip()
            .replace('', 'Unknown')
            .value_counts()
            .to_dict()
        )

        child_df = related_df[related_df['Key'] != selected_epic_key].copy()
        timing_df = child_df[
            child_df['_planned_duration_days'].notna()
            & child_df['_actual_duration_days'].notna()
            & (pd.to_numeric(child_df['_planned_duration_days'], errors='coerce') > 0)
        ].copy()
        timing_df['_planned_duration_days'] = pd.to_numeric(timing_df['_planned_duration_days'], errors='coerce')
        timing_df['_actual_duration_days'] = pd.to_numeric(timing_df['_actual_duration_days'], errors='coerce')
        timing_df['_slippage_days'] = pd.to_numeric(timing_df['_slippage_days'], errors='coerce')

        timing_df = timing_df.sort_values(['_slippage_days', '_actual_duration_days'], ascending=[False, False])
        max_timing_rows = 400
        timing_slice = timing_df.head(max_timing_rows)

        child_timing = []
        for _, timing_row in timing_slice.iterrows():
            child_timing.append({
                'key': _clean_text(timing_row.get('Key')),
                'parent': _clean_text(timing_row.get('Parent')),
                'summary': _clean_text(timing_row.get('Summary')),
                'issue_type': _clean_text(timing_row.get('Issue Type')),
                'assignee': _clean_text(timing_row.get('Assignee'), 'Unassigned'),
                'team': _clean_text(timing_row.get('Team'), 'Unknown'),
                'status': _clean_text(timing_row.get('Status'), 'Unknown'),
                'initial_sprint': _clean_text(timing_row.get('_initial_sprint'), _clean_text(timing_row.get('Sprint'), 'NA')),
                'initial_allocation_date': _format_timestamp(timing_row.get('_initial_allocated_dt')),
                'planned_days': _optional_rounded_float(timing_row.get('_planned_duration_days')),
                'actual_days': _optional_rounded_float(timing_row.get('_actual_duration_days')),
                'slippage_days': _optional_rounded_float(timing_row.get('_slippage_days'))
            })

        timing_summary = {
            'total_children': int(len(child_df)),
            'timed_children': int(len(timing_df)),
            'overrun_children': int((timing_df['_slippage_days'] > 0).sum()) if not timing_df.empty else 0,
            'on_track_children': int((timing_df['_slippage_days'] <= 0).sum()) if not timing_df.empty else 0,
            'avg_planned_days': round(float(timing_df['_planned_duration_days'].mean()), 2) if not timing_df.empty else 0.0,
            'avg_actual_days': round(float(timing_df['_actual_duration_days'].mean()), 2) if not timing_df.empty else 0.0,
            'avg_slippage_days': round(float(timing_df['_slippage_days'].mean()), 2) if not timing_df.empty else 0.0,
            'truncated': len(timing_df) > max_timing_rows,
            'returned_children': int(len(timing_slice))
        }

        return {
            'success': True,
            'epic': {
                'key': selected_epic_key,
                'summary': _clean_text(epic_issue.get('Summary')),
                'status': _clean_text(epic_issue.get('Status'), 'Unknown'),
                'priority': _clean_text(epic_issue.get('Priority')),
                'assignee': _clean_text(epic_issue.get('Assignee'), 'Unassigned'),
                'team': _clean_text(epic_issue.get('Team'), 'Unknown'),
                'sprint': _clean_text(epic_issue.get('Sprint'), 'NA'),
                'story_points': round(_safe_float(epic_issue.get('Story Points')), 2),
                'created': _clean_text(epic_issue.get('Created')),
                'updated': _clean_text(epic_issue.get('Updated')),
                'completion_date': _format_timestamp(epic_issue.get('_completion_dt')),
                'delay_days': round(_safe_float(epic_issue.get('_delay_days')), 2)
            },
            'tree': tree,
            'analysis': {
                'total_related_issues': total_related_issues,
                'total_descendants': len(descendant_keys),
                'done_issues': done_issues,
                'open_issues': open_issues,
                'delayed_issues': delayed_issues,
                'avg_age_days': round(float(age_series.mean()), 2) if not age_series.empty else 0.0,
                'avg_delay_days': round(float(positive_delays.mean()), 2) if not positive_delays.empty else 0.0,
                'max_delay_days': round(float(delay_series.max()), 2) if not delay_series.empty else 0.0,
                'status_counts': {str(key): int(value) for key, value in status_counts.items()},
                'assignee_breakdown': assignee_breakdown,
                'issue_type_breakdown': issue_type_breakdown,
                'timing_summary': timing_summary,
                'child_timing': child_timing
            }
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get('/jira-issues/{issue_key}/transitions')
def get_jira_issue_transitions(issue_key: str):
    """Get full transition history and delay-computation breakdown for one issue."""
    try:
        selected_issue_key = _clean_text(issue_key)
        if not selected_issue_key:
            raise HTTPException(status_code=400, detail='Issue key is required')

        issues_df = _load_jira_issue_data()
        issue_df = issues_df[issues_df['Key'] == selected_issue_key]
        if issue_df.empty:
            raise HTTPException(status_code=404, detail=f'Issue {selected_issue_key} not found')

        issue = issue_df.iloc[0]

        # Fast path: use pre-cached per-issue transition file if available
        _transitions_cache = _issue_transitions_cache_path(selected_issue_key)
        if _transitions_cache.exists():
            try:
                transitions = json.loads(_transitions_cache.read_text(encoding='utf-8'))
            except Exception:
                transitions = _load_issue_transition_rows(selected_issue_key)
        else:
            transitions = _load_issue_transition_rows(selected_issue_key)
            # Write to cache on first miss so subsequent requests are fast
            try:
                _transitions_cache.parent.mkdir(parents=True, exist_ok=True)
                _transitions_cache.write_text(json.dumps(transitions), encoding='utf-8')
            except Exception:
                pass

        sprint_end_dt = pd.to_datetime(issue.get('_sprint_end_dt'), errors='coerce', utc=True)
        delay_baseline_dt = pd.to_datetime(issue.get('_delay_baseline_dt'), errors='coerce', utc=True)
        delay_baseline_source = _clean_text(issue.get('_delay_baseline_source'), 'no_sprint_end_date')
        completion_dt = pd.to_datetime(issue.get('_completion_dt'), errors='coerce', utc=True)
        now_ts = pd.Timestamp.now(tz='UTC')
        is_done = bool(issue.get('_is_done', False))
        effective_end_dt = completion_dt if (is_done and not pd.isna(completion_dt)) else now_ts

        raw_delay_days: Optional[float] = None
        if delay_baseline_dt is not None and not pd.isna(delay_baseline_dt):
            raw_delay_days = (effective_end_dt - delay_baseline_dt).total_seconds() / 86400

        for transition in transitions:
            transition_dt = pd.to_datetime(transition.get('change_date'), errors='coerce', utc=True)
            accumulated_delay_days: Optional[float] = None

            if (
                delay_baseline_dt is not None
                and not pd.isna(delay_baseline_dt)
                and transition_dt is not None
                and not pd.isna(transition_dt)
            ):
                accumulated_delay_days = _normalize_delay_days(
                    (transition_dt - delay_baseline_dt).total_seconds() / 86400
                )

            transition['accumulated_delay_days'] = _optional_rounded_float(accumulated_delay_days)

        assignee_timeline = _build_issue_assignee_timeline(
            transitions=transitions,
            issue_assignee=issue.get('Assignee'),
            created_dt=issue.get('_created_dt'),
            effective_end_dt=effective_end_dt,
            delay_baseline_dt=delay_baseline_dt
        )

        clipped_delay_days = round(_safe_float(issue.get('_delay_days')), 2)
        delay_basis = (
            f'completion_date_vs_{delay_baseline_source}'
            if is_done
            else f'current_date_vs_{delay_baseline_source}'
        )
        if delay_baseline_dt is None or pd.isna(delay_baseline_dt):
            delay_basis = 'no_sprint_end_date'

        return {
            'success': True,
            'issue': {
                'key': selected_issue_key,
                'summary': _clean_text(issue.get('Summary')),
                'issue_type': _clean_text(issue.get('Issue Type')),
                'status': _clean_text(issue.get('Status'), 'Unknown'),
                'assignee': _clean_text(issue.get('Assignee'), 'Unassigned'),
                'team': _clean_text(issue.get('Team'), 'Unknown'),
                'sprint': _clean_text(issue.get('Sprint'), 'NA'),
                'created': _clean_text(issue.get('Created')),
                'updated': _clean_text(issue.get('Updated')),
                'sprint_end_date': _format_timestamp(sprint_end_dt),
                'completion_date': _format_timestamp(completion_dt),
                'is_done': is_done,
                'delay_days': clipped_delay_days
            },
            'delay_computation': {
                'formula': 'delay_days = max(0, effective_end_date - delay_baseline_date); delay_baseline_date = max(sprint_end_date, first_active_or_created_date); values below 1 day are treated as 0',
                'basis': delay_basis,
                'sprint_end_date': _format_timestamp(sprint_end_dt),
                'delay_baseline_date': _format_timestamp(delay_baseline_dt),
                'delay_baseline_source': delay_baseline_source,
                'effective_end_date': _format_timestamp(effective_end_dt),
                'completion_date': _format_timestamp(completion_dt),
                'current_reference_date': _format_timestamp(now_ts) if not is_done else '',
                'raw_delay_days': _optional_rounded_float(raw_delay_days),
                'delay_days': clipped_delay_days
            },
            'assignee_timeline': assignee_timeline,
            'transitions': transitions,
            'transition_count': len(transitions)
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/available-kpis")
def get_available_kpis():
    """Get list of available KPIs."""
    try:
        evaluator = _create_evaluator()
        kpis = evaluator.list_kpis()
        return {
            "success": True,
            "kpis": sorted(kpis, key=lambda x: int(x[1:]))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
