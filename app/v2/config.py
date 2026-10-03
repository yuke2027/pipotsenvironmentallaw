from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.v2.shared.license import read_license_confirmation


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ESP_", env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://platform:platform@localhost:55432/platform"
    redis_url: str = "redis://localhost:56379/0"
    secret_key: SecretStr = Field(min_length=32)
    storage_root: Path = Path("var/platform")
    frontend_dist: Path = Path("frontend/dist")
    environment: str = "development"
    public_origin: str = "http://localhost:8080"
    cookie_secure: bool = False
    session_hours: int = 8
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    user_administration_service_enabled: bool = True
    admin_read_service_enabled: bool = True
    ml_service_enabled: bool = True
    max_upload_bytes: int = 50 * 1024 * 1024
    source_base_url: str = "https://quotsoft.net/air/data"
    source_interval_seconds: float = 1.0
    source_timeout_seconds: float = 30
    source_license_confirmed: bool = False
    source_license_confirmation_file: Path = Path("var/platform/source-license-confirmation.json")
    max_query_days: int = 731
    model_device: str = "cpu"
    model_epochs: int = Field(20, ge=1, le=10000)
    model_window: int = Field(168, ge=24, le=336)
    notification_timeout: int = 10
    # Keep connection concurrency explicit so high fan-out read traffic does
    # not queue behind SQLAlchemy's small default pool. Deployments can tune
    # these independently through ESP_DB_POOL_SIZE/ESP_DB_MAX_OVERFLOW.
    db_pool_size: int = Field(10, ge=1, le=100)
    db_max_overflow: int = Field(20, ge=0, le=200)

    @model_validator(mode="after")
    def production_settings(self) -> "Settings":
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("production requires ESP_COOKIE_SECURE=true")
        if self.environment != "test" and not self.database_url.startswith("postgresql"):
            raise ValueError("the v2 platform requires PostgreSQL; SQLite is test-only")
        return self

    def prepare(self) -> None:
        self.storage_root = self.storage_root.resolve()
        for name in ("raw", "uploads", "exports", "models", "datasets", "derived", "backups"):
            (self.storage_root / name).mkdir(parents=True, exist_ok=True)

    def source_license_ready(self) -> bool:
        """Require both the deployment switch and an auditable confirmation."""
        return self.source_license_confirmed and read_license_confirmation(
            self.source_license_confirmation_file
        ).get("valid", False)
