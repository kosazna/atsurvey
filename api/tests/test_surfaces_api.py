import math

import pytest
from fastapi.testclient import TestClient

from atsurvey_api import auth
from atsurvey_api.config import Settings, get_settings
from atsurvey_api.main import app

E0, N0 = 476_000.0, 4_205_000.0


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: Settings(
        supabase_jwt_secret="test-secret-with-at-least-32-bytes-long!",  # secret-scan: allow
        supabase_url="http://supabase.invalid",
    )
    auth._plan_cache.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


def grid(n=11, step=10.0):
    return [
        {"name": f"P{i}_{j}", "x": E0 + i * step, "y": N0 + j * step, "z": 10.0 + 0.1 * i * step}
        for i in range(n)
        for j in range(n)
    ]


SURFACE = {"points": grid()}


def test_tin(client):
    r = client.post("/v1/surfaces/tin", json={"surface": SURFACE})
    assert r.status_code == 200
    body = r.json()
    assert body["stats"]["triangles"] == 200
    assert body["stats"]["area_2d"] == pytest.approx(10_000.0)
    assert len(body["outline"]) == 1


def test_contours(client):
    r = client.post("/v1/surfaces/contours", json={"surface": SURFACE, "interval": 2.5, "base": 0})
    assert r.status_code == 200
    lines = r.json()["lines"]
    # the east border lies exactly at 20 (z ≥ L counts as above, so it is drawn there)
    assert sorted({line["z"] for line in lines}) == [12.5, 15.0, 17.5, 20.0]
    assert all(line["index"] == (line["z"] == 12.5) for line in lines)  # 12.5 = 5 · 2.5


def test_heights(client):
    r = client.post(
        "/v1/surfaces/heights",
        json={
            "surface": SURFACE,
            "points": [{"name": "K1", "x": E0 + 33, "y": N0 + 41}, {"x": E0 - 5, "y": N0}],
        },
    )
    rows = r.json()["rows"]
    assert rows[0]["z"] == pytest.approx(13.3) and rows[1]["z"] is None
    assert r.json()["issues"][0]["code"] == "SURF_OUTSIDE"


def test_volumes(client):
    r = client.post("/v1/surfaces/volume/level", json={"surface": SURFACE, "level": 15.0})
    v = r.json()
    assert v["cut"] == pytest.approx(12_500.0) and v["fill"] == pytest.approx(12_500.0)
    design = {"points": [{**p, "z": p["z"] - 1.5} for p in grid()]}
    r = client.post("/v1/surfaces/volume/surfaces", json={"existing": SURFACE, "design": design})
    assert r.status_code == 200 and r.json()["cut"] == pytest.approx(15_000.0)


def test_profile(client):
    line = [{"x": E0 + 5, "y": N0 + 50}, {"x": E0 + 95, "y": N0 + 50}]
    r = client.post(
        "/v1/surfaces/profile",
        json={"surface": SURFACE, "alignment": line, "section_interval": 30, "half_width": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["length"] == pytest.approx(90.0)
    assert [s["chainage"] for s in body["sections"]] == [0, 30, 60, 90]
    assert body["sections"][0]["azimuth"] == pytest.approx(math.pi / 2)


@pytest.mark.parametrize(
    "path,body,fragment",
    [
        ("/v1/surfaces/tin", {"surface": {"points": grid()[:2]}}, "At least 3"),
        (
            "/v1/surfaces/tin",
            {"surface": {"points": [{"x": E0 + i, "y": N0 + i, "z": 1} for i in range(5)]}},
            "collinear",
        ),
        (
            "/v1/surfaces/contours",
            {"surface": SURFACE, "interval": 0.001},
            "Too many contour levels",
        ),
    ],
)
def test_bad_geometry_is_422(client, path, body, fragment):
    r = client.post(path, json=body)
    assert r.status_code == 422 and fragment in r.json()["detail"]


def test_input_bounds(client):
    too_many = {"surface": {"points": [{"x": 0, "y": 0, "z": 0}] * 50_001}}
    r = client.post("/v1/surfaces/tin", json=too_many)
    assert r.status_code in (413, 422)
    assert (
        client.post("/v1/surfaces/contours", json={"surface": SURFACE, "interval": 0}).status_code
        == 422
    )
    r = client.post(
        "/v1/surfaces/contours", json={"surface": SURFACE, "interval": 1, "index_every": 1000}
    )
    assert r.status_code == 422
    r = client.post("/v1/surfaces/tin", json={"surface": {**SURFACE, "max_edge": -1}})
    assert r.status_code == 422
    r = client.post(
        "/v1/surfaces/heights", json={"surface": SURFACE, "points": [{"x": 0, "y": 0}] * 10_001}
    )
    assert r.status_code == 422


def test_bounded_point_count_is_a_schema_rule():
    from atsurvey.core.surfaces.models import MAX_POINTS, SurfaceSpec

    with pytest.raises(ValueError):
        SurfaceSpec(points=[{"x": 0, "y": 0, "z": 0}] * (MAX_POINTS + 1))


def test_export_plan_gating(client, monkeypatch):
    req = {
        "format": "dxf",
        "content": "contours",
        "project_name": "Οικόπεδο",
        "contours": {"surface": SURFACE, "interval": 1},
        "include_tin": True,
    }
    r = client.post("/v1/surfaces/export", json=req)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "plan_required"
    r = client.post("/v1/surfaces/export", json={**req, "format": "csv"})
    assert r.status_code == 200
    assert "Oikopedo_isoypses.csv" in r.headers["content-disposition"]
    assert r.content.startswith("﻿line,z".encode())

    async def fake_plan(caller, settings, workspace_id=None):
        return "pro"

    monkeypatch.setattr(auth, "plan_for", fake_plan)
    r = client.post("/v1/surfaces/export", json=req)
    assert r.status_code == 200
    assert b"ISOYPSES_KYRIES" in r.content and b"3DFACE" in r.content


def test_export_requires_matching_parameters(client):
    r = client.post("/v1/surfaces/export", json={"format": "csv", "content": "profile"})
    assert r.status_code == 422
    r = client.post(
        "/v1/surfaces/export",
        json={
            "format": "dxf",
            "content": "volume",
            "volume_level": {"surface": SURFACE, "level": 1},
        },
    )
    assert r.status_code in (402, 422)


def test_routes_in_openapi(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    assert {
        "/v1/surfaces/tin",
        "/v1/surfaces/contours",
        "/v1/surfaces/heights",
        "/v1/surfaces/volume/level",
        "/v1/surfaces/volume/surfaces",
        "/v1/surfaces/profile",
        "/v1/surfaces/export",
    } <= paths
