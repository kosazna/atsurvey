"""Surfaces: DXF and CSV files."""

import io

import ezdxf
import pytest

from atsurvey.core.surfaces.export import export_surface
from atsurvey.core.surfaces.models import (
    ContoursRequest,
    HeightsRequest,
    LevelVolumeRequest,
    NamedXY,
    PlanXY,
    ProfileRequest,
    SurfaceExportRequest,
    SurfacePoint,
    SurfaceSpec,
)

E0, N0 = 476_000.0, 4_205_000.0


def hill_spec():
    pts = []
    for i in range(21):
        for j in range(21):
            x, y = i * 5.0, j * 5.0
            pts.append(
                SurfacePoint(
                    name=f"P{i}_{j}",
                    x=E0 + x,
                    y=N0 + y,
                    z=100 - ((x - 50) ** 2 + (y - 50) ** 2) / 100,
                )
            )
    return SurfaceSpec(points=pts)


def read_dxf(data: bytes):
    return ezdxf.read(io.StringIO(data.decode("utf-8")))  # pyright: ignore[reportPrivateImportUsage]


def test_contours_dxf_layers_elevations_labels_and_tin():
    req = SurfaceExportRequest(
        format="dxf",
        content="contours",
        project_name="Λόφος",
        contours=ContoursRequest(surface=hill_spec(), interval=1.0, index_every=5),
        include_tin=True,
    )
    data, name, media = export_surface(req)
    assert name == "Lofos_isoypses.dxf" and media == "application/dxf"
    doc = read_dxf(data)
    msp = doc.modelspace()
    polys = msp.query("LWPOLYLINE")
    assert len(polys) > 0
    for p in polys:
        z = p.dxf.elevation
        assert p.dxf.layer == ("ISOYPSES_KYRIES" if round(z) % 5 == 0 else "ISOYPSES")
        assert z == round(z)
    faces = msp.query("3DFACE")
    assert len(faces) == 2 * 20 * 20
    labels = [t.dxf.text for t in msp.query("TEXT")]
    assert "95" in labels and "90" in labels
    assert len(msp.query("POINT")) == 21 * 21


def test_contours_csv():
    req = SurfaceExportRequest(
        format="csv",
        content="contours",
        contours=ContoursRequest(surface=hill_spec(), interval=10.0),
        csv_delimiter=";",
    )
    data, _name, media = export_surface(req)
    text = data.decode("utf-8-sig").splitlines()
    assert text[0] == "line;z;index;closed;vertex;x;y" and media.startswith("text/csv")


def test_heights_files_guard_formula_injection():
    q = [NamedXY(name="=cmd()", x=E0 + 50, y=N0 + 50), NamedXY(name="out", x=E0 - 10, y=N0)]
    req = SurfaceExportRequest(
        format="csv", content="heights", heights=HeightsRequest(surface=hill_spec(), points=q)
    )
    rows = export_surface(req)[0].decode("utf-8-sig").splitlines()
    assert rows[0] == "name,x,y,z,inside"
    assert rows[1].startswith("'=cmd(),476050.000,4205050.000,100.000,1")
    assert rows[2].endswith(",,0")
    dxf = read_dxf(export_surface(req.model_copy(update={"format": "dxf"}))[0])
    assert len(dxf.modelspace().query("POINT")) == 1  # the outside point has no height


def test_volume_csv_and_no_volume_dxf():
    req = SurfaceExportRequest(
        format="csv",
        content="volume",
        volume_level=LevelVolumeRequest(surface=hill_spec(), level=90.0),
        decimals=2,
    )
    rows = export_surface(req)[0].decode("utf-8-sig").splitlines()
    assert rows[0] == "quantity,value,unit" and rows[3].startswith("cut,")
    with pytest.raises(ValueError):
        export_surface(req.model_copy(update={"format": "dxf"}))


def test_profile_dxf_and_csv():
    req = SurfaceExportRequest(
        format="dxf",
        content="profile",
        profile=ProfileRequest(
            surface=hill_spec(),
            alignment=[PlanXY(x=E0 + 5, y=N0 + 50), PlanXY(x=E0 + 95, y=N0 + 50)],
            section_interval=30.0,
            half_width=10.0,
        ),
    )
    doc = read_dxf(export_surface(req)[0])
    msp = doc.modelspace()
    ground = msp.query('LWPOLYLINE[layer=="MHKOTOMH_EDAFOS"]')
    assert len(ground) == 1
    sections = msp.query('LWPOLYLINE[layer=="DIATOMES_EDAFOS"]')
    assert len(sections) == 4
    rows = (
        export_surface(req.model_copy(update={"format": "csv"}))[0].decode("utf-8-sig").splitlines()
    )
    assert rows[0].startswith("type,section_chainage")
    assert any(r.startswith("section,30.000,") for r in rows)


def test_missing_parameters_are_value_errors():
    for content in ("contours", "heights", "volume", "profile"):
        with pytest.raises(ValueError):
            export_surface(SurfaceExportRequest(format="csv", content=content))
