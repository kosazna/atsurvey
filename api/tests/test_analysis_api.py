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


URL = "/v1/analysis/preanalysis"
POINTS = [
    {"name": "P", "x": 0, "y": 0},
    {"name": "A", "x": 100, "y": 0, "fixed": True},
    {"name": "C", "x": -100, "y": 0, "fixed": True},
    {"name": "B", "x": 0, "y": 100, "fixed": True},
]
OBS = [{"kind": "distance", "station": "P", "target": t} for t in "ACB"]
SPEC = {
    "sigma_direction_cc": 10,
    "sigma_distance_mm": 2,
    "sigma_distance_ppm": 0,
    "sigma_centering_instrument_mm": 0,
    "sigma_centering_target_mm": 0,
}


def test_preanalysis_route(client):
    r = client.post(
        URL,
        json={
            "points": POINTS,
            "observations": OBS,
            "instrument": SPEC,
            "relative_pairs": [["P", "A"]],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    p = body["points"][0]
    assert p["name"] == "P"
    assert p["sx"] == pytest.approx(0.002 / 2**0.5)
    assert p["sy"] == pytest.approx(0.002)
    assert body["delta0"] == pytest.approx(4.13, abs=0.005)
    assert [o["status"] for o in body["observations"]] == ["ok", "ok", "uncontrolled"]
    assert body["relative"][0]["frm"] == "P"
    assert any(i["code"] == "PREANALYSIS_UNCONTROLLED" for i in body["issues"])


def test_datum_defect_is_a_result_not_an_error(client):
    pts = [
        {"name": "A", "x": 0, "y": 0, "fixed": True},
        {"name": "N", "x": 100, "y": 0},
        {"name": "M", "x": 50, "y": 80},
    ]
    obs = [
        {"kind": k, "station": s, "target": t}
        for s, t in (("A", "N"), ("N", "M"), ("M", "A"))
        for k in ("direction", "distance")
    ]
    r = client.post(URL, json={"points": pts, "observations": obs})
    assert r.status_code == 200
    assert [i["code"] for i in r.json()["issues"]] == ["PREANALYSIS_DATUM"]


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        (
            {
                "points": POINTS,
                "observations": [{"kind": "distance", "station": "P", "target": "X"}],
            },
            "unknown point",
        ),
        ({"points": [*POINTS, POINTS[0]], "observations": OBS}, "Duplicate"),
    ],
)
def test_bad_input_is_422(client, body, fragment):
    r = client.post(URL, json=body)
    assert r.status_code == 422
    assert fragment in r.text


@pytest.mark.parametrize(
    "body",
    [
        {"points": POINTS, "observations": []},
        {"points": [{"name": f"P{i}", "x": i, "y": 0} for i in range(501)], "observations": OBS},
        {"points": POINTS, "observations": OBS * 1700},
        {"points": [{"name": "P", "x": 1e12, "y": 0}, *POINTS[1:]], "observations": OBS},
        {"points": POINTS, "observations": OBS, "instrument": {**SPEC, "sigma_direction_cc": 0}},
        {"points": POINTS, "observations": OBS, "unexpected": 1},
    ],
    ids=[
        "no-obs",
        "too-many-points",
        "too-many-obs",
        "huge-coordinate",
        "zero-sigma",
        "extra-field",
    ],
)
def test_bounds_are_enforced(client, body):
    assert client.post(URL, json=body).status_code == 422


def test_nan_is_rejected(client):
    raw = '{"points":[{"name":"P","x":NaN,"y":0}],"observations":[]}'
    r = client.post(URL, content=raw, headers={"Content-Type": "application/json"})
    assert r.status_code == 422
