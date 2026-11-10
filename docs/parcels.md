# Parcels (ιδιοκτησίες / γεωτεμάχια)

Area and tables of a parcel, comparison with the deed and the Cadastre, subdivision
(κατάτμηση), merge (συνένωση) and an exact-coverage check.

| Layer | Code |
|---|---|
| Contracts | [`core/parcels_models.py`](../engine/src/atsurvey/core/parcels_models.py) |
| Geometry, area comparison, presets | [`core/parcels.py`](../engine/src/atsurvey/core/parcels.py) |
| Subdivision | [`core/parcels_subdivide.py`](../engine/src/atsurvey/core/parcels_subdivide.py) |
| Merge | [`core/parcels_merge.py`](../engine/src/atsurvey/core/parcels_merge.py) |
| Coverage check | [`core/parcels_coverage.py`](../engine/src/atsurvey/core/parcels_coverage.py) |
| API | [`routers/parcels.py`](../api/src/atsurvey_api/routers/parcels.py) |
| Web | [`tools/parcels/`](../web/src/features/workspace/sections/tools/parcels), client [`lib/parcelsApi.ts`](../web/src/lib/parcelsApi.ts) |

UI: page **Ιδιοκτησίες** (sidebar group Εφαρμογές) with the tabs *Εμβαδόν & σύγκριση*, *Κατάτμηση*, *Συνένωση* and *Γρήγορο εμβαδόν* (polygon drawn on the map).
Vertices are typed or pasted one per line (`name X Y`), taken from project points by name, or
picked on the map. Every result has an inline SVG sketch (north up), coordinate and side tables,
areas in m² (2 decimals) and στρέμματα (1 στρέμμα = 1000 m²), and CSV downloads (`;`, UTF-8 BOM).

## Conventions

* x = Easting, y = Northing, metres, ΕΓΣΑ87; azimuths in radians clockwise from grid north
  (the UI shows the project unit).
* Areas are **grid (projection) areas**, as registered by the Hellenic Cadastre.
* float64 throughout, shoelace on coordinates relative to the first vertex, `math.fsum`
  (see [numerics.md](numerics.md)); nothing is rounded except for display.
* Problems are `Issue`s with stable `PARCEL_*` codes, Greek templates in `core/messages.py` and
  `web/src/locales/parcels.el.ts`. Geometry problems return **200** with issues; malformed
  requests (bounds, missing fields, side index out of range, incomplete tolerance rule) are 422.

## Parcel model (reusable API)

`Parcel {label, kaek, vertices: [ParcelVertex {name, x, y, arc?}]}` (≤ 1000 vertices, finite
coordinates within ±10⁸ m).

**Arc convention (one convention only).** An arc belongs to the side that **starts** at the
vertex (i → i+1) and is `ArcSpec {radius, side: left|right, large}`: the side towards which the
arc bulges, looking from vertex i to vertex i+1. The minor arc (central angle ≤ π) is meant
unless `large` is set.

`analyze_parcel(parcel) → ParcelGeometry`: cleaned vertices, side table (from, to, chord length
and azimuth, and for arcs arc length, radius, central angle, segment area), area, perimeter
(arc lengths for arcs), orientation, centroid, `has_arcs`, `valid`, `issues`.

Formulas:

* Shoelace: `2A = Σ (xᵢ·yᵢ₊₁ − xᵢ₊₁·yᵢ)` on coordinates relative to the first vertex.
* Circular segment: `θ = 2·atan2(c/2, √((R − c/2)(R + c/2)))` (or 2π − θ for a major arc; this
  form stays accurate for a semicircle where `asin` is ill-conditioned), `S = R²/2·(θ − sin θ)`,
  arc length `R·θ`. The signed (counter-clockwise positive) area gains **+S for an arc bulging
  to the right** of travel and −S to the left, whatever the ring orientation. The segment
  centroid lies on the symmetry axis at `4R·sin³(θ/2) / (3(θ − sin θ))` from the centre.

Validation: fewer than 3 distinct vertices (`PARCEL_TOO_FEW_VERTICES`), consecutive duplicates
within 1 µm (removed, `PARCEL_DUPLICATE_VERTEX`; a repeated closing vertex is dropped silently),
one name for two different points (`PARCEL_DUPLICATE_NAME`), self-intersection including a
vertex touching another side or a spike folding back (`PARCEL_SELF_INTERSECTION`, sides named;
arcs are densified into 8 chords for this test only), zero area (`PARCEL_ZERO_AREA`), arc radius
below half the chord (`PARCEL_ARC_RADIUS`).

## Area comparison

`POST /v1/parcels/compare` with the surveyed area (or the parcel), the deed area (τίτλος) and
the area on the **cadastral diagram** (the Cadastre compares against the parcel area shown on
its diagram). Rows: surveyed − deed, surveyed − Cadastre, Cadastre − deed, with differences in
m² and % of the reference area E, and — if a tolerance rule is chosen — the limit T(E) and
`within`. The UI says «εντός/εκτός ορίου» **only relative to the chosen rule** and always prints
the rule and its source next to the verdict.

Tolerance rules (`AreaToleranceRule`):

| kind | T(E) |
|---|---|
| `fixed` | `value` m² |
| `percent` | `value` % · E |
| `formula` | `a + b·√E` m² |
| `cadastre` | `U0·Π·(1 + U0/√E)` |

`cap_percent` caps any rule at that % of E. `source` is free text shown with the verdict.

**Hellenic Cadastre rule.** ΟΚΧΕ decision 461/03/21.7.2008 (ΦΕΚ Β΄ 1510/31.7.2008), quoting
ch. 7 §3.6 of decision 460/03/12.6.2008 (ΦΕΚ Β΄ 1156/2008):

```
A = [(√E + 2·U0)² − E] · Π / (4·√E)  ≡  U0 · Π · (1 + U0/√E)
```

E = area (m²; the reference area of the row), Π = parcel perimeter (m; the surveyed perimeter,
or `perimeter` in the request when only an area is given), U0 = 0.50 m for urban cadastral areas
(1:1000 mapping), 2.00 m for rural (1:5000). The factored form is used (no cancellation for large
E); a test proves it equal to the published form. Optional cap 7 % of E for areas surveyed under
the 2007 specifications (UI checkbox). Worked example: square of 500 m² (Π = 89.4427 m), urban:
A = 0.5·89.4427·(1 + 0.5/√500) = 45.72 m² (9.1 %); with the 7 % cap 35.00 m² (tested in engine
and web).

Presets (`AREA_TOLERANCE_PRESETS` in the engine, mirrored in `parcelsApi.ts`;
`GET /v1/parcels/tolerance-presets`):

| id | label | U0 | source | status |
|---|---|---|---|---|
| `cadastre_urban` | Κτηματολόγιο — αστική | 0.50 m | ΦΕΚ Β΄ 1510/2008 | confirmed |
| `cadastre_rural` | Κτηματολόγιο — αγροτική | 2.00 m | ΦΕΚ Β΄ 1510/2008 | **to be confirmed** |
| `cadastre_rural_dgm_guide` | αγροτική κατά οδηγό ΔΓΜ | 2.50 m | Κτηματολόγιο Α.Ε., οδηγός ΔΓΜ («ενδεικτικά», 99.7 %) | **to be confirmed** |

The ΦΕΚ and the ΔΓΜ guide disagree on the rural U0; both are offered and flagged
`to_be_confirmed` until the owner decides which applies. U0 is a parameter, so a custom rule
can use any value.

## Subdivision (κατάτμηση)

`POST /v1/parcels/subdivide`. Straight sides only (`PARCEL_ARCS_NOT_SUPPORTED`).

| `method` | Cut lines | Part 1 |
|---|---|---|
| `parallel` | parallel to side `side` (the side starting at vertex `side`) | contains that side |
| `perpendicular` | perpendicular to side `side` | at its start vertex (`from_end = start`) or end vertex |
| `pivot` | through `pivot` (a vertex) or `pivot_point` (coordinates within 1 mm of the boundary; projected onto the side and inserted as a new point) | from the pivot towards the neighbour `towards` (default: next vertex in input order) |

`parts` are areas (`mode = areas`) or ratios (`mode = ratios`, e.g. `[1, 1, 1]` for three equal
shares). Parts are cut off in order from the remainder; the remainder is the last part. If the
areas sum to the parcel within max(0.01 m², 10⁻⁹·E), the last area is the remainder; if they sum
to less, the rest becomes an extra part; more is `PARCEL_PARTS_EXCEED_AREA`. Repeated parallel /
perpendicular cuts keep the same direction; repeated pivot cuts fan out from the same pivot.

**Method.**

* *Half-plane cuts* (parallel, perpendicular): the cut-off area A(s) of `{p : n·p ≤ s}` is
  continuous, increasing and piecewise **quadratic** in s, with breakpoints at the vertex
  projections n·vᵢ (between two breakpoints every slab trapezoid/triangle widens linearly). The
  bracket holding the requested area comes from exact areas at the breakpoints; inside it the
  quadratic through three exact evaluations is solved in closed form (stable root), then
  polished with Newton steps (dA/ds = cut length). Areas of P ∩ half-plane: Sutherland–Hodgman
  clipping against one half-plane, then shoelace — for non-convex polygons the clip may contain
  zero-width bridges, whose contributions cancel.
* *Pivot cuts*: walking the boundary from the pivot P, the fan triangle (P, vₖ, X) has an area
  **linear** in the position of X along side vₖvₖ₊₁, so X follows in closed form.

**Non-convex parcels.** A half-plane cut is accepted only if the line crosses the boundary
exactly twice; a pivot cut only if the segment P–X stays inside and touches the boundary only at
its ends. Otherwise `PARCEL_CUT_MULTIPLE_CROSSINGS` (with the number of crossings) is reported
and no parts are returned — never a broken polygon.

**Exactness (needed by the Cadastre).** Original vertices are written back with their **exact
input coordinates** (no `(x − x₀) + x₀` round-trip), and every new point is one object shared by
the two parts on either side of the cut, so neighbouring parts share bit-identical coordinates.
New points are interpolated along the side they lie on, so they are on that side to within float64 rounding.

Output: the original geometry, every part as a full `ParcelGeometry` (starting at its first
original vertex, in the input orientation) with `requested_area`, `area_error` and `frontage`;
the cut lines (ends, length, azimuth) and the new points, named `prefix + n` (default `Ν1, Ν2, …`,
`new_point_start` configurable, names already used are skipped). Optional frontage check: the
length of each part's boundary on `frontage_side` (e.g. the road), with
`PARCEL_FRONTAGE_SHORT` below `min_frontage`. In the UI the new points can be added to the
project, and a coverage check runs automatically after each subdivision.

Accuracy: every cut part matches the requested area to ≤ 10⁻⁶ m² for parcels up to ~1 km across
at ΕΓΣΑ87 coordinates (120 random polygons in the test suite; an ad-hoc run of 3 000 random convex and star-shaped polygons during development found no other failure mode). Beyond that the limit is the float64
spacing of the stored coordinates (≈ 0.9 nm at northings of 4.2·10⁶ m: error ≲ perimeter × 1 ulp);
`PARCEL_CUT_NOT_CONVERGED` is reported only above that bound.

## Merge (συνένωση)

`POST /v1/parcels/merge`, 2–20 parcels, `snap_tolerance` (default 1 mm, ≤ 1 m).

1. Vertices closer than the tolerance become one node (first occurrence keeps name and exact
   coordinates; `PARCEL_MERGE_SNAPPED` reports how many and how far).
2. A node lying on another parcel's side (T-junction, e.g. an already subdivided neighbour, or
   partially shared collinear sides) is inserted into that side (`inserted`).
3. Rings are oriented counter-clockwise; shared sides appear once in each direction and cancel.
4. The remaining edges are traced: one counter-clockwise loop = the merged parcel; clockwise
   loops = holes (`PARCEL_MERGE_HOLES`); several outer loops = not adjacent
   (`PARCEL_MERGE_NOT_ADJACENT`); a node with two outgoing edges = contact at a point only
   (`PARCEL_MERGE_POINT_CONTACT`); duplicate same-direction edges or a union smaller than the sum
   of the parts = overlap (`PARCEL_MERGE_OVERLAP`).

Collinear vertices on the merged boundary (ends of former common sides) are kept: they are
boundary marks. The merged parcel takes the orientation of the first parcel and starts at its
first vertex.

## Coverage check (for the Cadastre diagram of geometric changes)

`check_coverage(CoverageRequest {outline, parts, tolerance = 1 µm, area_tolerance = 10⁻⁴ m²})`,
`POST /v1/parcels/coverage`. The Cadastre accepts final parcels only if they cover the original
cadastral outline with no gaps or overlaps (even mm slivers are rejected). The parts are united
as in the merge (overlaps, inner gaps, point contacts, disconnected parts are reported), then every
union vertex must lie on the outline (`PARCEL_COVERAGE_OUTSIDE`), every outline vertex on the
union boundary (`PARCEL_COVERAGE_GAP`), and |Σ parts − outline| ≤ `area_tolerance`
(`PARCEL_COVERAGE_AREA`, catches slivers thinner than the vertex tolerance). The default vertex
tolerance is exact matching (1 µm), which subdivision results pass by construction (tested for
every method and 30 random subdivisions).

## API

| Endpoint | Body → result |
|---|---|
| `POST /v1/parcels/compute` | `Parcel` → `ParcelGeometry` |
| `POST /v1/parcels/compare` | `AreaCompareRequest` → `AreaCompareResult` |
| `POST /v1/parcels/subdivide` | `SubdivideRequest` → `SubdivisionResult` |
| `POST /v1/parcels/merge` | `MergeRequest` → `MergeResult` |
| `POST /v1/parcels/coverage` | `CoverageRequest` → `CoverageResult` |
| `GET /v1/parcels/tolerance-presets` | → `AreaTolerancePreset[]` |

Open to the same callers as `/v1/compute` (`require_compute`, including the anonymous demo); no
plan gating (CSV is generated client-side).

## Validation evidence

* [`engine/tests/test_parcels.py`](../engine/tests/test_parcels.py): rectangle/triangle tables
  and centroid (also at ΕΓΣΑ87 magnitudes), orientation, cleaning and every validation issue; arcs
  against analytic truths — circle from a square with four arcs (πR², 2πR, centre; 10⁻¹⁴ relative
  at a local origin), half disc (area and centroid 4R/3π), inward arc, semicircle on a diameter,
  major-arc "pacman" (¾πR²); every tolerance rule including the cadastral worked example and the
  7 % cap; presets; every `PARCEL_*` code has a Greek template.
* [`engine/tests/test_parcels_subdivide.py`](../engine/tests/test_parcels_subdivide.py):
  hand-computed cuts (rectangle, trapezoid quadratic `100h − h²/2 = 1000`, cut from the short
  side, perpendicular from either end, triangle pivot splitting the opposite side 1:3, pivot fan
  over several sides, pivot by coordinates), clockwise input, ratios, remainder rules, frontage,
  naming; non-convex refusal (U-shape: 4 crossings) and acceptance below the notch, pivot leaving
  the parcel; 120 random convex polygons at ΕΓΣΑ87 magnitudes × 3 methods, each part checked by an
  independent **exact rational (Fraction) shoelace** to ≤ 10⁻⁶ m², parts summing to the parcel,
  new points on the original boundary, cut lines parallel/perpendicular to the side.
* [`engine/tests/test_parcels_merge.py`](../engine/tests/test_parcels_merge.py): two rectangles,
  mixed orientation with 0.4 mm snapping, T-junctions, partially shared sides, not adjacent,
  point contact, hole (3×3 ring), overlap, subdivide-then-merge restores the area.
* [`engine/tests/test_parcels_coverage.py`](../engine/tests/test_parcels_coverage.py): every
  subdivision method covers its outline with exact matching and keeps original coordinates bit
  for bit; 2 mm sliver gap, overlap, part outside, uncovered corner.
* [`api/tests/test_parcels_api.py`](../api/tests/test_parcels_api.py): every route, issues in
  200 responses, 422 on NaN / out-of-range / too many vertices / bad radius / limits.
* [`web/src/lib/parcelsApi.test.ts`](../web/src/lib/parcelsApi.test.ts): tolerance mirror
  (worked example, cap), presets mirror, part-list parsing, CSV tables, SVG framing.

## Limitations and dependencies

* **Rural U0 to be confirmed** by the owner (2.00 m ΦΕΚ vs 2.50 m ΔΓΜ guide). Both presets carry
  `to_be_confirmed`.
* In the comparison, E is the reference area of each row and Π the surveyed perimeter; confirm
  this reading of the ΦΕΚ formula (E could also be read as the surveyed area).
* Subdivision and merge need straight sides; arcs must be replaced by chords first.
* Pivot cuts require the pivot on the boundary (interior pivots are not monotone).
* Subdivision refuses non-convex cases where the cut line crosses the boundary more than twice;
  choose another side or method (no automatic multi-piece handling).
* The web presets are a copy of the engine list (`parcelsApi.ts`): keep both in sync.
* No DXF/PDF output yet (CSV only); the ΔΓΜ feature is expected to build the drawing on top of
  `analyze_parcel`, `subdivide`, `merge_parcels` / `union_boundary` and `check_coverage`.
