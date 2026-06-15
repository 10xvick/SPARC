"""
Job scheduler service using APScheduler
"""
import asyncio
import subprocess
import os
import uuid
import sys
import shutil
import shlex
import json
from datetime import datetime
from typing import Dict, Optional, List, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.models.job import (
    JobConfig, JobProgress, JobExecution, JobStatus, JobType, HealthCheckResult, JobSchedule
)
import logging

logger = logging.getLogger(__name__)


class JobScheduler:
    """Manages scheduled and on-demand job execution"""
    SECURITY_SCAN_DEFAULT_CRON = "30 4 * * *"
    SECURITY_SCAN_KPI_DEFAULT_CRON = "0 5 * * *"
    KPI_COMPUTATION_DEFAULT_CRON = "0 5 * * *"
    SECURITY_SCAN_KPI_JOB_ID = "security_scan_kpi_refresh"
    
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.scheduler = AsyncIOScheduler()
        self.jobs: Dict[str, JobConfig] = {}
        self.job_progress: Dict[str, JobProgress] = {}
        self.job_history: List[JobExecution] = []
        self.max_history = 100
        self.state_file = os.path.join(self.project_root, "data", "scheduler_state.json")
        self.run_all_status: dict = {
            "running": False,
            "current_job_id": None,
            "completed": [],
            "skipped": [],
            "failed": [],
            "pending": [],
            "started_at": None,
            "finished_at": None,
        }
        self._running_processes: Dict[str, Any] = {}
        self._initialize_jobs()
        self._load_persisted_state()
        self._persist_state()

    def _resolve_job_python(self) -> str:
        """Resolve the best Python executable for scheduled jobs."""
        candidates = [
            os.path.join(self.project_root, '.venv', 'bin', 'python'),
            os.path.join(self.project_root, 'dashboard', 'backend', 'venv', 'bin', 'python'),
        ]

        active_venv = os.environ.get("VIRTUAL_ENV")
        if active_venv:
            candidates.append(os.path.join(active_venv, 'bin', 'python'))

        for candidate in candidates:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

        return shutil.which("python3") or shutil.which("python") or sys.executable

    def _resolve_timeout_minutes(self, env_var: str, default_minutes: int) -> int:
        """Resolve timeout minutes from environment with validation."""
        raw_value = os.environ.get(env_var)
        if not raw_value:
            return default_minutes

        try:
            parsed_value = int(raw_value)
            if parsed_value < 1:
                raise ValueError("must be >= 1")
            return parsed_value
        except Exception:
            logger.warning(
                "Invalid %s=%r; using default timeout %s minutes",
                env_var,
                raw_value,
                default_minutes,
            )
            return default_minutes

    def _resolve_cron_expression(self, env_var: str, default_expression: str) -> str:
        """Resolve cron expression from environment with validation."""
        raw_value = os.environ.get(env_var)
        expression = (raw_value or default_expression).strip()

        try:
            CronTrigger.from_crontab(expression)
            return expression
        except Exception:
            logger.warning(
                "Invalid %s=%r; using default cron expression %r",
                env_var,
                raw_value,
                default_expression,
            )
            return default_expression

    def _build_job_command(self, python_executable: str, script_name: str, args: str = "", module_name: Optional[str] = None) -> str:
        """Build job command using src script when available, fallback to installed module."""
        script_path = os.path.join(self.project_root, "src", script_name)
        script_args = f" {args}" if args else ""
        project_root_env = f"TEAMSIGHT_HOME={shlex.quote(self.project_root)}"
        quoted_python = shlex.quote(python_executable)

        if os.path.isfile(script_path):
            return f"{project_root_env} {quoted_python} src/{script_name}{script_args}"

        fallback_module = module_name or os.path.splitext(script_name)[0]
        fallback_command = f"{project_root_env} {quoted_python} -m {fallback_module}{script_args}"
        logger.warning(
            "Script not found at %s, using module fallback command: %s",
            script_path,
            fallback_command,
        )
        return fallback_command

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        """Parse an ISO datetime string safely."""
        if not value:
            return None

        try:
            normalized = value.replace("Z", "+00:00") if isinstance(value, str) else value
            return datetime.fromisoformat(normalized)
        except Exception:
            return None

    def _persist_state(self):
        """Persist scheduler state to disk."""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

            jobs_state = {}
            for job_id, job in self.jobs.items():
                schedule_payload = job.schedule.model_dump(mode="json") if job.schedule else None
                last_status = job.last_run_status.value if isinstance(job.last_run_status, JobStatus) else job.last_run_status
                jobs_state[job_id] = {
                    "schedule": schedule_payload,
                    "enabled": job.enabled,
                    "timeout_minutes": job.timeout_minutes,
                    "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
                    "last_run_status": last_status,
                    "last_run_duration_seconds": job.last_run_duration_seconds,
                    "last_run_exit_code": job.last_run_exit_code,
                    "last_triggered_by": job.last_triggered_by,
                }

            state_payload = {
                "version": 1,
                "updated_at": datetime.now().isoformat(),
                "jobs": jobs_state,
                "history": [execution.model_dump(mode="json") for execution in self.job_history[-self.max_history:]],
            }

            temp_file = f"{self.state_file}.tmp"
            with open(temp_file, "w", encoding="utf-8") as handle:
                json.dump(state_payload, handle, indent=2)
            os.replace(temp_file, self.state_file)
        except Exception as exc:
            logger.error(f"Failed to persist scheduler state: {exc}", exc_info=True)

    async def _run_all_chain_scheduled(self) -> None:
        """APScheduler callback that fires run_all_jobs_sequential without overlapping."""
        if self.run_all_status.get("running"):
            logger.info("run_all_chain scheduled trigger: skipped — already running")
            return
        logger.info("run_all_chain: starting scheduled sequential run")
        await self.run_all_jobs_sequential(triggered_by="scheduled")

    def _apply_schedule(self, job_id: str, schedule: Optional[JobSchedule], persist_state: bool = True) -> bool:
        """Apply a schedule to a job and register/unregister APScheduler trigger."""
        job = self.jobs.get(job_id)
        if not job:
            return False

        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        if schedule and schedule.enabled and (schedule.cron_expression or schedule.interval_minutes):
            if schedule.cron_expression:
                trigger = CronTrigger.from_crontab(schedule.cron_expression)
            elif schedule.interval_minutes:
                trigger = IntervalTrigger(minutes=schedule.interval_minutes)
            else:
                return False

            # run_all_chain fires the full sequential run instead of a subprocess
            if job_id == "run_all_chain":
                callback = self._run_all_chain_scheduled
                self.scheduler.add_job(
                    callback,
                    trigger=trigger,
                    id=job_id,
                    replace_existing=True,
                )
            else:
                self.scheduler.add_job(
                    self._execute_job_async,
                    trigger=trigger,
                    id=job_id,
                    args=[job_id, "scheduled"],
                    replace_existing=True,
                )
            job.schedule = schedule
            logger.info(f"Scheduled job {job_id}: {schedule.model_dump(mode='json')}")
        else:
            job.schedule = None

        if persist_state:
            self._persist_state()

        return True

    def _load_persisted_state(self):
        """Load scheduler state from disk and restore schedules/history."""
        if not os.path.exists(self.state_file):
            return

        try:
            with open(self.state_file, "r", encoding="utf-8") as handle:
                persisted_state = json.load(handle)
        except Exception as exc:
            logger.error(f"Failed to load scheduler state file {self.state_file}: {exc}", exc_info=True)
            return

        jobs_state = persisted_state.get("jobs", {})
        if isinstance(jobs_state, dict):
            for job_id, job_state in jobs_state.items():
                job = self.jobs.get(job_id)
                if not job or not isinstance(job_state, dict):
                    continue

                schedule_state = job_state.get("schedule")
                if isinstance(schedule_state, dict):
                    try:
                        job.schedule = JobSchedule.model_validate(schedule_state)
                    except Exception:
                        logger.warning(f"Ignoring invalid persisted schedule for job {job_id}: {schedule_state}")
                        job.schedule = None
                else:
                    job.schedule = None

                if "enabled" in job_state:
                    job.enabled = bool(job_state.get("enabled"))

                timeout_minutes = job_state.get("timeout_minutes")
                if isinstance(timeout_minutes, int) and timeout_minutes > 0:
                    job.timeout_minutes = timeout_minutes

                job.last_run_at = self._parse_datetime(job_state.get("last_run_at"))

                last_status = job_state.get("last_run_status")
                if isinstance(last_status, str):
                    try:
                        job.last_run_status = JobStatus(last_status)
                    except ValueError:
                        job.last_run_status = None
                else:
                    job.last_run_status = None

                duration_seconds = job_state.get("last_run_duration_seconds")
                job.last_run_duration_seconds = float(duration_seconds) if isinstance(duration_seconds, (int, float)) else None

                exit_code = job_state.get("last_run_exit_code")
                job.last_run_exit_code = int(exit_code) if isinstance(exit_code, int) else None

                last_triggered_by = job_state.get("last_triggered_by")
                job.last_triggered_by = str(last_triggered_by) if isinstance(last_triggered_by, str) else None

        history_entries = persisted_state.get("history", [])
        loaded_history: List[JobExecution] = []
        if isinstance(history_entries, list):
            for entry in history_entries:
                if not isinstance(entry, dict):
                    continue
                try:
                    loaded_history.append(JobExecution.model_validate(entry))
                except Exception:
                    continue

        if loaded_history:
            self.job_history = sorted(loaded_history, key=lambda item: item.started_at)[-self.max_history:]

        # Re-register persisted schedules in APScheduler
        for job_id, job in self.jobs.items():
            if job.schedule and job.schedule.enabled and (job.schedule.cron_expression or job.schedule.interval_minutes):
                self._apply_schedule(job_id, job.schedule, persist_state=False)

        logger.info(f"Loaded persisted scheduler state from {self.state_file}")
        
    def _initialize_jobs(self):
        """Initialize default job configurations"""
        venv_python = self._resolve_job_python()
        jira_fetch_timeout_minutes = self._resolve_timeout_minutes(
            "TEAMSIGHT_JIRA_FETCH_TIMEOUT_MINUTES",
            360,
        )
        epic_tree_cache_timeout_minutes = self._resolve_timeout_minutes(
            "TEAMSIGHT_EPIC_TREE_CACHE_TIMEOUT_MINUTES",
            30,
        )
        daily_backup_timeout_minutes = self._resolve_timeout_minutes(
            "TEAMSIGHT_DAILY_BACKUP_TIMEOUT_MINUTES",
            45,
        )
        daily_backup_cron = self._resolve_cron_expression(
            "TEAMSIGHT_DAILY_BACKUP_CRON",
            "30 5 * * *",
        )
        logger.info(f"Using Python interpreter for scheduled jobs: {venv_python}")
        logger.info(f"JIRA fetch timeout: {jira_fetch_timeout_minutes} minutes")
        logger.info(f"Daily backup schedule: {daily_backup_cron}")
        
        self.jobs = {
            "jira_fetch": JobConfig(
                job_id="jira_fetch",
                job_type=JobType.JIRA_FETCH,
                name="JIRA Issues Fetch",
                description="Fetch JIRA issues from configured projects",
                command=self._build_job_command(venv_python, "jira_fetch.py", "--fetch", "jira_fetch"),
                working_dir=self.project_root,
                timeout_minutes=jira_fetch_timeout_minutes,
                schedule=JobSchedule(enabled=True, cron_expression="30 13 * * *"),
                enabled=True
            ),
            "jira_epic_tree_cache": JobConfig(
                job_id="jira_epic_tree_cache",
                job_type=JobType.JIRA_EPIC_TREE_CACHE,
                name="JIRA Epic Tree Cache",
                description="Precompute Epic Tree CSV cache for report list and epic workspaces",
                command=self._build_job_command(
                    venv_python,
                    "jira_epic_tree_cache_job.py",
                    module_name="jira_epic_tree_cache_job",
                ),
                working_dir=self.project_root,
                timeout_minutes=epic_tree_cache_timeout_minutes,
                schedule=JobSchedule(enabled=True, cron_expression="0 1 * * *"),
                enabled=True
            ),
            "github_fetch": JobConfig(
                job_id="github_fetch",
                job_type=JobType.GITHUB_FETCH,
                name="GitHub Commits Fetch",
                description="Fetch GitHub commits from configured repositories",
                command=self._build_job_command(venv_python, "github_fetch.py", "fetch", "github_fetch"),
                working_dir=self.project_root,
                timeout_minutes=30,
                schedule=JobSchedule(enabled=True, cron_expression="0 2 * * *"),
                enabled=True
            ),
            "gitlab_fetch": JobConfig(
                job_id="gitlab_fetch",
                job_type=JobType.GITLAB_FETCH,
                name="GitLab Commits Fetch",
                description="Fetch GitLab commits from configured repositories into shared commit dataset",
                command=self._build_job_command(venv_python, "gitlab_fetch.py", "fetch", "gitlab_fetch"),
                working_dir=self.project_root,
                timeout_minutes=30,
                schedule=JobSchedule(enabled=True, cron_expression="30 2 * * *"),
                enabled=True
            ),
            "bug_cycle_time": JobConfig(
                job_id="bug_cycle_time",
                job_type=JobType.BUG_CYCLE_TIME,
                name="Bug Cycle Time Analysis",
                description="Compute bug cycle times from JIRA history",
                command=self._build_job_command(venv_python, "kpp_bug_cycle_time.py", module_name="kpp_bug_cycle_time"),
                working_dir=self.project_root,
                timeout_minutes=15,
                schedule=JobSchedule(enabled=True, cron_expression="0 3 * * *"),
                enabled=True
            ),
            "replan_tracker": JobConfig(
                job_id="replan_tracker",
                job_type=JobType.REPLAN_TRACKER,
                name="Replan Tracker Analysis",
                description="Analyze sprint replanning from JIRA data",
                command=self._build_job_command(venv_python, "kpp_replan_tracker.py", module_name="kpp_replan_tracker"),
                working_dir=self.project_root,
                timeout_minutes=15,
                schedule=JobSchedule(enabled=True, cron_expression="30 3 * * *"),
                enabled=True
            ),
            "assignee_attributable_delay": JobConfig(
                job_id="assignee_attributable_delay",
                job_type=JobType.ASSIGNEE_ATTRIBUTABLE_DELAY,
                name="Assignee Attributable Delay",
                description="Calculate attributable delay per assignee across all JIRA issues",
                command=self._build_job_command(venv_python, "kpp_assignee_attributable_delay.py", module_name="kpp_assignee_attributable_delay"),
                working_dir=self.project_root,
                timeout_minutes=20,
                schedule=JobSchedule(enabled=True, cron_expression="0 4 * * *"),
                enabled=True
            ),
            "security_scan_fetch": JobConfig(
                job_id="security_scan_fetch",
                job_type=JobType.SECURITY_SCAN_FETCH,
                name="Security Scan Report Fetch",
                description="Download security scan reports (SAST, SCA, DAST, Mend) from Nexus for configured projects",
                command=self._build_job_command(venv_python, "security_scan_fetch.py", module_name="security_scan_fetch"),
                working_dir=self.project_root,
                timeout_minutes=15,
                schedule=JobSchedule(enabled=True, cron_expression=self.SECURITY_SCAN_DEFAULT_CRON),
                enabled=True
            ),
            "security_scan_kpi_refresh": JobConfig(
                job_id="security_scan_kpi_refresh",
                job_type=JobType.KPI_COMPUTATION,
                name="Security Scan KPI Refresh",
                description="Recompute scan-based KPIs k301-k307 after security scan files are downloaded",
                command=self._build_job_command(
                    venv_python,
                    "KppEvaluator.py",
                    "--kpis k301 k302 k303 k304 k305 k306 k307",
                    "KppEvaluator",
                ),
                working_dir=self.project_root,
                timeout_minutes=20,
                schedule=JobSchedule(enabled=True, cron_expression=self.SECURITY_SCAN_KPI_DEFAULT_CRON),
                enabled=True
            ),
            "kpi_computation_all": JobConfig(
                job_id="kpi_computation_all",
                job_type=JobType.KPI_COMPUTATION,
                name="All KPI Computation",
                description="Run all KPI computation scripts",
                command=self._build_job_command(venv_python, "KppEvaluator.py", module_name="KppEvaluator"),
                working_dir=self.project_root,
                timeout_minutes=60,
                schedule=JobSchedule(enabled=True, cron_expression=self.KPI_COMPUTATION_DEFAULT_CRON),
                enabled=True
            ),
            "daily_backup_matrix": JobConfig(
                job_id="daily_backup_matrix",
                job_type=JobType.DAILY_BACKUP_MATRIX,
                name="Daily Data Backup + Annual KPI Matrix",
                description="Backup key CSV data files, all config files, data/users.json, and generate annual KPI matrix. Additionally generates and backs up the daily employee score comparison report. Full backup of entire output/ runs every Sunday (or as catch-up). Backups older than 31 days are auto-deleted.",
                command=self._build_job_command(
                    venv_python,
                    "daily_backup_matrix_job.py",
                    "--project-root \"{root}\" --check-sunday --retention-days 31".format(root=self.project_root),
                    "daily_backup_matrix_job",
                ),
                working_dir=self.project_root,
                timeout_minutes=daily_backup_timeout_minutes,
                schedule=JobSchedule(enabled=True, cron_expression=daily_backup_cron),
                enabled=True
            ),
            "git_activity_cache": JobConfig(
                job_id="git_activity_cache",
                job_type=JobType.GIT_ACTIVITY_CACHE,
                name="Git Activity Report Cache",
                description="Pre-compute and cache the latest month Git Activity report rows, day columns, and filters. Team and scrum filters then use this cache, while scorecards are computed from commit history when the report is opened. Runs daily after KPI computations.",
                command=self._build_job_command(venv_python, "git_activity_cache_job.py", module_name="git_activity_cache_job"),
                working_dir=self.project_root,
                timeout_minutes=15,
                schedule=JobSchedule(enabled=True, cron_expression="15 5 * * *"),
                enabled=True
            ),
            "copilot_metrics_fetch": JobConfig(
                job_id="copilot_metrics_fetch",
                job_type=JobType.COPILOT_METRICS_FETCH,
                name="Copilot Usage Metrics Collection",
                description="Collect GitHub Copilot usage metrics from Azure SQL Database (test connectivity and list available tables)",
                command=self._build_job_command(venv_python, "copilot_metrics_fetch.py", module_name="copilot_metrics_fetch"),
                working_dir=self.project_root,
                timeout_minutes=15,
                schedule=JobSchedule(enabled=True, cron_expression="15 3 * * *"),
                enabled=True
            ),
            "run_all_chain": JobConfig(
                job_id="run_all_chain",
                job_type=JobType.RUN_ALL_CHAIN,
                name="Run All Jobs (Scheduled)",
                description="Scheduled trigger for the full Run All sequence: all KPI jobs run sequentially in order, followed by a Git Activity base-cache refresh and Team, Scrum, and Employee dashboard snapshot generation.",
                command="",  # Virtual job — runs run_all_jobs_sequential() directly
                working_dir=self.project_root,
                timeout_minutes=600,
                schedule=JobSchedule(enabled=False, cron_expression=None),
                enabled=True
            ),
            "dashboard_snapshot": JobConfig(
                job_id="dashboard_snapshot",
                job_type=JobType.RUN_ALL_CHAIN,
                name="Dashboard Snapshot (Team/Scrum/Employee)",
                description="Pre-compute and activate Team, Scrum, and Employee dashboard snapshots from the latest KPI data. Runs automatically as the final step of Run All Jobs and can also be triggered on demand.",
                command="",  # Virtual job — calls dashboard_snapshot_service.generate_snapshot() directly
                working_dir=self.project_root,
                timeout_minutes=30,
                schedule=JobSchedule(enabled=False, cron_expression=None),
                enabled=True
            ),
        }
        
    def start(self):
        """Start the scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Job scheduler started")
            
    def shutdown(self):
        """Shutdown the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Job scheduler shut down")
            
    def get_job(self, job_id: str) -> Optional[JobConfig]:
        """Get job configuration by ID"""
        return self.jobs.get(job_id)
    
    def list_jobs(self) -> List[JobConfig]:
        """List all job configurations"""
        return list(self.jobs.values())
    
    def update_job_schedule(self, job_id: str, schedule: dict) -> bool:
        """Update job schedule configuration"""
        if job_id not in self.jobs:
            return False

        try:
            schedule_model = JobSchedule.model_validate(schedule)
        except Exception as exc:
            logger.error(f"Invalid schedule payload for job {job_id}: {schedule} ({exc})")
            return False

        return self._apply_schedule(job_id, schedule_model, persist_state=True)
    
    def get_job_progress(self, job_id: str) -> Optional[JobProgress]:
        """Get current progress for a job"""
        return self.job_progress.get(job_id)
    
    def get_job_history(self, job_id: Optional[str] = None, limit: int = 50) -> List[JobExecution]:
        """Get job execution history"""
        if job_id:
            history = [ex for ex in self.job_history if ex.job_id == job_id]
        else:
            history = self.job_history
        return sorted(history, key=lambda x: x.started_at, reverse=True)[:limit]
    
    async def trigger_job(self, job_id: str, triggered_by: str = "manual") -> str:
        """Trigger a job to run immediately"""
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        if not job.enabled:
            raise ValueError(f"Job {job_id} is disabled")

        # Virtual job: run_all_chain delegates to the sequential runner
        if job_id == "run_all_chain":
            await self.run_all_jobs_sequential(triggered_by=triggered_by)
            return "run_all_chain"

        # Virtual job: dashboard_snapshot — generate snapshot synchronously in background
        if job_id == "dashboard_snapshot":
            execution_id = str(uuid.uuid4())
            asyncio.create_task(self._execute_snapshot_job(triggered_by, execution_id))
            return execution_id

        # Check if already running
        progress = self.job_progress.get(job_id)
        if progress and progress.status == JobStatus.RUNNING:
            raise ValueError(f"Job {job_id} is already running")
        
        # Execute in background
        execution_id = str(uuid.uuid4())
        asyncio.create_task(self._execute_job_async(job_id, triggered_by, execution_id))
        
        return execution_id

    async def _execute_snapshot_job(self, triggered_by: str, execution_id: str) -> None:
        """Run dashboard_snapshot as a trackable virtual job."""
        job_id = "dashboard_snapshot"
        started_at = datetime.now()
        self.job_progress[job_id] = JobProgress(
            job_id=job_id,
            status=JobStatus.RUNNING,
            progress_percent=0,
            current_step="Generating dashboard snapshot",
            message="Building pre-aggregated Team and Scrum dashboard payloads…",
            started_at=started_at.isoformat(),
            completed_at=None,
            error_message=None,
            output_lines=[],
        )
        try:
            from app.services.dashboard_snapshot_service import get_dashboard_snapshot_service
            snapshot_service = get_dashboard_snapshot_service()
            result = snapshot_service.generate_snapshot(source=triggered_by)
            completed_at = datetime.now()
            self.job_progress[job_id] = JobProgress(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                progress_percent=100,
                current_step="Done",
                message=f"Snapshot activated: id={result.get('snapshot_id')} as_of={result.get('as_of_date')}",
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                error_message=None,
                output_lines=[],
            )
            duration = (completed_at - started_at).total_seconds()
            job = self.jobs.get(job_id)
            if job:
                job.last_run_at = completed_at
                job.last_run_status = JobStatus.COMPLETED
                job.last_run_duration_seconds = duration
                job.last_triggered_by = triggered_by
            self.job_history.insert(0, JobExecution(
                execution_id=execution_id,
                job_id=job_id,
                status=JobStatus.COMPLETED,
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                duration_seconds=duration,
                exit_code=0,
                triggered_by=triggered_by,
            ))
            logger.info("dashboard_snapshot job completed: %s", result)
        except Exception as exc:
            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()
            self.job_progress[job_id] = JobProgress(
                job_id=job_id,
                status=JobStatus.FAILED,
                progress_percent=0,
                current_step="Error",
                message=str(exc),
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                error_message=str(exc),
                output_lines=[],
            )
            job = self.jobs.get(job_id)
            if job:
                job.last_run_at = completed_at
                job.last_run_status = JobStatus.FAILED
                job.last_run_duration_seconds = duration
                job.last_triggered_by = triggered_by
            self.job_history.insert(0, JobExecution(
                execution_id=execution_id,
                job_id=job_id,
                status=JobStatus.FAILED,
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                duration_seconds=duration,
                exit_code=1,
                triggered_by=triggered_by,
            ))
            logger.error("dashboard_snapshot job failed: %s", exc)
        self.job_history = self.job_history[:self.max_history]

    # ------------------------------------------------------------------ run-all

    RUN_ALL_SEQUENCE = [
        "jira_fetch",
        "github_fetch",
        "gitlab_fetch",
        "jira_epic_tree_cache",
        "bug_cycle_time",
        "replan_tracker",
        "assignee_attributable_delay",
        "copilot_metrics_fetch",
        "security_scan_fetch",
        "security_scan_kpi_refresh",
        "kpi_computation_all",
        "daily_backup_matrix",
        "git_activity_cache",
        "dashboard_snapshot",
    ]

    def get_run_all_status(self) -> dict:
        """Return current run-all status."""
        return dict(self.run_all_status)

    async def run_all_jobs_sequential(self, triggered_by: str = "manual") -> None:
        """Start running all schedulable jobs in sequence (background task)."""
        if self.run_all_status.get("running"):
            raise ValueError("A sequential run is already in progress")

        pending = [jid for jid in self.RUN_ALL_SEQUENCE if jid in self.jobs]
        self.run_all_status = {
            "running": True,
            "current_job_id": None,
            "completed": [],
            "skipped": [],
            "failed": [],
            "pending": list(pending),
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "triggered_by": triggered_by,
        }
        asyncio.create_task(self._run_all_sequential_task(pending))

    async def _run_all_sequential_task(self, sequence: list) -> None:
        """Internal task: run each job in order, waiting for each to finish."""
        try:
            for job_id in sequence:
                # Skip if already running (e.g. triggered by scheduler)
                progress = self.job_progress.get(job_id)
                if progress and progress.status == JobStatus.RUNNING:
                    logger.info(f"run-all: skipping {job_id} — already running")
                    self.run_all_status["skipped"].append(job_id)
                    if job_id in self.run_all_status["pending"]:
                        self.run_all_status["pending"].remove(job_id)
                    continue

                self.run_all_status["current_job_id"] = job_id
                if job_id in self.run_all_status["pending"]:
                    self.run_all_status["pending"].remove(job_id)

                logger.info(f"run-all: triggering {job_id}")
                try:
                    await self.trigger_job(job_id, "run_all")
                except Exception as exc:
                    logger.error(f"run-all: failed to trigger {job_id}: {exc}")
                    self.run_all_status["failed"].append(job_id)
                    continue

                # Wait for the job to leave RUNNING state (poll every 3 s)
                for _ in range(7200):  # max 6 hours
                    await asyncio.sleep(3)
                    p = self.job_progress.get(job_id)
                    if p is None or p.status not in (JobStatus.RUNNING, "running", "pending"):
                        break

                p = self.job_progress.get(job_id)
                status_val = p.status if p else None
                finished_ok = status_val in (JobStatus.COMPLETED, "completed")
                logger.info(f"run-all: {job_id} finished with status {status_val}")
                if finished_ok:
                    self.run_all_status["completed"].append(job_id)
                else:
                    self.run_all_status["failed"].append(job_id)
        finally:
            completed_at = datetime.now()
            self.run_all_status["running"] = False
            self.run_all_status["current_job_id"] = None
            self.run_all_status["finished_at"] = completed_at.isoformat()
            logger.info("run-all: sequence finished")

            # Record completion on the run_all_chain job so it appears in history
            chain_job = self.jobs.get("run_all_chain")
            if chain_job:
                started_at_str = self.run_all_status.get("started_at")
                started_at = datetime.fromisoformat(started_at_str) if started_at_str else completed_at
                chain_job.last_run_at = completed_at
                chain_job.last_run_status = JobStatus.COMPLETED if not self.run_all_status.get("failed") else JobStatus.FAILED
                chain_job.last_run_duration_seconds = (completed_at - started_at).total_seconds()

            # Refresh all in-memory caches now that data files are up-to-date
            try:
                from app.routers.admin import _refresh_all_caches
                results = _refresh_all_caches()
                logger.info("run-all: post-run cache refresh complete: %s", results)
            except Exception as exc:
                logger.warning("run-all: post-run cache refresh failed: %s", exc)

            if chain_job:
                chain_job.last_triggered_by = self.run_all_status.get("triggered_by", "scheduled")
            self._persist_state()

    # ------------------------------------------------------------------ end run-all

    async def cancel_job(self, job_id: str) -> bool:
        """Kill a running job process and mark it cancelled."""
        process = self._running_processes.get(job_id)
        progress = self.job_progress.get(job_id)

        if not process and (not progress or progress.status != JobStatus.RUNNING):
            return False

        if process:
            try:
                process.kill()
            except Exception as exc:
                logger.warning(f"cancel_job {job_id}: could not kill process: {exc}")

        if progress:
            progress.status = JobStatus.CANCELLED
            progress.message = "Job cancelled by user"
            progress.completed_at = datetime.now()

        self._running_processes.pop(job_id, None)
        logger.info(f"Job {job_id} cancelled by user")
        return True

    async def _execute_job_async(self, job_id: str, triggered_by: str = "system", execution_id: Optional[str] = None):
        """Execute a job asynchronously"""
        job = self.jobs.get(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        
        if execution_id is None:
            execution_id = str(uuid.uuid4())
        
        # Initialize progress tracking
        progress = JobProgress(
            job_id=job_id,
            status=JobStatus.RUNNING,
            started_at=datetime.now(),
            message=f"Starting {job.name}...",
            output_lines=[]
        )
        self.job_progress[job_id] = progress
        
        # Create execution record
        execution = JobExecution(
            execution_id=execution_id,
            job_id=job_id,
            status=JobStatus.RUNNING,
            started_at=datetime.now(),
            triggered_by=triggered_by
        )
        
        try:
            logger.info(f"Executing job {job_id}: {job.command}")
            
            # Execute command
            process = await asyncio.create_subprocess_shell(
                job.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=job.working_dir
            )
            self._running_processes[job_id] = process
            
            # Stream output and track progress
            output_lines = []
            async def read_stream(stream, is_stderr=False):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8').strip()
                    if line_str:
                        output_lines.append(line_str)
                        progress.output_lines = output_lines[-50:]  # Keep last 50 lines
                        
                        # Parse progress indicators
                        self._update_progress_from_output(progress, line_str)
            
            # Read both stdout and stderr
            await asyncio.gather(
                read_stream(process.stdout, False),
                read_stream(process.stderr, True)
            )
            
            # Wait for completion with timeout
            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=job.timeout_minutes * 60
                )
                exit_code = process.returncode
            except asyncio.TimeoutError:
                process.kill()
                exit_code = -1
                output_lines.append(f"ERROR: Job timed out after {job.timeout_minutes} minutes")
            
            # Update final status
            if exit_code == 0:
                progress.status = JobStatus.COMPLETED
                progress.progress_percent = 100
                progress.message = f"{job.name} completed successfully"
                execution.status = JobStatus.COMPLETED
            else:
                progress.status = JobStatus.FAILED
                progress.message = f"{job.name} failed with exit code {exit_code}"
                progress.error_message = "\n".join(output_lines[-10:])
                execution.status = JobStatus.FAILED
            
            progress.completed_at = datetime.now()
            execution.completed_at = datetime.now()
            execution.exit_code = exit_code
            execution.output = "\n".join(output_lines)
            execution.duration_seconds = (execution.completed_at - execution.started_at).total_seconds()
            
        except Exception as e:
            logger.error(f"Error executing job {job_id}: {e}", exc_info=True)
            progress.status = JobStatus.FAILED
            progress.error_message = str(e)
            progress.completed_at = datetime.now()
            
            execution.status = JobStatus.FAILED
            execution.completed_at = datetime.now()
            execution.error = str(e)
            execution.duration_seconds = (execution.completed_at - execution.started_at).total_seconds()

        # Clean up process reference
        self._running_processes.pop(job_id, None)

        # Update persisted last-run metadata on the job
        job.last_run_at = execution.completed_at
        job.last_run_status = execution.status
        job.last_run_duration_seconds = execution.duration_seconds
        job.last_run_exit_code = execution.exit_code
        job.last_triggered_by = execution.triggered_by
        
        # Store execution in history
        self.job_history.append(execution)
        if len(self.job_history) > self.max_history:
            self.job_history = self.job_history[-self.max_history:]

        self._persist_state()

        logger.info(f"Job {job_id} completed with status {execution.status}")
    
    def _update_progress_from_output(self, progress: JobProgress, line: str):
        """Parse output line to update progress indicators"""
        line_lower = line.lower()
        
        # Look for percentage indicators
        if "%" in line:
            import re
            match = re.search(r'(\d+)%', line)
            if match:
                progress.progress_percent = int(match.group(1))
        
        # Look for step indicators
        if "step" in line_lower or "processing" in line_lower:
            progress.current_step = line[:100]  # Truncate long lines
        
        # Update message with last meaningful line
        if any(keyword in line_lower for keyword in ["loading", "fetching", "analyzing", "computing", "completed", "error"]):
            progress.message = line[:200]
    
    async def check_service_health(self, service_name: str, url: str) -> HealthCheckResult:
        """Check health of a service"""
        import aiohttp
        
        result = HealthCheckResult(
            service_name=service_name,
            status="unknown"
        )
        
        try:
            start_time = datetime.now()
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    end_time = datetime.now()
                    result.response_time_ms = (end_time - start_time).total_seconds() * 1000
                    
                    if response.status == 200:
                        result.status = "healthy"
                        result.message = "Service is responding"
                        try:
                            data = await response.json()
                            result.details = data
                        except:
                            pass
                    else:
                        result.status = "unhealthy"
                        result.message = f"HTTP {response.status}"
        except asyncio.TimeoutError:
            result.status = "unhealthy"
            result.message = "Request timed out"
        except Exception as e:
            result.status = "unhealthy"
            result.message = str(e)
        
        result.checked_at = datetime.now()
        return result
    
    async def get_service_info(self) -> list:
        """Get information about running services"""
        from app.models.job import ServiceInfo
        import subprocess
        
        services = [
            ServiceInfo(
                name="Backend API",
                description="Dashboard API Server",
                port=8000,
                process_name="uvicorn",
                start_command="cd {root}/dashboard/backend && venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000",
                stop_command="pkill -9 -f 'uvicorn app.main:app'",
                restart_command="pkill -9 -f 'uvicorn app.main:app' && sleep 2 && cd {root}/dashboard/backend && venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 &",
                working_dir=f"{self.project_root}/dashboard/backend",
                status="unknown",
                health_url="http://127.0.0.1:8000/health"
            ),
            ServiceInfo(
                name="Frontend",
                description="Dashboard Web Interface",
                port=5173,
                process_name="vite",
                start_command="cd {root}/dashboard/frontend && npm run dev",
                stop_command="pkill -9 -f 'vite'",
                restart_command="pkill -9 -f 'vite' && sleep 2 && cd {root}/dashboard/frontend && npm run dev &",
                working_dir=f"{self.project_root}/dashboard/frontend",
                status="unknown",
                health_url="http://localhost:5173"
            )
        ]
        
        # Check if services are running
        for service in services:
            try:
                # Check if port is in use
                result = subprocess.run(
                    ["lsof", "-ti", f":{service.port}"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.stdout.strip():
                    service.status = "running"
                    pids = result.stdout.strip().split('\n')
                    if pids:
                        service.pid = int(pids[0])
                else:
                    service.status = "stopped"
            except Exception as e:
                logger.error(f"Error checking service {service.name}: {e}")
                service.status = "unknown"
        
        return services
    
    async def control_service(self, service_name: str, action: str) -> dict:
        """Control a service (start/stop/restart)"""
        import subprocess
        
        services = await self.get_service_info()
        service = next((s for s in services if s.name == service_name), None)
        
        if not service:
            raise ValueError(f"Service {service_name} not found")
        
        try:
            if action == "start":
                if service.status == "running":
                    return {"success": False, "message": f"{service_name} is already running"}
                
                command = service.start_command.replace("{root}", self.project_root)
                logger.info(f"Starting {service_name}: {command}")
                
                # Start service in background
                subprocess.Popen(
                    command,
                    shell=True,
                    cwd=service.working_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                
                return {"success": True, "message": f"{service_name} started successfully"}
                
            elif action == "stop":
                if service.status == "stopped":
                    return {"success": False, "message": f"{service_name} is not running"}
                
                command = service.stop_command
                logger.info(f"Stopping {service_name}: {command}")
                
                subprocess.run(command, shell=True, timeout=10)
                
                return {"success": True, "message": f"{service_name} stopped successfully"}
                
            elif action == "restart":
                command = service.restart_command.replace("{root}", self.project_root)
                logger.info(f"Restarting {service_name}: {command}")
                
                subprocess.run(command, shell=True, timeout=15)
                
                return {"success": True, "message": f"{service_name} restarted successfully"}
            
            else:
                raise ValueError(f"Invalid action: {action}")
                
        except subprocess.TimeoutExpired:
            return {"success": False, "message": f"Timeout while {action}ing {service_name}"}
        except Exception as e:
            logger.error(f"Error controlling service {service_name}: {e}", exc_info=True)
            return {"success": False, "message": str(e)}


# Global scheduler instance
_scheduler: Optional[JobScheduler] = None


def get_scheduler() -> JobScheduler:
    """Get the global scheduler instance"""
    global _scheduler
    if _scheduler is None:
        raise RuntimeError("Scheduler not initialized")
    return _scheduler


def init_scheduler(project_root: str):
    """Initialize the global scheduler"""
    global _scheduler
    _scheduler = JobScheduler(project_root)
    _scheduler.start()
    logger.info("Global scheduler initialized")


def shutdown_scheduler():
    """Shutdown the global scheduler"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
