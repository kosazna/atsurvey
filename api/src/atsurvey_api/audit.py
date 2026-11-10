"""Workspace audit log: record exports of stored projects (docs/security.md, DB-10).

The API holds no database credentials: it calls the ``log_export`` RPC with the caller's own
token, so the database checks project access and stamps the actor itself. Best effort: a
logging failure is reported in the server log and never blocks the download.
"""

from __future__ import annotations

import logging
import uuid

import httpx

from .auth import Caller
from .config import Settings

log = logging.getLogger("atsurvey_api.audit")


def valid_project_id(project_id: str | None) -> str | None:
    """Project ids are UUIDs; anything else is ignored (local demo projects are never logged)."""
    if project_id is None:
        return None
    try:
        return str(uuid.UUID(project_id))
    except (ValueError, AttributeError, TypeError):
        return None


async def log_export(caller: Caller, settings: Settings, project_id: str | None, fmt: str) -> bool:
    """Record ``project.exported`` for a signed-in caller; returns whether it was recorded."""
    pid = valid_project_id(project_id)
    if settings.auth_disabled or caller.anonymous or not caller.token or pid is None:
        return False
    url = settings.supabase_url.rstrip("/") + "/rest/v1/rpc/log_export"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                url,
                json={"p_project_id": pid, "p_format": fmt},
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Authorization": f"Bearer {caller.token}",
                },
            )
    except httpx.HTTPError as exc:
        log.warning("export audit failed: %s", type(exc).__name__)
        return False
    if r.status_code >= 300:
        log.warning("export audit rejected: HTTP %s", r.status_code)
        return False
    return True
