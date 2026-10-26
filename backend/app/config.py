"""Application settings, loaded from environment variables (prefix UKA_) or a .env file."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UKA_", env_file=ROOT_DIR / ".env", extra="ignore")

    data_dir: Path = ROOT_DIR / "data"
    template_path: Path = ROOT_DIR / "templates" / "output_template.xlsx"
    frontend_dist: Path = ROOT_DIR / "frontend" / "dist"

    # VO rating list. Empty URL = discover the newest compiled-epoch baseline for voa_list_year.
    voa_list_url: str = ""
    voa_list_year: int = 2026

    # Background data refresh (in-process, atomic swap). 0 disables. VO publishes ~every 2 months,
    # Overture ~monthly. auto_import_on_start builds missing datasets on first boot.
    refresh_voa_days: int = 30
    refresh_places_days: int = 30
    auto_import_on_start: bool = False

    # Limits
    max_results_per_search: int = 5000
    max_concurrent_jobs: int = 2
    export_retention_hours: int = 72

    # Optional shared password for the dashboard (HTTP Basic). Empty = no auth (local use only).
    app_password: str = ""

    log_level: str = "INFO"

    @property
    def voa_db_path(self) -> Path:
        return self.data_dir / "voa.sqlite"

    @property
    def places_db_path(self) -> Path:
        return self.data_dir / "places.sqlite"

    @property
    def app_db_path(self) -> Path:
        return self.data_dir / "app.sqlite"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"


@lru_cache
def get_settings() -> Settings:
    return Settings()
