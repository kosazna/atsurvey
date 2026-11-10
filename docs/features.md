# ATSurvey — features

What the application offers, for the product owner, developers and AI agents. Every feature has
an entry here; technical detail lives in the linked documents. **Rule:** a change that adds or
alters a feature updates this file in the same commit (see `CLAUDE.md`).

Status: ✅ available · 🧪 beta (works, needs real-world validation) · 🛠 backend only (no
screen yet) · 📋 planned (see [PLAN.md](PLAN.md))

## 1. Accounts and sign-in

| Feature | What it offers | Where | Status | Docs |
|---|---|---|---|---|
| Sign up / sign in | E-mail + password (10+ characters), magic link, Google (when configured); e-mail confirmation required | `/login` | ✅ | [supabase.md](supabase.md) |
| Profile | Name, language (Ελληνικά / English), light/dark theme | `/account` | ✅ | [web.md](web.md) |
| Demo mode | Try everything without an account; data stays in the browser | `/login` → "Δοκιμή χωρίς λογαριασμό" | ✅ | [web.md](web.md) |
| Delete my account | Erases the personal workspace, its projects, runs, files and audit history, then the account. Needs a sign-in within the last 10 minutes; blocked while the user alone owns a team that has other members (they must hand it over first) | API ready (`delete-account`); button 📋 Phase 2 | 🛠 | [supabase.md](supabase.md#edge-function-delete-account) |
| Password reset / change, e-mail change, sign out everywhere, export my data | Self-service account security | Account → Security | 📋 Phase 2 | — |
| Two-factor sign-in (TOTP) | Optional for everyone; a team owner can require it for their team (enforced by the database) | Account → Security | 📋 Phase 2 | — |

## 2. Workspaces, teams and roles

| Feature | What it offers | Where | Status | Docs |
|---|---|---|---|---|
| Personal workspace | Created at sign-up; holds the user's projects; cannot be shared away or orphaned | automatic | ✅ | [supabase.md](supabase.md) |
| Team workspaces (Pro) | Shared projects for an office | database ready; screens 📋 Phase 3 | 🛠 | [security.md](security.md) |
| Roles | **owner** (everything, incl. ownership), **admin** (manage members, delete/move projects), **member** (edit project data, upload, save runs), **viewer** (read-only: clients, reviewers) | enforced in the database | 🛠 (UI 📋 Phase 3) | [security.md](security.md#controls-by-layer) |
| Move a project between workspaces | Only someone who is owner/admin in *both* workspaces; stored files follow the project | database ready | 🛠 | [security.md](security.md) |
| Invitations, member list with names, transfer ownership | Membership by invitation and consent only | — | 📋 Phase 3 | — |
| Activity log | Who created, renamed, archived, moved, deleted or exported a project; who joined, left or changed role; files uploaded/deleted; runs saved/deleted. Visible to owners/admins; cannot be edited or deleted by anyone | recorded now; viewer screen 📋 Phase 3 | 🛠 | [security.md](security.md#controls-by-layer) |

## 3. Projects

| Feature | What it offers | Where | Status | Docs |
|---|---|---|---|---|
| Project list | Cards with search, create, rename, delete, open the example project | `/projects` | ✅ | [web.md](web.md) |
| Free-plan limit | 3 active projects (archived ones don't count); Pro unlimited | enforced in the database | ✅ | [supabase.md](supabase.md) |
| Autosave, undo/redo, keyboard shortcuts, ⌘K command palette | Saved/saving indicator, leave-page guard, `?` shows shortcuts | workspace | ✅ | [web.md](web.md) |
| Archive / restore, trash (30 days), duplicate, new from another project's settings, download original files, name/delete runs | Project lifecycle | — | 📋 Phase 4 | — |

## 4. Importing field data

| Feature | What it offers | Where | Status | Docs |
|---|---|---|---|---|
| Instrument files | Leica GSI-8/16, Trimble JobXML, LandXML, Nikon RAW, Carlson RW5, CSV (Greek Excel style), DXF points (blocks with attributes, labelled POINTs) | Import dialog | 🧪 (built from format specs; validate with real exports) | [formats.md](formats.md) |
| Topcon GTS-7 | Parser | Import dialog | 🧪 beta | [formats.md](formats.md) |
| Original file kept | Every imported file is stored privately with its SHA-256; deleted with its project | automatic | ✅ (download 📋 Phase 4) | [security.md](security.md) |
| Paste from Excel | Control points and observations grids accept pasted ranges; fill handle | Control / Observations | ✅ | [web.md](web.md) |

## 5. Computations

| Feature | What it offers | Where | Status | Docs |
|---|---|---|---|---|
| Reductions | ΕΓΣΑ87 scale factor, height reduction, curvature/refraction, face/round reduction | Settings | ✅ (validate against workbooks) | [engine.md](engine.md) |
| Traverses | Open, link, closed (Bowditch); automatic traverse suggestions; tolerances with Greek presets | Traverses | ✅ | [engine.md](engine.md) |
| Detail points, check shots, radiated stations | | Results | ✅ | [engine.md](engine.md) |
| Least-squares network adjustment | σ₀, χ² global test, Baarda w-test, error ellipses, exclude suspect observations | Adjustment | ✅ | [adjustment.md](adjustment.md) |
| COGO tools | Inverse, polar, intersections, resection, area, Helmert/affine transformation, chainage/offset, stakeout | Tools | ✅ | [cogo.md](cogo.md) |
| Geometric levelling | Benchmarks, readings, misclosure, distribution | Levelling | ✅ | [cogo.md](cogo.md) |
| Field-code linework | Lines built from point codes, also written to DXF/Shapefile | Linework | ✅ | [engine.md](engine.md) |
| Issues | Every problem as a coded issue with a Greek message | Issues | ✅ | [engine.md](engine.md) |
| Precision | float64 with compensated sums, no intermediate rounding (proven to nm against Decimal) | engine | ✅ | [numerics.md](numerics.md) |

## 6. Results, map and history

| Feature | What it offers | Where | Status | Docs |
|---|---|---|---|---|
| Results grid | Computed points by kind | Results | ✅ | [web.md](web.md) |
| Map | Points and lines on OSM / Esri imagery; map tools | map panel | ✅ | [web.md](web.md) |
| Report sheets | Computation sheets in the app; PDF report (Greek) | Reports | ✅ | [engine.md](engine.md) |
| Run history and comparison | Saved runs (immutable), side-by-side ΔX/ΔY/ΔZ, max and RMS | Runs | ✅ | [web.md](web.md) |

## 7. Exports and plans

| Plan | Formats |
|---|---|
| Demo (no account) | CSV |
| Free | CSV, XLSX |
| Pro | + Shapefile (EPSG:2100), DXF (layers by code, blocks, error ellipses), PDF report, LandXML, KML, GeoJSON |

Spreadsheet exports are protected against formula injection. Signed-in exports of stored projects
are recorded in the workspace activity log. Payments (Paddle) are built but parked. Docs:
[api.md](api.md), [security.md](security.md).

## 8. Security and privacy (what users can rely on)

* **Isolation:** nobody outside a workspace can see or even detect its projects, members or
  files: enforced by the database on every table and file, with 123 automated checks.
* **Least privilege inside a team:** viewers read only; members cannot delete or take projects
  away; only owners/admins move or delete them.
* **Accountability:** an activity log that nobody can edit or delete.
* **Erasure:** deleting a project removes its files from storage; deleting an account removes
  everything that belonged only to that user.
* **Safe files:** private storage, 20 MB limit, survey file types only.
* **Hardened service:** strict web security headers (CSP), rate limits, size limits, signed
  tokens verified on every request, no data in logs. Details: [security.md](security.md).

## Changelog (for developers and agents)

* **2026-11-11: isolation and data removal (security plan, phase 1).** Migrations
  `20261111000001…4`: viewer role; write/delete/move rules; storage access by project, MIME
  allow-list, path-must-match-project constraint; `audit_events` + triggers + `log_export`;
  `storage_deletions` queue, `storage_orphans`, `purge_memberless_workspaces`,
  `delete_account_data`. Edge functions `delete-account`, `storage-janitor` (+ `_shared/`).
  API records exports (`api/src/atsurvey_api/audit.py`); web sends `project_id` with exports and
  an explicit upload content type (`web/src/lib/rawFiles.ts`). Tests: 123 DB checks,
  24 edge-function tests, API `test_audit.py`. Local runner `supabase/tests/run_in_supabase.sh`.
  Next: Phase 2 (account security UI, MFA), 3 (teams UI), 4 (project lifecycle), see
  [PLAN.md](PLAN.md).
* **2026-11-10: local stack and dummy users.** `scripts/seed_users.py`, password minimum 10,
  redirect allow-list ([local-setup.md](local-setup.md)).
