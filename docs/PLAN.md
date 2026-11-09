# ATSurvey — plan and status

Goal: a paid web app for Greek surveyors that replaces Excel workbooks for traverse and
detail-point computations, with projects, accounts, a map and professional exports.

Decisions are recorded in [`adr/0001-architecture.md`](adr/0001-architecture.md); interfaces in
[`contracts.md`](contracts.md).

## Status

| Milestone | Scope | Status |
|---|---|---|
| M0 Foundations | Monorepo, uv workspace, CI, Docker, deploy stack, docs | ✅ done |
| M1 Engine | Reductions (EGSA87 k, height, curvature/refraction), face/round reduction, open/link/closed traverses (Bowditch), detail points, check shots, radiated stations, tolerances, issues (Greek), traverse suggestions | ✅ done — **awaiting validation against the Excel workbooks** |
| M2 Parsers | Leica GSI-8/16, Trimble JobXML, LandXML, Nikon RAW, Carlson RW5, CSV (Greek Excel style) | ✅ done — **awaiting real instrument files** |
| M3 Data platform | Supabase schema, RLS, storage, RPCs, plan limits | ✅ done (tested locally; not yet pushed to a hosted project) |
| M4 Outputs | CSV, Excel, Shapefile (EPSG:2100), DXF (blocks/attributes/layers by code), PDF report (Greek) | ✅ done |
| API | parse / compute / suggest / export, JWT, plan gating, anonymous demo | ✅ done |
| Web app | Auth, projects, import, grids, traverses, results, map, export, settings, demo mode | see `web/README.md` |
| M5 Launch | Paddle products, onboarding, landing page, legal, beta with Excel users | ⏳ next |

## Validation with the Excel workbooks (next step)

1. Put each workbook's inputs (control points, observations, traverse definitions) into
   `engine/tests/fixtures/excel/<name>/` and its expected coordinates/misclosures alongside.
2. Pick the reduction settings that match the workbook. The legacy workbooks most likely use one
   scale factor and one mean height per traverse: `scale_mode="traverse_mean"`,
   `elevation_mode="traverse"`. Check whether they apply curvature/refraction.
3. Add a test per workbook asserting agreement to **0.1 mm / 0.1 cc**. Differences are either a
   workbook error or an engine error — resolve each explicitly.
4. Cross-check two cases with a third tool before treating Excel as the reference.

## Known gaps / decisions to make

* **Tolerances**: defaults are generic placeholders (40 cc·√n, 2 cm + 5 cm·√km, 1:5000). Replace with
  the specification you work to (e.g. Ktimatologio technical specs) — they are per-project settings.
* **Parsers**: unit codes and record layouts follow the published formats; firmware quirks need real
  files. Nikon RAW and RW5 do not state their angle unit — taken from the project setting (gon).
* **Geoid**: heights are treated as orthometric; `geoid_undulation` is a single value per project.
* **Least squares** network adjustment, error ellipses, blunder detection — roadmap.
* **Transformations** (HEPOS/HTRS07 → ΕΓΣΑ87, Hatt) — roadmap.
* **Field codes → lines** in DXF, Cadastre deliverable templates — roadmap.
* **DWG** export via ODA — roadmap.

## Roadmap after launch

1. Least-squares adjustment (traverse networks with nodes), statistics and error ellipses
2. Resection / intersection, Helmert & affine transformations, HEPOS→ΕΓΣΑ87
3. Field coding → polylines/layers in DXF, Ktimatologio templates
4. Team workspaces (schema already supports them), DWG, more instrument formats
