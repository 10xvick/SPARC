"""
FastAPI main application entry point.
Employee Metrics Dashboard Backend.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import logging
from pathlib import Path
import re
from importlib.metadata import version as package_version, PackageNotFoundError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _resolve_app_version() -> str:
    """Resolve TeamSight version from installed package metadata."""
    try:
        return package_version("teamsight")
    except PackageNotFoundError:
        setup_path = Path(__file__).parent.parent.parent.parent / "setup.py"
        if setup_path.exists():
            try:
                setup_text = setup_path.read_text(encoding="utf-8")
                match = re.search(
                    r"^\s*version\s*=\s*['\"]([^'\"]+)['\"]\s*,\s*$",
                    setup_text,
                    re.MULTILINE,
                )
                if match:
                    return match.group(1)
            except Exception:
                logger.warning("Unable to parse version from setup.py", exc_info=True)
        return "0.1.0"


APP_VERSION = _resolve_app_version()

from app.api.employees import router as employees_router
from app.api.roles import router as roles_router
from app.api.reports import router as reports_router, warm_transitions_cache_in_background
from app.api.employee_dashboard import router as employee_dashboard_router
from app.api.team_dashboard import router as team_dashboard_router
from app.api.scrum_dashboard import router as scrum_dashboard_router
from app.api.bug_cycle_time import router as bug_cycle_time_router
from app.api.replan_tracker import router as replan_tracker_router
from app.api.assignee_delay_report import router as assignee_delay_report_router
from app.api.home_stats import router as home_stats_router
from app.api.project_config import router as project_config_router
from app.api.scoring import router as scoring_router
from app.api.file_viewer import router as file_viewer_router
from app.api.ude import router as ude_router
from app.api.audit_trail import router as audit_trail_router
from app.routers.auth import router as auth_router
from app.routers.admin import router as admin_router
from app.services.scheduler import init_scheduler, shutdown_scheduler

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events"""
    # Startup
    project_root = Path(__file__).parent.parent.parent.parent.absolute()
    init_scheduler(str(project_root))
    logger.info(f"Scheduler initialized with project root: {project_root}")
    warm_transitions_cache_in_background()
    logger.info("Transition history cache pre-warm started in background")

    # Refresh in-memory caches in the background so they're ready without blocking startup
    def _background_cache_refresh():
        try:
            from app.routers.admin import _refresh_all_caches
            results = _refresh_all_caches()
            logger.info("Startup cache refresh complete: %s", results)
        except Exception as exc:
            logger.warning("Startup cache refresh failed: %s", exc)

    import threading
    threading.Thread(target=_background_cache_refresh, daemon=True, name="startup-cache-refresh").start()
    logger.info("Startup cache refresh started in background")
    
    yield
    
    # Shutdown
    shutdown_scheduler()
    logger.info("Scheduler shut down")

# Create FastAPI app
app = FastAPI(
    title="Employee Metrics Dashboard API",
    description="API for employee KPI tracking with ROG status visualization",
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(home_stats_router)
app.include_router(employees_router)
app.include_router(roles_router)
app.include_router(reports_router)
app.include_router(employee_dashboard_router)
app.include_router(team_dashboard_router)
app.include_router(scrum_dashboard_router)
app.include_router(bug_cycle_time_router)
app.include_router(replan_tracker_router)
app.include_router(assignee_delay_report_router)
app.include_router(project_config_router)
app.include_router(scoring_router)
app.include_router(file_viewer_router)
app.include_router(ude_router)
app.include_router(audit_trail_router)
app.include_router(admin_router)

@app.get("/")
async def root():
    """Root endpoint - serve frontend UI if built, otherwise API info."""
    if _frontend_dist.exists():
        return FileResponse(str(_frontend_dist / "index.html"))
    return {
        "message": "Employee Metrics Dashboard API",
        "version": APP_VERSION,
        "status": "online",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "dashboard-api"
    }

@app.get("/api/config")
async def get_config():
    """Get application configuration (public info only)."""
    return {
        "app_name": "Employee Metrics Dashboard",
        "version": APP_VERSION,
        "features": {
            "employee_management": True,
            "role_management": True,
            "reports": True,
            "export": True
        }
    }

# Serve built React frontend static files if the dist folder exists
_frontend_dist = Path(__file__).parent.parent.parent.parent / "dashboard" / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")

    @app.get("/app/{full_path:path}")
    async def serve_spa(full_path: str):
        """Catch-all for React SPA routes."""
        index = _frontend_dist / "index.html"
        return FileResponse(str(index))

    @app.get("/ui")
    async def serve_ui_root():
        """Serve the React app root."""
        index = _frontend_dist / "index.html"
        return FileResponse(str(index))

# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "detail": str(exc) if app.debug else "An error occurred"
        }
    )

# SPA catch-all: serve index.html for any path not matched by API routes
# This must be LAST so it doesn't shadow API endpoints
if _frontend_dist.exists():
    @app.get("/{full_path:path}")
    async def serve_spa_fallback(full_path: str):
        """Serve React SPA for all unmatched routes."""
        # Serve actual static files if they exist in dist root (favicon, etc.)
        requested_file = _frontend_dist / full_path
        if requested_file.is_file():
            return FileResponse(str(requested_file))
        return FileResponse(str(_frontend_dist / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
