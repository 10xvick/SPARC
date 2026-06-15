"""
Project Configuration API endpoints for managing GitHub, GitLab and JIRA configurations.
"""
from fastapi import APIRouter, HTTPException, Body, Depends, Request
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import csv
import json
import logging
import os
from pathlib import Path
import re
from app.dependencies import require_admin, require_admin_or_read_api
from app.models.user import TokenData
from app.services.audit_trail_service import AuditTrailService

logger = logging.getLogger(__name__)

audit_trail_service = AuditTrailService()


def _sanitize_config_payload(payload: Any) -> Any:
    hidden_keys = {
        "password",
        "api_token",
        "token",
        "secret",
        "api_key",
        "githubtoken",
        "gitlabtoken",
        "jiratoken",
        "userid",
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
                safe[str(key)] = _sanitize_config_payload(value)
        return safe
    if isinstance(payload, list):
        return [_sanitize_config_payload(item) for item in payload[:50]]
    if isinstance(payload, str):
        return payload[:500]
    if isinstance(payload, (int, float, bool)):
        return payload
    return str(payload)


async def _audit_project_config_activity(request: Request, current_user: TokenData = Depends(require_admin_or_read_api)):
    body_summary: Any = None
    method = request.method.upper()

    if method in {"POST", "PUT", "PATCH", "DELETE"} and current_user.role not in ["Admin", "API User"]:
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )

    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        try:
            raw_body = await request.body()
            if raw_body:
                try:
                    parsed = json.loads(raw_body.decode("utf-8", "ignore"))
                    body_summary = _sanitize_config_payload(parsed)
                except Exception:
                    body_summary = {"raw_body_size": len(raw_body)}
        except Exception:
            body_summary = {"raw_body": "unavailable"}

    details = {
        "path": request.url.path,
        "query": _sanitize_config_payload(dict(request.query_params)),
        "change": body_summary,
        "module": "project_config",
    }

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

    return current_user

router = APIRouter(
    prefix="/api/project-config",
    tags=["project-config"],
    dependencies=[Depends(_audit_project_config_activity)]
)

# Pydantic models
class GitHubRepoConfig(BaseModel):
    """Configuration for a single GitHub repository"""
    repo_name: str = Field(..., description="Repository name in format 'owner/repo'")
    config: Dict[str, Any] = Field(default_factory=dict, description="Additional repository configuration")

class JIRAProjectConfig(BaseModel):
    """Configuration for a single JIRA project"""
    project_key: str = Field(..., description="JIRA project key")
    config: Dict[str, Any] = Field(default_factory=dict, description="Additional project configuration")

class GitHubDefaultConfig(BaseModel):
    """Default GitHub configuration"""
    githubToken: str
    githubApiBaseUrl: str
    checkpointOverlapDays: int = 15


class GitLabDefaultConfig(BaseModel):
    """Default GitLab configuration"""
    gitlabToken: str
    gitlabApiBaseUrl: str
    checkpointOverlapDays: int = 15

class JIRADefaultConfig(BaseModel):
    """Default JIRA configuration"""
    jiraServer: str
    userId: str
    apiToken: str
    maxResults: int = 50
    cutoffDate: str = "2025-03-31"


class CheckpointOverlapConfig(BaseModel):
    """Payload for checkpoint overlap day updates."""
    checkpointOverlapDays: int = Field(15, ge=0, le=365)

class ProjectOnboardingRequest(BaseModel):
    """Request model for onboarding a new project"""
    github_repos: List[str] = Field(default_factory=list, description="List of GitHub repositories")
    gitlab_repos: List[str] = Field(default_factory=list, description="List of GitLab repositories")
    gitlab_repo_team_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of GitLab repository path (group/repo) to Team name"
    )
    jira_projects: List[str] = Field(default_factory=list, description="List of JIRA project keys")
    jira_prefix_team_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of JIRA issue prefix/project key to Team name"
    )
    github_custom_config: Optional[GitHubDefaultConfig] = None
    gitlab_custom_config: Optional[GitLabDefaultConfig] = None
    jira_custom_config: Optional[JIRADefaultConfig] = None

class ConfigResponse(BaseModel):
    """Response model for configuration data"""
    github_config: Dict[str, Any]
    gitlab_config: Dict[str, Any]
    jira_config: Dict[str, Any]


def get_config_paths():
    """Get paths to configuration files"""
    project_root = Path(__file__).parent.parent.parent.parent.parent.absolute()
    github_config_path = project_root / "config" / "github_config.json"
    gitlab_config_path = project_root / "config" / "gitlab_config.json"
    jira_config_path = project_root / "config" / "jira_config.json"
    return github_config_path, gitlab_config_path, jira_config_path


def get_scan_config_path() -> Path:
    """Get path to the security scan configuration file."""
    project_root = Path(__file__).parent.parent.parent.parent.parent.absolute()
    return project_root / "config" / "security_scan_config.json"


def read_json_file(file_path: Path) -> Dict[str, Any]:
    """Read and parse JSON configuration file"""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {file_path}")
        raise HTTPException(status_code=404, detail=f"Configuration file not found: {file_path}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {file_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Invalid JSON in configuration file: {e}")


def write_json_file(file_path: Path, data: Dict[str, Any]):
    """Write configuration data to JSON file"""
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write configuration file {file_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to write configuration: {e}")


@router.get("/", response_model=ConfigResponse)
def get_current_config():
    """
    Get current GitHub and JIRA configurations
    """
    github_config_path, gitlab_config_path, jira_config_path = get_config_paths()
    
    github_config = read_json_file(github_config_path)
    gitlab_config = read_json_file(gitlab_config_path)
    jira_config = read_json_file(jira_config_path)
    
    return ConfigResponse(
        github_config=github_config,
        gitlab_config=gitlab_config,
        jira_config=jira_config
    )


@router.get("/defaults", response_model=Dict[str, Any])
def get_default_configs():
    """
    Get default configurations for GitHub, GitLab and JIRA
    """
    github_config_path, gitlab_config_path, jira_config_path = get_config_paths()
    
    github_config = read_json_file(github_config_path)
    gitlab_config = read_json_file(gitlab_config_path)
    jira_config = read_json_file(jira_config_path)
    gitlab_repo_team_mapping = {
        repo_name: str(repo_config.get("team", "")).strip()
        for repo_name, repo_config in gitlab_config.get("repositories", {}).items()
        if isinstance(repo_config, dict) and str(repo_config.get("team", "")).strip()
    }
    
    return {
        "github_defaults": github_config.get("default", {}),
        "gitlab_defaults": gitlab_config.get("default", {}),
        "jira_defaults": jira_config.get("default", {}),
        "github_repositories": list(github_config.get("repositories", {}).keys()),
        "gitlab_repositories": list(gitlab_config.get("repositories", {}).keys()),
        "gitlab_repo_team_mapping": gitlab_repo_team_mapping,
        "jira_projects": list(jira_config.get("projects", {}).keys()),
        "jira_prefix_team_mapping": jira_config.get("prefix_team_mapping", {})
    }


@router.post("/onboard")
def onboard_project(request: ProjectOnboardingRequest):
    """
    Onboard a new project by adding GitHub/GitLab repositories and JIRA projects
    """
    github_config_path, gitlab_config_path, jira_config_path = get_config_paths()
    
    # Read current configurations
    github_config = read_json_file(github_config_path)
    gitlab_config = read_json_file(gitlab_config_path)
    jira_config = read_json_file(jira_config_path)
    
    # Validate repository format
    repo_pattern = re.compile(r'^[\w.-]+(?:/[\w.-]+)+$')
    for repo in request.github_repos:
        if not repo_pattern.match(repo):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid repository format: {repo}. Expected format: 'owner/repo'"
            )
    for repo in request.gitlab_repos:
        if not repo_pattern.match(repo):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid GitLab repository format: {repo}. Expected format: 'group/repo'"
            )

    # Normalize optional GitLab repo -> team mapping
    normalized_gitlab_team_mapping: Dict[str, str] = {}
    for repo_path, team in request.gitlab_repo_team_mapping.items():
        normalized_repo = str(repo_path).strip()
        normalized_team = str(team).strip()
        if not repo_pattern.match(normalized_repo):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid GitLab repository key in mapping: {repo_path}. Expected format: 'group/repo'"
            )
        if not normalized_team:
            raise HTTPException(
                status_code=400,
                detail=f"Team mapping value cannot be empty for GitLab repository: {normalized_repo}"
            )
        normalized_gitlab_team_mapping[normalized_repo] = normalized_team
    
    # Validate JIRA project key format (uppercase letters)
    project_pattern = re.compile(r'^[A-Z][A-Z0-9]*$')
    for project in request.jira_projects:
        if not project_pattern.match(project):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid JIRA project key: {project}. Must start with uppercase letter and contain only uppercase letters and numbers"
            )

    # Validate and normalize JIRA prefix -> team mapping
    normalized_prefix_mapping: Dict[str, str] = {}
    for prefix, team in request.jira_prefix_team_mapping.items():
        normalized_prefix = str(prefix).strip().upper()
        normalized_team = str(team).strip()

        if not project_pattern.match(normalized_prefix):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid JIRA prefix in mapping: {prefix}. "
                    "Must start with uppercase letter and contain only uppercase letters and numbers"
                )
            )

        if not normalized_team:
            raise HTTPException(
                status_code=400,
                detail=f"Team mapping value cannot be empty for JIRA prefix: {normalized_prefix}"
            )

        normalized_prefix_mapping[normalized_prefix] = normalized_team

    # During onboarding, team mapping is required for each provided JIRA project
    for project in request.jira_projects:
        if project not in normalized_prefix_mapping:
            raise HTTPException(
                status_code=400,
                detail=f"Missing team mapping for JIRA project key: {project}"
            )
    
    # Add GitHub repositories
    added_repos = []
    existing_repos = []
    for repo in request.github_repos:
        if repo in github_config.get("repositories", {}):
            existing_repos.append(repo)
        else:
            github_config.setdefault("repositories", {})[repo] = {}
            added_repos.append(repo)

    # Add GitLab repositories
    added_gitlab_repos = []
    existing_gitlab_repos = []
    for repo in request.gitlab_repos:
        if repo in gitlab_config.get("repositories", {}):
            existing_gitlab_repos.append(repo)
        else:
            gitlab_config.setdefault("repositories", {})[repo] = {}
            added_gitlab_repos.append(repo)

    # Persist optional GitLab repo -> team mapping
    for repo_path, team in normalized_gitlab_team_mapping.items():
        repo_entry = gitlab_config.setdefault("repositories", {}).setdefault(repo_path, {})
        repo_entry["team"] = team
    
    # Add JIRA projects
    added_projects = []
    existing_projects = []
    for project in request.jira_projects:
        if project in jira_config.get("projects", {}):
            existing_projects.append(project)
        else:
            jira_config.setdefault("projects", {})[project] = {}
            added_projects.append(project)

    # Persist JIRA prefix -> team mapping in jira_config.json
    if normalized_prefix_mapping:
        jira_config.setdefault("prefix_team_mapping", {}).update(normalized_prefix_mapping)
    
    # Update custom configurations if provided
    if request.github_custom_config:
        github_config["default"] = request.github_custom_config.dict()

    if request.gitlab_custom_config:
        gitlab_config["default"] = request.gitlab_custom_config.dict()
    
    if request.jira_custom_config:
        jira_config["default"] = request.jira_custom_config.dict()
    
    # Write updated configurations
    write_json_file(github_config_path, github_config)
    write_json_file(gitlab_config_path, gitlab_config)
    write_json_file(jira_config_path, jira_config)
    
    return {
        "success": True,
        "message": "Configuration updated successfully",
        "github": {
            "added": added_repos,
            "existing": existing_repos,
            "total_repositories": len(github_config.get("repositories", {}))
        },
        "gitlab": {
            "added": added_gitlab_repos,
            "existing": existing_gitlab_repos,
            "total_repositories": len(gitlab_config.get("repositories", {})),
            "repo_team_mappings_updated": len(normalized_gitlab_team_mapping)
        },
        "jira": {
            "added": added_projects,
            "existing": existing_projects,
            "total_projects": len(jira_config.get("projects", {})),
            "prefix_team_mappings_updated": len(normalized_prefix_mapping)
        }
    }


@router.put("/github/repository/{owner}/{repo}")
def update_github_repository(
    owner: str, 
    repo: str, 
    config: Dict[str, Any] = Body(...)
):
    """
    Update configuration for a specific GitHub repository
    """
    github_config_path, _, _ = get_config_paths()
    github_config = read_json_file(github_config_path)
    
    repo_name = f"{owner}/{repo}"
    
    if repo_name not in github_config.get("repositories", {}):
        raise HTTPException(status_code=404, detail=f"Repository {repo_name} not found")
    
    github_config["repositories"][repo_name] = config
    write_json_file(github_config_path, github_config)
    
    return {
        "success": True,
        "message": f"Configuration updated for repository {repo_name}",
        "repository": repo_name,
        "config": config
    }


@router.delete("/github/repository/{owner}/{repo}")
def remove_github_repository(owner: str, repo: str):
    """
    Remove a GitHub repository from configuration
    """
    github_config_path, _, _ = get_config_paths()
    github_config = read_json_file(github_config_path)
    
    repo_name = f"{owner}/{repo}"
    
    if repo_name not in github_config.get("repositories", {}):
        raise HTTPException(status_code=404, detail=f"Repository {repo_name} not found")
    
    del github_config["repositories"][repo_name]
    write_json_file(github_config_path, github_config)
    
    return {
        "success": True,
        "message": f"Repository {repo_name} removed successfully"
    }


@router.put("/jira/project/{project_key}")
def update_jira_project(
    project_key: str, 
    config: Dict[str, Any] = Body(...)
):
    """
    Update configuration for a specific JIRA project
    """
    _, _, jira_config_path = get_config_paths()
    jira_config = read_json_file(jira_config_path)
    
    if project_key not in jira_config.get("projects", {}):
        raise HTTPException(status_code=404, detail=f"JIRA project {project_key} not found")
    
    jira_config["projects"][project_key] = config
    write_json_file(jira_config_path, jira_config)
    
    return {
        "success": True,
        "message": f"Configuration updated for JIRA project {project_key}",
        "project_key": project_key,
        "config": config
    }


@router.delete("/jira/project/{project_key}")
def remove_jira_project(project_key: str):
    """
    Remove a JIRA project from configuration
    """
    _, _, jira_config_path = get_config_paths()
    jira_config = read_json_file(jira_config_path)
    
    if project_key not in jira_config.get("projects", {}):
        raise HTTPException(status_code=404, detail=f"JIRA project {project_key} not found")
    
    del jira_config["projects"][project_key]
    write_json_file(jira_config_path, jira_config)
    
    return {
        "success": True,
        "message": f"JIRA project {project_key} removed successfully"
    }


@router.put("/github/defaults")
def update_github_defaults(config: GitHubDefaultConfig):
    """
    Update default GitHub configuration
    """
    github_config_path, _, _ = get_config_paths()
    github_config = read_json_file(github_config_path)
    
    github_config["default"] = config.dict()
    write_json_file(github_config_path, github_config)
    
    return {
        "success": True,
        "message": "GitHub default configuration updated successfully",
        "config": config.dict()
    }


@router.put("/jira/defaults")
def update_jira_defaults(config: JIRADefaultConfig):
    """
    Update default JIRA configuration
    """
    _, _, jira_config_path = get_config_paths()
    jira_config = read_json_file(jira_config_path)

    jira_config["default"] = config.dict()
    write_json_file(jira_config_path, jira_config)

    return {
        "success": True,
        "message": "JIRA default configuration updated successfully",
        "config": config.dict()
    }


@router.put("/gitlab/repository/{group}/{repo}")
def update_gitlab_repository(
    group: str,
    repo: str,
    config: Dict[str, Any] = Body(...)
):
    """Update configuration for a specific GitLab repository."""
    _, gitlab_config_path, _ = get_config_paths()
    gitlab_config = read_json_file(gitlab_config_path)

    repo_name = f"{group}/{repo}"
    if repo_name not in gitlab_config.get("repositories", {}):
        raise HTTPException(status_code=404, detail=f"Repository {repo_name} not found")

    gitlab_config["repositories"][repo_name] = config
    write_json_file(gitlab_config_path, gitlab_config)

    return {
        "success": True,
        "message": f"Configuration updated for repository {repo_name}",
        "repository": repo_name,
        "config": config,
    }


@router.delete("/gitlab/repository/{group}/{repo}")
def remove_gitlab_repository(group: str, repo: str):
    """Remove a GitLab repository from configuration."""
    _, gitlab_config_path, _ = get_config_paths()
    gitlab_config = read_json_file(gitlab_config_path)

    repo_name = f"{group}/{repo}"
    if repo_name not in gitlab_config.get("repositories", {}):
        raise HTTPException(status_code=404, detail=f"Repository {repo_name} not found")

    del gitlab_config["repositories"][repo_name]
    write_json_file(gitlab_config_path, gitlab_config)

    return {
        "success": True,
        "message": f"Repository {repo_name} removed successfully",
    }


@router.put("/gitlab/defaults")
def update_gitlab_defaults(config: GitLabDefaultConfig):
    """Update default GitLab configuration."""
    _, gitlab_config_path, _ = get_config_paths()
    gitlab_config = read_json_file(gitlab_config_path)

    gitlab_config["default"] = config.dict()
    write_json_file(gitlab_config_path, gitlab_config)

    return {
        "success": True,
        "message": "GitLab default configuration updated successfully",
        "config": config.dict(),
    }


@router.put("/gitlab/checkpoint-overlap")
def update_gitlab_checkpoint_overlap(config: CheckpointOverlapConfig):
    """Update only GitLab checkpoint overlap days while preserving other defaults."""
    _, gitlab_config_path, _ = get_config_paths()
    gitlab_config = read_json_file(gitlab_config_path)

    default_cfg = gitlab_config.get("default", {})
    default_cfg["checkpointOverlapDays"] = int(config.checkpointOverlapDays)
    # Keep legacy key aligned for backwards compatibility.
    default_cfg["overlapDays"] = int(config.checkpointOverlapDays)
    gitlab_config["default"] = default_cfg

    write_json_file(gitlab_config_path, gitlab_config)

    return {
        "success": True,
        "message": "GitLab checkpoint overlap updated successfully",
        "checkpointOverlapDays": int(config.checkpointOverlapDays),
    }


@router.put("/github/checkpoint-overlap")
def update_github_checkpoint_overlap(config: CheckpointOverlapConfig):
    """Update only GitHub checkpoint overlap days while preserving other defaults."""
    github_config_path, _, _ = get_config_paths()
    github_config = read_json_file(github_config_path)

    default_cfg = github_config.get("default", {})
    default_cfg["checkpointOverlapDays"] = int(config.checkpointOverlapDays)
    # Keep legacy key aligned for backwards compatibility.
    default_cfg["overlapDays"] = int(config.checkpointOverlapDays)
    github_config["default"] = default_cfg

    write_json_file(github_config_path, github_config)

    return {
        "success": True,
        "message": "GitHub checkpoint overlap updated successfully",
        "checkpointOverlapDays": int(config.checkpointOverlapDays),
    }


# ---------------------------------------------------------------------------
# Security Scan Config models
# ---------------------------------------------------------------------------

class ScanReportEntry(BaseModel):
    """A single report (SAST / SCA / DAST / Mend) for a project."""
    type: str = Field(..., description="Report type: sast | sca | dast | mend")
    url: str = Field(..., description="Full Nexus URL to download the report from")
    filename: str = Field(..., description="Output filename, e.g. apm_sast.html")


class ScanProjectConfig(BaseModel):
    """Configuration for one project's security scan reports."""
    id: str = Field(..., description="Short identifier used in filenames, e.g. 'apm'")
    name: str = Field(..., description="Display name, e.g. 'APM'")
    teams: List[str] = Field(default_factory=list, description="TeamSight team names this project belongs to, e.g. ['APM-Core', 'APM-RUM']")
    reports: List[ScanReportEntry] = Field(default_factory=list)


class ScanCredentials(BaseModel):
    """Nexus authentication credentials."""
    username: str
    password: str


# ---------------------------------------------------------------------------
# Security Scan Config endpoints
# ---------------------------------------------------------------------------

@router.get("/teams")
def get_teams():
    """Return the sorted list of unique team names from Resources.csv."""
    project_root = Path(__file__).parent.parent.parent.parent.parent.absolute()
    resources_path = project_root / "config" / "Resources.csv"
    if not resources_path.exists():
        raise HTTPException(status_code=404, detail="Resources.csv not found")
    teams: set[str] = set()
    try:
        with open(resources_path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                team = (row.get("Team") or "").strip()
                if team and team not in ("-NA-", "Team"):
                    teams.add(team)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read Resources.csv: {exc}")
    return {"teams": sorted(teams)}


@router.get("/scan-config")
def get_scan_config():
    """Return the full security_scan_config.json content."""
    scan_path = get_scan_config_path()
    config = read_json_file(scan_path)
    return config


@router.put("/scan-credentials")
def update_scan_credentials(creds: ScanCredentials):
    """Update Nexus credentials in security_scan_config.json."""
    scan_path = get_scan_config_path()
    config = read_json_file(scan_path)
    config["credentials"] = {"username": creds.username, "password": creds.password}
    write_json_file(scan_path, config)
    return {"success": True, "message": "Scan credentials updated"}


@router.post("/scan-projects")
def add_scan_project(project: ScanProjectConfig):
    """
    Add or replace a project in security_scan_config.json.
    If a project with the same id already exists it is overwritten.
    """
    scan_path = get_scan_config_path()
    config = read_json_file(scan_path)

    projects: list = config.setdefault("projects", [])
    existing_ids = [p.get("id") for p in projects]

    entry = project.dict()
    if project.id in existing_ids:
        idx = existing_ids.index(project.id)
        projects[idx] = entry
        action = "updated"
    else:
        projects.append(entry)
        action = "added"

    write_json_file(scan_path, config)
    return {
        "success": True,
        "message": f"Scan project '{project.id}' {action}",
        "action": action,
        "total_projects": len(projects),
    }


@router.delete("/scan-projects/{project_id}")
def remove_scan_project(project_id: str):
    """Remove a project from security_scan_config.json by its id."""
    scan_path = get_scan_config_path()
    config = read_json_file(scan_path)

    projects: list = config.get("projects", [])
    original_len = len(projects)
    config["projects"] = [p for p in projects if p.get("id") != project_id]

    if len(config["projects"]) == original_len:
        raise HTTPException(status_code=404, detail=f"Scan project '{project_id}' not found")

    write_json_file(scan_path, config)
    return {
        "success": True,
        "message": f"Scan project '{project_id}' removed",
        "total_projects": len(config["projects"]),
    }


# ---------------------------------------------------------------------------
# Copilot Metrics Configuration endpoints
# ---------------------------------------------------------------------------

class CopilotDBConfig(BaseModel):
    """Copilot Metrics database configuration"""
    server: str = Field(..., description="Database server hostname")
    port: int = Field(default=1433, description="Database port")
    database: str = Field(..., description="Database name")
    user: str = Field(..., description="Database user")
    password: str = Field(..., description="Database password")
    authentication: str = Field(default="ActiveDirectoryPassword", description="Authentication mode (e.g., ActiveDirectoryPassword, SqlPassword)")
    encrypt: bool = Field(default=True, description="Enable SSL/TLS encryption")
    trustServerCertificate: bool = Field(default=False, description="Trust server certificate")
    hostNameInCertificate: Optional[str] = Field(default="*.database.windows.net", description="Host name for certificate validation")
    loginTimeout: int = Field(default=30, description="Login timeout in seconds")


class CopilotProjectsConfig(BaseModel):
    """Selected Copilot projects (derived from team_name values)."""
    projects: List[str] = Field(default_factory=list)


REDACTED_PASSWORD = "[REDACTED]"


def _resolve_copilot_password(submitted_password: str, existing_password: str) -> str:
    """Resolve effective password from submitted value and existing config value."""
    normalized = (submitted_password or "").strip()
    if normalized and normalized != REDACTED_PASSWORD:
        return submitted_password
    return existing_password or ""


def get_copilot_config_path() -> Path:
    """Get path to the copilot metrics configuration file."""
    project_root = Path(__file__).parent.parent.parent.parent.parent.absolute()
    return project_root / "config" / "copilot_metrics_config.json"


def get_copilot_team_user_csv_path() -> Path:
    """Get path to the generated team/user export for Copilot metrics."""
    project_root = Path(__file__).parent.parent.parent.parent.parent.absolute()
    return project_root / "output" / "copilot_unique_team_user_logins.csv"


def _get_copilot_project_options() -> List[str]:
    """Load unique team_name values from copilot_unique_team_user_logins.csv."""
    csv_path = get_copilot_team_user_csv_path()
    if not csv_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "copilot_unique_team_user_logins.csv not found. "
                "Generate it first from the Copilot usage dataset."
            ),
        )

    teams: set[str] = set()
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                team_name = (row.get("team_name") or "").strip()
                if team_name:
                    teams.add(team_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read {csv_path.name}: {exc}")

    return sorted(teams)


def _normalize_copilot_projects(projects: List[str]) -> List[str]:
    """Normalize and de-duplicate selected project names while preserving order."""
    normalized: List[str] = []
    seen: set[str] = set()
    for item in projects:
        value = str(item or "").strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


@router.get("/copilot-config")
def get_copilot_config():
    """Get current Copilot metrics database configuration (without sensitive password)"""
    config_path = get_copilot_config_path()
    config = read_json_file(config_path)
    
    # Don't return password in GET request
    db_config = config.get("database", {}).copy()
    db_config["password"] = REDACTED_PASSWORD
    if not db_config.get("authentication"):
        db_config["authentication"] = "ActiveDirectoryPassword"
    
    return {
        "database": db_config,
        "schedule": config.get("schedule", {}),
        "features": config.get("features", {}),
        "projects": config.get("projects", [])
    }


@router.get("/copilot-project-options")
def get_copilot_project_options():
    """Get available Copilot project options from team_name values in CSV export."""
    return {"projects": _get_copilot_project_options()}


@router.get("/copilot-projects")
def get_copilot_projects():
    """Get selected Copilot projects from copilot_metrics_config.json."""
    config_path = get_copilot_config_path()
    config = read_json_file(config_path)
    selected = _normalize_copilot_projects(config.get("projects", []))
    return {"projects": selected}


@router.put("/copilot-projects")
def update_copilot_projects(payload: CopilotProjectsConfig):
    """Update selected Copilot projects in copilot_metrics_config.json."""
    config_path = get_copilot_config_path()
    config = read_json_file(config_path)

    normalized_projects = _normalize_copilot_projects(payload.projects)
    valid_options = set(_get_copilot_project_options())
    invalid_projects = [project for project in normalized_projects if project not in valid_options]
    if invalid_projects:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid project selections: {', '.join(invalid_projects)}",
        )

    config["projects"] = normalized_projects
    write_json_file(config_path, config)

    return {
        "success": True,
        "message": "Copilot projects updated successfully",
        "projects": normalized_projects,
    }


@router.put("/copilot-config")
def update_copilot_config(db_config: CopilotDBConfig):
    """Update Copilot metrics database configuration"""
    config_path = get_copilot_config_path()
    config = read_json_file(config_path)
    
    existing_password = config.get("database", {}).get("password", "")
    effective_password = _resolve_copilot_password(db_config.password, existing_password)
    if (db_config.password or "").strip() in {"", REDACTED_PASSWORD} and effective_password:
        logger.info("Copilot config update: using stored database password (redacted input received)")

    # Update database configuration
    config["database"] = {
        "server": db_config.server,
        "port": db_config.port,
        "database": db_config.database,
        "user": db_config.user,
        "password": effective_password,
        "authentication": db_config.authentication,
        "encrypt": db_config.encrypt,
        "trustServerCertificate": db_config.trustServerCertificate,
        "hostNameInCertificate": db_config.hostNameInCertificate,
        "loginTimeout": db_config.loginTimeout
    }
    
    write_json_file(config_path, config)
    
    # Return config without password
    response_config = config["database"].copy()
    response_config["password"] = REDACTED_PASSWORD
    
    return {
        "success": True,
        "message": "Copilot metrics database configuration updated successfully",
        "database": response_config
    }


@router.post("/copilot-test")
def test_copilot_connection(db_config: CopilotDBConfig):
    """Test connection to Copilot metrics database"""
    import subprocess
    import sys
    from pathlib import Path
    
    try:
        # Build connection test command
        project_root = Path(__file__).parent.parent.parent.parent.parent.absolute()
        script_path = project_root / "src" / "copilot_metrics_fetch.py"
        config_path = get_copilot_config_path()
        config = read_json_file(config_path)
        existing_password = config.get("database", {}).get("password", "")
        effective_password = _resolve_copilot_password(db_config.password, existing_password)
        if (db_config.password or "").strip() in {"", REDACTED_PASSWORD} and effective_password:
            logger.info("Copilot test connection: using stored database password (redacted input received)")

        if not effective_password:
            return {
                "success": False,
                "status": "error",
                "message": "Database password is missing. Enter password and try again.",
                "output": "No saved password found in config and no new password provided in request."
            }
        
        # Create a temporary environment with the provided credentials
        env = os.environ.copy()
        env['COPILOT_DB_SERVER'] = db_config.server
        env['COPILOT_DB_PORT'] = str(db_config.port)
        env['COPILOT_DB_NAME'] = db_config.database
        env['COPILOT_DB_USER'] = db_config.user
        env['COPILOT_DB_PASSWORD'] = effective_password
        env['COPILOT_DB_AUTHENTICATION'] = db_config.authentication
        env['TEAMSIGHT_HOME'] = str(project_root)
        
        # Get Python executable
        venv_python = (project_root / "dashboard" / "backend" / "venv" / "bin" / "python").absolute()
        if not venv_python.exists():
            venv_python = Path(sys.executable)
        
        # Run the test (connectivity test only, don't collect metrics)
        result = subprocess.run(
            [str(venv_python), str(script_path)],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            cwd=str(project_root)
        )
        
        success = result.returncode == 0
        output = result.stdout + result.stderr
        
        return {
            "success": success,
            "status": "connected" if success else "failed",
            "message": "Database connection successful" if success else "Database connection failed",
            "output": output[-500:] if len(output) > 500 else output  # Last 500 chars
        }
        
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "status": "timeout",
            "message": "Connection test timed out (30 seconds)",
            "output": "The test took too long to complete. Check network connectivity to the database server."
        }
    except Exception as e:
        return {
            "success": False,
            "status": "error",
            "message": f"Failed to test connection: {str(e)}",
            "output": str(e)
        }


# ---------------------------------------------------------------------------
# UDE Configuration endpoints
# ---------------------------------------------------------------------------

UDE_CONFIG_FILENAME = "ude_config.json"
UDE_INSTALLATIONS_FILENAME = "ude_installations.json"


def get_ude_config_path() -> Path:
    project_root = Path(__file__).parent.parent.parent.parent.parent.absolute()
    return project_root / "config" / UDE_CONFIG_FILENAME


def get_ude_installations_path() -> Path:
    project_root = Path(__file__).parent.parent.parent.parent.parent.absolute()
    return project_root / "output" / UDE_INSTALLATIONS_FILENAME


def _normalize_ude_version(value: Any) -> str:
    version = str(value or "").strip()
    if version.lower().startswith("v") and len(version) > 1 and version[1].isdigit():
        return version[1:]
    return version


class UDEVersionConfigRequest(BaseModel):
    """UDE version team mapping configuration.

    version_team_mapping maps a version string to the list of teams it is
    specific to.  Once a version is marked for specific teams every subsequent
    version (ordered by release date) inherits that assignment unless
    explicitly overridden.  An empty list means the version is for ALL teams.
    """
    version_team_mapping: Dict[str, List[str]] = Field(
        default_factory=dict,
        description=(
            "Map of version → list of team names it is specific to. "
            "Empty list means ALL teams."
        ),
    )


@router.get("/ude-versions")
def get_ude_versions():
    """Return all UDE versions found in the installations data with their release dates."""
    ude_path = get_ude_installations_path()
    if not ude_path.exists():
        return {"versions": []}
    try:
        payload = json.loads(ude_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read UDE installations: {exc}")

    records = list(payload.values()) if isinstance(payload, dict) else payload

    release_by_version: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        version = _normalize_ude_version(record.get("version"))
        release_date = (record.get("release_date") or "").strip()
        if not version or not release_date:
            continue
        # Keep earliest release_date per version (robust to duplicates)
        if version not in release_by_version or release_date < release_by_version[version]:
            release_by_version[version] = release_date

    def _version_sort_key(v: str):
        try:
            return [int(x) for x in v.split(".")]
        except Exception:
            return [0]

    sorted_versions = sorted(release_by_version.keys(), key=_version_sort_key)
    return {
        "versions": [
            {"version": v, "release_date": release_by_version[v]}
            for v in sorted_versions
        ]
    }


@router.get("/ude-config")
def get_ude_config():
    """Return the current UDE version-to-team configuration plus available versions."""
    ude_config_path = get_ude_config_path()
    if ude_config_path.exists():
        try:
            config = json.loads(ude_config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read UDE config: {exc}")
    else:
        config = {"version_team_mapping": {}}

    # Also return the avaliable versions so the UI can render in one call
    try:
        versions_response = get_ude_versions()
        available_versions = versions_response["versions"]
    except Exception:
        available_versions = []

    return {
        "version_team_mapping": config.get("version_team_mapping", {}),
        "available_versions": available_versions,
    }


@router.put("/ude-config")
def update_ude_config(request: UDEVersionConfigRequest):
    """Save UDE version-to-team configuration."""
    ude_config_path = get_ude_config_path()

    # Validate that version values are lists of non-empty strings
    for version, teams in request.version_team_mapping.items():
        if not isinstance(teams, list):
            raise HTTPException(
                status_code=400,
                detail=f"Teams value for version '{version}' must be a list.",
            )
        for team in teams:
            if not isinstance(team, str) or not team.strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"Team name in version '{version}' mapping must be a non-empty string.",
                )

    config = {"version_team_mapping": {
        k: v for k, v in request.version_team_mapping.items()
    }}
    try:
        ude_config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write UDE config: {exc}")

    return {
        "success": True,
        "message": "UDE configuration updated successfully",
        "version_team_mapping": config["version_team_mapping"],
    }

