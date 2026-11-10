"""Supabase access-token verification and plan lookup."""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Annotated, Literal

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, status

from .config import Settings, get_settings

log = logging.getLogger("atsurvey.auth")

Plan = Literal["anonymous", "free", "pro"]

EXPORTS_BY_PLAN: dict[str, list[str]] = {
    "anonymous": ["csv"],
    "free": ["csv", "xlsx"],
    "pro": ["csv", "xlsx", "shp", "dxf", "pdf", "landxml", "kml", "geojson"],
}


@dataclass(slots=True)
class Caller:
    user_id: str | None
    token: str | None
    email: str | None = None

    @property
    def anonymous(self) -> bool:
        return self.user_id is None


_jwks_clients: dict[str, jwt.PyJWKClient] = {}

#: verified tokens → (claims, expiry); avoids re-verifying on every request (bounded)
_token_cache: dict[str, tuple[float, dict]] = {}
_TOKEN_CACHE_MAX = 10_000


def _jwks(settings: Settings) -> jwt.PyJWKClient:
    url = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
    client = _jwks_clients.get(url)
    if client is None:
        client = _jwks_clients[url] = jwt.PyJWKClient(
            url, cache_keys=True, lifespan=3600, timeout=settings.jwks_timeout_s
        )
    return client


def _decode(token: str, settings: Settings) -> dict:
    issuer = settings.supabase_url.rstrip("/") + "/auth/v1" if settings.supabase_url else None
    options = {"require": ["exp", "sub"], "verify_iss": issuer is not None}
    common = {
        "audience": "authenticated",
        "issuer": issuer,
        "leeway": settings.jwt_leeway_s,
        "options": options,
    }
    # Supabase signs user tokens with asymmetric keys (ES256/RS256, published as JWKS) on new
    # projects and the CLI; older projects and service tokens use the legacy HS256 secret.
    # The path is chosen from the header, but each algorithm is only ever verified against its
    # own key type: HS256 against the secret, ES256/RS256 against the JWKS public keys.
    alg = jwt.get_unverified_header(token).get("alg")
    if alg == "HS256":
        if not settings.supabase_jwt_secret:
            raise jwt.InvalidAlgorithmError("HS256 tokens are not accepted (no shared secret)")
        return jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], **common)
    if not settings.supabase_url:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Auth is not configured")
    if alg not in ("ES256", "RS256"):
        raise jwt.InvalidAlgorithmError(f"Algorithm {alg!r} not allowed")
    key = _jwks(settings).get_signing_key_from_jwt(token)
    return jwt.decode(token, key, algorithms=["ES256", "RS256"], **common)


def verify_token(token: str, settings: Settings) -> dict:
    """Verify a Supabase access token. Errors are logged, never echoed to the client."""
    material = "\x00".join((token, settings.supabase_jwt_secret, settings.supabase_url))
    digest = hashlib.sha256(material.encode()).hexdigest()
    now = time.time()
    hit = _token_cache.get(digest)
    if hit and hit[0] > now:
        return hit[1]
    try:
        claims = _decode(token, settings)
    except (jwt.PyJWTError, ValueError) as exc:
        log.info("rejected token: %s", type(exc).__name__)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if len(_token_cache) >= _TOKEN_CACHE_MAX:
        for k in [k for k, (exp, _) in _token_cache.items() if exp <= now] or list(_token_cache):
            _token_cache.pop(k, None)
    # cache until expiry, at most 5 minutes
    _token_cache[digest] = (min(float(claims["exp"]), now + 300), claims)
    return claims


def get_caller(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> Caller:
    if settings.auth_disabled:
        return Caller(user_id="dev", token=None)
    if not authorization:
        return Caller(user_id=None, token=None)
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 8192:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Expected a Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = verify_token(token, settings)
    sub = claims.get("sub")
    if not sub or claims.get("role") == "anon":
        return Caller(user_id=None, token=None)
    return Caller(user_id=sub, token=token, email=claims.get("email"))


def require_compute(
    caller: Annotated[Caller, Depends(get_caller)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Caller:
    if caller.anonymous and not settings.allow_anonymous_compute:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    return caller


_plan_cache: dict[tuple[str, str | None], tuple[float, Plan]] = {}
_PLAN_CACHE_MAX = 10_000


def valid_workspace_id(workspace_id: str | None) -> str | None:
    """Workspace ids are UUIDs; anything else is rejected before it reaches PostgREST."""
    if workspace_id is None:
        return None
    try:
        return str(uuid.UUID(workspace_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(422, "workspace_id must be a UUID") from exc


async def plan_for(caller: Caller, settings: Settings, workspace_id: str | None = None) -> Plan:
    if settings.auth_disabled:
        return "pro"
    if caller.anonymous or not caller.token:
        return "anonymous"
    workspace_id = valid_workspace_id(workspace_id)
    key = (caller.user_id or "", workspace_id)
    hit = _plan_cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    rpc, body = (
        ("workspace_plan", {"p_workspace_id": workspace_id}) if workspace_id else ("my_plan", {})
    )
    url = settings.supabase_url.rstrip("/") + f"/rest/v1/rpc/{rpc}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                url,
                json=body,
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Authorization": f"Bearer {caller.token}",
                },
            )
        plan: Plan = "pro" if r.status_code == 200 and r.json() == "pro" else "free"
    except (httpx.HTTPError, ValueError):
        plan = "free"  # fail closed for paid features
    if len(_plan_cache) >= _PLAN_CACHE_MAX:
        _plan_cache.clear()
    _plan_cache[key] = (time.monotonic() + 60.0, plan)
    return plan
