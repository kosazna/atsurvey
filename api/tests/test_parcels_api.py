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


E0, N0 = 476000.0, 4205000.0


def v(name, x, y, **kw):
    return {"name": name, "x": E0 + x, "y": N0 + y, **kw}


RECT = {
    "label": "Αγρός",
    "kaek": "050011234001",
    "vertices": [v("A", 0, 0), v("B", 100, 0), v("C", 100, 50), v("D", 0, 50)],
}


def test_compute(client):
    r = client.post("/v1/parcels/compute", json=RECT)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["area"] == pytest.approx(5000.0, abs=1e-9)
    assert body["perimeter"] == pytest.approx(300.0)
    assert body["valid"] is True and body["issues"] == []
    assert [s["frm"] for s in body["sides"]] == ["A", "B", "C", "D"]
    assert body["kaek"] == "050011234001"


def test_compute_with_arc(client):
    body = {
        "vertices": [
            v("A", 0, 0, arc={"radius": 50, "side": "right"}),
            v("B", 100, 0),
            v("C", 100, 100),
            v("D", 0, 100),
        ]
    }
    r = client.post("/v1/parcels/compute", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["area"] == pytest.approx(10_000 + 3.141592653589793 * 2500 / 2, rel=1e-12)


def test_compute_reports_self_intersection_as_issue(client):
    body = {"vertices": [v("A", 0, 0), v("B", 10, 10), v("C", 10, 0), v("D", 0, 10)]}
    r = client.post("/v1/parcels/compute", json=body)
    assert r.status_code == 200
    assert r.json()["valid"] is False
    assert r.json()["issues"][0]["code"] == "PARCEL_SELF_INTERSECTION"


def test_compare(client):
    body = {
        "parcel": RECT,
        "deed_area": 4950.0,
        "cadastre_area": 5010.0,
        "tolerance": {"kind": "percent", "value": 1.0, "source": "συμβατικό όριο"},
    }
    r = client.post("/v1/parcels/compare", json=body)
    assert r.status_code == 200, r.text
    rows = {row["kind"]: row for row in r.json()["rows"]}
    assert rows["surveyed_vs_deed"]["difference"] == pytest.approx(50.0)
    assert rows["surveyed_vs_deed"]["within"] is False
    assert rows["surveyed_vs_cadastre"]["within"] is True
    assert r.json()["tolerance"]["source"] == "συμβατικό όριο"


def test_compare_incomplete_rule_is_422(client):
    body = {"surveyed_area": 10, "deed_area": 9, "tolerance": {"kind": "formula", "a": 1}}
    r = client.post("/v1/parcels/compare", json=body)
    assert r.status_code == 422
    assert "a + b" in r.json()["detail"]


def test_subdivide_parallel_by_ratios(client):
    body = {"parcel": RECT, "method": "parallel", "side": 0, "mode": "ratios", "parts": [1, 1]}
    r = client.post("/v1/parcels/subdivide", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert [p["geometry"]["area"] for p in out["parts"]] == pytest.approx([2500, 2500], abs=1e-6)
    assert [p["name"] for p in out["new_points"]] == ["Ν1", "Ν2"]
    assert len(out["cut_lines"]) == 1


def test_subdivide_pivot(client):
    body = {"parcel": RECT, "method": "pivot", "pivot": "A", "parts": [1000]}
    r = client.post("/v1/parcels/subdivide", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["parts"][0]["geometry"]["area"] == pytest.approx(1000, abs=1e-6)


def test_subdivide_issue_and_422(client):
    r = client.post(
        "/v1/parcels/subdivide",
        json={"parcel": RECT, "method": "parallel", "side": 0, "parts": [9000]},
    )
    assert r.status_code == 200
    assert r.json()["issues"][0]["code"] == "PARCEL_PARTS_EXCEED_AREA"
    r = client.post(
        "/v1/parcels/subdivide",
        json={"parcel": RECT, "method": "parallel", "side": 7, "parts": [10]},
    )
    assert r.status_code == 422 and "out of range" in r.json()["detail"]
    r = client.post(
        "/v1/parcels/subdivide",
        json={"parcel": RECT, "method": "parallel", "side": 0, "parts": [-1]},
    )
    assert r.status_code == 422


def test_merge(client):
    a = {"label": "1", "vertices": [v("A", 0, 0), v("B", 10, 0), v("C", 10, 10), v("D", 0, 10)]}
    b = {"label": "2", "vertices": [v("B", 10, 0), v("E", 20, 0), v("F", 20, 10), v("C", 10, 10)]}
    r = client.post("/v1/parcels/merge", json={"parcels": [a, b]})
    assert r.status_code == 200, r.text
    assert r.json()["merged"]["area"] == pytest.approx(200.0)
    far = {"vertices": [v("X", 50, 0), v("Y", 60, 0), v("Z", 60, 10)]}
    r = client.post("/v1/parcels/merge", json={"parcels": [a, far]})
    assert r.json()["merged"] is None
    assert r.json()["issues"][0]["code"] == "PARCEL_MERGE_NOT_ADJACENT"


@pytest.mark.parametrize(
    "body",
    [
        {
            "vertices": [
                {"name": "A", "x": "NaN", "y": 0},
                {"name": "B", "x": 1, "y": 0},
                {"name": "C", "x": 1, "y": 1},
            ]
        },
        {
            "vertices": [
                {"name": "A", "x": 1e12, "y": 0},
                {"name": "B", "x": 1, "y": 0},
                {"name": "C", "x": 1, "y": 1},
            ]
        },
        {"vertices": [{"name": f"P{i}", "x": i, "y": i % 2} for i in range(1001)]},
        {"vertices": []},
        {
            "vertices": [
                v("A", 0, 0, arc={"radius": -5, "side": "left"}),
                v("B", 1, 0),
                v("C", 1, 1),
            ]
        },
    ],
)
def test_input_bounds_are_422(client, body):
    assert client.post("/v1/parcels/compute", json=body).status_code == 422


def test_merge_limits_are_422(client):
    one = {"vertices": [v("A", 0, 0), v("B", 1, 0), v("C", 1, 1)]}
    assert client.post("/v1/parcels/merge", json={"parcels": [one]}).status_code == 422
    assert client.post("/v1/parcels/merge", json={"parcels": [one] * 21}).status_code == 422
    assert (
        client.post(
            "/v1/parcels/merge", json={"parcels": [one, one], "snap_tolerance": 5}
        ).status_code
        == 422
    )


def test_tolerance_presets(client):
    r = client.get("/v1/parcels/tolerance-presets")
    assert r.status_code == 200
    assert [p["rule"]["u0"] for p in r.json()] == [0.5, 2.0, 2.5]


def test_routes_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in ("compute", "compare", "subdivide", "merge", "coverage", "tolerance-presets"):
        assert f"/v1/parcels/{p}" in paths


def test_coverage(client):
    sub = client.post(
        "/v1/parcels/subdivide",
        json={"parcel": RECT, "method": "parallel", "side": 0, "mode": "ratios", "parts": [1, 3]},
    ).json()
    parts = [{"vertices": p["geometry"]["vertices"]} for p in sub["parts"]]
    r = client.post("/v1/parcels/coverage", json={"outline": RECT, "parts": parts})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    r = client.post("/v1/parcels/coverage", json={"outline": RECT, "parts": parts[:1]})
    assert r.json()["ok"] is False


def test_compare_cadastre_rule(client):
    body = {
        "parcel": RECT,
        "cadastre_area": 5050.0,
        "tolerance": {
            "kind": "cadastre",
            "u0": 0.5,
            "cap_percent": 7,
            "source": "ΦΕΚ Β΄ 1510/2008",
        },
    }
    r = client.post("/v1/parcels/compare", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["perimeter"] == pytest.approx(300.0)
    t = 0.5 * 300 * (1 + 0.5 / 5050**0.5)
    assert out["rows"][0]["tolerance"] == pytest.approx(t)
    assert out["rows"][0]["within"] is True
