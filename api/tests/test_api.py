import sys
import time
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[2] / "engine" / "tests"))
from atsurvey import ProjectInput, TraverseSpec
from atsurvey_api import auth
from atsurvey_api.config import Settings, get_settings
from atsurvey_api.main import app

from synth import TRUTH, observe, traverse_setups
from test_formats import gsi16
from test_traverse import LINK, control

SECRET = "test-secret-with-at-least-32-bytes-long!"


def make_settings(**kw):
    base = dict(supabase_jwt_secret=SECRET, supabase_url="http://supabase.invalid")
    base.update(kw)
    return Settings(**base)


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: make_settings()
    auth._plan_cache.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


def token(sub="user-1", **claims):
    payload = {
        "sub": sub,
        "aud": "authenticated",
        "role": "authenticated",
        "iss": "http://supabase.invalid/auth/v1",
        "exp": time.time() + 600,
    }
    payload.update(claims)
    return jwt.encode(payload, SECRET, algorithm="HS256")


def project_json():
    setups = traverse_setups(TRUTH, LINK)
    setups.append(observe(TRUTH, "S1", ["T2", "D1"]))
    return ProjectInput(
        control_points=control(), setups=setups, traverses=[TraverseSpec(route=LINK)]
    ).model_dump(mode="json")


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_anonymous_compute_allowed(client):
    r = client.post("/v1/compute", json=project_json())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["n_traverses_ok"] == 1
    names = {p["name"] for p in body["points"]}
    assert {"S1", "S2", "S3", "D1"} <= names


def test_anonymous_compute_can_be_disabled(client):
    app.dependency_overrides[get_settings] = lambda: make_settings(allow_anonymous_compute=False)
    assert client.post("/v1/compute", json=project_json()).status_code == 401
    r = client.post(
        "/v1/compute", json=project_json(), headers={"Authorization": f"Bearer {token()}"}
    )
    assert r.status_code == 200


def test_invalid_token_rejected(client):
    r = client.post("/v1/compute", json=project_json(), headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    bad = jwt.encode(
        {"sub": "x", "aud": "authenticated"}, "other-secret-0123456789abcdef0123", "HS256"
    )
    r = client.post("/v1/compute", json=project_json(), headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401
    expired = token(exp=time.time() - 120)  # beyond the 30 s clock-skew leeway
    r = client.post(
        "/v1/compute", json=project_json(), headers={"Authorization": f"Bearer {expired}"}
    )
    assert r.status_code == 401


def test_parse_upload(client):
    setups = traverse_setups(TRUTH, LINK)
    r = client.post("/v1/parse", files={"file": ("job.gsi", gsi16(setups), "text/plain")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["format"] == "leica_gsi" and body["stats"]["setups"] == 5


def test_parse_rejects_garbage_and_oversize(client):
    r = client.post("/v1/parse", files={"file": ("x.txt", b"hello\nworld", "text/plain")})
    assert r.status_code == 422
    app.dependency_overrides[get_settings] = lambda: make_settings(max_upload_mb=0)
    r = client.post("/v1/parse", files={"file": ("x.gsi", b"x" * 10, "text/plain")})
    assert r.status_code == 413


def test_suggest(client):
    body = project_json()
    body["traverses"] = []
    r = client.post("/v1/suggest-traverses", json=body)
    assert r.status_code == 200
    assert len(r.json()["suggestions"]) == 1


def test_export_plan_gating(client, monkeypatch):
    req = {"format": "dxf", "project_name": "Αφίδνες", "input": project_json()}
    # anonymous: only csv
    assert client.post("/v1/export", json=req).status_code == 402
    r = client.post("/v1/export", json={**req, "format": "csv"})
    assert r.status_code == 200
    assert "filename*=UTF-8''Afidnes.csv" in r.headers["content-disposition"]

    async def fake_plan(caller, settings, workspace_id=None):
        return "pro"

    monkeypatch.setattr("atsurvey_api.main.plan_for", fake_plan)
    r = client.post("/v1/export", json=req, headers={"Authorization": f"Bearer {token()}"})
    assert r.status_code == 200
    assert r.content.startswith(b"  0\nSECTION") or b"SECTION" in r.content[:200]
    assert r.headers["x-input-hash"]


def test_plan_lookup_fails_closed(client):
    # supabase.invalid is unreachable → free plan, so DXF is refused
    req = {"format": "pdf", "project_name": "p", "input": project_json()}
    r = client.post("/v1/export", json=req, headers={"Authorization": f"Bearer {token()}"})
    assert r.status_code == 402
    me = client.get("/v1/me", headers={"Authorization": f"Bearer {token()}"}).json()
    assert me["plan"] == "free" and me["export_formats"] == ["csv", "xlsx"]


def test_observation_limit(client):
    app.dependency_overrides[get_settings] = lambda: make_settings(max_observations=3)
    assert client.post("/v1/compute", json=project_json()).status_code == 413


def test_openapi_schema_lists_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/v1/parse", "/v1/compute", "/v1/export", "/v1/suggest-traverses", "/v1/me"} <= set(
        paths
    )
