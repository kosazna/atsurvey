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


P = {"x": 476000.0, "y": 4205000.0}
Q = {"x": 476100.0, "y": 4205100.0}

HAPPY = [
    ("/v1/cogo/inverse", {"a": P, "b": Q}, lambda r: r["distance"] == pytest.approx(100 * 2**0.5)),
    (
        "/v1/cogo/polar",
        {"station": P, "azimuth": math.pi / 2, "distance": 10},
        lambda r: r["point"]["x"] == pytest.approx(476010.0),
    ),
    (
        "/v1/cogo/intersection/angles",
        {
            "a": {"x": 0, "y": 0},
            "b": {"x": 100, "y": 0},
            "angle_a": 3.5 * math.pi / 2,
            "angle_b": math.pi / 4,
        },
        lambda r: r["solutions"][0]["y"] == pytest.approx(50),
    ),
    (
        "/v1/cogo/intersection/distances",
        {"a": {"x": 0, "y": 0}, "r_a": 5, "b": {"x": 8, "y": 0}, "r_b": 5},
        lambda r: len(r["solutions"]) == 2,
    ),
    (
        "/v1/cogo/intersection/lines",
        {
            "p1": {"x": 0, "y": 0},
            "p2": {"x": 10, "y": 10},
            "p3": {"x": 0, "y": 10},
            "p4": {"x": 10, "y": 0},
        },
        lambda r: r["solutions"][0]["x"] == pytest.approx(5),
    ),
    (
        "/v1/cogo/area",
        {"points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}, {"x": 0, "y": 10}]},
        lambda r: r["area"] == pytest.approx(100),
    ),
    (
        "/v1/cogo/transform",
        {
            "method": "helmert",
            "common": [
                {"name": "A", "src": {"x": 0, "y": 0}, "dst": {"x": 10, "y": 10}},
                {"name": "B", "src": {"x": 1, "y": 0}, "dst": {"x": 11, "y": 10}},
            ],
            "points": [{"x": 5, "y": 5}],
        },
        lambda r: r["points"][0]["x"] == pytest.approx(15),
    ),
    (
        "/v1/cogo/offset",
        {"a": {"x": 0, "y": 0}, "b": {"x": 0, "y": 10}, "points": [{"x": 2, "y": 3}]},
        lambda r: r["rows"][0]["offset"] == pytest.approx(2),
    ),
    (
        "/v1/leveling",
        {
            "benchmarks": [{"name": "BM", "h": 10}],
            "setups": [
                {
                    "readings": [
                        {"point": "BM", "reading": 1.5, "kind": "bs"},
                        {"point": "TP", "reading": 1.0, "kind": "fs"},
                    ]
                }
            ],
        },
        lambda r: r["points"][-1]["h"] == pytest.approx(10.5),
    ),
]


def _resection_body():
    s = (1000.0, 2000.0)
    pts = [(1500.0, 2600.0), (1900.0, 1800.0), (700.0, 1500.0)]
    return {
        "observations": [
            {"point": {"x": x, "y": y}, "direction": math.atan2(x - s[0], y - s[1]) % (2 * math.pi)}
            for x, y in pts
        ]
    }


@pytest.mark.parametrize(("path", "body", "check"), HAPPY, ids=[h[0] for h in HAPPY])
def test_cogo_routes(client, path, body, check):
    r = client.post(path, json=body)
    assert r.status_code == 200, r.text
    assert check(r.json())


def test_resection_route(client):
    r = client.post("/v1/cogo/resection", json=_resection_body())
    assert r.status_code == 200, r.text
    assert r.json()["station"]["x"] == pytest.approx(1000.0, abs=1e-6)


BAD = [
    ("/v1/cogo/inverse", {"a": P, "b": P}, "coincide"),
    ("/v1/cogo/polar", {"station": P, "distance": 10}, "azimuth"),
    (
        "/v1/cogo/intersection/lines",
        {"p1": P, "p2": P, "p3": {"x": 0, "y": 1}, "p4": {"x": 1, "y": 2}},
        "two distinct",
    ),
    (
        "/v1/cogo/resection",
        {"observations": _resection_body()["observations"][:2]},
        "needs",
    ),
    (
        "/v1/cogo/area",
        {"points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}, {"x": 2, "y": 2}]},
        "zero area",
    ),
    (
        "/v1/cogo/transform",
        {
            "method": "affine",
            "common": [
                {"name": "A", "src": {"x": 0, "y": 0}, "dst": {"x": 0, "y": 0}},
                {"name": "B", "src": {"x": 1, "y": 0}, "dst": {"x": 1, "y": 0}},
            ],
        },
        "at least 3",
    ),
    ("/v1/cogo/offset", {"a": P, "b": P, "points": [Q]}, "coincide"),
    (
        "/v1/leveling",
        {
            "benchmarks": [{"name": "X", "h": 0}],
            "setups": [
                {
                    "readings": [
                        {"point": "A", "reading": 1, "kind": "bs"},
                        {"point": "B", "reading": 1, "kind": "fs"},
                    ]
                }
            ],
        },
        "benchmark",
    ),
]


@pytest.mark.parametrize(("path", "body", "fragment"), BAD, ids=[b[0] for b in BAD])
def test_cogo_routes_reject_degenerate_geometry(client, path, body, fragment):
    r = client.post(path, json=body)
    assert r.status_code == 422, r.text
    assert fragment in str(r.json()["detail"])


def test_schema_errors_are_422(client):
    assert client.post("/v1/cogo/inverse", json={"a": P}).status_code == 422


def test_routes_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in [h[0] for h in HAPPY] + ["/v1/cogo/resection"]:
        assert p in paths


def test_stakeout_route(client):
    body = {
        "station": {"x": 100.0, "y": 100.0, "z": 10.0},
        "backsight": {"x": 100.0, "y": 200.0},
        "points": [{"x": 200.0, "y": 100.0, "z": 12.0, "name": "D1"}],
    }
    r = client.post("/v1/cogo/stakeout", json=body)
    assert r.status_code == 200, r.text
    row = r.json()["rows"][0]
    assert row["name"] == "D1"
    assert abs(row["angle"] - math.pi / 2) < 1e-12 and abs(row["distance"] - 100.0) < 1e-12
    bad = client.post("/v1/cogo/stakeout", json={**body, "backsight": None})
    assert bad.status_code == 422


def test_tolerance_presets_route(client):
    r = client.get("/v1/presets/tolerances")
    assert r.status_code == 200
    presets = {p["id"]: p for p in r.json()}
    p = presets["gr:flat:primary:1/500"]
    assert p["tolerances"]["linear_per_sqrt_m_m"] == 0.005
    assert p["tolerances"]["angular_per_sqrt_n_cc"] == 200.0
    assert p["label_el"] == "Πρωτεύουσα · Ομαλό · 1/500"
