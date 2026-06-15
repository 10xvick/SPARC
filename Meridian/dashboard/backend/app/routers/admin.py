"""
Admin API endpoints for job management and user/role management
"""
from fastapi import APIRouter, HTTPException, Query, Depends, status, Body, Request
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime, timezone
import os
import json
import csv
import shutil
import threading
from pathlib import Path
import time

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False
from app.models.job import (
    JobConfig, JobProgress, JobExecution, JobTriggerRequest, 
    HealthCheckResult, JobSchedule
)
from app.models.user import (
    UserResponse, UserCreate, UserUpdate, RoleResponse, 
    SyncResponse, UserPasswordReset, TokenData, UserCreateResponse
)
from app.services.scheduler import get_scheduler
from app.services.user_service import UserService
from app.services.role_service import RoleService
from app.services.user_sync_service import UserSyncService
from app.services import resources_service
from app.dependencies import require_admin, require_admin_or_read_api
from app.services.audit_trail_service import AuditTrailService
from app.services.dashboard_message_service import (
    load_messages,
    save_messages,
    normalize_message_payload,
    serialize_message_for_admin,
    get_supported_placeholders,
    get_placeholder_categories,
)
from app.services.notification_mail_service import NotificationMailService
import logging

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
BACKUP_DIR = PROJECT_ROOT / "backup"

class BackupDeleteRequest(BaseModel):
    names: List[str]


class AuditLogTrimRequest(BaseModel):
    keep_latest: Optional[int] = None
    trim_mode: Optional[str] = None
    date: Optional[str] = None
    month: Optional[str] = None
    year: Optional[int] = None


class DashboardMessagePayload(BaseModel):
    text: str
    severity: str = "info"
    scope: str = "all"
    target_values: List[str] = []
    require_any_red_kpi: bool = False
    kpi_red_ids: List[str] = []
    empty_resource_fields: List[str] = []
    empty_resource_field_sentinels: List[str] = []
    validity_days: int = 7
    enabled: bool = True


class DashboardSnapshotGenerateRequest(BaseModel):
    as_of_date: Optional[str] = None
    run_in_background: bool = True


class MailConfigResponse(BaseModel):
    enabled: bool
    smtp_host: str
    smtp_port: int
    use_tls: bool
    from_address: str
    timeout_seconds: int


class MailConfigUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    use_tls: Optional[bool] = None
    from_address: Optional[str] = None
    timeout_seconds: Optional[int] = None


class SendCredentialsEmailRequest(BaseModel):
    user_sapid: str
    password: str
    mode: str
    dashboard_url: Optional[str] = None


audit_trail_service = AuditTrailService()


def _sanitize_admin_payload(payload: Any) -> Any:
    hidden_keys = {
        "password",
        "new_password",
        "current_password",
        "refresh_token",
        "access_token",
        "token",
        "secret",
        "api_key",
    }

    if payload is None:
        return None
    if isinstance(payload, dict):
        safe: dict[str, Any] = {}
        for key, value in list(payload.items())[:50]:
            lowered = str(key).lower()
            if lowered in hidden_keys:
                safe[str(key)] = "***"
            else:
                safe[str(key)] = _sanitize_admin_payload(value)
        return safe
    if isinstance(payload, list):
        return [_sanitize_admin_payload(item) for item in payload[:50]]
    if isinstance(payload, str):
        return payload[:500]
    if isinstance(payload, (int, float, bool)):
        return payload
    return str(payload)


def _derive_admin_audit_context(method: str, path: str) -> tuple[str, str]:
    """Map admin routes to audit module/action for clearer filtering in Audit Trail."""
    method_upper = method.upper()
    normalized_path = (path or "").strip().lower()

    if normalized_path == "/api/admin/users" and method_upper == "POST":
        return "configuration", "rbac_user_add"
    if normalized_path.startswith("/api/admin/users/") and normalized_path.endswith("/reset-password") and method_upper == "POST":
        return "configuration", "rbac_user_password_reset"
    if normalized_path.startswith("/api/admin/users/") and method_upper == "PUT":
        return "configuration", "rbac_user_edit"
    if normalized_path.startswith("/api/admin/users/") and method_upper == "DELETE":
        return "configuration", "rbac_user_delete"
    if normalized_path in {"/api/admin/users-sync", "/api/admin/users/sync"} and method_upper == "POST":
        return "configuration", "rbac_users_sync"

    if normalized_path == "/api/admin/roles" and method_upper == "POST":
        return "configuration", "rbac_role_add"
    if normalized_path.startswith("/api/admin/roles/") and method_upper == "PUT":
        return "configuration", "rbac_role_edit"
    if normalized_path.startswith("/api/admin/roles/") and method_upper == "DELETE":
        return "configuration", "rbac_role_delete"

    if normalized_path.startswith("/api/admin/users") or normalized_path.startswith("/api/admin/roles"):
        return "configuration", "rbac_access"

    if normalized_path == "/api/admin/notifications/mail-config" and method_upper == "PUT":
        return "configuration", "notification_mail_config_update"
    if normalized_path == "/api/admin/notifications/mail-config" and method_upper == "GET":
        return "configuration", "notification_mail_config_view"

    return "system_admin", "admin_activity"


async def _audit_admin_activity(request: Request, current_user: TokenData = Depends(require_admin_or_read_api)):
    body_summary: Any = None
    method = request.method.upper()

    if method in {"POST", "PUT", "PATCH", "DELETE"} and current_user.role not in ["Admin", "API User"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        try:
            raw_body = await request.body()
            if raw_body:
                try:
                    parsed = json.loads(raw_body.decode("utf-8", "ignore"))
                    body_summary = _sanitize_admin_payload(parsed)
                except Exception:
                    body_summary = {"raw_body_size": len(raw_body)}
        except Exception:
            body_summary = {"raw_body": "unavailable"}

    module, action = _derive_admin_audit_context(method, request.url.path)

    details = {
        "path": request.url.path,
        "query": _sanitize_admin_payload(dict(request.query_params)),
        "change": body_summary,
        "module": module,
        "action": action,
    }

    if module == "configuration":
        audit_trail_service.record_configuration_event(
            sapid=current_user.sapid,
            user_id=current_user.user_id,
            user_name=current_user.name,
            role=current_user.role,
            method=method,
            path=request.url.path,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details=details,
        )
    else:
        audit_trail_service.record_system_admin_event(
            sapid=current_user.sapid,
            user_id=current_user.user_id,
            user_name=current_user.name,
            role=current_user.role,
            method=method,
            path=request.url.path,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details=details,
        )

    return current_user

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(_audit_admin_activity)])

# Service instances for RBAC
user_service = UserService()
role_service = RoleService()
sync_service = UserSyncService(user_service)
notification_mail_service = NotificationMailService()

_snapshot_generation_lock = threading.Lock()
_snapshot_generation_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "last_error": None,
    "last_as_of_date": None,
}


@router.get("/jobs", response_model=List[JobConfig])
def list_jobs():
    """List all configured jobs"""
    scheduler = get_scheduler()
    return scheduler.list_jobs()


@router.get("/scheduler/timezone")
def get_scheduler_timezone():
    """Return scheduler timezone metadata for local-time UI conversion."""
    scheduler = get_scheduler()
    scheduler_timezone = getattr(scheduler.scheduler, "timezone", None)
    scheduler_tz = str(scheduler_timezone or "UTC")
    return {
        "timezone": scheduler_tz,
        "now": datetime.now(scheduler_timezone).isoformat() if scheduler_timezone else datetime.utcnow().isoformat(),
    }


@router.get("/jobs/{job_id}", response_model=JobConfig)
def get_job(job_id: str):
    """Get job configuration by ID"""
    scheduler = get_scheduler()
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


# Jobs that are not user-schedulable (currently none)
_CHAIN_ONLY_JOBS: set = set()


@router.put("/jobs/{job_id}/schedule")
def update_job_schedule(job_id: str, schedule: JobSchedule):
    """Update job schedule configuration"""
    if job_id in _CHAIN_ONLY_JOBS:
        raise HTTPException(
            status_code=400,
            detail=f"Job '{job_id}' is triggered automatically by its parent job and cannot be manually scheduled.",
        )
    scheduler = get_scheduler()
    
    schedule_dict = {
        "enabled": schedule.enabled,
        "cron_expression": schedule.cron_expression,
        "interval_minutes": schedule.interval_minutes
    }
    
    success = scheduler.update_job_schedule(job_id, schedule_dict)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to update schedule for job {job_id}")
    
    return {"success": True, "message": f"Schedule updated for job {job_id}"}



@router.post("/scheduler/pause-all")
def pause_all_jobs():
    """Disable all scheduled jobs. Cron expressions are preserved so they can be re-enabled later."""
    scheduler = get_scheduler()
    paused = []
    skipped = []
    for job in scheduler.list_jobs():
        if job.id in _CHAIN_ONLY_JOBS:
            skipped.append(job.id)
            continue
        # Build a schedule payload with enabled=False but keep the existing cron intact
        existing_schedule = job.schedule
        schedule_dict = {
            "enabled": False,
            "cron_expression": existing_schedule.cron_expression if existing_schedule else None,
            "interval_minutes": existing_schedule.interval_minutes if existing_schedule else None,
        }
        scheduler.update_job_schedule(job.id, schedule_dict)
        paused.append(job.id)
    return {"success": True, "paused": paused, "skipped": skipped,
            "message": f"Paused {len(paused)} job(s). Use /scheduler/resume-all to re-enable."}


@router.post("/scheduler/resume-all")
def resume_all_jobs():
    """Re-enable all scheduled jobs that have a cron expression."""
    scheduler = get_scheduler()
    resumed = []
    skipped = []
    no_schedule = []
    for job in scheduler.list_jobs():
        if job.id in _CHAIN_ONLY_JOBS:
            skipped.append(job.id)
            continue
        existing_schedule = job.schedule
        if not existing_schedule or not (existing_schedule.cron_expression or existing_schedule.interval_minutes):
            no_schedule.append(job.id)
            continue
        schedule_dict = {
            "enabled": True,
            "cron_expression": existing_schedule.cron_expression,
            "interval_minutes": existing_schedule.interval_minutes,
        }
        scheduler.update_job_schedule(job.id, schedule_dict)
        resumed.append(job.id)
    return {"success": True, "resumed": resumed, "skipped": skipped, "no_schedule": no_schedule,
            "message": f"Resumed {len(resumed)} job(s)."}


@router.post("/jobs/run-all")
async def run_all_jobs():
    """Trigger all schedulable jobs to run sequentially in the background."""
    scheduler = get_scheduler()
    try:
        await scheduler.run_all_jobs_sequential()
        return {"success": True, "message": "Sequential run started"}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/jobs/run-all/status")
def get_run_all_status():
    """Return current status of the sequential run-all operation."""
    scheduler = get_scheduler()
    return scheduler.get_run_all_status()


@router.post("/jobs/{job_id}/trigger")
async def trigger_job(job_id: str, triggered_by: str = "manual"):
    """Trigger a job to run immediately"""
    scheduler = get_scheduler()
    
    try:
        execution_id = await scheduler.trigger_job(job_id, triggered_by)
        return {
            "success": True,
            "execution_id": execution_id,
            "message": f"Job {job_id} triggered successfully"
        }
    except ValueError as e:
        if "already running" in str(e).lower():
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error triggering job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/jobs/{job_id}/progress", response_model=Optional[JobProgress])
def get_job_progress(job_id: str):
    """Get current progress for a job"""
    scheduler = get_scheduler()
    progress = scheduler.get_job_progress(job_id)
    return progress


@router.get("/jobs/{job_id}/history", response_model=List[JobExecution])
def get_job_history(
    job_id: str,
    limit: int = Query(50, ge=1, le=200)
):
    """Get execution history for a job"""
    scheduler = get_scheduler()
    return scheduler.get_job_history(job_id, limit)


@router.get("/history", response_model=List[JobExecution])
def get_all_history(
    limit: int = Query(50, ge=1, le=200)
):
    """Get execution history for all jobs"""
    scheduler = get_scheduler()
    return scheduler.get_job_history(None, limit)


@router.get("/health/services", response_model=List[HealthCheckResult])
async def check_services_health():
    """Check health of all services"""
    scheduler = get_scheduler()
    
    # Define services to check
    services = [
        {"name": "Backend API", "url": "http://127.0.0.1:8000/health"},
        {"name": "Frontend", "url": "http://localhost:5173"},
    ]
    
    results = []
    for service in services:
        try:
            result = await scheduler.check_service_health(service["name"], service["url"])
            results.append(result)
        except Exception as e:
            logger.error(f"Error checking {service['name']}: {e}")
            results.append(HealthCheckResult(
                service_name=service["name"],
                status="error",
                message=str(e)
            ))
    
    return results


@router.get("/health/service/{service_name}", response_model=HealthCheckResult)
async def check_service_health(service_name: str):
    """Check health of a specific service"""
    scheduler = get_scheduler()
    
    # Map service names to URLs
    service_urls = {
        "backend": "http://127.0.0.1:8000/health",
        "frontend": "http://localhost:5173",
    }
    
    url = service_urls.get(service_name.lower())
    if not url:
        raise HTTPException(status_code=404, detail=f"Service {service_name} not found")
    
    try:
        result = await scheduler.check_service_health(service_name, url)
        return result
    except Exception as e:
        logger.error(f"Error checking {service_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running job by killing its subprocess."""
    scheduler = get_scheduler()
    cancelled = await scheduler.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(status_code=400, detail=f"Job {job_id} is not currently running")
    return {"success": True, "message": f"Job {job_id} cancelled"}


@router.get("/services")
async def get_services():
    """Get information about all services"""
    scheduler = get_scheduler()
    services = await scheduler.get_service_info()
    return services


def _refresh_all_caches() -> dict[str, Any]:
    """Reload all in-memory caches from disk. Returns per-cache results."""
    from app.api.reports import _load_jira_issue_data
    import app.api.replan_tracker as _replan_mod
    import app.api.assignee_delay_report as _adr_mod

    results = {}
    for name, fn in [
        ("jira_issue_data", _load_jira_issue_data),
        ("replan_tracker", _replan_mod.load_replan_data),
        ("assignee_delay", _adr_mod._load_assignee_delay_data),
    ]:
        try:
            fn()
            results[name] = "refreshed"
        except Exception as exc:
            results[name] = f"error: {exc}"
    return results


@router.post("/cache/refresh")
def refresh_caches():
    """On-demand: reload all in-memory caches from disk."""
    results = _refresh_all_caches()
    logger.info("On-demand cache refresh: %s", results)
    return {"success": True, "results": results}


def _generate_dashboard_snapshot_task(as_of_date: Optional[str], source: str = "manual") -> None:
    """Background task for dashboard snapshot generation."""
    from app.services.dashboard_snapshot_service import get_dashboard_snapshot_service

    with _snapshot_generation_lock:
        _snapshot_generation_state["running"] = True
        _snapshot_generation_state["started_at"] = datetime.now().isoformat()
        _snapshot_generation_state["finished_at"] = None
        _snapshot_generation_state["last_error"] = None
        _snapshot_generation_state["last_as_of_date"] = as_of_date

    try:
        service = get_dashboard_snapshot_service()
        service.generate_snapshot(as_of_date=as_of_date, source=source)
    except Exception as exc:
        logger.error("Dashboard snapshot generation failed: %s", exc, exc_info=True)
        _snapshot_generation_state["last_error"] = str(exc)
    finally:
        _snapshot_generation_state["running"] = False
        _snapshot_generation_state["finished_at"] = datetime.now().isoformat()


@router.get("/dashboard-snapshots/status")
def get_dashboard_snapshot_status():
    """Get active dashboard snapshot metadata and generator status."""
    from app.services.dashboard_snapshot_service import get_dashboard_snapshot_service

    service = get_dashboard_snapshot_service()
    return {
        "generator": dict(_snapshot_generation_state),
        "active_snapshot": service.get_snapshot_status(),
    }


@router.post("/dashboard-snapshots/generate")
def generate_dashboard_snapshot(request: DashboardSnapshotGenerateRequest = Body(default=DashboardSnapshotGenerateRequest())):
    """Generate Team/Scrum/Employee dashboard snapshot for selected as-of date.

    as_of_date accepts YYYYMMDD or YYYY-MM-DD.
    """
    if _snapshot_generation_state.get("running"):
        raise HTTPException(status_code=409, detail="Dashboard snapshot generation is already running")

    if request.run_in_background:
        thread = threading.Thread(
            target=_generate_dashboard_snapshot_task,
            kwargs={"as_of_date": request.as_of_date, "source": "manual"},
            daemon=True,
            name="dashboard-snapshot-generator",
        )
        thread.start()
        return {
            "success": True,
            "message": "Dashboard snapshot generation started",
            "as_of_date": request.as_of_date,
            "running": True,
        }

    _generate_dashboard_snapshot_task(request.as_of_date, source="manual")
    if _snapshot_generation_state.get("last_error"):
        raise HTTPException(status_code=500, detail=_snapshot_generation_state["last_error"])
    return {
        "success": True,
        "message": "Dashboard snapshot generated",
        "as_of_date": request.as_of_date,
        "running": False,
    }


@router.get("/resource-usage")
async def get_resource_usage() -> dict[str, Any]:
    """Return memory/CPU usage for running processes and in-memory cache stats.
    Does NOT refresh caches — call POST /cache/refresh explicitly when needed.
    """
    from app.api.reports import (
        _jira_data_cache,
        JIRA_ISSUES_FILE,
        JIRA_HISTORY_FILE,
        EPIC_TREE_OUTPUT_DIR,
    )
    import app.api.replan_tracker as _replan_mod
    import app.api.assignee_delay_report as _adr_mod

    # ── Process metrics ──────────────────────────────────────────────────────
    def _proc_info(pid: int) -> dict[str, Any]:
        if not _PSUTIL_AVAILABLE or pid is None:
            return {"available": False}
        try:
            p = psutil.Process(pid)
            with p.oneshot():
                mem = p.memory_info()
                cpu = p.cpu_percent(interval=0.1)
                create_time = p.create_time()
                uptime_seconds = int(time.time() - create_time)
            return {
                "available": True,
                "pid": pid,
                "cpu_percent": round(cpu, 1),
                "memory_rss_mb": round(mem.rss / 1024 / 1024, 1),
                "memory_vms_mb": round(mem.vms / 1024 / 1024, 1),
                "memory_percent": round(p.memory_percent(), 1),
                "uptime_seconds": uptime_seconds,
                "threads": p.num_threads(),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {"available": False}

    scheduler = get_scheduler()
    services_info = await scheduler.get_service_info()
    process_metrics: list[dict[str, Any]] = []
    for svc in services_info:
        info = _proc_info(getattr(svc, 'pid', None))
        info["name"] = getattr(svc, 'name', '')
        info["port"] = getattr(svc, 'port', None)
        info["status"] = getattr(svc, 'status', '')
        process_metrics.append(info)

    # System-level memory
    system_mem: dict[str, Any] = {"available": False}
    if _PSUTIL_AVAILABLE:
        vm = psutil.virtual_memory()
        system_mem = {
            "available": True,
            "total_mb": round(vm.total / 1024 / 1024, 1),
            "used_mb": round(vm.used / 1024 / 1024, 1),
            "available_mb": round(vm.available / 1024 / 1024, 1),
            "percent": vm.percent,
        }

    # ── In-memory cache stats ────────────────────────────────────────────────
    def _df_size_mb(df: Any) -> float:
        try:
            return round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2)
        except Exception:
            return 0.0

    jira_df = _jira_data_cache.get("df")
    jira_mtimes = _jira_data_cache.get("mtimes")
    jira_loaded_at: str | None = None
    if jira_mtimes and isinstance(jira_mtimes, dict):
        latest_mtime = max((v for v in jira_mtimes.values() if v), default=None)
        if latest_mtime:
            jira_loaded_at = datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat()

    replan_df = _replan_mod._replan_cache
    replan_loaded_at: str | None = None
    if _replan_mod._replan_cache_mtime:
        replan_loaded_at = datetime.fromtimestamp(_replan_mod._replan_cache_mtime, tz=timezone.utc).isoformat()

    adr_df = _adr_mod._assignee_delay_cache
    adr_loaded_at: str | None = None
    if _adr_mod._assignee_delay_cache_mtime:
        adr_loaded_at = datetime.fromtimestamp(_adr_mod._assignee_delay_cache_mtime, tz=timezone.utc).isoformat()

    memory_caches = [
        {
            "name": "JIRA Issue Data",
            "description": "Enriched JIRAIssues.csv with delay, team, and sprint metrics",
            "loaded": jira_df is not None,
            "rows": int(len(jira_df)) if jira_df is not None else 0,
            "size_mb": _df_size_mb(jira_df) if jira_df is not None else 0.0,
            "loaded_at": jira_loaded_at,
        },
        {
            "name": "Replan Tracker",
            "description": "replan_tracker.csv with epic and description enrichment",
            "loaded": replan_df is not None,
            "rows": int(len(replan_df)) if replan_df is not None else 0,
            "size_mb": _df_size_mb(replan_df) if replan_df is not None else 0.0,
            "loaded_at": replan_loaded_at,
        },
        {
            "name": "Assignee Delay",
            "description": "assignee_attributable_delay.csv with per-assignee delay metrics",
            "loaded": adr_df is not None,
            "rows": int(len(adr_df)) if adr_df is not None else 0,
            "size_mb": _df_size_mb(adr_df) if adr_df is not None else 0.0,
            "loaded_at": adr_loaded_at,
        },
    ]

    # ── On-disk cache stats ──────────────────────────────────────────────────
    def _dir_stats(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"exists": False, "file_count": 0, "total_size_mb": 0.0}
        files = list(path.iterdir())
        total = sum(f.stat().st_size for f in files if f.is_file())
        return {
            "exists": True,
            "file_count": len([f for f in files if f.is_file()]),
            "total_size_mb": round(total / 1024 / 1024, 2),
        }

    epic_dir = EPIC_TREE_OUTPUT_DIR
    epic_workspace_stats = {"exists": False, "file_count": 0, "total_size_mb": 0.0}
    if epic_dir and Path(str(epic_dir)).exists():
        wf = [f for f in Path(str(epic_dir)).iterdir() if f.is_file() and f.name.startswith("epic_") and f.suffix == ".csv"]
        epic_workspace_stats = {
            "exists": True,
            "file_count": len(wf),
            "total_size_mb": round(sum(f.stat().st_size for f in wf) / 1024 / 1024, 2),
        }

    transitions_dir = Path(str(epic_dir)) / "transitions" if epic_dir else None
    transitions_stats = _dir_stats(transitions_dir) if transitions_dir else {"exists": False, "file_count": 0, "total_size_mb": 0.0}

    # Coverage: compare against unique issue keys in JIRAIssues.csv
    issue_count = int(len(jira_df)) if jira_df is not None else 0
    transitions_coverage_pct: float | None = (
        round(transitions_stats["file_count"] / issue_count * 100, 1)
        if issue_count > 0
        else None
    )

    disk_caches = [
        {
            "name": "Epic Workspace Files",
            "description": "Per-epic CSV snapshots (output/EpicTree/epic_*.csv)",
            **epic_workspace_stats,
            "coverage_pct": None,
        },
        {
            "name": "Issue Transition Cache",
            "description": "Per-issue JSON transition history (output/EpicTree/transitions/)",
            **transitions_stats,
            "coverage_pct": transitions_coverage_pct,
        },
    ]

    return {
        "process_metrics": process_metrics,
        "system_memory": system_mem,
        "memory_caches": memory_caches,
        "disk_caches": disk_caches,
        "active_threads": threading.active_count(),
        "psutil_available": _PSUTIL_AVAILABLE,
    }


@router.post("/services/{service_name}/control")
async def control_service(service_name: str, action: str = Query(..., regex="^(start|stop|restart)$")):
    """Control a service (start/stop/restart)"""
    scheduler = get_scheduler()
    
    try:
        result = await scheduler.control_service(service_name, action)
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error controlling service {service_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Notifications ====================

@router.get("/notifications/mail-config", response_model=MailConfigResponse)
def get_mail_config(current_user: TokenData = Depends(require_admin_or_read_api)):
    """Get mail relay configuration used for RBAC notifications."""
    return MailConfigResponse(**notification_mail_service.get_config())


@router.put("/notifications/mail-config", response_model=MailConfigResponse)
def update_mail_config(
    payload: MailConfigUpdateRequest,
    current_user: TokenData = Depends(require_admin),
):
    """Update mail relay configuration used for RBAC notifications."""
    try:
        config = notification_mail_service.update_config(payload.model_dump(exclude_none=True))
        return MailConfigResponse(**config)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/notifications/send-credentials-email")
def send_credentials_email(
    payload: SendCredentialsEmailRequest,
    request: Request,
    current_user: TokenData = Depends(require_admin),
):
    """Send RBAC credential email on explicit user action."""
    mode = (payload.mode or "").strip().lower()
    if mode not in {"create", "reset"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mode must be 'create' or 'reset'")

    target_user = user_service.get_user_by_sapid(str(payload.user_sapid or "").strip())
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target RBAC user not found")

    resolved_to_email = _resolve_employee_email_for_sapid(target_user.sapid, target_user.email)

    result = notification_mail_service.send_credentials_email(
        to_address=resolved_to_email,
        user_name=target_user.name,
        user_sapid=target_user.sapid,
        password=payload.password,
        mode=mode,
        dashboard_url=payload.dashboard_url or _request_dashboard_url(request),
    )

    if result.get("status") == "failed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message") or "Failed to send email")

    return {
        "status": result.get("status"),
        "message": result.get("message"),
    }


def _request_dashboard_url(request: Request) -> str:
    base_url = str(request.base_url).rstrip("/")
    return base_url if base_url else "http://localhost:8000"


def _resolve_employee_email_for_sapid(sapid: str, fallback_email: Optional[str] = None) -> Optional[str]:
    """Prefer employee email from Resources.csv for a SAPID, fallback to RBAC user email."""
    try:
        employee = resources_service.get_employee_by_sapid(str(sapid or "").strip())
        if employee:
            email_value = str(employee.get("email") or "").strip()
            if email_value:
                return email_value
    except Exception:
        pass

    fallback = str(fallback_email or "").strip()
    return fallback or None


# ==================== User Management ====================

@router.get("/users", response_model=List[UserResponse])
def list_users(current_user: TokenData = Depends(require_admin_or_read_api)):
    """List all users (Admin only)"""
    users = user_service.get_all_users()
    return [
        UserResponse(
            id=u.id,
            sapid=u.sapid,
            name=u.name,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            team_ids=u.team_ids,
            managed_user_ids=u.managed_user_ids,
            source=u.source,
            last_login=u.last_login,
            created_at=u.created_at,
            updated_at=u.updated_at
        )
        for u in users
    ]


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, current_user: TokenData = Depends(require_admin_or_read_api)):
    """Get user by ID (Admin only)"""
    user = user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(
        id=user.id,
        sapid=user.sapid,
        name=user.name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        team_ids=user.team_ids,
        managed_user_ids=user.managed_user_ids,
        source=user.source,
        last_login=user.last_login,
        created_at=user.created_at,
        updated_at=user.updated_at
    )


@router.post("/users", response_model=UserCreateResponse)
def create_user(
    user_create: UserCreate,
    request: Request,
    current_user: TokenData = Depends(require_admin)
):
    """Create new user (Admin only)"""
    try:
        user = user_service.create_user(user_create)
        resolved_email = _resolve_employee_email_for_sapid(user.sapid, user.email)
        return UserCreateResponse(
            user=UserResponse(
                id=user.id,
                sapid=user.sapid,
                name=user.name,
                email=resolved_email,
                role=user.role,
                is_active=user.is_active,
                team_ids=user.team_ids,
                managed_user_ids=user.managed_user_ids,
                source=user.source,
                last_login=user.last_login,
                created_at=user.created_at,
                updated_at=user.updated_at
            ),
            email_notification_status="skipped",
            email_notification_message="Email is sent only when Send Email is clicked",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: TokenData = Depends(require_admin)
):
    """Update user (Admin only)"""
    user = user_service.update_user(user_id, user_update)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(
        id=user.id,
        sapid=user.sapid,
        name=user.name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        team_ids=user.team_ids,
        managed_user_ids=user.managed_user_ids,
        source=user.source,
        last_login=user.last_login,
        created_at=user.created_at,
        updated_at=user.updated_at
    )


@router.delete("/users/{user_id}")
def delete_user(user_id: int, current_user: TokenData = Depends(require_admin)):
    """Delete user (Admin only)"""
    if user_service.delete_user(user_id):
        logger.info(f"User deleted: {user_id}")
        return {"message": "User deleted successfully"}
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="User not found"
    )


@router.post("/users/{user_id}/reset-password", response_model=UserPasswordReset)
def reset_user_password(
    user_id: int,
    request: Request,
    current_user: TokenData = Depends(require_admin),
):
    """Reset user password to new default (Admin only)"""
    user = user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    new_password = user_service.reset_password(user_id)
    if not new_password:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    resolved_email = _resolve_employee_email_for_sapid(user.sapid, user.email)

    return UserPasswordReset(
        new_password=new_password,
        user_email=resolved_email,
        user_name=user.name,
        user_sapid=user.sapid,
        email_notification_status="skipped",
        email_notification_message="Email is sent only when Send Email is clicked",
    )


# ==================== Role Management ====================

@router.get("/roles", response_model=dict)
def list_all_roles(current_user: TokenData = Depends(require_admin_or_read_api)):
    """List all roles (built-in and custom) (Admin only)"""
    all_roles = role_service.get_all_roles()
    return {
        "built_in": all_roles["built_in"],
        "custom": all_roles["custom"]
    }


@router.get("/roles/available-permissions", response_model=List[str])
def get_available_permissions(current_user: TokenData = Depends(require_admin_or_read_api)):
    """Get all available permissions (Admin only)"""
    return role_service.get_all_available_permissions()


@router.get("/roles/{role_name}", response_model=RoleResponse)
def get_role(role_name: str, current_user: TokenData = Depends(require_admin_or_read_api)):
    """Get role by name (Admin only)"""
    role = role_service.get_role(role_name)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    return RoleResponse(
        name=role["name"],
        permissions=role["permissions"],
        is_built_in=role["is_built_in"]
    )


@router.get("/roles-available-permissions", response_model=List[str])
def get_available_permissions_legacy(current_user: TokenData = Depends(require_admin_or_read_api)):
    """Backward-compatible endpoint for available permissions."""
    return role_service.get_all_available_permissions()


@router.post("/roles", response_model=RoleResponse)
def create_role(
    role_data: dict,  # { "name": str, "permissions": List[str] }
    current_user: TokenData = Depends(require_admin)
):
    """Create custom role (Admin only)"""
    role_name = role_data.get("name")
    permissions = role_data.get("permissions", [])
    
    if not role_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role name is required"
        )
    
    if not role_service.create_custom_role(role_name, permissions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create role (may already exist or be built-in)"
        )
    
    return RoleResponse(
        name=role_name,
        permissions=permissions,
        is_built_in=False
    )


@router.put("/roles/{role_name}", response_model=RoleResponse)
def update_role(
    role_name: str,
    role_data: dict,  # { "permissions": List[str] }
    current_user: TokenData = Depends(require_admin)
):
    """Update custom role (Admin only)"""
    permissions = role_data.get("permissions", [])
    
    if not role_service.update_custom_role(role_name, permissions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update role (may not exist or be built-in)"
        )
    
    return RoleResponse(
        name=role_name,
        permissions=permissions,
        is_built_in=False
    )


@router.delete("/roles/{role_name}")
def delete_role(role_name: str, current_user: TokenData = Depends(require_admin)):
    """Delete custom role (Admin only)"""
    if not role_service.delete_custom_role(role_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to delete role (may not exist or be built-in)"
        )
    
    logger.info(f"Role deleted: {role_name}")
    return {"message": "Role deleted successfully"}


# ==================== Backup Management ====================

@router.get("/backups")
def list_backups() -> dict:
    """List all backup folders (daily_backup_* and full_backup_*) with minimal metadata.
    
    Ultra-fast: Only extracts name, type, and timestamp from folder name.
    No file traversal required.
    """
    if not BACKUP_DIR.exists():
        return {"backups": []}
    
    backups = []
    for item in sorted(BACKUP_DIR.iterdir(), key=lambda p: p.name, reverse=True):
        if not item.is_dir():
            continue
        if not (item.name.startswith("daily_backup_") or item.name.startswith("full_backup_")):
            continue
        
        # Extract timestamp from folder name: daily_backup_YYYYMMDD_HHMMSS or similar
        created_at_local = None
        try:
            name = item.name
            # Extract the timestamp portion after the backup type prefix
            if "daily_backup_" in name:
                ts_match = name.replace("daily_backup_", "")
            elif "full_backup_catchup_" in name:
                ts_match = name.replace("full_backup_catchup_", "")
            else:  # full_backup_
                ts_match = name.replace("full_backup_", "")
            
            # Parse YYYYMMDD_HHMMSS format
            if len(ts_match) >= 15:  # YYYYMMDD_HHMMSS
                date_part = ts_match[:8]
                time_part = ts_match[9:15]
                
                # Construct datetime string: YYYY-MM-DD HH:MM:SS
                created_at_local = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
        except Exception:
            pass
        
        # Derive backup type for the UI
        if item.name.startswith("full_backup_catchup_"):
            backup_type = "full_catchup"
        elif item.name.startswith("full_backup_"):
            backup_type = "full"
        else:
            backup_type = "daily"
        
        backups.append({
            "name": item.name,
            "created_at": created_at_local,
            "backup_type": backup_type,
        })
    return {"backups": backups}


@router.delete("/backups")
def delete_backups(request: BackupDeleteRequest) -> dict:
    """Delete the specified backup folders by name."""
    names = request.names
    if not BACKUP_DIR.exists():
        return {"deleted": [], "errors": ["Backup directory not found"]}
    deleted = []
    errors = []
    for name in names:
        if not (name.startswith("daily_backup_") or name.startswith("full_backup_")) or ".." in name or "/" in name or os.sep in name:
            errors.append(f"Invalid backup name: {name}")
            continue
        target = BACKUP_DIR / name
        if not target.exists():
            errors.append(f"Not found: {name}")
            continue
        try:
            shutil.rmtree(target)
            deleted.append(name)
            logger.info("Deleted backup folder: %s", name)
        except Exception as exc:
            errors.append(f"Failed to delete {name}: {exc}")
    return {"deleted": deleted, "errors": errors}


# ==================== On-demand Full Backup ====================

@router.post("/backup/full-backup")
async def trigger_full_backup():
    """Trigger an on-demand full backup (copies entire output/ directory).
    Sets a flag file that makes the daily_backup_matrix job run in full-backup mode,
    then triggers the job immediately.
    """
    scheduler = get_scheduler()
    job = scheduler.jobs.get("daily_backup_matrix")
    if not job:
        raise HTTPException(status_code=404, detail="daily_backup_matrix job not found")

    # Temporarily override the job command to include --full-backup flag.
    # The override is applied to a copy so the scheduled (non-full) command is preserved.
    import shlex
    original_command = job.command
    full_backup_command = original_command
    # Insert --full-backup before the end of the command if not already present
    if "--full-backup" not in full_backup_command:
        full_backup_command = full_backup_command + " --full-backup"
    job.command = full_backup_command

    try:
        from app.models.job import JobStatus
        progress = scheduler.job_progress.get("daily_backup_matrix")
        if progress and progress.status == JobStatus.RUNNING:
            job.command = original_command  # restore before raising
            raise HTTPException(status_code=409, detail="daily_backup_matrix is already running")

        execution_id = await scheduler.trigger_job("daily_backup_matrix", triggered_by="manual-full-backup")
        logger.info("On-demand full backup triggered: execution_id=%s", execution_id)
        return {"success": True, "execution_id": execution_id, "message": "Full backup triggered"}
    finally:
        # Restore original command regardless of outcome so scheduled runs keep standard behaviour
        job.command = original_command


# ==================== Audit Log Maintenance ====================

@router.get("/audit-logs/stats")
def get_audit_log_stats() -> dict:
    """Return simple audit log statistics for maintenance UI."""
    return {
        "total_events": audit_trail_service.get_total_event_count(),
        "audit_file": str(audit_trail_service.audit_file),
    }


@router.post("/audit-logs/trim")
def trim_audit_logs(request: AuditLogTrimRequest) -> dict:
    """Trim audit log JSON by latest count or age cutoff (date/month/year)."""
    mode = (request.trim_mode or "").strip().lower()

    if not mode and request.keep_latest is not None:
        mode = "keep_latest"

    if mode in {"", "keep_latest"}:
        keep_latest = int(request.keep_latest if request.keep_latest is not None else 0)
        if keep_latest < 0:
            raise HTTPException(status_code=400, detail="keep_latest must be >= 0")

        result = audit_trail_service.trim_events(keep_latest=keep_latest)
        logger.info(
            "Audit log trimmed by count: keep_latest=%s removed=%s remaining=%s",
            keep_latest,
            result.get("removed"),
            result.get("after_count"),
        )
        return {
            "success": True,
            "mode": "keep_latest",
            "keep_latest": keep_latest,
            **result,
        }

    if mode == "before_date":
        raw_date = (request.date or "").strip()
        if not raw_date:
            raise HTTPException(status_code=400, detail="date is required for trim_mode=before_date")
        try:
            cutoff_utc = datetime.strptime(raw_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="date must be in YYYY-MM-DD format")

        result = audit_trail_service.trim_events_before(cutoff_utc=cutoff_utc)
        logger.info(
            "Audit log trimmed by date: cutoff=%s removed=%s remaining=%s",
            raw_date,
            result.get("removed"),
            result.get("after_count"),
        )
        return {
            "success": True,
            "mode": "before_date",
            "cutoff": raw_date,
            **result,
        }

    if mode == "before_month":
        raw_month = (request.month or "").strip()
        if not raw_month:
            raise HTTPException(status_code=400, detail="month is required for trim_mode=before_month")
        try:
            cutoff_utc = datetime.strptime(raw_month, "%Y-%m").replace(day=1, tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="month must be in YYYY-MM format")

        result = audit_trail_service.trim_events_before(cutoff_utc=cutoff_utc)
        logger.info(
            "Audit log trimmed by month: cutoff=%s removed=%s remaining=%s",
            raw_month,
            result.get("removed"),
            result.get("after_count"),
        )
        return {
            "success": True,
            "mode": "before_month",
            "cutoff": raw_month,
            **result,
        }

    if mode == "before_year":
        if request.year is None:
            raise HTTPException(status_code=400, detail="year is required for trim_mode=before_year")
        year = int(request.year)
        if year < 1970 or year > 3000:
            raise HTTPException(status_code=400, detail="year must be between 1970 and 3000")

        cutoff_utc = datetime(year, 1, 1, tzinfo=timezone.utc)
        result = audit_trail_service.trim_events_before(cutoff_utc=cutoff_utc)
        logger.info(
            "Audit log trimmed by year: cutoff=%s removed=%s remaining=%s",
            year,
            result.get("removed"),
            result.get("after_count"),
        )
        return {
            "success": True,
            "mode": "before_year",
            "cutoff": year,
            **result,
        }

    raise HTTPException(
        status_code=400,
        detail="trim_mode must be one of: keep_latest, before_date, before_month, before_year",
    )


# ==================== JIRA Fetch Delta Mode Control ====================

class JiraFetchFullFetchRequest(BaseModel):
    projects: List[str]  # ["__ALL__"] for all projects, or list of specific project IDs


@router.get("/jira-fetch/status")
def get_jira_fetch_status():
    """Return JIRA fetch checkpoint data: per-project last-run timestamps and forceFullFetch flags."""
    checkpoint_path = PROJECT_ROOT / "data" / "jira_fetch_checkpoint.json"
    jira_config_path = PROJECT_ROOT / "config" / "jira_config.json"

    configured_projects: list = []
    if jira_config_path.exists():
        try:
            with open(jira_config_path, "r", encoding="utf-8") as fh:
                jira_cfg = json.load(fh)
            configured_projects = list(jira_cfg.get("projects", {}).keys())
        except Exception:
            pass

    if not checkpoint_path.exists():
        return {
            "configuredProjects": configured_projects,
            "projectLastFetchTimestamp": {},
            "forceFullFetch": [],
            "projectTokens": {},
        }
    try:
        with open(checkpoint_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {
            "configuredProjects": configured_projects,
            "projectLastFetchTimestamp": data.get("projectLastFetchTimestamp", {}),
            "forceFullFetch": data.get("forceFullFetch", []),
            "projectTokens": {k: bool(v) for k, v in data.get("projectTokens", {}).items()},
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read JIRA checkpoint: {exc}")


@router.post("/jira-fetch/force-full-fetch")
def set_jira_force_full_fetch(request: JiraFetchFullFetchRequest):
    """Mark projects for a forced full re-fetch on the next jira_fetch run.
    Pass projects=["__ALL__"] to force all, or a list of specific project IDs.
    An empty list clears all forced full-fetch flags (reverts to delta mode).
    """
    checkpoint_path = PROJECT_ROOT / "data" / "jira_fetch_checkpoint.json"
    try:
        if checkpoint_path.exists():
            with open(checkpoint_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = {
                "currentProjectIndex": 0,
                "projectTokens": {},
                "projectLastFetchTimestamp": {},
                "forceFullFetch": [],
            }
        data["forceFullFetch"] = request.projects
        temp = str(checkpoint_path) + ".tmp"
        with open(temp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(temp, str(checkpoint_path))
        logger.info("JIRA fetch forceFullFetch set to: %s", request.projects)
        return {"success": True, "forceFullFetch": data["forceFullFetch"]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update JIRA checkpoint: {exc}")


@router.delete("/jira-fetch/force-full-fetch")
def clear_jira_force_full_fetch():
    """Clear all forced full-fetch flags — reverts all projects to delta mode for the next run."""
    checkpoint_path = PROJECT_ROOT / "data" / "jira_fetch_checkpoint.json"
    try:
        if checkpoint_path.exists():
            with open(checkpoint_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            data["forceFullFetch"] = []
            temp = str(checkpoint_path) + ".tmp"
            with open(temp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(temp, str(checkpoint_path))
        logger.info("JIRA fetch forceFullFetch cleared")
        return {"success": True, "forceFullFetch": []}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to clear JIRA force-full-fetch: {exc}")


# ==================== User Sync ====================

@router.post("/users-sync", response_model=SyncResponse)
@router.post("/users/sync", response_model=SyncResponse)
def sync_users(current_user: TokenData = Depends(require_admin)):
    """Sync users from Resources.csv (Admin only, add-only)"""
    result = sync_service.sync_users()
    logger.info(f"User sync: created={result['created']}, updated={result['updated']}")
    
    return SyncResponse(
        created=result["created"],
        updated=result["updated"],
        errors=result.get("errors", [])
    )


# ==================== Dashboard Message Ticker ====================

@router.get("/dashboard-messages")
def list_dashboard_messages(current_user: TokenData = Depends(require_admin_or_read_api)):
    """List all dashboard ticker messages with computed active/expiry state."""
    messages = [serialize_message_for_admin(message) for message in load_messages()]
    messages.sort(key=lambda m: str(m.get("created_at", "")), reverse=True)
    return {"success": True, "messages": messages}


@router.get("/dashboard-messages/options")
def get_dashboard_message_target_options(current_user: TokenData = Depends(require_admin_or_read_api)):
    """Return team/scrum/employee target options from Resources.csv."""
    resources_file = PROJECT_ROOT / "config" / "Resources.csv"
    teams: set[str] = set()
    scrums: set[str] = set()
    employees: list[dict[str, str]] = []
    resource_fields: list[str] = []

    if not resources_file.exists():
        return {
            "success": True,
            "teams": [],
            "scrums": [],
            "employees": [],
            "resource_fields": [],
            "placeholders": get_supported_placeholders([]),
            "placeholder_categories": get_placeholder_categories([]),
        }

    with open(resources_file, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        resource_fields = [str(field).strip() for field in (reader.fieldnames or []) if str(field).strip()]
        for row in reader:
            sapid = str(row.get("SAPID", "")).strip()
            name = str(row.get("Name", "")).strip()
            team = str(row.get("Team", "")).strip()
            scrum = str(row.get("Scrum", "")).strip()

            if team:
                teams.add(team)
            if scrum:
                scrums.add(scrum)
            if sapid and name:
                employees.append({"sapid": sapid, "name": name, "team": team, "scrum": scrum})

    employees.sort(key=lambda emp: (emp.get("name", "").lower(), emp.get("sapid", "")))
    return {
        "success": True,
        "teams": sorted(teams),
        "scrums": sorted(scrums),
        "employees": employees,
        "resource_fields": resource_fields,
        "placeholders": get_supported_placeholders(resource_fields),
        "placeholder_categories": get_placeholder_categories(resource_fields),
    }


@router.post("/dashboard-messages")
def create_dashboard_message(payload: DashboardMessagePayload, current_user: TokenData = Depends(require_admin)):
    """Create a new dashboard ticker message."""
    messages = load_messages()
    try:
        message = normalize_message_payload(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    messages.append(message)
    save_messages(messages)
    return {"success": True, "message": serialize_message_for_admin(message)}


@router.put("/dashboard-messages/{message_id}")
def update_dashboard_message(
    message_id: str,
    payload: DashboardMessagePayload,
    current_user: TokenData = Depends(require_admin),
):
    """Update an existing dashboard ticker message."""
    messages = load_messages()
    index = next((idx for idx, item in enumerate(messages) if str(item.get("id")) == message_id), -1)
    if index < 0:
        raise HTTPException(status_code=404, detail="Message not found")

    existing = messages[index]
    merged_payload = {**existing, **payload.model_dump()}

    try:
        updated = normalize_message_payload(merged_payload, existing_id=message_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    updated["created_at"] = existing.get("created_at") or updated.get("created_at")
    messages[index] = updated
    save_messages(messages)
    return {"success": True, "message": serialize_message_for_admin(updated)}


@router.delete("/dashboard-messages/{message_id}")
def delete_dashboard_message(message_id: str, current_user: TokenData = Depends(require_admin)):
    """Delete a dashboard ticker message."""
    messages = load_messages()
    next_messages = [item for item in messages if str(item.get("id")) != message_id]
    if len(next_messages) == len(messages):
        raise HTTPException(status_code=404, detail="Message not found")

    save_messages(next_messages)
    return {"success": True, "message": "Dashboard message deleted"}
