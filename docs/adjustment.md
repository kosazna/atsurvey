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
* Single-blunder data snooping; there is no iterative automatic rejection.
* Vertical deflection and geoid variation over the network are ignored (one `geoid_undulation`).
* The scale factor is not estimated (EGSA87 k is applied in the reduction).


### Interpreting the global test

* σ₀ **above** the upper bound → `ADJUSTMENT_GLOBAL_TEST` (warning): the observations fit worse
  than their stated precision. Look for blunders (w-test) or a priori σ that are too optimistic.
* σ₀ **below** the lower bound → `ADJUSTMENT_SIGMA0_LOW` (info): the observations fit better
  than stated; the a priori σ are conservative. This is common with good instruments and is not
  a quality problem.
