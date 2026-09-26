"""Process settings, loaded once from environment variables.

Why this exists: every secret and every knob enters the system through this one
module, so a reviewer can see the full surface in a single file and nothing reads
`os.environ` elsewhere.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Values that differ between local, staging and production."""

    model_config = SettingsConfigDict(env_prefix="NOVAXIS_", env_file=".env", extra="ignore")

    env: str = "local"
    database_url: str = "postgresql+psycopg://novaxis:novaxis@localhost:5432/novaxis"
    worker_enabled: bool = True
    worker_poll_seconds: float = 1.0
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, built on first use."""
    return Settings()
