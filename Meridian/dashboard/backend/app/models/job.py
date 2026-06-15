"""
Job models for task scheduling and execution tracking
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class JobStatus(str, Enum):
    """Job execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    """Types of jobs that can be scheduled"""
    JIRA_FETCH = "jira_fetch"
    JIRA_EPIC_TREE_CACHE = "jira_epic_tree_cache"
    GITHUB_FETCH = "github_fetch"
    GITLAB_FETCH = "gitlab_fetch"
    KPI_COMPUTATION = "kpi_computation"
    DAILY_BACKUP_MATRIX = "daily_backup_matrix"
    BUG_CYCLE_TIME = "bug_cycle_time"
    REPLAN_TRACKER = "replan_tracker"
    ASSIGNEE_ATTRIBUTABLE_DELAY = "assignee_attributable_delay"
    SECURITY_SCAN_FETCH = "security_scan_fetch"
    COPILOT_METRICS_FETCH = "copilot_metrics_fetch"
    GIT_ACTIVITY_CACHE = "git_activity_cache"
    HEALTH_CHECK = "health_check"
    RUN_ALL_CHAIN = "run_all_chain"


class JobSchedule(BaseModel):
    """Job scheduling configuration"""
    enabled: bool = True
    cron_expression: Optional[str] = None  # e.g., "0 2 * * *" for 2 AM daily
    interval_minutes: Optional[int] = None  # Alternative to cron
    

class JobConfig(BaseModel):
    """Job configuration"""
    job_id: str
    job_type: JobType
    name: str
    description: str
    schedule: Optional[JobSchedule] = None
    command: str  # Shell command to execute
    working_dir: str  # Working directory for the command
    timeout_minutes: int = 60
    enabled: bool = True
    parameters: Dict[str, Any] = Field(default_factory=dict)
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[JobStatus] = None
    last_run_duration_seconds: Optional[float] = None
    last_run_exit_code: Optional[int] = None
    last_triggered_by: Optional[str] = None


class JobProgress(BaseModel):
    """Job execution progress"""
    job_id: str
    status: JobStatus
    progress_percent: int = 0
    current_step: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    output_lines: List[str] = Field(default_factory=list)  # Last N lines of output


class JobExecution(BaseModel):
    """Job execution record"""
    execution_id: str
    job_id: str
    status: JobStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    exit_code: Optional[int] = None
    output: str = ""
    error: str = ""
    triggered_by: str = "system"  # "system" or "manual"


class JobTriggerRequest(BaseModel):
    """Request to trigger a job manually"""
    job_id: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class HealthCheckResult(BaseModel):
    """Health check result for a service"""
    service_name: str
    status: str  # "healthy", "unhealthy", "unknown"
    message: str = ""
    response_time_ms: Optional[float] = None
    checked_at: datetime = Field(default_factory=datetime.now)
    details: Dict[str, Any] = Field(default_factory=dict)


class ServiceInfo(BaseModel):
    """Service information"""
    name: str
    description: str
    port: int
    process_name: str
    start_command: str
    stop_command: str
    restart_command: str
    working_dir: str
    status: str  # "running", "stopped", "unknown"
    pid: Optional[int] = None
    health_url: str


class ServiceControlRequest(BaseModel):
    """Request to control a service"""
    service_name: str
    action: str  # "start", "stop", "restart"
