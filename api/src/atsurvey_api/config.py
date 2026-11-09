from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ORIGIN_RE = re.compile(r"^https?://[A-Za-z0-9.\-]+(:\d{1,5})?$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    #: development | test | production. Production enforces the safe settings below.
    environment: Literal["development", "test", "production"] = "development"

    #: https://<project-ref>.supabase.co — used for JWKS, the issuer check and plan lookups
    supabase_url: str = ""
    #: Publishable / anon key (sent as `apikey` to PostgREST together with the user's JWT)
    supabase_anon_key: str = ""
    #: Legacy HS256 JWT secret. Leave empty to verify with the project's JWKS (recommended).
    supabase_jwt_secret: str = ""
    #: Seconds of clock skew tolerated when checking exp / iat / nbf
    jwt_leeway_s: int = 30
    #: Timeout for fetching the JWKS document
    jwks_timeout_s: float = 5.0
    #: Development only: skip authentication entirely and treat every caller as "pro".
    #: Refused when environment=production.
    auth_disabled: bool = False
    #: Allow parse/compute/suggest without a token (powers the no-signup demo).
    allow_anonymous_compute: bool = True
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:4173"]

    # ---- request size guards
    max_upload_mb: int = 20
    #: JSON request bodies (compute, export, COGO). Multipart uploads use max_upload_mb.
    max_body_mb: int = 10
    max_observations: int = 200_000
    max_setups: int = 5_000
    max_control_points: int = 50_000
    max_traverses: int = 2_000
    max_route_points: int = 500

    # ---- computation guards
    #: Seconds a request may spend computing before it is aborted
    compute_timeout_s: float = 30.0
    #: Concurrent heavy computations (parse / compute / suggest / export). 0 = 2 × CPU count.
    max_concurrent_computations: int = 0
    #: Seconds a request waits for a free computation slot before 503
    compute_queue_timeout_s: float = 10.0
    #: Timeout for traverse suggestions, which run in a killable child process
    suggest_timeout_s: float = 10.0

    # ---- rate limiting (token buckets, per user id or client IP)
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 240
    rate_limit_burst: int = 60
    #: Stricter bucket for /v1/export and /v1/parse
    rate_limit_heavy_per_minute: int = 30
    rate_limit_heavy_burst: int = 10
    #: Use the first X-Forwarded-For hop as client IP (only behind our own reverse proxy)
    trusted_proxy: bool = False

    @field_validator("cors_origins")
    @classmethod
    def _explicit_origins(cls, v: list[str]) -> list[str]:
        for origin in v:
            if origin == "*" or not _ORIGIN_RE.match(origin):
                raise ValueError(
                    f"CORS origin {origin!r} must be an explicit scheme://host[:port] (no '*')"
                )
        return v

    @model_validator(mode="after")
    def _production_safety(self) -> Settings:
        if self.environment != "production":
            return self
        problems = []
        if self.auth_disabled:
            problems.append("AUTH_DISABLED must be false in production")
        if not self.supabase_url.startswith("https://"):
            problems.append("SUPABASE_URL must be an https URL in production")
        if any(o.startswith("http://") for o in self.cors_origins):
            problems.append("CORS_ORIGINS must use https in production")
        if not self.rate_limit_enabled:
            problems.append("RATE_LIMIT_ENABLED must be true in production")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self

    @property
    def concurrency(self) -> int:
        return self.max_concurrent_computations or 2 * (os.cpu_count() or 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
