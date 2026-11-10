# Levelling network adjustment and instrument checks

Code: [`core/levelnet.py`](../engine/src/atsurvey/core/levelnet.py) (network),
[`core/_loops.py`](../engine/src/atsurvey/core/_loops.py) (graph, loop basis),
[`core/instruments.py`](../engine/src/atsurvey/core/instruments.py) (checks),
[`core/_lsq.py`](../engine/src/atsurvey/core/_lsq.py) (least squares, χ² quantiles, Baarda δ0).
API: [`routers/instruments.py`](../api/src/atsurvey_api/routers/instruments.py).
Web: Levelling section → **Δίκτυο** mode
([`LevelNetPanel.tsx`](../web/src/features/workspace/sections/LevelNetPanel.tsx),
[`LevelNetResults.tsx`](../web/src/features/workspace/sections/LevelNetResults.tsx));
page **Έλεγχοι οργάνων** (sidebar group Εργαλεία) ([`tools/instruments/`](../web/src/features/workspace/sections/tools/instruments)).
Client and types: [`lib/instrumentsApi.ts`](../web/src/lib/instrumentsApi.ts); reports:
[`lib/instrumentsReport.ts`](../web/src/lib/instrumentsReport.ts).

All endpoints are stateless `POST`s behind `require_compute` (same callers as `/v1/compute`,
including the anonymous demo), no plan gating. Invalid input returns **422** with a message.
Issue codes: `LEVNET_*`, `INSTR_*` (Greek templates in `core/messages.py` and
`web/src/locales/instruments.el.ts`).

## 1. Levelling network adjustment (συνόρθωση χωροσταθμικού δικτύου) — `POST /v1/leveling/network`

**Where in the app.** The Levelling section has a *Όδευση / Δίκτυο* switch. The network mode
shares the section's benchmarks and tolerance (base + c·√L) and stores its lines in
`projects.extras.leveling.network`. **Από τις μετρήσεις** turns the section's readings (forward and
return runs) into network lines: each run is split at the benchmarks and the section points;
Δh = Σ(bs − fs), length = Σ sight lengths, setups = count (intermediate sights are ignored; a
piece that returns to its own start carries no height information and is dropped). Lines can
also be typed or pasted (from, to, ΔH, length km, setups). *Ενημέρωση υψομέτρων σημείων* writes
the adjusted heights into matching control points (undoable); CSV exports name;H;σ.

The network mode was put in the Levelling section (not a tool tab) because its inputs are the
section's own benchmarks and readings.

**Input** (`LevelNetRequest`)

| Field | Meaning |
|---|---|
| `benchmarks[]` | `name`, `h` (m). ≤ 500, unique names |
| `lines[]` | `frm`, `to`, `dh` = H(to) − H(frm) (m), `length_km` and/or `setups`. 1–3000 lines, ≤ 1000 points |
| `weighting` | `length` (σ = σ_km·√L) or `setups` (σ = σ_n·√n) |
| `sigma_mm_per_sqrt_km` / `sigma_mm_per_setup` | a priori σ (default 2.0 mm/√km, 0.5 mm/√setup) |
| `datum` | `fixed` (benchmarks held fixed) or `free` (minimal constraint) |
| `free_points` | free datum: points whose mean height is kept (default: benchmarks, else all) |
| `alpha_global`, `alpha_w` | 0.05 (χ² two-sided), 0.001 (w-test, critical 3.29) |
| `tolerance_base_mm`, `tolerance_mm_per_sqrt_km`, `tolerance_mm_per_sqrt_setup` | loop tolerance base + c·√L (or c_n·√n) |

**Method** (Niemeier, *Ausgleichungsrechnung* §4.3, §6; Ghilani, *Adjustment Computations*
ch. 12; Koch, *Parameter Estimation* §3.4; Baarda 1968):

* Observation equation Δh_ij + v_ij = H_j − H_i, weights P = 1/σ², a priori σ0 = 1. Normal
  equations are assembled directly (two non-zeros per line), solved on corrections to heights
  carried along a BFS tree (exact for a tree, keeps numbers small).
* **Fixed datum**: benchmarks are hard constraints. Every connected part needs one; parts
  without a benchmark are excluded with `LEVNET_NO_DATUM` (error) and listed in
  `excluded_points`. Several parts each with a benchmark: `LEVNET_PARTS` (info).
* **Free datum**: no point fixed; Σ_{i∈S} H_i = Σ_{i∈S} H_i^ref (benchmark height, or the carried
  height). Q_xx is the upper-left block of the inverse of the bordered matrix [[N, Cᵀ], [C, 0]].
  The network must be connected (`LEVNET_DISCONNECTED`: the largest part is adjusted). Each
  benchmark gets `known_diff` = adjusted − known: a stability check of the benchmarks.
* **Statistics**: f = n − u (+1 for the free datum). Global test Ω = vᵀPv ∈ [χ²_f(α/2),
  χ²_f(1−α/2)] (`LEVNET_GLOBAL_TEST` / `LEVNET_SIGMA0_LOW`). σH uses s0² only when the test passes,
  otherwise σ0 = 1 (as in the traverse adjustment). χ² quantiles are exact (regularized
  incomplete gamma + bisection), not Wilson–Hilferty, because f is often 1–5 here.
* **Data snooping**: w_i = v_i / σ_vi, σ_vi² = σ_i² − (Q_jj + Q_ii − 2Q_ij). Only the largest
  |w| > N(1 − α0/2) is flagged (`suspect_line`, `LEVNET_BLUNDER`); remove it and re-adjust before
  looking at the next one. Redundancy numbers r_i and MDB = δ0·σ_i/√r_i (δ0 = 4.13) are returned;
  lines with r < 0.001 (dangling lines) are not controlled (`w = null`).
* **Loops (βρόχοι)**: an independent cycle basis with exactly f members — loops plus one
  benchmark-to-benchmark *connection* per extra fixed benchmark in a part. Short loops are
  preferred: candidates are, for every line, the shortest path between its ends without it,
  and the shortest path between every benchmark pair; they are accepted in order of length
  while independent over GF(2) (greedy matroid basis, Horton 1987), and the fundamental cycles
  of a BFS forest complete the basis. With more than 200 candidates the fundamental basis is used.
  Misclosure w = Σ ±Δh − (H_end − H_start) (0 for a loop); tolerance = base + c·√L_km
  (`LEVNET_LOOP_TOLERANCE` when exceeded).

**Output** (`LevelNetResult`): points (H, σH, fixed/adjusted, known_diff), lines (Δh, adjusted
Δh, v, σ, r, w, MDB, flagged), loops (kind, path, lines with signs, misclosure, L, n, tolerance,
pass), n, u, f, σ0, variance factor, χ² test, critical w, suspect line, excluded points, issues.

**Validation** ([`engine/tests/test_levelnet.py`](../engine/tests/test_levelnet.py)):
noise-free network reproduces the true heights to 1e-9 m with zero misclosures and
f = number of loops; a hand-computed two-benchmark line (X = 105.005, σX = √2 mm, r = ½);
300 noisy networks give mean vᵀPv/f = 1 ± 0.08 and > 98 % 3σ coverage of the true heights;
a 25 mm blunder is the single flagged line with MDB < 25 mm; for every loop
Σ ±v = −w exactly (adjusted heights close all loops); single benchmark fixed = free network on
that benchmark (heights, σ, f identical); residuals do not depend on the datum; the mean of
the datum points is preserved; parts without datum, disconnected free networks, parallel
lines with 1/n weights against the closed-form weighted mean, a ladder network whose basis is
its three elementary meshes plus one connection; χ² quantiles against tables. Max-size request
(1000 points, 3000 lines): ≈ 0.15 s.

## 2. Instrument checks — page Έλεγχοι οργάνων

Each check has instrument model, serial number, operator and date fields (kept in the browser
only) and produces a **printable report** (new window → print / save as PDF; no scripts; user text
escaped) and a **CSV** (UTF-8 BOM, `;`).

### 2a. Total station two-face test — `POST /v1/instruments/two-face`

Input: `targets[]` (1–200) with face I/II horizontal readings `hz1`, `hz2` and zenith angles
`v1`, `v2` (radians; the UI takes the project unit), `trunnion` = `auto | always | never`.

Model (Kahmen, *Vermessungskunde* §4.4; Deumlich & Staiger, *Instrumentenkunde* §5.3;
Leica white paper *Surveying instruments – check and adjust*): a face I reading contains
c/sin z + a·cot z, face II the opposite. With δ_j = ½·wrap(Hz_I − Hz_II + π):

    δ_j = c / sin z_j + a · cot z_j          (least squares, equal weights)
    i_j = ½ (V_I + V_II − 2π),  i = mean,   z_j = ½ (V_I − V_II + 2π)

The corrected face I readings are Hz_I − δ and V_I − i. a is estimated only if cot z spans
≥ 0.15 (≈ ±10 gon around the horizon) and there are ≥ 2 targets (`auto`), otherwise
`INSTR_TRUNNION_UNRESOLVED`; `always` with an unresolvable layout returns 422. Pairs with
|δ| or |i| > 0.01 rad (≈ 0.64 gon) raise `INSTR_FACE_MISMATCH`; sights within 4.5° of the
zenith/nadir are rejected. Output: c, a, i with σ (from the residual scatter; null with no
redundancy), s0 of one δ and one i_j, d.o.f., per-target zenith, mean direction, δ, i_j,
residuals. The UI shows **cc and mgon**.

Tests: injected c = 12cc, i = −25cc, a = 30cc recovered to 1e-12 rad from five targets at
70–120 gon, mean directions free of c and a; horizontal-only targets give c exactly and no a;
40 noisy targets give s0 ≈ 3cc/√2 and parameters within 4σ; wrap-around at 0/400 gon.

### 2b. Level two-peg test — `POST /v1/instruments/two-peg`

Input: `setup1`, `setup2` each with staff readings `a`, `b` (m) and sight lengths `dist_a`,
`dist_b` (m); `method` (label only); `tolerance_mm_per_30m` (default 3).

General two-setup formula (Deumlich & Staiger §6.4; ε = tangent of the line-of-sight
inclination, positive upward): a reading at sight length s contains ε·s, so

    ε = [(a₁ − b₁) − (a₂ − b₂)] / [(s_A1 − s_B1) − (s_A2 − s_B2)]

The **Förstner** layout is the default (A–B 45 m, setups 15 m from A and 15 m from B:
15/30 and 30/15 m); **Kukkamäki** (10/10, then 20 m beyond B: 40/20) and **middle-and-end**
(15/15, then 33/3) are presets of the same formula, and any distances can be typed. The
setups must differ in sight imbalance by ≥ 5 m. Output: ε, error in mm/30 m, angle in ″ and cc,
true ΔH = (a₁ − ε s_A1) − (b₁ − ε s_B1), the correct readings on A and B from setup 2 (the
reading to set the crosshair to when adjusting), pass/fail.

Tests: synthetic readings with ε = 2 mm/30 m for all three layouts recover ε, ΔH and the
corrected readings exactly; a textbook-style middle-and-end example (ε = −0.013/54).

### 2c. EDM additive constant — `POST /v1/instruments/edm-constant`

Input: `pillars` (3–12, in order along the line), `observations[]` (3–500: `frm`, `to`,
`distance` m, either direction), optional `positions` (certified distances from the first
pillar, increasing).

Model (Deumlich & Staiger §7.6; ISO 17123-4 baseline procedure):
* unknown positions: d_ij + k0 = x_j − x_i, x_0 = 0 → unknowns x_1…x_{k−1}, k0. With 4
  pillars and all 6 combinations f = 2. Scale is **not** separable from unknown positions.
* certified baseline: d_ij + k0 + m·d_ij = X_j − X_i → k0 and scale m (ppm).

A layout where k0 is not determined (e.g. only consecutive pillars) returns 422; f = 0 gives
`INSTR_EDM_NO_REDUNDANCY`. Output: k0 (add to measured distances) ± σ, scale ppm ± σ
(certified only), s0, positions ± σ, per-distance adjusted pillar distance and residual.

Tests: k0 = −23.4 mm recovered to 1e-10 m with positions to 1e-9 m; 5 repeated sets with 0.5 mm
noise and reversed observations give s0 ≈ 0.5 mm and k0 within 4σ; certified baseline recovers
k0 = 7.1 mm and −12 ppm; 3 pillars (f = 0) and a singular layout.

## Limitations and dependencies

* Distances for the EDM check must already be horizontal and atmospherically corrected.
* The two-peg tolerance default (3 mm / 30 m) and the network a priori σ defaults (2 mm/√km,
  0.5 mm/√setup) are reasonable values, not an official Greek specification: **owner to
  confirm**. specs.py has no height presets (the traverse table has none), so loop tolerances
  reuse the Levelling section's base + c·√L fields.
* Two-face test assumes a single round per target row (repeat rows for more rounds); it does
  not model the compensator or the ATR collimation separately.
* No published Greek worked examples were available; validation is against synthetic truth and
  closed-form cases. A real instrument-check record from the owner would be a useful fixture.
* Reports are client-side HTML/CSV, not part of the server PDF export.
