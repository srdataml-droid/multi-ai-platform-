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
    # HS256 secret that signs dashboard JWTs. Supabase projects expose theirs in
    # project settings. The default is only acceptable when env == "local".
    jwt_secret: str = "dev-secret-change-me-before-any-deploy-0123456789"
    jwt_audience: str = "authenticated"
    # The Postgres role the app switches to inside tenant_session. RLS applies to it.
    app_role: str = "novaxis_app"
    # Public URL the providers call, used to recompute Twilio's signed URL behind a proxy.
    public_base_url: str = "http://localhost:8000"
    # Twilio: one Novaxis account, one number per tenant (tenant settings hold the number).
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    # Postmark: outbound server token, and the shared token the inbound webhook must present.
    postmark_server_token: str = ""
    postmark_inbound_token: str = ""
    # Signs web-chat visitor tokens. Defaults to the JWT secret; set separately in production.
    visitor_token_secret: str = ""
    # Fernet key (urlsafe base64, 32 bytes) for sensitive intake fields at rest. Empty means
    # "derive from the JWT secret", which is acceptable only when env == "local".
    sensitive_fields_key: str = ""
    # Scheduling. Google OAuth app credentials; the redirect URI is
    # {public_base_url}/integrations/google/callback.
    google_client_id: str = ""
    google_client_secret: str = ""
    hold_minutes: int = 10
    slots_offered: int = 3
    availability_days: int = 14
    # Media storage. "local" writes under storage_local_dir; "supabase" uses Storage REST.
    storage_backend: str = "local"
    storage_local_dir: str = ".novaxis-media"
    storage_bucket: str = "media"
    supabase_url: str = ""
    supabase_service_key: str = ""
    media_max_bytes: int = 10 * 1024 * 1024
    media_allowed_types: tuple[str, ...] = ("image/", "application/pdf", "video/mp4")
    # Local: Mailpit; production: unused when Postmark is configured.
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    # LLM. "anthropic" uses the SDK (credentials from ANTHROPIC_API_KEY or an `ant auth`
    # profile); "fake" uses scripted responses for tests and offline demos.
    llm_provider: str = "anthropic"
    model_worker: str = "claude-sonnet-5"
    model_classify: str = "claude-haiku-4-5"
    model_summarise: str = "claude-haiku-4-5"
    llm_timeout_seconds: float = 45.0
    llm_max_retries: int = 2
    # Worker loop.
    worker_id: str = ""
    worker_lease_seconds: int = 600
    worker_backoff_seconds: tuple[int, ...] = (10, 60, 300)
    worker_max_attempts: int = 3
    context_max_messages: int = 30
    summary_every_messages: int = 10


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, built on first use."""
    return Settings()
