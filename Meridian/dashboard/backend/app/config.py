"""
Configuration settings for the dashboard application.
"""
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR / ".env"

class Settings(BaseSettings):
    # Application
    app_name: str = "Employee Metrics Dashboard"
    app_version: str = "0.1.0"
    debug: bool = True
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    
    # JWT
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    
    # Data paths resolved from the TeamSight installation root
    base_dir: Path = Field(default_factory=lambda: PROJECT_ROOT)
    resources_csv_path: Path | None = None
    roles_csv_path: Path | None = None
    kpi_data_path: Path | None = None
    config_path: Path | None = None
    data_path: Path | None = None
    
    # ROG Thresholds
    rog_green_min: float = 0.62
    rog_orange_min: float = 0.40
    
    # Data Retention
    data_retention_months: int = 15
    
    # Additional settings
    environment: str = "development"
    auto_refresh_enabled: bool = True
    hourly_refresh_kpis: str = "k3,k12,k13"
    daily_refresh_time: str = "02:00"
    log_level: str = "INFO"
    log_file: str = "logs/dashboard.log"

    @staticmethod
    def _resolve_path(value: Path | None, base_dir: Path, *default_parts: str) -> Path:
        if value is None or str(value) == "":
            return (base_dir / Path(*default_parts)).resolve()

        path = Path(value).expanduser()
        return path.resolve() if path.is_absolute() else (base_dir / path).resolve()

    @model_validator(mode="after")
    def resolve_project_paths(self):
        base_dir = Path(self.base_dir).expanduser()
        if not base_dir.is_absolute():
            base_dir = (PROJECT_ROOT / base_dir).resolve()
        else:
            base_dir = base_dir.resolve()

        self.base_dir = base_dir
        self.resources_csv_path = self._resolve_path(self.resources_csv_path, base_dir, "config", "Resources.csv")
        self.roles_csv_path = self._resolve_path(self.roles_csv_path, base_dir, "config", "Roles.csv")
        self.kpi_data_path = self._resolve_path(self.kpi_data_path, base_dir, "output")
        self.config_path = self._resolve_path(self.config_path, base_dir, "config")
        self.data_path = self._resolve_path(self.data_path, base_dir, "data")
        return self
    
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        extra="allow"  # Allow extra fields from .env
    )

settings = Settings()
