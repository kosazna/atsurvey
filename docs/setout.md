# Setting out and road alignments (Χαράξεις)

Code: [`core/setout.py`](../engine/src/atsurvey/core/setout.py) (batch setting out, as-staked
check), [`core/alignment.py`](../engine/src/atsurvey/core/alignment.py) (horizontal alignment and
queries), [`core/alignment_profile.py`](../engine/src/atsurvey/core/alignment_profile.py)
(vertical profile), contracts in
[`core/alignment_models.py`](../engine/src/atsurvey/core/alignment_models.py). API router:
[`routers/setout.py`](../api/src/atsurvey_api/routers/setout.py). Web: page
**Χαράξεις** (sidebar group Εφαρμογές; also holds the single-point stakeout tab) (`web/src/features/workspace/sections/tools/setout/`), client
`web/src/lib/setoutApi.ts`.

Conventions as everywhere: x = Easting, y = Northing (ΕΓΣΑ87 metres), angles in radians inside
the engine and API, azimuths clockwise from grid north, directions clockwise, **offsets positive
to the right** of the direction of increasing chainage, grades as fractions. Every endpoint is a
stateless `POST` open to the same callers as `/v1/compute` (including the demo); degenerate
input returns **422** with a message; geometric problems that still allow an answer are `Issue`s
with stable codes (Greek templates in `core/messages.py` and `web/src/locales/setout.*.ts`).

## 1. Batch setting out (χάραξη σημείων) — `POST /v1/setout/points`

Input: station (known point, z optional), orientation by a **backsight point** (Hz = 0 on it) or
a **known azimuth** of the zero direction, instrument and target heights (optional, default 0),
up to 10 000 design points (name, x, y, z?), and optionally the project's `reduction` settings.
The web form takes design points as project point names, pasted `name X Y [Z]` lines, or a DXF
read by the existing DXF importer (`formats/dxf.py` via `/v1/parse`).

Per point (reuses `cogo.stakeout` for the horizontal part):

| Output | Formula |
|---|---|
| ΔE, ΔN | `P − S` |
| Azimuth | `α = atan2(ΔE, ΔN)` |
| Direction to set | `Hz = α − α(S→B)` (wrapped to `[0, 2π)`) |
| Grid distance | `D = √(ΔE² + ΔN²)` |
| Distance to set | ground distance `HD = D / (k · R/(R + Hm + N))` when `reduction` is given (same scale mode, geoid N and default height as the project; `Hm` = mean of station and point heights), else `D` |
| Vertical (station and point heights) | `V = ΔZ − hi + ht − (1 − κ)·HD²/2R` (curvature-refraction term only when enabled), zenith `z = atan2(HD, V)`, slope `S = √(HD² + V²)` |

The vertical formula is the exact inverse of `geodesy.height_difference`, so measuring the
returned S and z reproduces ΔZ (tested to 1 nm). The existing single-tool `cogo.stakeout` does not
apply curvature-refraction to the zenith; this tool does, consistently with the reductions.

`field_order` sorts the points by direction from the backsight (one clockwise sweep), nearer
first for equal directions; `rows` stay in input order. The result also gives the
station–backsight distance (ground when reduced) to check the orientation in the field.
The CSV (`;`, UTF-8 with BOM, angles in the project unit) follows the order shown.

Issues: `SETOUT_DUPLICATE_NAME` (same name, different coordinates), `SETOUT_NO_STATION_HEIGHT`
(points have heights but the station has none).

## 2. As-staked check (έλεγχος χάραξης) — `POST /v1/setout/check`

Design and measured points (≤ 10 000 each) are matched **by name** (trimmed, case-sensitive).
`Δ = measured − design`; radial error `r = √(ΔX² + ΔY²)`; with a reference line A→B,
`along = Δ·u` and `across = Δ·n` (n = right normal). Flags: `ok_xy = r ≤ tolerance_xy`,
`ok_z = |ΔZ| ≤ tolerance_z` (when both heights exist). Summary: matched, out of tolerance (any,
xy, z), max and RMS (`√(Σr²/n)`) radial error, mean ΔX/ΔY (a systematic shift shows here, e.g. a
wrong orientation), max |ΔZ|, RMS and mean ΔZ. Unmatched names are listed both ways.
A point measured twice uses the **last** measurement (`SETOUT_RESTAKED`, info); a duplicated design
name keeps the first (`SETOUT_DUPLICATE_NAME`); unnamed points are ignored (`SETOUT_UNNAMED`).

## 3. Horizontal alignment (οριζοντιογραφία) — `POST /v1/setout/alignment`

PI method: the tangent polygon `V₀ … Vₙ` (≤ 200 vertices); each interior vertex carries the
radius R and optionally the entry and exit clothoids by parameter A or length L (`L = A²/R`).
Without exit values the curve is symmetric; give 0 for no clothoid. Per vertex, with deflection
Δ (positive right):

| Quantity | Formula |
|---|---|
| Clothoid tangent angle | `τ = L / 2R` |
| Clothoid end point | `X + iY = L · Σₖ (iτ)ᵏ / (k!(2k+1))` (Fresnel series; converges for any τ, used for τ ≤ π) |
| Shift (ΔR, p) | `ΔR = Y − R(1 − cos τ)` |
| Centre abscissa (XM, k) | `XM = X − R sin τ` |
| Tangent lengths | `T₁ = XM₁ + (R+ΔR₂)/sin|Δ| − (R+ΔR₁)/tan|Δ|`, `T₂ = XM₂ + (R+ΔR₁)/sin|Δ| − (R+ΔR₂)/tan|Δ|` |
| Arc | central angle `|Δ| − τ₁ − τ₂`, length `R·(|Δ| − τ₁ − τ₂)` |
| External | `E = |V − C| − R` |

Symmetric case: `T = XM + (R + ΔR) tan(|Δ|/2)`; plain arc: `T = R tan(|Δ|/2)`,
`E = R(sec(|Δ|/2) − 1)`. References: Kasper–Schürba–Lorenz, *Die Klothoide als
Trassierungselement*; RAS-L; Greek ΟΜΟΕ-Χ (same notation A, τ, ΔR, XM as the Greek road-design
course sheets).

Output: vertex table (Δ, R, A/L, τ, ΔR, XM, T₁/T₂, arc, curve length, E, centre, chainages),
element table (tangent / clothoid / arc with chainages, lengths, end points and azimuths), main
points, a densified polyline for the preview, and the issues.

**Main points.** International codes, Greek descriptions in the UI:

| Code | Meaning (UI) |
|---|---|
| BP / EP | Αρχή / τέλος άξονα |
| TS | Αρχή κλωθοειδούς εισόδου (tangent → spiral) |
| SC | Τέλος κλωθοειδούς – αρχή τόξου |
| MC | Μέσο κυκλικού τόξου |
| CS | Τέλος τόξου – αρχή κλωθοειδούς εξόδου |
| ST | Τέλος κλωθοειδούς εξόδου |
| PC / PT | Αρχή / τέλος κυκλικού τόξου without clothoids |

Greek abbreviations (e.g. ΑΚ/ΤΚ) are **not** used because their meaning could not be verified
against an official source; the owner may supply the convention to adopt.

**Checks (Issues).** `ALIGN_NO_RADIUS` (direction changes at a vertex without R; error),
`ALIGN_REVERSAL` (Δ = ±π; error), `ALIGN_CLOTHOIDS_TOO_LONG` (τ₁ + τ₂ > |Δ|; error),
`ALIGN_NEGATIVE_TANGENT` (strongly asymmetric clothoids put TS/ST beyond the vertex; error),
`ALIGN_OVERLAP` (T₂ of one vertex + T₁ of the next exceed the side, with the overlap in metres;
error), `ALIGN_NO_DEFLECTION` (R given on a straight vertex, < 1 cc; warning, ignored),
`ALIGN_CLOTHOID_RANGE` (A outside the guideline range R/3 ≤ A ≤ R; warning). With any error the
element list is empty and the query endpoints return 422 with the messages.

### Queries — `POST /v1/setout/alignment/locate`

* **(chainage, offset) → (x, y, azimuth)**: the element is found by binary search; offset along
  the right normal. Chainages beyond the ends are extended along the end tangents (`inside=false`).
* **(x, y) → (chainage, offset)**: perpendicular foot on every candidate element — closed form on
  tangents and arcs, bracketed bisection of `(P − C(s))·t(s) = 0` on clothoids — and the nearest
  foot wins. Elements are visited by a lower bound (every element point lies within L/2 of its
  middle point), so 10 000 points on a 200-vertex axis take ≈ 1 s. Points beyond the ends project
  on the extended end tangents (`inside=false`). With a profile, `z_design` and `dz = z − z_design`
  (cut/fill on the axis, no cross-fall).

### Stakeout list — `POST /v1/setout/alignment/stakeout`

Round chainages every `interval` m (multiples of the interval, e.g. 0+020, 0+040 even if the axis
starts at 0+013.5), the range ends, and all main points (optional), each at the requested offsets
(≤ 20, negative = left). Limit 50 000 rows. The web names points `0+120.00`, `0+120.00L3.50`,
`0+120.00R3.50`, offers CSV and "add to project".

## 4. Vertical profile (μηκοτομή ερυθράς) — `profile` in the alignment request

PVIs (≤ 500) with chainage, elevation and a parabolic vertical curve by length L or parameter H
(`L = H·|g₂ − g₁|`). `z(x) = z_PVC + g₁x + (g₂ − g₁)x²/2L`, grade `g₁ + (g₂ − g₁)x/L`, x from the
PVC = PVI − L/2; high/low point at `x = −g₁L/(g₂ − g₁)` when the grades change sign. Errors:
non-increasing chainages (422), `ALIGN_VERTICAL_OVERLAP` (curves overlap or run past the ends).
Design elevations are added to main points, stakeout rows and located points.

## Validation evidence

* `engine/tests/test_alignment.py`
  * clothoid series vs **two independent integrations** (SciPy Fresnel integrals and a 40×40-point
    Gauss–Legendre quadrature) for A = 30…800, L = 10…900 and τ up to π: |Δ| < 1 nm (requirement
    0.1 mm);
  * circular curves vs closed form (T, arc, E, chord `2R sin(Δ/2)`, chainages) for Δ = 20°…170°,
    both directions;
  * symmetric clothoid–arc–clothoid: ΔR, XM and T vs formulas and textbook approximations
    (`ΔR ≈ L²/24R`, `XM ≈ L/2 − L³/240R²`), τ at SC, total turn Δ at ST, ST at T from the vertex,
    MC at E on the bisector, SC/CS at R from the centre;
  * asymmetric curves: the centre is at `R + ΔR` from both tangent lines (independent check of
    T₁/T₂), and the mirror image gives the same tangents with opposite Δ;
  * **continuity of position (< 1 nm) and azimuth (< 10⁻¹² rad) at every element joint**;
  * round trip (chainage, offset) → (x, y) → (chainage, offset) on every element type at
    offsets −15 … +18 m, at ΕΓΣΑ87 magnitudes: < 10 nm;
  * issues, stakeout spacing/main points/limits, vertical curve mid-ordinate `(g₂ − g₁)L/8`,
    tangent grades outside the curve, H ↔ L, high point.
* `engine/tests/test_setout.py`: hand-computed directions and distances (45°, 3-4-5 triangles),
  known-azimuth orientation, polar round trip of 40 points (< 1 nm), field order, ΕΓΣΑ87 reduction
  vs the independent chain, zenith inverting the height reduction, as-staked statistics,
  along/across components, re-staked/unnamed/unmatched handling.
* `api/tests/test_setout_api.py`: each route, 422 paths and request bounds.
* `web/src/lib/setoutApi.test.ts`: chainage format/parse, vertex and profile parsers, CSV builders,
  point naming, SVG frame.

## Limitations and open items

* Greek abbreviations of main points (ΑΚ, ΤΚ …): international codes are used until the owner
  confirms the convention.
* The clothoid guideline check (R/3 ≤ A ≤ R) is the commonly quoted RAS-L/ΟΜΟΕ-Χ rule; other
  ΟΜΟΕ-Χ checks (minimum radii per design speed, clothoid length from the superelevation ramp,
  tangent lengths between reverse curves) need the design speed and are not implemented.
* No superelevation/cross-fall: offsets get the axis elevation; `dz` is relative to the axis.
* Vertical curves are symmetric parabolas only; no compound or asymmetric vertical curves.
* Egg-shaped clothoids between two arcs at one vertex (compound curves) are not supported;
  model them as separate vertices.
* The as-staked check matches names exactly; there is no nearest-neighbour matching.
* Not validated yet against an existing road design file or the owner's workbooks.
