"""Batch coordinate conversion and point information (scale factor, convergence, zones).

Pipeline per point:  source grid/geographic → (φ, λ, h) in the source datum → datum shifts
(``datum.py``) → (φ, λ, h) in the target datum → target grid/geographic. Projection steps are
exact (nm level); only datum shifts are approximate, and the result says so.

Heights: ``height_in`` / ``height_out`` say whether ``z`` is ellipsoidal (h) or orthometric (H).
With a constant geoid undulation N, h = H + N, where N refers to the ellipsoid of the side
whose heights are ellipsoidal. Orthometric in and out passes H through unchanged; ellipsoidal
in and out follows the datum shift.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from ..models import Issue, Severity
from . import hatt as hatt_mod
from .datum import ELLIPSOIDS, DatumId, DatumShift, apply_path, datum_path
from .errors import CoordsError
from .hatt import (
    ATHENS_MERIDIAN_RAD,
    HATT_PRACTICAL_RADIUS_M,
    HattPolynomial,
    HattProjection,
    HattSheet,
)
from .models import (
    ConvertedPoint,
    ConvertRequest,
    ConvertResult,
    CoordPoint,
    HattSpec,
    HeightKind,
    PointInfoRequest,
    PointInfoResult,
    SystemId,
)
from .systems import SYSTEMS, Projection, SystemDef, outside_zone, tm3_zone, utm_zone

#: Step of the numerical Jacobian used for the Tissot indicatrix of non-conformal projections.
_JACOBIAN_STEP_RAD = 1e-6
#: Code of the pseudo-sheet built from user-entered polynomial coefficients
USER_SHEET = "χρήστη"
#: Names listed in an aggregated issue
_MAX_NAMES = 5


# ----------------------------------------------------------------------------- helpers


class _Issues:
    """Collects per-point problems and emits one issue per code (lists the first names)."""

    def __init__(self) -> None:
        self.items: list[Issue] = []
        self._points: dict[str, tuple[Severity, str, list[str], dict[str, Any]]] = {}
        self._counts: dict[str, int] = defaultdict(int)

    def add(self, severity: Severity, code: str, message: str, **params: Any) -> None:
        self.items.append(Issue(severity=severity, code=code, message=message, params=params))

    def point(self, severity: Severity, code: str, message: str, name: str, **params: Any) -> None:
        self._counts[code] += 1
        entry = self._points.setdefault(code, (severity, message, [], params))
        if len(entry[2]) < _MAX_NAMES:
            entry[2].append(name)

    def result(self) -> list[Issue]:
        out = list(self.items)
        for code, (sev, msg, names, params) in self._points.items():
            p = {**params, "count": self._counts[code], "points": names}
            out.append(Issue(severity=sev, code=code, message=msg, params=p))
        return out


def _hatt_projection(spec: HattSpec | None) -> tuple[HattProjection, HattSheet | None]:
    if spec is None:
        raise CoordsError(
            "COORD_HATT_ORIGIN_REQUIRED", "The Hatt system needs the sheet centre (φ₀, λ₀)"
        )
    if spec.sheet is not None:
        sheet = hatt_mod.HATT_SHEETS.get(spec.sheet)
        if sheet is None:
            raise CoordsError(
                "COORD_HATT_TABLE_MISSING",
                f"Hatt sheet {spec.sheet!r} is not in the sheet table (official table not loaded)",
                sheet=spec.sheet,
            )
        return sheet.projection, sheet
    assert spec.lat0 is not None and spec.lon0 is not None  # guaranteed by the model
    lon0 = spec.lon0 + (ATHENS_MERIDIAN_RAD if spec.meridian == "athens" else 0.0)
    if spec.coefficients is None:
        return HattProjection(spec.lat0, lon0), None
    c = spec.coefficients
    poly = HattPolynomial(*c)
    sheet = HattSheet(USER_SHEET, USER_SHEET, spec.lat0, lon0 - ATHENS_MERIDIAN_RAD, poly)
    return sheet.projection, sheet


def _projection(sd: SystemDef, spec: HattSpec | None) -> tuple[Projection | None, HattSheet | None]:
    if sd.id == "hatt":
        return _hatt_projection(spec)
    return sd.projection, None


def _to_geo(sd: SystemDef, proj: Projection | None, x: float, y: float) -> tuple[float, float]:
    if proj is None:
        if abs(y) > math.pi / 2 or abs(x) > 2 * math.pi:
            raise ValueError("φ/λ out of range (radians expected)")
        return y, x
    return proj.inverse(x, y)


def _from_geo(proj: Projection | None, lat: float, lon: float) -> tuple[float, float]:
    if proj is None:
        return math.remainder(lon, 2 * math.pi), lat
    return proj.forward(lat, lon)


def _height_for_shift(z: float | None, kind: HeightKind, n: float | None) -> float:
    if z is None:
        return 0.0
    return z if kind == "ellipsoidal" else z + (n or 0.0)


def _height_out(z: float | None, h_dst: float, req: ConvertRequest, shifted: bool) -> float | None:
    if z is None:
        return None
    n = req.geoid_undulation or 0.0
    if req.height_in == req.height_out:
        return h_dst if req.height_in == "ellipsoidal" and shifted else z
    if req.height_in == "ellipsoidal":  # h (source ellipsoid) → H
        return z - n
    return z + n  # H → h (target ellipsoid)


# ----------------------------------------------------------------------------- convert


def _official_polynomial(req: ConvertRequest, sheet: HattSheet | None) -> ConvertRequest | None:
    """Hatt sheet with official polynomials → rewrite the request as ΕΓΣΑ87 input."""
    dst_datum = SYSTEMS[req.dst].datum
    if req.datum_method != "official" or req.src != "hatt" or dst_datum == "greek":
        return None
    if sheet is None or sheet.polynomial is None:
        raise CoordsError(
            "COORD_HATT_TABLE_MISSING",
            "Official Hatt → ΕΓΣΑ87 polynomials are not loaded for this sheet",
            sheet=sheet.code if sheet else "—",
        )
    if "ellipsoidal" in (req.height_in, req.height_out):
        raise ValueError("The Hatt polynomials are 2D: use orthometric heights")
    poly = sheet.polynomial
    pts = [
        CoordPoint(name=p.name, x=e, y=n, z=p.z)
        for p in req.points
        for e, n in (poly.apply(p.x, p.y),)
    ]
    return req.model_copy(update={"src": "egsa87", "points": pts, "src_hatt": None})


def convert(req: ConvertRequest) -> ConvertResult:
    src, dst = SYSTEMS[req.src], SYSTEMS[req.dst]
    src_proj, src_sheet = _projection(src, req.src_hatt)
    dst_proj, _ = _projection(dst, req.dst_hatt)
    poly_req = _official_polynomial(req, src_sheet)
    if poly_req is not None:
        result = convert(poly_req)
        code = src_sheet.code if src_sheet else ""
        labels = [
            "Πολυώνυμο Hatt → ΕΓΣΑ87 (συντελεστές χρήστη)"
            if code == USER_SHEET
            else f"ΟΚΧΕ Hatt φύλλο {code}"
        ]
        return result.model_copy(
            update={"src": req.src, "datum_shift": labels + result.datum_shift}
        )

    path = datum_path(src.datum, dst.datum, req.datum_method)
    issues = _Issues()
    _check_heights(req, issues)
    accuracy = math.fsum(s.accuracy_m for s, _ in path) if path else None
    approximate = any(s.approximate for s, _ in path)
    if approximate:
        issues.add(
            "warning",
            "COORD_APPROXIMATE",
            f"Approximate datum shift (≈ {accuracy:g} m): not for cadastral work",
            accuracy_m=accuracy,
        )
    if any(s.src == "greek" for s, _ in path):
        issues.add(
            "warning",
            "COORD_OLD_DATUM_LOCAL_FIT",
            "Old Greek datum: for survey work fit a local Helmert/affine transformation on "
            "common points",
        )
    points = [
        _convert_point(p, req, src, dst, src_proj, dst_proj, path, issues) for p in req.points
    ]
    return ConvertResult(
        src=req.src,
        dst=req.dst,
        points=points,
        datum_shift=[s.label for s, _ in path],
        approximate=approximate,
        accuracy_m=accuracy,
        issues=issues.result(),
    )


def _check_heights(req: ConvertRequest, issues: _Issues) -> None:
    has_z = any(p.z is not None for p in req.points)
    if not has_z or req.height_in == req.height_out:
        return
    if req.geoid_undulation is None:
        raise CoordsError(
            "COORD_GEOID_REQUIRED",
            "Converting between ellipsoidal and orthometric heights needs the geoid undulation N",
        )
    issues.add(
        "info",
        "COORD_CONSTANT_GEOID",
        f"Heights converted with a constant N = {req.geoid_undulation:g} m (valid only locally)",
        n=req.geoid_undulation,
    )


def _convert_point(
    p: CoordPoint,
    req: ConvertRequest,
    src: SystemDef,
    dst: SystemDef,
    src_proj: Projection | None,
    dst_proj: Projection | None,
    path: list[tuple[DatumShift, bool]],
    issues: _Issues,
) -> ConvertedPoint:
    name = p.name or ""
    try:
        lat, lon_src = _to_geo(src, src_proj, p.x, p.y)
        h = _height_for_shift(p.z, req.height_in, req.geoid_undulation)
        lat, lon, h = apply_path(path, (lat, lon_src, h))
        x, y = _from_geo(dst_proj, lat, lon)
    except ValueError as exc:
        issues.point("error", "COORD_POINT_FAILED", str(exc), name, reason=str(exc))
        return ConvertedPoint(name=p.name, x=None, y=None, z=None)
    for sd, lon_check in ((src, lon_src), (dst, lon)):
        if outside_zone(sd, lon_check):
            issues.point(
                "warning", "COORD_OUTSIDE_ZONE", "Point outside the zone", name, system=sd.id
            )
    for sd, gx, gy in ((src, p.x, p.y), (dst, x, y)):
        if sd.id == "hatt" and math.hypot(gx, gy) > HATT_PRACTICAL_RADIUS_M:
            issues.point(
                "info",
                "COORD_HATT_FAR",
                "Point far from the Hatt sheet centre",
                name,
                radius_km=HATT_PRACTICAL_RADIUS_M / 1000,
            )
    z = _height_out(p.z, h, req, bool(path))
    return ConvertedPoint(name=p.name, x=x, y=y, z=z)


# --------------------------------------------------------------------------- point info


def tissot(proj: Projection, datum: DatumId, lat: float, lon: float) -> tuple[float, float, float]:
    """(a, b, γ) by central differences of ``proj.forward``: Tissot semi-axes and convergence.

    The Jacobian of (E, N) with respect to the local (east, north) ground distances,
    J = [[∂E/∂λ / (N cos φ), ∂E/∂φ / M], [∂N/∂λ / (N cos φ), ∂N/∂φ / M]], has the Tissot
    semi-axes a ≥ b as singular values (Snyder 1987, *Map Projections — A Working Manual*,
    USGS PP 1395, §4). They are computed with the closed-form 2×2 SVD, which stays accurate
    when a ≈ b (conformal projections). γ = −atan2(∂E/∂φ, ∂N/∂φ): bearing of grid north
    clockwise from true north.
    """
    ell = ELLIPSOIDS[datum]
    d = _JACOBIAN_STEP_RAD
    e1, n1 = proj.forward(lat + d, lon)
    e0, n0 = proj.forward(lat - d, lon)
    e3, n3 = proj.forward(lat, lon + d)
    e2, n2 = proj.forward(lat, lon - d)
    m = ell.meridian_radius(lat)
    nc = ell.prime_vertical_radius(lat) * math.cos(lat)
    p, q = (e3 - e2) / (2 * d * nc), (e1 - e0) / (2 * d * m)
    r, s = (n3 - n2) / (2 * d * nc), (n1 - n0) / (2 * d * m)
    big_q = math.hypot((p + s) / 2, (r - q) / 2)
    big_r = math.hypot((p - s) / 2, (r + q) / 2)
    return big_q + big_r, abs(big_q - big_r), -math.atan2(q, s)


def point_info(req: PointInfoRequest) -> PointInfoResult:
    sd = SYSTEMS[req.system]
    proj, _ = _projection(sd, req.hatt)
    p = req.point
    lat, lon = _to_geo(sd, proj, p.x, p.y)
    issues = _Issues()
    k = k_min = k_max = gamma = None
    if sd.projection is not None:
        k, gamma = sd.projection.scale_convergence(lat, lon)
        k_min = k_max = k
    elif proj is not None:
        k_max, k_min, gamma = tissot(proj, sd.datum, lat, lon)
    ef = cf = None
    if p.z is not None:
        h = _height_for_shift(p.z, req.height_kind, req.geoid_undulation)
        if req.height_kind == "orthometric" and req.geoid_undulation is None:
            issues.add(
                "info",
                "COORD_GEOID_ASSUMED_ZERO",
                "Geoid undulation not given: the height is used as ellipsoidal (N = 0)",
            )
        r = ELLIPSOIDS[sd.datum].gaussian_radius(lat)
        ef = r / (r + h)
        cf = k * ef if k is not None else None
    inside = not outside_zone(sd, lon)
    if sd.id == "hatt" and math.hypot(p.x, p.y) > HATT_PRACTICAL_RADIUS_M:
        inside = False
    return PointInfoResult(
        system=req.system,
        lat=lat,
        lon=lon,
        lon_athens=lon - ATHENS_MERIDIAN_RAD if sd.datum == "greek" else None,
        x=p.x if proj is not None else None,
        y=p.y if proj is not None else None,
        scale_factor=k,
        scale_min=k_min,
        scale_max=k_max,
        convergence=gamma,
        elevation_factor=ef,
        combined_factor=cf,
        utm_zone=utm_zone(lon),
        tm3_zone=tm3_zone(lon),
        inside_zone=inside,
        issues=issues.result(),
    )


__all__ = ["SystemId", "convert", "point_info", "tissot"]
