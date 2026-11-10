# Surfaces (Ανάγλυφο): TIN, contours, heights, volumes, profiles

Code: [`engine/src/atsurvey/core/surfaces/`](../engine/src/atsurvey/core/surfaces) ·
API: [`api/src/atsurvey_api/routers/surfaces.py`](../api/src/atsurvey_api/routers/surfaces.py) ·
Web: Tools → **Ανάγλυφο** ([`tools/surfaces/`](../web/src/features/workspace/sections/tools/surfaces),
client [`lib/surfacesApi.ts`](../web/src/lib/surfacesApi.ts), map layer
[`map/contoursOverlay.ts`](../web/src/features/workspace/map/contoursOverlay.ts)).

Why: Greek building permits need the natural ground level (φυσικό έδαφος) at building corners and
contours (ισοϋψείς) on sloping plots; contractors need cut/fill volumes; roads and walls need
profiles and cross-sections.

## What it does

| Tab | Output |
|---|---|
| Επιφάνεια & ισοϋψείς | TIN statistics (vertices, triangles, z range, plan and sloped area), contours at an interval with base height and index contour every N, shown on the map (toggle in the map layer menu, index contours labelled), DXF / CSV |
| Υψόμετρα σημείων | Height of any list of points (project names or typed coordinates, e.g. building corners), "outside" flag, CSV / DXF |
| Όγκοι | Cut, fill, net, cut/fill plan areas against a horizontal level or a second surface, CSV |
| Μηκοτομή & διατομές | Long profile along a polyline (station at every TIN edge crossing), cross-sections at an interval and half-width, SVG charts, DXF drawing / CSV |

All four tabs share the **surface settings** (collapsible panel, kept per project for the session):
point kinds (control / traverse / detail), "only codes" and "exclude codes", breaklines from
field-coded line work (by line code), an optional boundary polygon and the maximum border edge.
Points without a height are left out and reported.

## Method

Everything runs in float64 in local coordinates (relative to the mean of the points), so
ΕΓΣΑ87 magnitudes cost no precision. Sums use `math.fsum`.

1. **Points.** Points closer than `duplicate_tolerance` (default 1 mm) in plan are merged with
   a k-d tree + connected components; the first is kept. Height spreads > 1 cm are a warning
   (`SURF_DUPLICATE_Z`): a TIN cannot represent a vertical step.
2. **Delaunay triangulation** with Qhull (`scipy.spatial.Delaunay`; Barber, Dobkin & Huhdanpaa
   1996). Fewer than 3 points or collinear points → error.
3. **Breaklines** (constrained Delaunay) by edge flipping, **Sloan (1993)**, *A fast algorithm for
   generating constrained Delaunay triangulations*, Computers & Structures 47(3): the crossed
   edges are collected by walking from the first vertex; convex quadrilaterals are flipped until
   the segment is an edge; Lawson swaps restore the Delaunay property on the new edges, never
   across a constrained edge. A segment through an existing vertex is split there. A segment
   that crosses an earlier breakline is skipped (`SURF_BREAKLINE_CROSSING`), because its crossing
   point would need a height from two lines. Predicates (`orient`, `incircle`) are exact in sign:
   float filter with an error bound, `Fraction` fallback (after Shewchuk 1997).
4. **Trimming** (`max_edge`): triangles on the current border whose border edge is longer than
   the limit are peeled repeatedly (χ-shape idea, Duckham et al. 2008). Interior triangles are
   never removed, so no holes appear.
5. **Boundary** (exact clip): the polygon is triangulated (constrained Delaunay of its vertices,
   inside triangles kept; a self-intersecting polygon is refused). TIN triangles that cannot touch
   the boundary are kept or dropped by a centroid test; the others are intersected with the
   boundary triangles (vectorised Sutherland–Hodgman), fan-triangulated and welded (1 µm). New
   vertices take their height from the plane of their triangle, so the clipped surface is the
   **same** piecewise-linear surface. Boundary area not covered by data → `SURF_BOUNDARY_PARTIAL`.
6. **Height at a point**: the containing triangle is found via a uniform grid index and the
   height is its plane, z = a·x + b·y + c (= barycentric interpolation). Continuous on shared
   edges and vertices. Outside → `null` + `SURF_OUTSIDE`.
7. **Contours** (marching triangles): for level L, an edge with one end `z ≥ L` and the other
   `z < L` is crossed at the linear interpolation point. Counting `z = L` as "above" is a symbolic
   perturbation: each triangle has 0 or 2 crossed edges, lines never branch and vertices exactly
   on a level need no special case. Crossings are identified by (level, TIN edge), so chaining is
   topological (closed loops close exactly). Lines run with **higher ground on the left** (hills
   counter-clockwise). Levels are `base + k·interval` (computed directly, never accumulated);
   index contour when `k mod N = 0`. **No smoothing**: the lines are the exact contours of the
   TIN. Flat areas exactly at a level draw their line at the lower border (e.g. a flat summit at
   an exact level produces no line).
8. **Volumes** (exact prisms, no grid): on each triangle — or for two surfaces each polygon of
   their exact overlay (every triangle of the first clipped by the candidate triangles of the
   second) — d = z_surface − z_reference is linear. A half-plane clip splits it at d = 0 and
   cut = ∫max(d,0)dA, fill = ∫max(−d,0)dA are evaluated exactly with ∫f dA = A·(f₀+f₁+f₂)/3 over a
   fan. Sign: **cut** where the (first/existing) surface is above the reference, **fill** below,
   **net = cut − fill**. Two surfaces are compared only where both exist (`SURF_VOLUME_PARTIAL`
   reports the rest); the boundary applies to both.
9. **Profiles**: each alignment segment is clipped against candidate triangles (Cyrus–Beck);
   entry/exit parameters are the TIN edge crossings, so the stations describe the ground line
   exactly. Gaps outside the surface start a new `run` (`SURF_PROFILE_GAP`). Cross-sections at
   `0, I, 2I, …` and the end chainage, perpendicular to the segment they fall on (at a vertex:
   the following segment), offsets negative to the **left**.

## Files

* **DXF** (R2013, metres; Pro, same gating as `/v1/export`): contours as `LWPOLYLINE` with
  `elevation` = height on `ISOYPSES` / `ISOYPSES_KYRIES` (index), labels on `ISOYPSES_KEIMENO`
  along the line (index lines, or all lines when there are no index lines), optional TIN
  `3DFACE` on `TIN`, points on `TIN_SHMEIA`; heights as 3D `POINT` + label on `YPSOMETRA`;
  profile drawing (x = chainage, y = (z − datum) × vertical exaggeration, default 10) with ground
  line `MHKOTOMH_EDAFOS`, datum/band/ticks `MHKOTOMH_PLAISIO`, heights and chainages
  `MHKOTOMH_KEIMENO`, cross-sections below it on `DIATOMES_EDAFOS` (same exaggeration).
* **CSV** (UTF-8 with BOM, formula-injection guard): contours (line, z, index, closed, vertex,
  x, y), heights (name, x, y, z, inside), volumes (quantity, value, unit), profile (type,
  section_chainage, chainage_or_offset, x, y, z, run).

## API (`/v1/surfaces/*`, `require_compute`, ValueError → 422)

| Endpoint | Request → result |
|---|---|
| `POST /tin` | `{surface}` → stats, outline rings, merged groups, issues |
| `POST /contours` | `{surface, interval, base, index_every}` → levels, lines `{z, index, closed, points}` |
| `POST /heights` | `{surface, points[{name,x,y}]}` → rows `{name, x, y, z, inside}` |
| `POST /volume/level` | `{surface, level}` → `{cut, fill, net, cut_area, fill_area, area, method}` |
| `POST /volume/surfaces` | `{existing, design, boundary?}` → same |
| `POST /profile` | `{surface, alignment, section_interval?, half_width}` → stations, sections |
| `POST /export` | `{format: dxf|csv, content: contours|heights|volume|profile, …}` → file (402 when the plan lacks the format) |

`surface` = `{points[{name,x,y,z}], breaklines[{points: [names], closed}], boundary?, max_edge?,
duplicate_tolerance}`. Bounds: ≤ 50 000 points, ≤ 1 000 breaklines / 20 000 breakline vertices,
≤ 2 000 boundary vertices, ≤ 10 000 query points, ≤ 500 alignment vertices, ≤ 2 000
cross-sections, ≤ 2 000 contour levels and ≤ 1 000 000 contour vertices; coordinates |·| ≤ 10⁸,
heights |·| ≤ 20 000, finite numbers only. Computation runs in the guarded worker pool with the
compute timeout. Measured on a laptop with 50 000 random points (≈100 000 triangles): TIN
0.3 s, contours at 0.5 m 0.5 s, level volume with a 400-vertex boundary 0.4 s, surface vs
surface (50 000 + 30 000 points) 3.7 s, profile with 1 600 sections 0.6 s, 500 breakline
segments 0.9 s.

## Validation (engine/tests/test_surfaces*.py, api/tests/test_surfaces_api.py)

* Plane at ΕΓΣΑ87 magnitudes: plan area exact, sloped area = A·√(1+a²+b²) to 1e-12; contours
  straight, on the plane to 1e-9 m, ending on the border, one line per level, higher ground on
  the left; heights equal the plane to 1e-9 m (including on edges and vertices).
* Paraboloid hill: each inner level is one closed counter-clockwise loop with area πr² (2 %),
  levels reaching the border are open; a pyramid grid with many vertices exactly on integer
  levels gives one closed, non-degenerate loop per level.
* Volumes: ramp vs level (12 500 / 12 500 m³ exact), pyramid at four levels (similar-pyramid
  formulas, 1e-12), cone as polygonal pyramid (exact) and converging to πR²H/3 (0.1 %), tilted
  plane vs an independent 2000×2000 midpoint grid (1e-5), concave boundary (area × plane at
  centroid), two parallel planes from different point sets (2 m × area, 1e-11), crossing planes
  (cut = fill = 2 500 m³), partial overlap, boundary applied to both, disjoint → error.
* Profiles: chainage, station count = brute-force count of TIN edges crossed + vertices, heights
  on the plane; gaps; cross-section chainages, azimuth, left/right sign.
* Breaklines: ridge forced against Delaunay's choice; 50-segment random breakline on 600 points:
  all segments become edges, triangulation area and orientation preserved, every unconstrained
  edge passes the exact incircle test (constrained Delaunay); vertex-on-segment split; crossing
  breaklines rejected; unknown names reported.
* Degenerate input: < 3 points, collinear, coincident, regular grids (co-circular), duplicates,
  self-intersecting boundary, too many levels / sections, API bounds (413/422), plan gating (402).

## Limitations / open items

* Contours are not smoothed (deliberate: smoothing moves lines off the measured surface).
* Breaklines must connect existing surface points by name; crossing breaklines are skipped,
  not intersected. Breaklines typed as free coordinates are not supported yet.
* A boundary that is not a simple polygon is refused; holes (islands) are not supported.
* Surface-vs-surface volumes take the second surface from point codes or a pasted list;
  importing a design surface from LandXML/DXF is not implemented.
* No grid (DEM) export, no slope/aspect maps, no TIN editing (swap edge by hand).
* DXF profile drawings use one vertical exaggeration for profile and sections and a simple band
  (heights + chainages); layer names are Greeklish. Owner to confirm the drawing conventions
  (scales, band rows, layer names) expected by Greek authorities and offices.
* Validate on a real project against the owner's workbooks / CAD software output (e.g. contours
  and volumes from Civil 3D or a Greek CAD package) before launch.
