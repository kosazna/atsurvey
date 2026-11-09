from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    #: https://<project-ref>.supabase.co — used for JWKS and PostgREST plan lookups
    supabase_url: str = ""
    #: Publishable / anon key (sent as `apikey` to PostgREST together with the user's JWT)
    supabase_anon_key: str = ""
    #: Legacy HS256 JWT secret. Leave empty to verify with the project's JWKS (recommended).
    supabase_jwt_secret: str = ""
    #: Development only: skip authentication entirely and treat every caller as "pro".
    auth_disabled: bool = False
    #: Allow parse/compute/suggest without a token (powers the no-signup demo).
    allow_anonymous_compute: bool = True
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:4173"]
    max_upload_mb: int = 20
    max_observations: int = 200_000
    #: Seconds a request may spend computing before it is aborted
    compute_timeout_s: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
