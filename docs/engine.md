# Computation engine

Code: [`engine/src/atsurvey`](../engine/src/atsurvey). Pure Python (pydantic + standard library);
export libraries are optional extras. Entry point:

```python
from atsurvey import ProjectInput, compute_project
result = compute_project(ProjectInput.model_validate(data))
```

## Conventions

| Quantity | Convention |
|---|---|
| Coordinates | `x` = Easting, `y` = Northing, `z` = orthometric height, metres, ΕΓΣΑ87 (EPSG:2100) |
| Angles | **radians** internally; converted only at the edges (parsers, API clients, exports) |
| `hz` | horizontal **circle reading** (direction), not an angle; the backsight need not be zero |
| `v` | zenith angle (0 = up). Readings with `v > π` are face II and reduced automatically |
| Azimuth | grid bearing, clockwise from grid north, in `[0, 2π)` (computed with `atan2`) |
| Misclosures | angular in **cc** (10⁻⁴ gon), linear and height in metres |

## Pipeline

```
control points ─┐
setups ── reduce faces/rounds ── observation index ──┬── traverses (dependency order) ──┐
                                                      └──────────────── detail points ───┴── result
```

1. **Setup reduction** (`core/reduce.py`). Per setup and target: face II → face I
   (`hz − π`, `2π − v`), circular mean of directions, mean zenith, and per-observation
   horizontal distance and height difference averaged. A spread between rounds above
   `round_spread_cc` raises `ROUND_SPREAD`.
2. **Observation index.** The angle at station S from B to F is the mean over every setup at S that
   observed both B and F: `β = dir(F) − dir(B)`. A leg A–B combines forward (setups at A) and
   backward (setups at B) measurements, the two groups weighted equally. Their difference is
   checked against `leg_distance_fb_m` / `leg_height_fb_m`.
3. **Traverses** (`core/traverse.py`), then **detail points** (`core/detail.py`).

## Reductions (`core/geodesy.py`)

For a slope distance `S` and zenith `z`:

| Step | Formula | Setting |
|---|---|---|
| Horizontal distance | `HD = S · sin z` | — |
| Height difference | `Δh = S · cos z + hi − ht + (1 − κ) · HD² / 2R` | `curvature_refraction`, `refraction_coefficient` (κ = 0.13), `earth_radius` (R = 6 371 000 m) |
| Reference surface | `D₀ = HD · R / (R + Hm + N)` | `elevation_reduction`, `elevation_mode`, `geoid_undulation` (N) |
| Grid distance | `D = D₀ · k` | `scale_mode`, `fixed_scale` |

**ΕΓΣΑ87 scale factor** (Transverse Mercator, k₀ = 0.9996, false easting 500 000 m):

```
k(E) = 0.9996 + 0.012311 · ((E − 500000) / 10⁶)²          point scale factor
k_line = (k(E₁) + 4 · k((E₁+E₂)/2) + k(E₂)) / 6            line scale factor (Simpson)
```

| `scale_mode` | Meaning |
|---|---|
| `leg_simpson` (default) | line factor per leg; eastings from a provisional pass |
| `leg_mean` | point factor at the leg mid-point |
| `traverse_mean` | one factor at the mean easting of the start and end stations (Excel/legacy style) |
| `none` | k = 1 (local grids) |
| `fixed` | `fixed_scale` |

`elevation_mode`: `leg` uses each leg's mean height (from the trigonometric heights of the
traverse); `traverse` uses one mean height (start and end station), as the legacy workbooks do.

## Traverses

Route convention, same as on the Greek computation sheet:

```
[A, B, P1, …, Pn, E, F]
 A = start orientation (known)   B = start station (known)
 E = end station                 F = end orientation (known, optional)
```

| Kind | Detected when | Checks |
|---|---|---|
| Link with closing azimuth | E and F known | angular, linear, height |
| Link on position | last point known, no closing azimuth | linear, height |
| Closed | the route returns to B (`[A, B, …, B, A]` or `[A, B, …, B]`) | as link |
| Open (hanging) | last point unknown | none (`TRAVERSE_OPEN` info) |

A route written from the unknown end is reversed automatically. Traverses run in dependency order,
so a traverse may start from points computed by another one, whatever the order they are listed in.

**Computation (compass/Bowditch rule):**

1. Azimuth chain `α(i→i+1) = α(i−1→i) + βᵢ + π`.
2. Angular misclosure `wβ = α_known(E→F) − α_computed(E→F)`; each of the n angles gets `wβ / n`.
3. Grid distances (two passes for per-leg scale factors), `ΔX = D sin α`, `ΔY = D cos α`.
4. Linear misclosures `wx`, `wy` distributed proportionally to leg length: `δXⱼ = wx · Dⱼ / ΣD`.
5. Heights from leg Δh, with misclosure `wz` distributed in proportion to length.

**Tolerances** (`Tolerances`, per project). The defaults are placeholders; set them to your
specification:

| Check | Limit | Default |
|---|---|---|
| Angular | `angular_base_cc + angular_per_sqrt_n_cc · √n` | 0 + 40 cc·√n |
| Linear | `linear_base_m + linear_per_sqrt_km_m · √L(km)` | 2 cm + 5 cm·√km |
| Relative precision | `L / w ≥ min_relative_precision` | 1:5000 |
| Height | `height_base_m + height_per_sqrt_km_m · √L(km)` | 2 cm + 5 cm·√km |

A traverse that passes through an already known point keeps the known coordinates and reports the
difference (`TRAVERSE_KNOWN_POINT_MID`). A point determined twice keeps the first value
(`POINT_CONFLICT`).

## Detail points

Each setup at a known station is oriented on **all** the known points it observes. The orientation
unknown is `ω = mean(α(S→K) − dir(K))`; a spread above `orientation_spread_cc` is reported. Unknown
targets are radiated. Known targets that have a distance become **check shots** with a residual.
The same point measured from several setups is averaged (`DETAIL_DUPLICATE` beyond
`detail_duplicate_m`). Stations that only become known by radiation are processed in a following
pass (`STATION_BY_RADIATION`). Points on enabled traverse routes are never computed as detail
points.

## Traverse suggestions (`core/suggest.py`)

Walks the observation graph from every known station that observes a known orientation point,
through occupied unknown stations, until it reaches a known point. Preference order: closing
azimuth, then position only, then open. Each new point is covered once.

## Issues

Every issue has a stable `code`, `severity` (`error` / `warning` / `info`), `params` and an English
`message`. Greek templates: [`core/messages.py`](../engine/src/atsurvey/core/messages.py) (the web
app has the same catalogue).

| Code | Severity | Meaning |
|---|---|---|
| `TRAVERSE_ROUTE_TOO_SHORT` | error | fewer than 3 points |
| `TRAVERSE_UNRESOLVED` | error | neither end has two known points |
| `TRAVERSE_MISSING_ANGLE` | error | no setup observes both neighbours |
| `TRAVERSE_MISSING_DISTANCE` | error | no distance on a leg |
| `TRAVERSE_ANGULAR_TOLERANCE` / `_LINEAR_` / `_RELATIVE_PRECISION` / `_HEIGHT_` | warning | limit exceeded |
| `TRAVERSE_KNOWN_POINT_MID`, `POINT_CONFLICT` | warning | double determination |
| `LEG_DISTANCE_FB`, `LEG_HEIGHT_FB` | warning | forward/backward disagreement |
| `ROUND_SPREAD`, `ORIENTATION_SPREAD` | warning | inconsistent rounds / orientations |
| `SETUP_STATION_UNKNOWN`, `SETUP_NO_ORIENTATION` | warning | setup cannot be used |
| `DETAIL_DUPLICATE`, `DETAIL_NO_DISTANCE`, `CHECK_SHOT_RESIDUAL` | warning | detail problems |
| `CONTROL_DUPLICATE` | warning | control point defined twice |
| `TRAVERSE_NO_HEIGHTS`, `TRAVERSE_OPEN`, `STATION_BY_RADIATION` | info | — |

## Result

`ProjectResult` holds `points` (control, traverse, detail, with source), `traverses` (summary,
per-station rows and per-leg rows: the full computation sheet), `detail` shots, setup
`orientations`, `issues`, a `summary` with extent, the `engine_version` and the `input_hash`
(SHA-256 of the input). The hash makes any saved run reproducible.

## Differences from the 2020 prototype

| 2020 behaviour | Now |
|---|---|
| Valid traverses were dropped by the project (indentation bug) | fixed, tested |
| Open traverse overwrote the last new point with the start station | fixed (`test_open_traverse_regression…`) |
| Closed traverse reported 0 angular misclosure and pushed the error to the last leg | real closure check and distribution |
| Azimuth crashed when Δx or Δy = 0 | `atan2` |
| Backsight had to read zero; one setup per station | directions; any number of setups and rounds |
| No curvature/refraction, intermediate rounding everywhere | full precision, rounding only for display |
| Projects stored with `pickle` | JSON models + Supabase |

## Tests

`uv run pytest engine/tests` runs synthetic surveys generated from true coordinates. The generator
inverts the reduction chain, so perfect data must reproduce the truth to 0.1 mm. That includes
randomised property tests (Hypothesis), the error-distribution checks, format round-trips and
exports. Excel validation: [validation.md](validation.md).
