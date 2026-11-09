"""Supabase access-token verification and plan lookup."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Annotated, Literal

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, status

from .config import Settings, get_settings

Plan = Literal["anonymous", "free", "pro"]

EXPORTS_BY_PLAN: dict[str, list[str]] = {
    "anonymous": ["csv"],
    "free": ["csv", "xlsx"],
    "pro": ["csv", "xlsx", "shp", "dxf", "pdf"],
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


def _jwks(settings: Settings) -> jwt.PyJWKClient:
    url = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
    client = _jwks_clients.get(url)
    if client is None:
        client = _jwks_clients[url] = jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)
    return client


def verify_token(token: str, settings: Settings) -> dict:
    try:
        if settings.supabase_jwt_secret:
            return jwt.decode(
                token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated"
            )
        if not settings.supabase_url:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Auth is not configured")
        key = _jwks(settings).get_signing_key_from_jwt(token)
        return jwt.decode(token, key, algorithms=["ES256", "RS256"], audience="authenticated")
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc


def get_caller(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> Caller:
    if settings.auth_disabled:
        return Caller(user_id="dev", token=None)
    if not authorization:
        return Caller(user_id=None, token=None)
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Expected a Bearer token")
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


async def plan_for(caller: Caller, settings: Settings, workspace_id: str | None = None) -> Plan:
    if settings.auth_disabled:
        return "pro"
    if caller.anonymous or not caller.token:
        return "anonymous"
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
    except httpx.HTTPError:
        plan = "free"  # fail closed for paid features
    _plan_cache[key] = (time.monotonic() + 60.0, plan)
    return plan
