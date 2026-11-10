# COGO tools and geometric levelling

Code: [`engine/src/atsurvey/core/cogo.py`](../engine/src/atsurvey/core/cogo.py),
[`core/leveling.py`](../engine/src/atsurvey/core/leveling.py). Contract:
[`core/cogo_models.py`](../engine/src/atsurvey/core/cogo_models.py). API router:
[`api/src/atsurvey_api/routers/cogo.py`](../api/src/atsurvey_api/routers/cogo.py).

Every tool is a stateless `POST`, open to the same callers as `/v1/compute` (including the
anonymous demo). Degenerate geometry returns **422** with a `detail` message that explains why.

## Conventions

| Quantity | Convention |
|---|---|
| Coordinates | `x` = Easting, `y` = Northing, metres (ΕΓΣΑ87 grid) |
| Angles | radians; the UI converts from the project unit (gon / deg / DMS) |
| Azimuth | grid bearing, clockwise from grid north, `[0, 2π)` |
| Measured angles | **clockwise** (as a total station turns) |
| Offsets | **positive to the right** of the reference line A→B |
| Distances | **grid** distances unless stated; `distance_ground` reverses the reductions |
| Areas | **grid (projection) area**, as registered by the Hellenic Cadastre; `area_ellipsoid = area / k²` |

## Tools

### Inverse (`/v1/cogo/inverse`), αντίστροφο πρόβλημα

`d = √(ΔX² + ΔY²)` and `α = atan2(ΔX, ΔY)`, plus the back azimuth `α + π`. With heights, it also
returns `ΔZ`, the slope distance and the gradient (%). With `reduction` settings it returns the
ground distance `d / (k · R/(R+Hm))`, using the project's scale-factor mode (`Hm` is the mean
height, or the default height if no heights are given).

### Polar (`/v1/cogo/polar`), ακτινωτή αποτύπωση

`P = S + d · (sin α, cos α)`. The azimuth is either given directly, or derived from a backsight
point and a clockwise angle: `α = α(S→B) + β`. With `dz`, `Z_P = Z_S + dz`.

### Forward intersection by angles (`/v1/cogo/intersection/angles`), εμπροσθοτομία

`angle_a` is turned at A **clockwise from B to P**, and `angle_b` at B **clockwise from A to P**.
For a point on the other side of the base, use `2π − angle`. The rays
`α_AP = α_AB + angle_a` and `α_BP = α_BA + angle_b` are intersected. The tool returns no solution
(with a message) when the rays are parallel or do not meet in front of both stations. A crossing
angle under 15° or over 165° adds a weak-geometry warning.

### Intersection of two circles (`/v1/cogo/intersection/distances`), τομή κύκλων

With `a = (r_A² − r_B² + d²) / 2d` and `h = √(r_A² − a²)`, the solutions are the foot point
`A + a·u` shifted `±h` along the normal. The tool returns 0, 1 (tangent) or 2 points; with two,
**the first lies to the right of A→B**.

### Intersection of two lines (`/v1/cogo/intersection/lines`)

The lines through P1P2 and P3P4 are infinite. Parallel lines return no solution.

### Resection (`/v1/cogo/resection`), οπισθοτομία

Input: circle readings to known points, optionally with distances. It needs **3 directions**, or
**2 directions with 2 distances**.

* **Approximate station.** From the first two distances by circle intersection, choosing the
  solution consistent with the observed angle. Otherwise from three directions in closed form
  (the *ToTal* three-point algorithm, Pierlot & Van Droogenbroeck 2014).
* **Adjustment.** Gauss–Newton least squares on `(X, Y, ω)` with a priori σ of 10 cc per direction
  and 3 mm per distance. The tool returns the orientation `ω` (azimuth = reading + ω), the
  residuals, and with redundancy `σ₀`, `sx` and `sy`.
* **Danger circle (επικίνδυνος κύκλος).** A station on the circle through the known points makes
  directions alone indeterminate.
  * Exactly on the circle: the request is rejected.
  * Within 2 % of the radius (of every triple of known points), using directions only:
    `danger_circle = true`. Treat the result with suspicion and add a point or a distance.

### Area (`/v1/cogo/area`), εμβαδόν

Shoelace formula on vertices taken relative to the first vertex, so full precision is kept at
ΕΓΣΑ87 magnitudes. Sums use `math.fsum`. A repeated closing vertex is ignored. The tool returns the
area, perimeter, orientation (clockwise / counterclockwise) and centroid. With `reduction`, it also
returns the mean scale factor over the vertices and `area_ellipsoid = area / k²`.

### 2D transformation (`/v1/cogo/transform`), μετασχηματισμός

Least squares from the common points flagged `use`, computed on centroid-reduced coordinates.

| Method | Model | Min. points | Parameters |
|---|---|---|---|
| `helmert` (similarity, 4 parameters) | `X = tx + a·x − b·y`, `Y = ty + b·x + a·y` | 2 | `tx, ty, scale = √(a²+b²), rotation = atan2(b, a), a, b` |
| `affine` (6 parameters) | `X = a0 + a1·x + a2·y`, `Y = b0 + b1·x + b2·y` | 3, not collinear | `a0, a1, a2, b0, b1, b2` |

Residuals `v = dst − T(src)` are returned for **every** common point, so you can check unused
points against the fit. `rms = √(Σv² / (2n − u))` is returned when there is redundancy. Heights are
passed through unchanged.

### Chainage and offset (`/v1/cogo/offset`), χιλιομέτρηση και απόσταση από ευθεία

For the line A→B: `chainage = (P−A)·u` (negative before A) and `offset = (P−A)·n`, where `n` is
the right-hand normal (positive to the right). Also returns the foot of the perpendicular.

## Example

```http
POST /v1/cogo/intersection/angles
{ "a": {"x": 0, "y": 0}, "b": {"x": 100, "y": 0},
  "angle_a": 5.497787,      // 350 gon, clockwise from B
  "angle_b": 0.785398 }     //  50 gon, clockwise from A
→ { "solutions": [ { "x": 50.0, "y": 50.0 } ], "message": null }
```

## Geometric levelling (`/v1/leveling`), γεωμετρική χωροστάθμηση

**Input.** Benchmarks (`name`, `h`) and a chain of setups. Each setup has exactly one backsight
(`bs`) and one foresight (`fs`) staff reading, plus any intermediate sights (`is`). Each reading
can carry a sight distance. The foresight point of setup *i* must be the backsight point of setup
*i + 1*, and the line must start on a benchmark.

**Procedure:**

1. **Height of collimation.** For each setup, `HI = H(bs) + bs`, `H(fs) = HI − fs`,
   `H(is) = HI − is`, and `Δh = bs − fs`.
2. **Misclosure.** If the last foresight point is a benchmark (or the start, for a loop),
   `w = H_known − H_computed`. Otherwise the line is open and is not checked.
3. **Distribution.**
   * `distance` (default): in proportion to the cumulative sight length. If any distance is
     missing, it falls back to equal shares per setup and says so in `message`.
   * `setups`: equal shares per setup.
4. **Intermediate sights.** They get the correction of their setup's instrument height,
   interpolated between the backsight and foresight of that setup (the backsight's share of the
   setup's sight length, or half when distances are missing).
5. **Tolerance.** `tolerance = (base + c·√L_km) mm`, default 12 mm·√km. It needs sight distances;
   without them the tolerance is not evaluated.

**Output:**
* Per point: height, unadjusted height, correction and kind (benchmark / turning / intermediate).
* Per setup: `Δh` and sight length.
* For the line: misclosure, tolerance, pass/fail, length and number of setups.

## Tests

* [`engine/tests/test_cogo.py`](../engine/tests/test_cogo.py): textbook cases, random
  round-trips (inverse ∘ polar), recovery of known transformation parameters, resection with 3, 4
  and 5 points and with distances (station within 0.1 mm), noisy redundant statistics, the danger
  circle, and degenerate cases.
* [`engine/tests/test_leveling.py`](../engine/tests/test_leveling.py): closed, open and loop lines,
  correction distribution, intermediate sights, tolerance and validation.
* [`api/tests/test_cogo_api.py`](../api/tests/test_cogo_api.py): every route, happy path and 422.


## Stakeout (χάραξη) — `POST /v1/cogo/stakeout`

Setting-out data for design points from a station oriented on a backsight point (or on a
given zero azimuth). For each point: grid azimuth, horizontal **angle clockwise from the
backsight**, grid distance, and — with `reduction` — the **ground horizontal distance** the
instrument will display (grid ÷ k ÷ R/(R+H)). With heights: Δz, zenith angle and slope
distance for the given instrument and target heights. Setting out the returned angle and
distance with the polar tool reproduces each design point exactly (tested).


## Double-run levelling (μετάβαση – επιστροφή) — `POST /v1/leveling` with `return_setups`

Give the forward run in `setups` and the return run (from the forward end back to the start) in
`return_setups`. Sections are delimited by `section_points` (default: benchmarks plus every point
measured in both runs; list the fixed points explicitly when turning points reuse names such as
Κ1, Κ2 in both runs). For every section the engine reports ΔH forward, ΔH return, their
**discrepancy** (with a tolerance when sight distances are given) and the mean; the line is then
carried on the section means and, if it ends on a benchmark, the misclosure is distributed by
section length (or equally). Averaging signed values per section — not |ΔH| with the forward
sign — is what lets a misread or a wrong sign show up instead of being absorbed.
