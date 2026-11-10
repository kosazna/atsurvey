# ATSurvey — features

What the application offers, for the product owner, developers and AI agents. Every feature has
an entry here; technical detail lives in the linked documents. **Rule:** a change that adds or
alters a feature updates this file in the same commit (see `CLAUDE.md`).

Status: ✅ available · 🧪 beta (works, needs real-world validation) · 🛠 backend only (no
screen yet) · 📋 planned (see [PLAN.md](PLAN.md))

## 1. Accounts and sign-in

| Feature | What it offers | Where | Status | Docs |
|---|---|---|---|---|
| Sign up / sign in | E-mail + password (10+ characters), magic link; e-mail confirmation required | `/login` | ✅ | [supabase.md](supabase.md) |
| Google sign-in | "Continue with Google"; the button appears only when Google is switched on in Supabase; same e-mail links to the existing account | `/login` | ✅ (needs the owner's Google OAuth client) | [supabase.md](supabase.md#google-sign-in) |
| Forgot password | E-mail link to `/reset-password`; same answer whether or not the account exists | `/login` → "Ξεχάσατε τον κωδικό;" | ✅ | [supabase.md](supabase.md) |
| Bot protection | Cloudflare Turnstile on sign-up, sign-in and reset, when configured | `/login` | ✅ (hosted setting) | [supabase.md](supabase.md) |
| Profile | Name, language (Ελληνικά / English), light/dark theme | `/account` | ✅ | [web.md](web.md) |
| Demo mode | Try everything without an account; data stays in the browser | `/login` → "Δοκιμή χωρίς λογαριασμό" | ✅ | [web.md](web.md) |
| Two-factor sign-in (TOTP) | Authenticator app codes (Google/Microsoft Authenticator, 1Password…). Once on, a password alone opens nothing: the database refuses every workspace to a session without the code. A team owner can require it for the whole team | Account → Security; code prompt after sign-in | ✅ | [security.md](security.md) |
| Change password / e-mail | Password change asks for an e-mailed code when the last sign-in is old; e-mail change is confirmed from both addresses | Account → Security | ✅ | [supabase.md](supabase.md) |
| Sign out everywhere | Ends every session on every device | Account → Security | ✅ | — |
| Export my data | One zip: every project as JSON (with saved runs) plus the original instrument files, built in the browser | Account → Security | ✅ | [security.md](security.md) |
| Delete my account | Erases the personal workspace, its projects, runs, files and audit history, then the account. Typed e-mail confirmation; needs a sign-in within 10 minutes (and the code, with two-factor on); blocked while the user alone owns a team that has other members | Account → Security | ✅ | [supabase.md](supabase.md#edge-function-delete-account) |
| Delete demo data | Removes all demo projects from this browser (shared computers) | user menu in demo mode | ✅ | — |

## 2. Workspaces, teams and roles

| Feature | What it offers | Where | Status | Docs |
|---|---|---|---|---|
| Personal workspace | Created at sign-up; holds the user's projects; cannot be shared away or orphaned | automatic | ✅ | [supabase.md](supabase.md) |
| Workspace switcher | Personal workspace and every team the user belongs to (with role); projects list per workspace | `/projects` header | ✅ | [web.md](web.md) |
| Team workspaces (Pro) | Shared projects for an office; create from the switcher ("Νέα ομάδα…") | `/projects`, `/team` | ✅ | [security.md](security.md) |
| Roles | **owner** (everything, incl. transfer/delete workspace, require two-factor), **admin** (members, invitations, move/delete projects), **member** (edit data, import, save runs), **viewer** (read and export only: clients, reviewers; the project page shows "Μόνο ανάγνωση") | `/team`; enforced in the database | ✅ | [security.md](security.md#controls-by-layer) |
| Invitations (consent) | Owner/admin invites an e-mail with a role; the person sees it on `/projects` after signing in with that confirmed e-mail and accepts or declines. No secret links; owners cannot add anyone directly. Owners invite admins; admins invite members/viewers; 7-day expiry; revocable | `/team` → Προσκλήσεις; banner on `/projects` | ✅ (e-mail notification 📋 with custom SMTP) | [supabase.md](supabase.md) |
| Members | Names, e-mails and two-factor status of fellow members (visible to members only); change role, remove, leave, transfer ownership | `/team` | ✅ | — |
| Workspace settings | Rename; require two-factor for everyone (owner, from a two-factor session); delete workspace (typed confirmation) | `/team` | ✅ | — |
| Move a project between workspaces | "Μετακίνηση σε…" in the project menu, only where the user is owner/admin on both sides; stored files follow the project | `/projects` card menu | ✅ | [security.md](security.md) |
| Activity log | Who created, renamed, archived, moved, deleted or exported a project; who was invited, joined, left or changed role; files, runs, two-factor setting. Owners/admins; nobody can edit or delete it | `/team` → Δραστηριότητα | ✅ | [security.md](security.md#controls-by-layer) |

## 3. Projects

| Feature | What it offers | Where | Status | Docs |
|---|---|---|---|---|
| Project list | Cards with search, create, rename, delete, open the example project | `/projects` | ✅ | [web.md](web.md) |
| Free-plan limit | 3 active projects (archived ones don't count); Pro unlimited | enforced in the database | ✅ | [supabase.md](supabase.md) |
| Autosave, undo/redo, keyboard shortcuts, ⌘K command palette | Saved/saving indicator, leave-page guard, `?` shows shortcuts | workspace | ✅ | [web.md](web.md) |
| Archive / restore | Archived projects leave the active list and stop counting towards the free-plan limit; restoring checks the limit again | card menu "Αρχειοθέτηση"; tab "Αρχειοθετημένα" | ✅ | [supabase.md](supabase.md) |
| Trash (30 days) | "Delete" moves a project to the trash (owner/admin), with Undo; trashed projects are read-only and free their plan slot; restore any time within 30 days, then they are purged with their files. "Delete forever" for owner/admin | tab "Κάδος" | ✅ | [security.md](security.md) |
| Duplicate project | Full copy (points, setups, observations, traverses, settings) in the same workspace; not the original files or runs; counts towards the plan limit | card menu "Αντίγραφο" | ✅ | — |
| New project with another's settings | Copy computation settings (reductions, tolerances, units) from an existing project | "Νέο έργο" → "Ρυθμίσεις από" | ✅ | — |
| Original files | The imported instrument files of a project, with size and date; download through a 60-second link | project → Επισκόπηση → "Πρωτότυπα αρχεία" | ✅ (signed in) | — |
| Named runs, delete runs | Give a saved run a name ("Τελική λύση"); delete runs (writers); everything else in a run stays immutable | project → Ιστορικό | ✅ | — |

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
  files: enforced by the database on every table and file, with 174 automated checks.
* **Least privilege inside a team:** viewers read only; members cannot delete or take projects
  away; only owners/admins move or delete them.
* **Accountability:** an activity log that nobody can edit or delete.
* **Erasure:** deleted projects stay 30 days in the trash, then are purged with their files;
  deleting an account removes everything that belonged only to that user.
* **Safe files:** private storage, 20 MB limit, survey file types only.
* **Hardened service:** strict web security headers (CSP), rate limits, size limits, signed
  tokens verified on every request, no data in logs. Details: [security.md](security.md).

## 9. Surveying tools (Greek practice)

Roadmap and dependencies: [science-roadmap.md](science-roadmap.md). Items marked ⛔ need input from
the owner or a third party.

| Feature | What it offers | Where | Status | Docs |
|---|---|---|---|---|
| Parcel area & comparison | Area/perimeter/centroid with circular arcs, coordinate & side tables (CSV), m² and στρέμματα; surveyed vs deed vs cadastral-diagram area against a stated tolerance rule (fixed, %, a+b√E, Cadastre U0·Π·(1+U0/√E) with presets and 7 % cap) | Tools → Ιδιοκτησίες → Εμβαδόν & σύγκριση; `/v1/parcels/compute`, `/compare`, `/tolerance-presets` | 🧪 (⛔ rural U0 2.00 vs 2.50 m to confirm) | [parcels.md](parcels.md) |
| Subdivision (κατάτμηση) | Cut by areas or ratios, parallel/perpendicular to a side or through a pivot; new points Ν1…; frontage; refuses unsafe non-convex cuts; exact-coverage check; add new points to the project | Tools → Ιδιοκτησίες → Κατάτμηση; `/v1/parcels/subdivide`, `/coverage` | ✅ | [parcels.md](parcels.md) |
| Merge (συνένωση) | 2–20 adjacent parcels with snapping and T-junctions; reports non-adjacent, point contact, holes, overlap | Tools → Ιδιοκτησίες → Συνένωση; `/v1/parcels/merge` | ✅ | [parcels.md](parcels.md) |
| Terrain model & contours | Delaunay TIN from project points (filter by kind/code), breaklines from coded lines, boundary clip, border trimming; contours with index lines on the map and in DXF/CSV | Tools → Ανάγλυφο → Επιφάνεια & ισοϋψείς; `/v1/surfaces/tin`, `/contours`, `/export` | 🧪 (validate on real projects) | [surfaces.md](surfaces.md) |
| Ground heights at points | Natural ground height (φυσικό έδαφος) at building corners or any point from the TIN | Tools → Ανάγλυφο → Υψόμετρα σημείων; `/v1/surfaces/heights` | ✅ | [surfaces.md](surfaces.md) |
| Cut/fill volumes | Exact prism volumes against a level or a second surface, cut/fill/net and areas, within a boundary | Tools → Ανάγλυφο → Όγκοι; `/v1/surfaces/volume/*` | ✅ | [surfaces.md](surfaces.md) |
| Profiles & cross-sections | Long profile at every TIN edge crossing, cross-sections at interval, charts, DXF/CSV | Tools → Ανάγλυφο → Μηκοτομή & διατομές; `/v1/surfaces/profile` | 🧪 (drawing conventions to confirm) | [surfaces.md](surfaces.md) |
| Batch setting out | Directions, distances, zenith, ΔE/ΔN/ΔZ from one station; backsight or azimuth; ΕΓΣΑ87 scale/height reduction; field order; DXF and paste input; CSV | Tools → Χαράξεις → Χάραξη σημείων; `/v1/setout/points` | ✅ | [setout.md](setout.md) |
| As-staked check | Design vs measured by name: ΔX/ΔY/ΔZ, radial, along/across a line, tolerance flags, max/RMS; CSV | Tools → Χαράξεις → Έλεγχος χάραξης; `/v1/setout/check` | ✅ | [setout.md](setout.md) |
| Road axis | PI method with R and clothoids (A or L); element and main-point tables, chainages; chainage/offset ↔ XY; stakeout every Δ m; parabolic vertical curves | Tools → Χαράξεις → Άξονας οδού; `/v1/setout/alignment*` | 🧪 (Greek main-point names to confirm) | [setout.md](setout.md) |
| Network pre-analysis | Expected σ, absolute/relative error ellipses, redundancy, Baarda MDB and external reliability of a planned network, from the project or by hand | Tools → Σχεδιασμός δικτύου → Προανάλυση; `/v1/analysis/preanalysis` | ✅ | [analysis.md](analysis.md) |
| Robust estimation | Optional IRLS (Huber or Danish) in the adjustment, weights per observation; off by default (results unchanged) | Adjustment → Εύρωστη εκτίμηση | ✅ | [adjustment.md](adjustment.md#robust-estimation) |
| Levelling network adjustment | Fixed or free datum, 1/L or 1/n weights, σH, χ² and w-tests with MDB, loop misclosures with tolerance, lines from the section's readings, heights → control points | Levelling → Δίκτυο; `/v1/leveling/network` | 🧪 (default σ values to confirm) | [instruments.md](instruments.md) |
| Instrument checks | Two-face test (c, i, trunnion), level two-peg test (Förstner/Kukkamäki/middle-and-end), EDM constant from a baseline; printable/CSV reports | Tools → Όργανα; `/v1/instruments/*` | ✅ | [instruments.md](instruments.md) |
| Coordinate conversion | ≤ 10 000 points between ΕΓΣΑ87, φλ (ΕΓΣΑ87/WGS84/old datum), UTM 34/35, TM3, Hatt; DMS or decimal; approximate datum shifts labelled; official HEPOS when grids are installed | Tools → Συστήματα; `/v1/coords/convert` | 🧪 (⛔ HEPOS grids licence, Hatt table, geoid, TM3 confirmation) | [coords.md](coords.md) |
| Point information | φ λ, scale factor, meridian convergence, combined factor, zone | Tools → Συστήματα → Στοιχεία σημείου; `/v1/coords/point-info` | ✅ | [coords.md](coords.md) |
| ΔΓΜ drafting (Διάγραμμα Γεωμετρικών Μεταβολών) | Deed ΔΓΜ (subdivision with the ΤΔ partition line clipped to PST_KAEK, merge) and correction ΔΓΜ / ΤΔΓΜ (A/Δ parts, change table ΤΜΗΜΑ/ΠΕΡΙΓΡΑΦΗ/ΕΜΒΑΔΟ/ΑΠΟ ΚΑΕΚ/ΣΕ ΚΑΕΚ, totals check); load the Κτηματογραφικό Διάγραμμα DXF; area and coordinate tables; Cadastre tolerance; DXF 2004 with the 27 Cadastre layers; SHA-512 and unsigned hash PDF for signing | Tools → ΔΓΜ Κτηματολογίου → Σύνταξη ΔΓΜ; `/v1/dgm/build`, `/kd`, `/export` (Pro), `/hash-pdf` | 🧪 (⛔ real ΚΔ DXF and one accepted submission, science-roadmap D6) | [dgm.md](dgm.md) |
| ΔΓΜ pre-submission check | Checks any DXF (also from CAD) against the Cadastre's rules: file name/size, version, layer names (Greek «Α» look-alikes), required layers per diagram type, Table I entities, MTEXT/blocks/hatches/xrefs, 2D, KAEK text inside its parcel, duplicates, overlaps, gaps, missing shared vertices, outline equality; each failure with layer, handle and coordinates. A pre-check: the Cadastre's system is authoritative | Tools → ΔΓΜ Κτηματολογίου → Έλεγχος DXF; `/v1/dgm/validate` | 🧪 | [dgm.md](dgm.md) |

## Changelog (for developers and agents)

* **2026-11-11: surveying tools wave 1.** Parallel build of parcels (`core/parcels*.py`),
  surfaces (`core/surfaces/`, adds scipy), setting out and road axis (`core/setout.py`,
  `core/alignment*.py`), pre-analysis and robust IRLS (`core/preanalysis*.py`, `adjust.py`,
  `models.py` additive), levelling network and instrument checks (`core/levelnet.py`,
  `core/instruments.py`, `_lsq.py`, `_loops.py`), coordinate systems (`core/coords/`), ΔΓΜ builder and validator (`core/dgm/`, adds shapely);
  routers `/v1/{parcels,dgm,surfaces,setout,analysis,instruments,coords}/*`, `/v1/leveling/network`; web Tools
  section grouped (`tools/registry.ts`, one group per feature, locales `<pkg>.{el,en}.ts` with
  their own `issues.codes`), contours overlay on the map, Δίκτυο mode in Levelling. Roadmap and
  dependencies: `docs/science-roadmap.md`.

* **2026-11-11: project lifecycle (security plan, phase 4).** Migration
  `20261111000007_lifecycle.sql`: `projects.deleted_at`, `trash_project` / `restore_project`
  (owner/admin, audited), `purge_trashed_projects` (janitor, 30 days), `duplicate_project`
  (security invoker), plan limit counts neither archived nor trashed and re-checks on restore,
  writes blocked in the trash, `computation_runs.label` (column-level update grant only). Web:
  `data/lifecycle.ts` (+ tests), `features/projects/ProjectShelves.tsx` (Archived / Trash tabs),
  card menu archive/duplicate, delete → trash with Undo, "settings from" on create,
  `sections/RawFilesCard.tsx`, `sections/RunLabel.tsx`, run delete; `ProjectStore.deleteRun /
  labelRun`; locales `lifecycle.*.ts`. Tests: 174 DB checks.

* **2026-11-11: team workspaces (security plan, phase 3).** Migration `20261111000006_teams.sql`:
  `workspace_invitations`, `invite_member` / `my_invitations` / `accept_invitation` /
  `decline_invitation` / `revoke_invitation`, `workspace_roster`, `my_workspaces`,
  `transfer_ownership`; direct `workspace_members` inserts removed (consent only). Web:
  `data/teams.ts` (+ tests), `data/useTeams.ts`, `components/WorkspaceSwitcher.tsx`,
  `features/projects/InvitationsBanner.tsx`, `features/team/*` (`/team`), viewer read-only mode
  (`WorkspaceProvider readOnly`), move-project menu, role-aware project actions, locales
  `teams.*.ts`. Store: `setWorkspace()`, `ProjectMeta.workspace_id`; **fixed** uploads into team
  projects (path used the personal workspace). Seed: viewer user, team project, pending invite.
  Tests: 159 DB checks.

* **2026-11-11: account security (security plan, phase 2).** Migration `20261111000005_mfa.sql`
  (`require_mfa`, `mfa_satisfied()` inside every access helper, owner+aal2 guard). Web:
  `features/account/security/*` (two-factor, password, e-mail, sessions, data export, delete),
  `features/auth/MfaChallenge.tsx` (root gate, session mode `mfa`), `ResetPasswordPage.tsx`,
  `components/Turnstile.tsx`, `lib/authProviders.ts` (Google button only when enabled),
  `lib/exportData.ts` (fflate), `lib/functions.ts`, locales `security.*.ts`. `delete-account`
  requires aal2 for two-factor users. Config: TOTP on, `jwt_expiry` 900, Google via
  `supabase/.env` (defaults) + `.env.local` (credentials). Chores: `marked` removed, Actions pinned
  to SHAs, `.github/dependabot.yml`, `/.well-known/security.txt`. Tests: 133 DB checks.

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
