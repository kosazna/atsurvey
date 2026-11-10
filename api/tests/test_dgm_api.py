import hashlib
import io

import ezdxf
import pytest
from fastapi.testclient import TestClient

from atsurvey.core.dgm.samples import KAEK_A, sample_parcels
from atsurvey_api import auth
from atsurvey_api.config import Settings, get_settings
from atsurvey_api.main import app
from atsurvey_api.routers import dgm as dgm_router


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: Settings(
        supabase_jwt_secret="test-secret-with-at-least-32-bytes-long!",  # secret-scan: allow
        supabase_url="http://supabase.invalid",
    )
    auth._plan_cache.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def pro(monkeypatch):
    async def fake_plan(caller, settings, workspace_id=None):
        return "pro"

    monkeypatch.setattr(auth, "plan_for", fake_plan)


def parcels():
    return [p.model_dump() for p in sample_parcels()]


SUBDIVISION = {
    "mode": "subdivision",
    "parcels": parcels()[:1],
    "partition_lines": [
        {
            "vertices": [
                {"name": "T1", "x": 476215.0, "y": 4205103.0},
                {"name": "T2", "x": 476215.5, "y": 4205137.0},
            ]
        }
    ],
    "topo_prop": parcels()[:1],
    "title": {"title": "Agros", "author": "Μηχανικός"},
}


def test_sample_and_build(client):
    r = client.get("/v1/dgm/sample")
    assert r.status_code == 200 and len(r.json()) == 3
    r = client.post("/v1/dgm/build", json=SUBDIVISION)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["kind"] == "deed"
    finals = [p for p in body["polygons"] if p["layer"] == "DGM_PROP_FINAL"]
    assert len(finals) == 2
    assert sum(p["area"] for p in finals) == pytest.approx(body["total_before"], abs=1e-6)


def test_build_validation_is_422(client):
    r = client.post("/v1/dgm/build", json={**SUBDIVISION, "parcels": parcels() * 20})
    assert r.status_code == 422
    r = client.post("/v1/dgm/build", json={**SUBDIVISION, "snap_tolerance": 5})
    assert r.status_code == 422


def test_export_is_pro_and_returns_a_valid_dxf(client, pro):
    r = client.post("/v1/dgm/export", json={"request": SUBDIVISION})
    assert r.status_code == 200
    assert r.headers["x-dxf-sha512"] == hashlib.sha512(r.content).hexdigest()
    assert r.headers["x-dgm-valid"] == "true"
    assert 'filename="dgm_Agros_v01.dxf"' in r.headers["content-disposition"]
    doc = ezdxf.read(io.StringIO(r.content.decode("cp1253")))  # pyright: ignore[reportPrivateImportUsage]
    assert doc.dxfversion == "AC1018"
    # round trip: the exported file passes the validator endpoint
    files = {"file": ("dgm_Agros_v01.dxf", r.content, "application/dxf")}
    v = client.post("/v1/dgm/validate", files=files, data={"kind": "deed"})
    assert v.status_code == 200 and v.json()["ok"] is True


def test_export_requires_pro(client):
    r = client.post("/v1/dgm/export", json={"request": SUBDIVISION})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "plan_required"
    r = client.post("/v1/dgm/hash-pdf", json={"sha512": "a" * 128})
    assert r.status_code == 402


def test_hash_pdf(client, pro):
    r = client.post("/v1/dgm/hash-pdf", json={"sha512": hashlib.sha512(b"x").hexdigest()})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    r = client.post("/v1/dgm/hash-pdf", json={"sha512": "z" * 128})
    assert r.status_code == 422


def test_validate_reports_problems(client):
    doc = ezdxf.new("R2004")  # pyright: ignore[reportPrivateImportUsage]
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (10, 0), (10, 10), (0, 10)], close=True, dxfattribs={"layer": "PST_KAEK"}
    )
    msp.add_mtext(KAEK_A, dxfattribs={"layer": "PST_KAEK", "insert": (5, 5)})
    buf = io.StringIO()
    doc.write(buf)
    files = {"file": ("my drawing.dxf", buf.getvalue().encode(), "application/dxf")}
    r = client.post("/v1/dgm/validate", files=files, data={"kind": "correction"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    codes = {i["code"] for c in body["checks"] for i in c["issues"]}
    assert {
        "DGM_FORBIDDEN_ENTITY",
        "DGM_KAEK_TEXT_MISSING",
        "DGM_LAYER_REQUIRED",
        "DGM_FILE_CHARS",
    } <= codes
    r = client.post("/v1/dgm/validate", files=files, data={"kind": "nonsense"})
    assert r.status_code == 422


def test_unreadable_upload_is_a_report_not_a_crash(client):
    files = {
        "file": (
            "dgm_x_v01.dxf",
            b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF garbage",
            "application/dxf",
        )
    }
    r = client.post("/v1/dgm/validate", files=files, data={"kind": "deed"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_upload_size_limit(client, monkeypatch):
    monkeypatch.setattr(dgm_router, "MAX_DXF_BYTES", 1024)
    files = {"file": ("dgm_x_v01.dxf", b"0\n" * 2000, "application/dxf")}
    r = client.post("/v1/dgm/validate", files=files, data={"kind": "deed"})
    assert r.status_code == 413
    r = client.post("/v1/dgm/kd", files=files)
    assert r.status_code == 413
    r = client.post("/v1/dgm/kd", files={"file": ("empty.dxf", b"", "application/dxf")})
    assert r.status_code == 422


def test_kd_upload(client):
    from pathlib import Path

    data = (
        Path(__file__).parents[2] / "engine/tests/fixtures/dgm/kd_three_parcels.dxf"
    ).read_bytes()
    r = client.post("/v1/dgm/kd", files={"file": ("kd.dxf", data, "application/dxf")})
    assert r.status_code == 200
    assert [p["kaek"] for p in r.json()["parcels"]] == [p.kaek for p in sample_parcels()]
