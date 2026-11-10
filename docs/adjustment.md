# Least-squares network adjustment

Code: [`engine/src/atsurvey/core/adjust.py`](../engine/src/atsurvey/core/adjust.py) ·
tests: [`engine/tests/test_adjust.py`](../engine/tests/test_adjust.py).

Enable per project with `settings.adjustment.method = "least_squares"` (default `"bowditch"`).
The traverses are still computed first, by the compass rule. Their coordinates serve as
approximate values. All observations between occupied stations, traverse points and control
points are then adjusted **simultaneously**, so junctions, cross-ties and repeated measurements
give one consistent solution. Detail points are radiated afterwards from the *adjusted* stations.

## Network

| Element | Contents |
|---|---|
| Free points | traverse points and occupied stations that are not control points and have approximate coordinates |
| Fixed points | control points connected to the network by at least one observation |
| Excluded | stations without approximate coordinates (e.g. determined later by radiation) and free points with fewer than two effective observations (`ADJUSTMENT_EXCLUDED_POINT`) |
| Not adjusted | detail points (targets that are not network points) |

## Functional model

**Horizontal** (non-linear, Gauss–Newton until the largest coordinate correction is below
0.05 mm or `max_iterations`):

| Observation | Model | Unknowns |
|---|---|---|
| Direction r (reduced circle reading, face I) | `r = α(i→j) − ω_s` | x, y of i and j, orientation ω of setup s |
| Grid distance D | `D = √((x_j − x_i)² + (y_j − y_i)²)` | x, y of i and j |

Measured horizontal distances are reduced to the grid with the project's `ReductionSettings`:
`D = HD · R/(R + Hm + N) · k`. Hm is the line's mean height from approximate heights. k follows
`scale_mode`; for the least-squares adjustment it is always evaluated per line, even in
`traverse_mean` mode. Each setup has its own orientation unknown, so re-occupations, rounds
and setups without a zeroed backsight need no special handling.

**Heights** (linear, separate 1D adjustment): `h_j − h_i = Δh`, with Δh the reduced
trigonometric height difference (instrument and target heights, curvature and refraction
included). Only the parts of the height network that are connected to at least one control point
with a height are adjusted.

## Stochastic model (a priori)

| Observation | σ | Settings |
|---|---|---|
| Direction | `√(σ_dir² + 2·(c/D)²)` | `sigma_direction_cc`, `sigma_centering_mm` (c) |
| Distance | `√((a + b·D)² + c²)` | `sigma_distance_mm` (a), `sigma_distance_ppm` (b) |
| Height difference | `max(σ_h·√(D km), 1 mm)` | `sigma_height_mm` |

Weights are `p = 1/σ²` (a priori σ0 = 1). A reduced direction or distance is the mean of all
rounds and faces of one setup and counts as one observation. Its σ is not divided by √n, so give
σ for the mean of a typical set of readings. Forward and backward measurements of the same line
are separate observations.

## Datum

Control points are **fixed**; there are no minimum-constraint or free-network solutions.

* Horizontal: at least 2 fixed points must be connected, and the normal matrix must be regular.
  Otherwise the adjustment reports `ADJUSTMENT_DATUM` (error), returns `None` and the traverse
  (Bowditch) coordinates are kept.
* Heights: at least one fixed point with a height. Without one, the horizontal results are kept
  and `ADJUSTMENT_DATUM` (warning, `dimension = "height"`) is reported.

Networks above 4000 unknowns are not adjusted (`ADJUSTMENT_TOO_LARGE`).

## Statistics

| Quantity | Definition |
|---|---|
| Degrees of freedom | `dof = n_observations − n_unknowns` (horizontal + heights; orientations count as unknowns) |
| σ0 (a posteriori) | `√(vᵀPv / dof)`; 0 when `dof = 0` (`ADJUSTMENT_NO_REDUNDANCY`) |
| Global test | `vᵀPv ~ χ²(dof)`, two-sided at `alpha_global` (default 5 %); bounds from the Wilson–Hilferty approximation |
| Redundancy numbers | `r_i = 1 − p_i · a_i Qxx a_iᵀ`, in [0, 1]; Σr_i = dof |
| w-test (Baarda) | `w_i = v_i / (σ_i √r_i)` for `r_i ≥ 0.01`; critical value `N⁻¹(1 − alpha_w/2)` (3.29 for α = 0.1 %) |
| Suspect | the observation with the largest \|w\| above the critical value (`ADJUSTMENT_BLUNDER`) |

Residuals are `adjusted − observed`. In `AdjustmentResult.observations`, directions are circle
readings in radians (not azimuths) and distances are grid distances in metres.

**Precision of points.** `sx`, `sy`, `sz` and the standard (1σ) error ellipse come from the
cofactor matrix Qxx, scaled by:

* **σ0² when the global test passes**: the observations agree with the stochastic model, so the
  empirical variance factor is the best estimate.
* **1 (a priori) when the global test fails or dof = 0.** A failed test means σ0 is distorted by
  blunders or wrong a priori σ, so it is not used to rescale the precision. Fix the cause first.

Ellipse: `a`, `b` semi-axes in metres, `theta` the azimuth of the major axis in [0, π). Multiply
the axes by `k95 = 2.4477` for a 95 % confidence ellipse.

## Robust estimation

Optional, **off by default** (`settings.adjustment.robust = "off"`; with it off the computation
is exactly the plain least-squares adjustment — verified bit-identical against the code before
the option existed, `engine/tests/test_robust.py` + `fixtures/adjust_golden.json`). Toggle in the
Adjustment section («Εύρωστη εκτίμηση»).

| Setting | Default | Meaning |
|---|---|---|
| `robust` | `off` | `huber` or `danish` |
| `robust_threshold` | 2.5 | c: \|ū\| above which an observation is down-weighted (1–10) |
| `robust_max_iterations` | 20 | maximum re-weightings (1–100) |

**Method** — iteratively re-weighted least squares (IRLS) on the standardised residuals
`ū_i = v_i / (σ_i √r_i)` (a priori σ, redundancy of the current solution; observations with
r < 0.01 keep full weight because they cannot be judged). Each re-weighting solves the horizontal
(Gauss–Newton, warm start) and the height network with `p_i · w_i`:

* Huber (1964): `w = 1` for |ū| ≤ c, `c/|ū|` beyond.
* Danish method (Krarup, Juhl & Kubik 1980), smooth form: `w = 1` for |ū| ≤ c,
  `exp(1 − (|ū|/c)²)` beyond. It is redescending, so it **starts from the converged Huber
  weights** (a gross error smeared by the first least-squares solution would otherwise switch
  off good observations around it) and then continues with the Danish function.
* Weights are floored at 10⁻⁴ (σ inflated at most 100×) so the normal matrix stays regular; if a
  re-weighting makes it singular anyway, the last regular solution is kept.
* Convergence: no weight factor changes by more than 10⁻³. Otherwise `ROBUST_NOT_CONVERGED`.

**Reported statistics after re-weighting** (they are those of the final weighted least-squares
solution, so they are internally consistent):

* Coordinates, Qxx, σx/σy/σz, ellipses and redundancy numbers: from the final weights `p_i w_i`.
* σ0 and the global test: `vᵀ(PW)v / (n − u)`. A down-weighted observation contributes
  `w_i ū_i²`; the degrees of freedom are not reduced (conservative: σ0 slightly low). The rule
  for scaling the precision (σ0² if the test passes, otherwise 1) is unchanged.
* w-test: `w_i = v_i / (σ_i √r_i)` with the **a priori** σ, i.e. the standardised residual
  against the robust solution. Gross errors therefore stay flagged and named as `suspect` /
  `ADJUSTMENT_BLUNDER`, even though they no longer distort the coordinates. Fix or exclude them.
* Per observation `weight` (1 = full weight); in the result `robust = {method, threshold,
  iterations, converged, downweighted}` (count of factors < 0.99) and the warning
  `ROBUST_DOWNWEIGHTED` listing the most down-weighted observations.

Evidence (`test_robust.py`): in a 5×5 network with noise matching the a priori model, one, two
or three injected gross errors (150 cc direction, 6 cm distance, ≈ 10 cm height difference) get
weight < 0.35 (Danish: 10⁻⁴), remain flagged, and the robust coordinates match the clean solution
within 1.5 mm horizontally / 1 mm in height, while the plain adjustment is pulled > 3× further.
On clean data fewer than 6 % of observations lose any weight and coordinates change < 1 mm.

Caveats: robust estimation assumes the a priori σ are realistic (too optimistic σ make many good
observations look suspicious); it cannot help with observations that have no redundancy; with
several gross errors in one weak part of a network it can still be misled (masking).

## Reading the results

1. **Global test passed and no suspect.** The network is consistent; the ellipses are the
   precision of the coordinates.
2. **Global test failed, σ0 ≫ 1.** Look at `suspect`. Data snooping assumes one blunder at a
   time: exclude the suspect observation, recompute, and repeat.
3. **Global test failed, σ0 ≪ 1.** The a priori σ are too pessimistic (common with perfect
   synthetic data or when rounds are averaged); tighten them.
4. **Small redundancy numbers (r < 0.1)** mark weakly checked observations; a blunder there is
   hardly detectable (e.g. the only distance to a hanging point).

## Limitations

* Only directions, horizontal distances and trigonometric height differences; no GNSS baselines
  or levelling lines in the network yet.
* Fixed datum only (no weighted control points, no free-network adjustment).
* Single-blunder data snooping; no automatic rejection (robust estimation down-weights instead).
* Centring: one value c enters directions as `2c²/D²` but distances as `c²` (the pre-analysis
  uses instrument and target centring on both; see [analysis.md](analysis.md)). Kept for
  backward-compatible results; awaiting the owner's decision.
* Vertical deflection and geoid variation over the network are ignored (one `geoid_undulation`).
* The scale factor is not estimated (EGSA87 k is applied in the reduction).


### Interpreting the global test

* σ₀ **above** the upper bound → `ADJUSTMENT_GLOBAL_TEST` (warning): the observations fit worse
  than their stated precision. Look for blunders (w-test) or a priori σ that are too optimistic.
* σ₀ **below** the lower bound → `ADJUSTMENT_SIGMA0_LOW` (info): the observations fit better
  than stated; the a priori σ are conservative. This is common with good instruments and is not
  a quality problem.
