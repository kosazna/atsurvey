import math

import pytest
from fastapi.testclient import TestClient

from atsurvey_api.config import Settings, get_settings
from atsurvey_api.main import app

ATHENS = {"name": "ATH", "x": math.radians(23.7275), "y": math.radians(37.9838)}


def _settings(**kw) -> Settings:
    return Settings(
        supabase_jwt_secret="test-secret-with-at-least-32-bytes-long!",  # secret-scan: allow
        supabase_url="http://supabase.invalid",
        **kw,
    )


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: _settings()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_convert_wgs84_to_egsa87(client):
    r = client.post(
        "/v1/coords/convert", json={"src": "wgs84_geo", "dst": "egsa87", "points": [ATHENS]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    p = body["points"][0]
    assert p["name"] == "ATH"
    assert 475_000 < p["x"] < 478_000 and 4_203_000 < p["y"] < 4_206_000
    assert body["approximate"] is True and body["accuracy_m"] == 1.5
    assert any(i["code"] == "COORD_APPROXIMATE" for i in body["issues"])


def test_point_info(client):
    r = client.post(
        "/v1/coords/point-info",
        json={"system": "egsa87", "point": {"x": 500000.0, "y": 4200000.0}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scale_factor"] == pytest.approx(0.9996, abs=1e-12)
    assert body["convergence"] == pytest.approx(0.0, abs=1e-12)
    assert body["utm_zone"] == 35 and body["inside_zone"] is True


def test_coded_failure_returns_code_and_params(client):
    r = client.post(
        "/v1/coords/convert",
        json={
            "src": "hatt",
            "dst": "greek_geo",
            "points": [{"x": 0, "y": 0}],
            "src_hatt": {"sheet": "6124"},
        },
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "COORD_HATT_TABLE_MISSING"
    assert detail["params"] == {"sheet": "6124"}


def test_hepos_unavailable(client):
    r = client.post(
        "/v1/coords/convert",
        json={"src": "wgs84_geo", "dst": "egsa87", "points": [ATHENS], "datum_method": "official"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "COORD_HEPOS_UNAVAILABLE"


@pytest.mark.parametrize(
    "body",
    [
        {"src": "egsa87", "dst": "wgs84_geo", "points": []},
        {"src": "egsa87", "dst": "wgs84_geo", "points": [{"x": 0, "y": 0}] * 10_001},
        {"src": "egsa87", "dst": "mars", "points": [{"x": 0, "y": 0}]},
        {"src": "egsa87", "dst": "wgs84_geo", "points": [{"x": 1e30, "y": 0}]},
        {"src": "egsa87", "dst": "wgs84_geo", "points": [{"x": 0, "y": 0}], "extra": 1},
    ],
)
def test_validation(client, body):
    r = client.post("/v1/coords/convert", json=body)
    assert r.status_code == 422


def test_point_info_out_of_domain_is_422(client):
    r = client.post(
        "/v1/coords/point-info", json={"system": "wgs84_geo", "point": {"x": 0.0, "y": 3.0}}
    )
    assert r.status_code == 422
    assert "radians" in r.json()["detail"]


def test_requires_sign_in_when_anonymous_compute_disabled():
    app.dependency_overrides[get_settings] = lambda: _settings(allow_anonymous_compute=False)
    try:
        r = TestClient(app).post(
            "/v1/coords/convert", json={"src": "wgs84_geo", "dst": "egsa87", "points": [ATHENS]}
        )
        assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()
