# Network design: pre-analysis (προανάλυση)

Code: [`engine/src/atsurvey/core/preanalysis.py`](../engine/src/atsurvey/core/preanalysis.py),
contracts [`preanalysis_models.py`](../engine/src/atsurvey/core/preanalysis_models.py) ·
API [`api/src/atsurvey_api/routers/analysis.py`](../api/src/atsurvey_api/routers/analysis.py) ·
web: page «Σχεδιασμός δικτύου» (sidebar group Εργαλεία)
([`tools/analysis/`](../web/src/features/workspace/sections/tools/analysis/),
[`lib/analysisApi.ts`](../web/src/lib/analysisApi.ts)) ·
tests: [`test_preanalysis.py`](../engine/tests/test_preanalysis.py),
[`test_analysis_api.py`](../api/tests/test_analysis_api.py),
[`analysisApi.test.ts`](../web/src/lib/analysisApi.test.ts).

The robust-estimation option of the real adjustment is documented in
[adjustment.md](adjustment.md#robust-estimation).

## What it does

Given approximate coordinates (control points fixed, new points free) and a **planned**
observation set, it computes — without any measurement — how precise and how reliable the
network will be:

| Output | Meaning |
|---|---|
| `σx`, `σy`, `σpos` per point | standard deviations (σ0 = 1), Helmert point error √(σx² + σy²) |
| absolute ellipse | standard (1σ) ellipse `a`, `b`, `theta` (azimuth of the major axis) and the 95 % axes `a95`, `b95` |
| `σz` | height precision, when height differences are planned |
| relative ellipses | for pairs joined by a planned observation (the request's `relative_pairs`): σ of the distance, of the azimuth, transverse σ = D·σα, 1σ / 95 % ellipse |
| redundancy number `r_i` | share of observation i in the degrees of freedom (Σr = n − u) |
| MDB `∇_i` | minimal detectable bias (internal reliability) |
| external reliability | `δ̄_i` and the largest point displacement an undetected ∇_i would cause |
| status | `ok`, `weak` (r < 0.3), `uncontrolled` (r < 0.01), `excluded` (not in the solved network) |

## Model

The functional model is **the adjustment's own code**: `_hz_linearise` (directions with one
orientation unknown per setup, grid distances), `_h_design` (height differences), the same
unknown layout, fixed-control datum, normal equations, Jacobi-scaled Cholesky singularity check
and redundancy formula (see [adjustment.md](adjustment.md)). Directions from the same station
form one orientation group unless a `setup` label separates them (the project derivation uses
one group per project setup).

With σ0 = 1 a priori and `P = diag(1/σ_i²)`:

* `Qxx = (AᵀPA)⁻¹`; point σ and the ellipse from its 2×2 blocks (eigenvalues
  `½(qxx + qyy) ± √(¼(qxx − qyy)² + qxy²)`).
* 95 % ellipse: axes × `k = √χ²₂(0.95) = √(−2 ln 0.05) = 2.4477` (two degrees of freedom; the
  one-dimensional 1.96 would be wrong for an ellipse).
* Relative: `Q_Δ = Q_jj + Q_ii − Q_ij − Q_ji` (zero blocks for a fixed point); σD = √(gᵀQ_Δg)
  with `g = (Δx/D, Δy/D)`, σα with `g = (Δy/D², −Δx/D²)`.
* Redundancy: `r_i = 1 − p_i a_i Qxx a_iᵀ`.
* Internal reliability (Baarda 1968): `∇_i = δ0 · σ_i / √r_i` with
  `δ0 = N⁻¹(1 − α0/2) + N⁻¹(β0)`. Defaults α0 = 0.1 % (the adjustment's w-test level), β0 = 80 %
  → δ0 = 4.13, λ0 = δ0² = 17.07. Both are request parameters.
* External reliability: `δ̄_i = δ0·√((1 − r_i)/r_i)` and the coordinate effect
  `Δx̂ = Qxx a_iᵀ p_i ∇_i`; the largest point shift (horizontal √(Δx² + Δy²), heights |Δz|) and
  the point where it occurs are reported.

### Stochastic model

σ_ci, σ_ct = centring of instrument and target, D = planned distance:

| Observation | σ |
|---|---|
| Direction | `√(σ_r² + (σ_ci² + σ_ct²)/D²)` |
| Distance | `√((a + b·D)² + σ_ci² + σ_ct²)` (a mm + b ppm added linearly, as in the adjustment) |
| Height difference | `max(σ_h·√(D km), 1 mm)` (as in the adjustment) |

The direction σ is entered in cc or mgon (1 mgon = 10 cc) and is the σ of the **mean** of the
planned sets, as in the adjustment settings.

**Known difference from the adjustment (owner decision needed).** The adjustment has a single
centring value c and uses `2c²/D²` for directions but only `c²` for distances. The physically
consistent model (both centrings act on both observation types) is the one above; with
σ_ci = σ_ct = c the pre-analysis therefore uses √2·c in the distance σ where the adjustment uses
c. With centring 0 the two models are identical (this is what the equality test uses). Changing
the adjustment would change existing results, so it was not done.

## Warnings (Issue codes)

| Code | Severity | When |
|---|---|---|
| `PREANALYSIS_DATUM` | error / warning | fewer than 2 control points in the horizontal network (no result); heights of a part not connected to a control point (warning) |
| `PREANALYSIS_SINGULAR` | error | singular normal matrix: datum defect or weak geometry (e.g. a point fixed only by collinear distances) |
| `PREANALYSIS_UNDETERMINED` | warning | new points with fewer than two effective observations (same rule as the adjustment); they and their observations are `excluded` |
| `PREANALYSIS_UNCONTROLLED` | warning | observations with r ≈ 0: a blunder in them is undetectable |
| `PREANALYSIS_WEAK` | warning | observations with r < 0.3 |

Invalid input (unknown point, duplicate names, station = target, coincident points, more than
4000 unknowns) is a 422 error, not an issue.

## Using it in the app

1. **Από το έργο** fills the plan: control points (fixed), occupied stations and traverse points
   (new, with the coordinates of the latest computation), and for every non-excluded
   observation between them one direction, one distance (if measured) and optionally one height
   difference per setup and target (faces and rounds collapse, as in the adjustment). Detail
   points are not part of the network.
2. Edit the table: untick rows to try the network without them, «Διαγραφή ανενεργών» removes
   them, the add row takes From/To (any plan or project point) and the observation types.
3. Instrument specification: defaults from the project's adjustment settings
   (`σ_ci = σ_ct = sigma_centering_mm`).
4. Results: summary (observations/unknowns, dof, worst 95 % ellipse, smallest r), issues, tables
   of points, observation reliability and relative ellipses, and an SVG plan with the 95 %
   ellipses at an automatic 1·2·5 exaggeration printed under the plot; observation lines are
   coloured by status (warning colour = weak, danger = uncontrolled).

## API

`POST /v1/analysis/preanalysis` (compute permission, like the COGO tools).

Bounds: ≤ 500 points, ≤ 5 000 observations, ≤ 1 000 relative pairs, |x|, |y| ≤ 10⁸ m, finite
numbers only, σ in (0, 1000] (centring ≤ 100 mm), α0 ∈ [10⁻⁶, 0.2], β0 ∈ [0.5, 0.999], no
extra fields. A 500-point, ≈ 3 800-observation network computes in ≈ 0.15 s.

```json
{
  "points": [{"name": "P", "x": 0, "y": 0}, {"name": "A", "x": 100, "y": 0, "fixed": true}],
  "observations": [{"kind": "direction", "station": "P", "target": "A", "setup": null}],
  "instrument": {"sigma_direction_cc": 10, "sigma_distance_mm": 2, "sigma_distance_ppm": 2,
                 "sigma_centering_instrument_mm": 1, "sigma_centering_target_mm": 1,
                 "sigma_height_mm": 5},
  "relative_pairs": [["P", "A"]], "alpha0": 0.001, "beta0": 0.8
}
```

The response's `observations` list follows the order of the request (excluded ones included).
Angles (σ and MDB of directions, σα, θ) are radians; lengths metres.

## Validation evidence

* **Identical to the adjustment**: a 4×4 network (8 neighbours; directions, distances, heights)
  is adjusted from perfect synthetic observations; σ0 ≈ 0 fails the global test low, so the
  adjustment reports a priori (σ0 = 1) precision. The pre-analysis of the same geometry
  reproduces σx, σy, σz, ellipse a, b, θ (rel. 10⁻⁶), the redundancy numbers (10⁻⁷) and
  n, u, dof exactly.
* **Independent dense model**: A built in the test by central finite differences of
  atan2/hypot, `Q = (AᵀPA)⁻¹` by numpy; point σ, relative ellipse and σD agree to 10⁻⁶.
* **Closed form**: a point fixed by three perpendicular distances (σx = σ/√2, σy = σ,
  r = ½, ½, 0, ∇ = δ0σ/√½, shift = ∇/2, δ̄ = δ0); a height from two fixed points (σz = σ/√2);
  four symmetric directions (r = ¼ each).
* **Baarda constants**: δ0 = 4.13, λ0 = 17.07; an error of size ∇ is detected with probability β0.
* Datum defect, collinear singularity, undetermined points, input validation and API bounds.

## Limitations

* Fixed datum only (no free-network / minimum-constraint pre-analysis, no weighted control).
* No GNSS baselines or levelling lines; heights only as trigonometric height differences.
* Observations are uncorrelated (Baarda's diagonal case); correlations within a set are ignored.
* The plan is not saved with the project (it lives in the tool while it is open).
* No automatic optimisation (which observation to add): the surveyor iterates by editing the table.

## References

* Baarda W. (1968). *A testing procedure for use in geodetic networks.* Netherlands Geodetic
  Commission, Publications on Geodesy 2(5).
* Kuang S. (1996). *Geodetic Network Analysis and Optimal Design.* Ann Arbor Press.
* Ghilani C. D. (2017). *Adjustment Computations: Spatial Data Analysis*, 6th ed. Wiley
  (ch. 16 observation equations, ch. 19 error ellipses).
* Mikhail E. M., Ackermann F. (1976). *Observations and Least Squares.* IEP.
