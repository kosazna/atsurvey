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


GON = math.pi / 200
CC = GON / 10000

NETWORK = {
    "benchmarks": [{"name": "A", "h": 100.0}, {"name": "B", "h": 110.0}],
    "lines": [
        {"frm": "A", "to": "X", "dh": 5.010, "length_km": 1.0},
        {"frm": "X", "to": "B", "dh": 5.000, "length_km": 1.0},
        {"frm": "A", "to": "Y", "dh": 2.0, "length_km": 0.5},
        {"frm": "Y", "to": "X", "dh": 3.006, "length_km": 0.5},
    ],
}


def _face(z_gon, c=10 * CC, i=-20 * CC):
    z = z_gon * GON
    e = c / math.sin(z)
    return {"name": f"T{z_gon}", "hz1": 1.0 + e, "hz2": 1.0 + math.pi - e, "v1": z + i,
            "v2": 2 * math.pi - z + i}  # fmt: skip


HAPPY = [
    (
        "/v1/leveling/network",
        NETWORK,
        lambda r: r["dof"] == 2 and len(r["loops"]) == 2,
    ),
    (
        "/v1/instruments/two-face",
        {"targets": [_face(100), _face(95), _face(103)]},
        lambda r: (
            r["collimation"] == pytest.approx(10 * CC) and r["index"] == pytest.approx(-20 * CC)
        ),
    ),
    (
        "/v1/instruments/two-peg",
        {
            "setup1": {"a": 1.523, "b": 1.211, "dist_a": 30, "dist_b": 30},
            "setup2": {"a": 1.408, "b": 1.083, "dist_a": 3, "dist_b": 57},
        },
        lambda r: r["epsilon"] == pytest.approx(-0.013 / 54) and r["within_tolerance"] is False,
    ),
    (
        "/v1/instruments/edm-constant",
        {
            "pillars": ["P0", "P1", "P2"],
            "observations": [
                {"frm": "P0", "to": "P1", "distance": 49.99},
                {"frm": "P1", "to": "P2", "distance": 59.99},
                {"frm": "P0", "to": "P2", "distance": 109.99},
            ],
        },
        lambda r: r["constant"] == pytest.approx(0.01) and r["dof"] == 0,
    ),
]


@pytest.mark.parametrize(("path", "body", "check"), HAPPY)
def test_happy_paths(client, path, body, check):
    res = client.post(path, json=body)
    assert res.status_code == 200, res.text
    assert check(res.json())


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/v1/leveling/network", {"benchmarks": [], "lines": []}),
        ("/v1/leveling/network", {"lines": [{"frm": "A", "to": "B", "dh": 1}]}),  # no length
        (
            "/v1/leveling/network",
            {**NETWORK, "datum": "free", "free_points": ["NOPE"]},
        ),
        ("/v1/instruments/two-face", {"targets": [_face(2)]}),  # too steep
        (
            "/v1/instruments/two-peg",
            {
                "setup1": {"a": 1.5, "b": 1.2, "dist_a": 20, "dist_b": 20},
                "setup2": {"a": 1.5, "b": 1.2, "dist_a": 20, "dist_b": 20},
            },
        ),
        (
            "/v1/instruments/edm-constant",
            {
                "pillars": ["P0", "P1", "P2"],
                "observations": [
                    {"frm": "P0", "to": "P1", "distance": 50},
                    {"frm": "P1", "to": "P2", "distance": 60},
                    {"frm": "P1", "to": "P2", "distance": 60.001},
                ],
            },
        ),
    ],
)
def test_invalid_inputs_are_422(client, path, body):
    assert client.post(path, json=body).status_code == 422


def test_bounds_reject_huge_inputs(client):
    lines = [{"frm": f"P{i}", "to": f"P{i + 1}", "dh": 0.1, "length_km": 0.1} for i in range(3001)]
    res = client.post("/v1/leveling/network", json={"benchmarks": [], "lines": lines})
    assert res.status_code == 422
    res = client.post(
        "/v1/leveling/network",
        json={"lines": [{"frm": "A", "to": "B", "dh": "NaN", "length_km": 1}]},
    )
    assert res.status_code == 422


def test_network_issues_are_returned(client):
    body = {
        **NETWORK,
        "lines": [*NETWORK["lines"], {"frm": "Q", "to": "R", "dh": 1, "length_km": 1}],
    }
    res = client.post("/v1/leveling/network", json=body)
    assert res.status_code == 200
    codes = {i["code"] for i in res.json()["issues"]}
    assert "LEVNET_NO_DATUM" in codes
