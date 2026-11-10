"""Export audit hook (docs/security.md, DB-10)."""

import asyncio

import httpx
from test_api import client, make_settings, project_json, token  # noqa: F401  (fixture)

from atsurvey_api import audit
from atsurvey_api.auth import Caller

PROJECT = "cccccccc-0000-0000-0000-000000000101"
SIGNED_IN = Caller(user_id="user-1", token="tok")
REAL_CLIENT = httpx.AsyncClient


def _patch(monkeypatch, handler):
    monkeypatch.setattr(
        audit.httpx,
        "AsyncClient",
        lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **kw),
    )


def _capture(monkeypatch, status=204):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status)

    _patch(monkeypatch, handler)
    return calls


def test_export_is_logged_with_the_callers_token(monkeypatch):
    calls = _capture(monkeypatch)
    ok = asyncio.run(audit.log_export(SIGNED_IN, make_settings(), PROJECT, "pdf"))
    assert ok
    (req,) = calls
    assert req.url.path == "/rest/v1/rpc/log_export"
    assert req.headers["authorization"] == "Bearer tok"
    assert req.read() == b'{"p_project_id":"' + PROJECT.encode() + b'","p_format":"pdf"}'


def test_nothing_logged_for_anonymous_demo_or_malformed_ids(monkeypatch):
    calls = _capture(monkeypatch)
    s = make_settings()
    assert not asyncio.run(audit.log_export(Caller(user_id=None, token=None), s, PROJECT, "csv"))
    assert not asyncio.run(audit.log_export(SIGNED_IN, s, None, "csv"))
    assert not asyncio.run(audit.log_export(SIGNED_IN, s, "local-1'; drop", "csv"))
    assert calls == []


def test_logging_failure_never_raises(monkeypatch):
    _capture(monkeypatch, status=403)
    assert not asyncio.run(audit.log_export(SIGNED_IN, make_settings(), PROJECT, "pdf"))

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    _patch(monkeypatch, unreachable)
    assert not asyncio.run(audit.log_export(SIGNED_IN, make_settings(), PROJECT, "pdf"))


def test_export_endpoint_passes_project_id(client, monkeypatch):  # noqa: F811
    seen: list[tuple[str | None, str]] = []

    async def fake_log(caller, settings, project_id, fmt):
        seen.append((project_id, fmt))
        return True

    monkeypatch.setattr("atsurvey_api.main.log_export", fake_log)
    req = {"format": "csv", "project_name": "p", "input": project_json(), "project_id": PROJECT}
    r = client.post("/v1/export", json=req, headers={"Authorization": f"Bearer {token()}"})
    assert r.status_code == 200
    assert seen == [(PROJECT, "csv")]
