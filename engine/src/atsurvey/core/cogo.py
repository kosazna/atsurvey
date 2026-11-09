"""Coordinate-geometry (COGO) tools.

Conventions (same as the rest of the engine): x = Easting, y = Northing, angles in radians,
azimuths are grid bearings clockwise from north, horizontal circle readings increase
clockwise, offsets are positive to the right of the reference line. Every function is pure
and raises ``ValueError`` with a clear message for degenerate geometry.
"""

from __future__ import annotations

import itertools
import math

from .cogo_models import (
    XY,
    AreaRequest,
    AreaResult,
    CommonPoint,
    IntersectionAnglesRequest,
    IntersectionDistancesRequest,
    IntersectionLinesRequest,
    IntersectionResult,
    InverseRequest,
    InverseResult,
    OffsetRequest,
    OffsetResult,
    OffsetRow,
    PolarRequest,
    PolarResult,
    ResectionObservation,
    ResectionRequest,
    ResectionResidual,
    ResectionResult,
    TransformRequest,
    TransformResidual,
    TransformResult,
)
from .geodesy import egsa87_point_scale, elevation_factor, grid_azimuth, scale_for_line
from .units import CC_TO_RAD, wrap_2pi, wrap_pi

EPS = 1e-12
#: A priori standard deviations used to weight resection observations
RESECTION_SIGMA_DIRECTION = 10 * CC_TO_RAD
RESECTION_SIGMA_DISTANCE = 0.003
DANGER_CIRCLE_RATIO = 0.02


def _cross(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * by - ay * bx


def _az(a: XY, b: XY) -> float:
    if math.hypot(b.x - a.x, b.y - a.y) < EPS:
        raise ValueError(f"Points {a.name or 'A'} and {b.name or 'B'} coincide")
    return grid_azimuth(a.x, a.y, b.x, b.y)


# ----------------------------------------------------------------------------- inverse


def inverse(req: InverseRequest) -> InverseResult:
    a, b = req.a, req.b
    dx, dy = b.x - a.x, b.y - a.y
    d = math.hypot(dx, dy)
    if d < EPS:
        raise ValueError("The two points coincide")
    az = grid_azimuth(a.x, a.y, b.x, b.y)
    dz = b.z - a.z if a.z is not None and b.z is not None else None
    ground = None
    if req.reduction is not None:
        rs = req.reduction
        zs = [z for z in (a.z, b.z) if z is not None]
        hm = sum(zs) / len(zs) if zs else rs.default_elevation
        k = scale_for_line(rs, a.x, b.x, egsa87_point_scale((a.x + b.x) / 2))
        ground = d / (k * elevation_factor(rs, hm))
    return InverseResult(
        dx=dx,
        dy=dy,
        dz=dz,
        distance=d,
        azimuth=az,
        azimuth_back=wrap_2pi(az + math.pi),
        distance_ground=ground,
        slope_distance=math.hypot(d, dz) if dz is not None else None,
        gradient_percent=dz / d * 100.0 if dz is not None else None,
    )


# ------------------------------------------------------------------------------- polar


def polar(req: PolarRequest) -> PolarResult:
    st = req.station
    if req.azimuth is not None:
        az = wrap_2pi(req.azimuth)
    elif req.backsight is not None and req.angle is not None:
        az = wrap_2pi(_az(st, req.backsight) + req.angle)
    else:
        raise ValueError("Give either an azimuth, or a backsight point and an angle")
    z = st.z + req.dz if st.z is not None and req.dz is not None else None
    p = XY(
        x=st.x + req.distance * math.sin(az),
        y=st.y + req.distance * math.cos(az),
        z=z,
        name=req.name,
    )
    return PolarResult(point=p, azimuth=az)


# ------------------------------------------------------------------------ intersections


def intersection_angles(req: IntersectionAnglesRequest) -> IntersectionResult:
    a, b = req.a, req.b
    az_ab = _az(a, b)
    az_ap = wrap_2pi(az_ab + req.angle_a)
    az_bp = wrap_2pi(az_ab + math.pi + req.angle_b)
    dax, day = math.sin(az_ap), math.cos(az_ap)
    dbx, dby = math.sin(az_bp), math.cos(az_bp)
    det = _cross(dax, day, dbx, dby)
    if abs(det) < 1e-9:
        return IntersectionResult(solutions=[], message="The two rays are parallel")
    bax, bay = b.x - a.x, b.y - a.y
    t = _cross(bax, bay, dbx, dby) / det
    s = _cross(bax, bay, dax, day) / det
    if t <= 0 or s <= 0:
        return IntersectionResult(
            solutions=[],
            message="The rays do not meet in front of both stations; check the angle sides",
        )
    p = XY(x=a.x + t * dax, y=a.y + t * day, name=req.name)
    gamma = abs(wrap_pi(az_ap - az_bp))
    msg = None
    if gamma < math.radians(15) or gamma > math.radians(165):
        msg = "Weak geometry: the rays cross at a very acute angle"
    return IntersectionResult(solutions=[p], message=msg)


def intersection_distances(req: IntersectionDistancesRequest) -> IntersectionResult:
    a, b = req.a, req.b
    dx, dy = b.x - a.x, b.y - a.y
    d = math.hypot(dx, dy)
    if d < EPS:
        return IntersectionResult(solutions=[], message="The centres coincide")
    ra, rb = req.r_a, req.r_b
    if d > ra + rb + 1e-9:
        return IntersectionResult(solutions=[], message="The circles are too far apart to meet")
    if d < abs(ra - rb) - 1e-9:
        return IntersectionResult(solutions=[], message="One circle lies inside the other")
    ux, uy = dx / d, dy / d
    along = (ra * ra - rb * rb + d * d) / (2 * d)
    h = math.sqrt(max(0.0, ra * ra - along * along))
    px, py = a.x + along * ux, a.y + along * uy
    rx, ry = uy, -ux  # unit normal to the right of A→B
    if h < 1e-9:
        return IntersectionResult(
            solutions=[XY(x=px, y=py)], message="The circles touch at a single point"
        )
    return IntersectionResult(
        solutions=[XY(x=px + h * rx, y=py + h * ry), XY(x=px - h * rx, y=py - h * ry)]
    )


def intersection_lines(req: IntersectionLinesRequest) -> IntersectionResult:
    p1, p2, p3, p4 = req.p1, req.p2, req.p3, req.p4
    d1x, d1y = p2.x - p1.x, p2.y - p1.y
    d2x, d2y = p4.x - p3.x, p4.y - p3.y
    l1, l2 = math.hypot(d1x, d1y), math.hypot(d2x, d2y)
    if l1 < EPS or l2 < EPS:
        raise ValueError("Each line needs two distinct points")
    det = _cross(d1x, d1y, d2x, d2y)
    if abs(det) < 1e-12 * l1 * l2:
        return IntersectionResult(solutions=[], message="The lines are parallel")
    t = _cross(p3.x - p1.x, p3.y - p1.y, d2x, d2y) / det
    return IntersectionResult(solutions=[XY(x=p1.x + t * d1x, y=p1.y + t * d1y)])


# ---------------------------------------------------------------------------- resection


def _solve(n: list[list[float]], u: list[float]) -> tuple[list[float], list[list[float]]]:
    """Gauss-Jordan solve of a small symmetric system; returns (x, inverse)."""
    size = len(u)
    m = [row[:] + [1.0 if i == j else 0.0 for j in range(size)] + [u[i]] for i, row in enumerate(n)]
    for col in range(size):
        piv = max(range(col, size), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-300:
            raise ValueError("The geometry is singular (station on the danger circle?)")
        m[col], m[piv] = m[piv], m[col]
        f = m[col][col]
        m[col] = [v / f for v in m[col]]
        for r in range(size):
            if r != col and m[r][col] != 0.0:
                g = m[r][col]
                m[r] = [vr - g * vc for vr, vc in zip(m[r], m[col], strict=True)]
    x = [m[i][-1] for i in range(size)]
    inv = [m[i][size : 2 * size] for i in range(size)]
    return x, inv


def _three_point(obs: list[ResectionObservation]) -> tuple[float, float] | None:
    """Closed-form three-point resection (ToTal algorithm, Pierlot & Van Droogenbroeck 2014).
    Circle readings are clockwise, so they are negated into counter-clockwise angles."""
    (p1, r1), (p2, r2), (p3, r3) = ((o.point, -o.direction) for o in obs[:3])
    x1, y1 = p1.x - p2.x, p1.y - p2.y
    x3, y3 = p3.x - p2.x, p3.y - p2.y
    s12, s23 = math.sin(r2 - r1), math.sin(r3 - r2)
    if abs(s12) < 1e-12 or abs(s23) < 1e-12:
        return None
    t12 = math.cos(r2 - r1) / s12
    t23 = math.cos(r3 - r2) / s23
    if abs(t12 + t23) < 1e-12:
        return None
    t31 = (1 - t12 * t23) / (t12 + t23)
    x12, y12 = x1 + t12 * y1, y1 - t12 * x1
    x23, y23 = x3 - t23 * y3, y3 + t23 * x3
    x31, y31 = (x3 + x1) + t31 * (y3 - y1), (y3 + y1) - t31 * (x3 - x1)
    k31 = x1 * x3 + y1 * y3 + t31 * (x1 * y3 - x3 * y1)
    det = (x12 - x23) * (y23 - y31) - (y12 - y23) * (x23 - x31)
    if abs(det) < 1e-9:
        return None
    return p2.x + k31 * (y12 - y23) / det, p2.y + k31 * (x23 - x12) / det


def _circumcircle(a: XY, b: XY, c: XY) -> tuple[float, float, float] | None:
    ox, oy = a.x, a.y
    bx, by, cx, cy = b.x - ox, b.y - oy, c.x - ox, c.y - oy
    d = 2 * (bx * cy - by * cx)
    if abs(d) < 1e-9:
        return None  # collinear
    ux = (cy * (bx * bx + by * by) - by * (cx * cx + cy * cy)) / d
    uy = (bx * (cx * cx + cy * cy) - cx * (bx * bx + by * by)) / d
    return ox + ux, oy + uy, math.hypot(ux, uy)


def _near_danger_circle(x: float, y: float, pts: list[XY]) -> bool:
    """True when the station is close to the circle through every triple of known points
    (with three points: the one circle). Directions alone are then indeterminate."""
    triples = list(itertools.combinations(pts, 3))[:20]
    if not triples:
        return False
    for a, b, c in triples:
        circ = _circumcircle(a, b, c)
        if circ is None:
            return False
        cx, cy, r = circ
        if abs(math.hypot(x - cx, y - cy) - r) > DANGER_CIRCLE_RATIO * r:
            return False
    return True


def resection(req: ResectionRequest) -> ResectionResult:
    obs = req.observations
    pts = [o.point for o in obs]
    for a, b in itertools.combinations(pts, 2):
        if math.hypot(a.x - b.x, a.y - b.y) < 1e-6:
            raise ValueError(f"Known points {a.name or ''} and {b.name or ''} coincide".strip())
    dists = [o for o in obs if o.distance is not None]
    n_dir = len(obs)
    n_obs = n_dir + len(dists)
    if n_obs < 3 or (n_dir < 3 and len(dists) < 2):
        raise ValueError("Resection needs 3 directions, or 2 directions with 2 distances")

    # approximate station
    start: tuple[float, float] | None = None
    method = "least squares"
    if len(dists) >= 2:
        o1, o2 = dists[0], dists[1]
        circ = intersection_distances(
            IntersectionDistancesRequest(
                a=o1.point, r_a=o1.distance or 0, b=o2.point, r_b=o2.distance or 0
            )
        )
        if not circ.solutions:
            raise ValueError(f"The distances do not intersect: {circ.message}")
        observed = wrap_2pi(o2.direction - o1.direction)
        best = None
        for s in circ.solutions:
            ang = wrap_2pi(
                grid_azimuth(s.x, s.y, o2.point.x, o2.point.y)
                - grid_azimuth(s.x, s.y, o1.point.x, o1.point.y)
            )
            err = abs(wrap_pi(ang - observed))
            if best is None or err < best[0]:
                best = (err, s)
        assert best is not None
        start = (best[1].x, best[1].y)
    else:
        for triple in itertools.combinations(obs, 3):
            start = _three_point(list(triple))
            if start is not None:
                break
        if start is None:
            raise ValueError(
                "The station lies on the danger circle through the known points; "
                "the resection is indeterminate"
            )
        if n_obs == 3:
            method = "three-point closed form"

    danger = len(dists) == 0 and _near_danger_circle(start[0], start[1], pts)

    # Gauss-Newton least squares on (X, Y, ω)
    x, y = start
    omega = 0.0
    weights = [1 / RESECTION_SIGMA_DIRECTION**2] * n_dir + [1 / RESECTION_SIGMA_DISTANCE**2] * len(
        dists
    )
    inv: list[list[float]] = [[0.0] * 3 for _ in range(3)]
    for _ in range(30):
        omega = _mean_orientation(x, y, obs)
        rows: list[list[float]] = []
        misc: list[float] = []
        for o in obs:
            dx, dy = o.point.x - x, o.point.y - y
            d2 = dx * dx + dy * dy
            if d2 < 1e-12:
                raise ValueError("The station coincides with a known point")
            az = math.atan2(dx, dy)
            # azimuth = direction + ω  →  direction = az − ω
            rows.append([-dy / d2, dx / d2, -1.0])
            misc.append(wrap_pi(o.direction - (az - omega)))
        for o in dists:
            dx, dy = o.point.x - x, o.point.y - y
            d = math.hypot(dx, dy)
            rows.append([-dx / d, -dy / d, 0.0])
            misc.append((o.distance or 0.0) - d)
        n = [
            [sum(w * r[i] * r[j] for r, w in zip(rows, weights, strict=True)) for j in range(3)]
            for i in range(3)
        ]
        u = [
            sum(w * r[i] * m for r, w, m in zip(rows, weights, misc, strict=True)) for i in range(3)
        ]
        dxyz, inv = _solve(n, u)
        x += dxyz[0]
        y += dxyz[1]
        omega += dxyz[2]
        if math.hypot(dxyz[0], dxyz[1]) < 1e-9:
            break

    omega = _mean_orientation(x, y, obs)
    residuals: list[ResectionResidual] = []
    vpv = 0.0
    for o in obs:
        az = grid_azimuth(x, y, o.point.x, o.point.y)
        v_dir = wrap_pi((az - omega) - o.direction)
        v_dist = None
        vpv += v_dir**2 / RESECTION_SIGMA_DIRECTION**2
        if o.distance is not None:
            v_dist = math.hypot(o.point.x - x, o.point.y - y) - o.distance
            vpv += v_dist**2 / RESECTION_SIGMA_DISTANCE**2
        residuals.append(
            ResectionResidual(name=o.point.name, direction_residual=v_dir, distance_residual=v_dist)
        )
    dof = n_obs - 3
    sigma0 = sx = sy = None
    if dof > 0:
        sigma0 = math.sqrt(vpv / dof)
        sx = sigma0 * math.sqrt(max(inv[0][0], 0.0))
        sy = sigma0 * math.sqrt(max(inv[1][1], 0.0))
    return ResectionResult(
        station=XY(x=x, y=y, name=req.station_name),
        orientation=wrap_2pi(omega),
        sigma0=sigma0,
        sx=sx,
        sy=sy,
        residuals=residuals,
        danger_circle=danger,
        method=method,
    )


def _mean_orientation(x: float, y: float, obs: list[ResectionObservation]) -> float:
    vals = [grid_azimuth(x, y, o.point.x, o.point.y) - o.direction for o in obs]
    ref = vals[0]
    return wrap_2pi(ref + sum(wrap_pi(v - ref) for v in vals) / len(vals))


# --------------------------------------------------------------------------------- area


def area(req: AreaRequest) -> AreaResult:
    pts = list(req.points)
    if len(pts) > 3 and math.hypot(pts[0].x - pts[-1].x, pts[0].y - pts[-1].y) < 1e-9:
        pts = pts[:-1]  # closing vertex repeated
    if len(pts) < 3:
        raise ValueError("A polygon needs at least 3 distinct vertices")
    ox, oy = pts[0].x, pts[0].y  # local origin keeps the products small
    xs = [p.x - ox for p in pts]
    ys = [p.y - oy for p in pts]
    n = len(pts)
    terms = [xs[i] * ys[(i + 1) % n] - xs[(i + 1) % n] * ys[i] for i in range(n)]
    a2 = math.fsum(terms)
    if abs(a2) < 1e-9:
        raise ValueError("The polygon has zero area (collinear or self-cancelling vertices)")
    cx = math.fsum((xs[i] + xs[(i + 1) % n]) * terms[i] for i in range(n)) / (3 * a2)
    cy = math.fsum((ys[i] + ys[(i + 1) % n]) * terms[i] for i in range(n)) / (3 * a2)
    perimeter = math.fsum(
        math.hypot(pts[(i + 1) % n].x - pts[i].x, pts[(i + 1) % n].y - pts[i].y) for i in range(n)
    )
    a = abs(a2) / 2
    k_mean = area_ell = None
    if req.reduction is not None:
        ks = [scale_for_line(req.reduction, p.x, p.x, egsa87_point_scale(p.x)) for p in pts]
        k_mean = sum(ks) / len(ks)
        area_ell = a / (k_mean * k_mean)
    return AreaResult(
        area=a,
        perimeter=perimeter,
        orientation="counterclockwise" if a2 > 0 else "clockwise",
        centroid=XY(x=ox + cx, y=oy + cy),
        scale_factor_mean=k_mean,
        area_ellipsoid=area_ell,
    )


# ------------------------------------------------------------------------ transformation


def transform(req: TransformRequest) -> TransformResult:
    used = [c for c in req.common if c.use]
    if req.method == "helmert":
        if len(used) < 2:
            raise ValueError("A Helmert transformation needs at least 2 common points")
        params, fn = _helmert(used)
        u = 4
    else:
        if len(used) < 3:
            raise ValueError("An affine transformation needs at least 3 common points")
        params, fn = _affine(used)
        u = 6
    residuals: list[TransformResidual] = []
    vv = 0.0
    for c in req.common:
        tx, ty = fn(c.src.x, c.src.y)
        vx, vy = c.dst.x - tx, c.dst.y - ty
        if c.use:
            vv += vx * vx + vy * vy
        residuals.append(
            TransformResidual(name=c.name, vx=vx, vy=vy, v=math.hypot(vx, vy), used=c.use)
        )
    dof = 2 * len(used) - u
    rms = math.sqrt(vv / dof) if dof > 0 else None
    out = []
    for p in req.points:
        x, y = fn(p.x, p.y)
        out.append(XY(x=x, y=y, z=p.z, name=p.name))
    return TransformResult(
        method=req.method, params=params, rms=rms, residuals=residuals, points=out
    )


def _centred(used: list[CommonPoint]):
    n = len(used)
    sx = math.fsum(c.src.x for c in used) / n
    sy = math.fsum(c.src.y for c in used) / n
    dx = math.fsum(c.dst.x for c in used) / n
    dy = math.fsum(c.dst.y for c in used) / n
    src = [(c.src.x - sx, c.src.y - sy) for c in used]
    dst = [(c.dst.x - dx, c.dst.y - dy) for c in used]
    return sx, sy, dx, dy, src, dst


def _helmert(used: list[CommonPoint]):
    sx, sy, dx, dy, src, dst = _centred(used)
    q = math.fsum(x * x + y * y for x, y in src)
    if q < 1e-12:
        raise ValueError("The common points coincide")
    a = math.fsum(x * X + y * Y for (x, y), (X, Y) in zip(src, dst, strict=True)) / q
    b = math.fsum(x * Y - y * X for (x, y), (X, Y) in zip(src, dst, strict=True)) / q
    tx = dx - a * sx + b * sy
    ty = dy - b * sx - a * sy
    params = {
        "tx": tx,
        "ty": ty,
        "scale": math.hypot(a, b),
        "rotation": math.atan2(b, a),
        "a": a,
        "b": b,
    }
    return params, lambda x, y: (tx + a * x - b * y, ty + b * x + a * y)


def _affine(used: list[CommonPoint]):
    sx, sy, dx, dy, src, dst = _centred(used)
    sxx = math.fsum(x * x for x, _ in src)
    syy = math.fsum(y * y for _, y in src)
    sxy = math.fsum(x * y for x, y in src)
    det = sxx * syy - sxy * sxy
    if abs(det) < 1e-9 * max(sxx * syy, 1.0):
        raise ValueError("The common points are collinear; an affine transformation is undefined")
    sxX = math.fsum(x * X for (x, _), (X, _) in zip(src, dst, strict=True))
    syX = math.fsum(y * X for (_, y), (X, _) in zip(src, dst, strict=True))
    sxY = math.fsum(x * Y for (x, _), (_, Y) in zip(src, dst, strict=True))
    syY = math.fsum(y * Y for (_, y), (_, Y) in zip(src, dst, strict=True))
    a1 = (sxX * syy - syX * sxy) / det
    a2 = (syX * sxx - sxX * sxy) / det
    b1 = (sxY * syy - syY * sxy) / det
    b2 = (syY * sxx - sxY * sxy) / det
    a0 = dx - a1 * sx - a2 * sy
    b0 = dy - b1 * sx - b2 * sy
    params = {"a0": a0, "a1": a1, "a2": a2, "b0": b0, "b1": b1, "b2": b2}
    return params, lambda x, y: (a0 + a1 * x + a2 * y, b0 + b1 * x + b2 * y)


# ------------------------------------------------------------------------------- offset


def offset(req: OffsetRequest) -> OffsetResult:
    a, b = req.a, req.b
    dx, dy = b.x - a.x, b.y - a.y
    length = math.hypot(dx, dy)
    if length < EPS:
        raise ValueError("The line points coincide")
    ux, uy = dx / length, dy / length
    rx, ry = uy, -ux
    rows = []
    for p in req.points:
        wx, wy = p.x - a.x, p.y - a.y
        ch = wx * ux + wy * uy
        rows.append(
            OffsetRow(
                name=p.name,
                chainage=ch,
                offset=wx * rx + wy * ry,
                foot=XY(x=a.x + ch * ux, y=a.y + ch * uy),
            )
        )
    return OffsetResult(line_length=length, azimuth=grid_azimuth(a.x, a.y, b.x, b.y), rows=rows)
