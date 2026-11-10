import math

import pytest
from fastapi.testclient import TestClient

from atsurvey_api.config import Settings, get_settings
from atsurvey_api.main import app


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: Settings(
        supabase_jwt_secret="test-secret-with-at-least-32-bytes-long!",  # secret-scan: allow
        supabase_url="http://supabase.invalid",
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


ROAD = {
    "vertices": [
        {"x": 0, "y": 0},
        {"name": "K1", "x": 0, "y": 500, "radius": 300, "a_in": 150},
        {"x": 400, "y": 800},
    ]
}


def test_setout_points(client):
    r = client.post(
        "/v1/setout/points",
        json={
            "station": {"name": "S", "x": 0, "y": 0, "z": 10},
            "backsight": {"name": "B", "x": 0, "y": 100},
            "points": [{"name": "P", "x": 100, "y": 0, "z": 11}, {"name": "Q", "x": 10, "y": 10}],
            "instrument_height": 1.5,
            "target_height": 1.5,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"][0]["direction"] == pytest.approx(math.pi / 2)
    assert body["rows"][0]["zenith"] == pytest.approx(math.atan2(100, 1))
    assert body["field_order"] == [1, 0]


def test_setout_points_errors(client):
    same = {"x": 0, "y": 0}
    r = client.post(
        "/v1/setout/points", json={"station": same, "backsight": same, "points": [same]}
    )
    assert r.status_code == 422
    assert "coincides" in r.json()["detail"]
    too_many = [{"x": i, "y": 1} for i in range(10_001)]
    r = client.post(
        "/v1/setout/points", json={"station": same, "backsight_azimuth": 0, "points": too_many}
    )
    assert r.status_code == 422


def test_setout_check(client):
    r = client.post(
        "/v1/setout/check",
        json={
            "design": [{"name": "A", "x": 0, "y": 0}, {"name": "B", "x": 5, "y": 5}],
            "measured": [{"name": "A", "x": 0.03, "y": 0.04}],
            "tolerance_xy": 0.02,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"][0]["radial"] == pytest.approx(0.05)
    assert body["summary"]["out_of_tolerance"] == 1
    assert body["unmatched_design"] == ["B"]


def test_alignment_and_queries(client):
    r = client.post("/v1/setout/alignment", json=ROAD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [m["code"] for m in body["main_points"]] == ["BP", "TS", "SC", "MC", "CS", "ST", "EP"]
    assert len(body["polyline"]) > 10
    r = client.post(
        "/v1/setout/alignment/locate",
        json={
            "alignment": ROAD,
            "stations": [{"chainage": 100, "offset": 2}],
            "points": [{"x": 2, "y": 100}],
        },
    )
    assert r.status_code == 200, r.text
    loc = r.json()
    assert loc["stations"][0]["x"] == pytest.approx(2.0)
    assert loc["points"][0]["chainage"] == pytest.approx(100.0)
    r = client.post(
        "/v1/setout/alignment/stakeout",
        json={"alignment": ROAD, "interval": 50, "offsets": [-3, 3]},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["rows"]) % 2 == 0


def test_alignment_issues_and_bounds(client):
    bad = {"vertices": [{"x": 0, "y": 0}, {"x": 0, "y": 100}, {"x": 100, "y": 100}]}
    r = client.post("/v1/setout/alignment", json=bad)
    assert r.status_code == 200
    assert r.json()["issues"][0]["code"] == "ALIGN_NO_RADIUS"
    r = client.post(
        "/v1/setout/alignment/locate", json={"alignment": bad, "points": [{"x": 1, "y": 1}]}
    )
    assert r.status_code == 422 and "radius" in r.json()["detail"]
    r = client.post("/v1/setout/alignment/stakeout", json={"alignment": ROAD, "interval": 0.001})
    assert r.status_code == 422
    many = {"vertices": [{"x": i, "y": i * i} for i in range(201)]}
    assert client.post("/v1/setout/alignment", json=many).status_code == 422
