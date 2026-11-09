# ATSurvey — plan and status

Goal: a paid web app for Greek surveyors that replaces Excel workbooks for traverse and
detail-point computations, with projects, accounts, a map and professional exports.

Decisions: [`adr/0001-architecture.md`](adr/0001-architecture.md) · interfaces: [`contracts.md`](contracts.md) ·
all docs: [`README.md`](README.md).

## Status

| Milestone | Scope | Status |
|---|---|---|
| M0 Foundations | Monorepo, uv workspace, CI, Docker, deploy stack, docs | ✅ done |
| M1 Engine | Reductions (EGSA87 k, height, curvature/refraction), face/round reduction, open/link/closed traverses (Bowditch), detail points, check shots, radiated stations, tolerances, issues (Greek), traverse suggestions | ✅ done — **awaiting validation against the Excel workbooks** |
| M2 Parsers | Leica GSI-8/16, Trimble JobXML, LandXML, Nikon RAW, Carlson RW5, CSV (Greek Excel style) | ✅ done — **awaiting real instrument files** |
| M3 Data platform | Supabase schema, RLS, storage, RPCs, plan limits | ✅ done (tested locally; not yet pushed to a hosted project) |
| M4 Outputs | CSV, Excel, Shapefile (EPSG:2100), DXF (blocks/attributes/layers by code), PDF report (Greek) | ✅ done |
| API | parse / compute / suggest / export, JWT, plan gating, anonymous demo | ✅ done |
| Web app | Auth, projects, import, grids, traverses + suggestions, results, map, export, settings, demo mode, el/en, dark mode | ✅ done — demo flow verified end-to-end; Supabase store not yet exercised against a live project |
| Design system | Tokens (`design/tokens.json`) for app and reports, IBM Plex Sans, minimal style | ✅ done — **palette to be chosen** |
| Night 1 — engine | Least-squares network adjustment (σ, error ellipses, χ² global test, Baarda w-test); COGO (inverse, polar, intersections, resection, area, Helmert/affine, chainage, stakeout); geometric levelling; field-code linework; LandXML/KML/GeoJSON exports; DXF point import; DXF error ellipses; report sections; float64 precision proof | ✅ done |
| Night 1 — security | Threat model, API hardening, export sanitisation, parser fuzzing, RLS re-review, CSP, supply-chain checks | see [security.md](security.md) |
| Night 1 — web | Landing page, least-squares UI, tools, levelling, linework, run history and comparison, map tools, account and billing | see [web.md](web.md) |
| M5 Launch | Paddle products, onboarding, landing page, legal, beta with Excel users | ⏳ next |

## Next steps

1. **Validate against the Excel workbooks**: see [validation.md](validation.md).
2. Choose the brand palette and edit [`design/tokens.json`](../design/tokens.json).
3. Create the hosted Supabase project and go live: [deploy.md](deploy.md).
4. Real instrument files from each family to harden the parsers ([formats.md](formats.md)).
5. Paddle products, landing page, legal pages, beta with the current Excel users.

## Known gaps / decisions to make

* **Tolerances**: defaults are generic placeholders (40 cc·√n, 2 cm + 5 cm·√km, 1:5000). Replace with
  the specification you work to (e.g. Ktimatologio technical specs) — they are per-project settings.
* **Parsers**: unit codes and record layouts follow the published formats; firmware quirks need real
  files. Nikon RAW and RW5 do not state their angle unit — taken from the project setting (gon).
* **Geoid**: heights are treated as orthometric; `geoid_undulation` is a single value per project.
* **Official transformations** (HEPOS/HTRS07 → ΕΓΣΑ87 grid, Hatt polynomials) — roadmap; local Helmert/affine from common points is available now.
* **Field codes → lines** in DXF, Cadastre deliverable templates — roadmap.
* **DWG** export via ODA — roadmap.
* **Cadastre orthophoto basemap** (WMS) — check whether it serves Web Mercator; OSM and Esri imagery are available now.
* **Glide Data Grid** declares React ≤ 18 as peer dependency; works on React 19 in testing — watch for a v7 release.
* **Map bundle** is ~1.2 MB (lazy-loaded); consider a lighter chunk split later.

## Roadmap after launch

1. Official HEPOS→ΕΓΣΑ87 and Hatt transformations, Ktimatologio deliverable templates
2. Team workspaces UI (schema and role guards are in place), DWG export
3. More instrument formats (Topcon GTS-7, Sokkia SDR33, South) once real samples exist
4. Parcel subdivision (κατάτμηση), curves/alignments, volumes from surfaces
