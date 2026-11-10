# Web app (`web/`)

React single-page app for ATSurvey: projects, raw-file import, live computation on the
engine API, map visualisation and exports. Greek is the default language, English second.

## Stack

| Concern | Choice |
|---|---|
| Build | Vite 8 + React 19 + TypeScript (strict) |
| Routing / data | TanStack Router (code-based routes) + TanStack Query |
| Styling | Tailwind CSS v4 driven entirely by design tokens (`src/styles/tokens.css`, generated from `design/tokens.json`) |
| UI primitives | Local shadcn-style components in `src/components/ui` on Radix (`radix-ui`), `sonner` toasts, `cmdk` command palette, `lucide-react` icons |
| Grids | `@glideapps/glide-data-grid` (canvas; paste ranges from Excel, fill handle, 100k rows) |
| Map | `maplibre-gl` 6 + `proj4` (EGSA87 ⇄ WGS84) |
| Auth / DB | `@supabase/supabase-js` v2 |
| i18n | `i18next` + `react-i18next` (`src/locales/el.ts`, `en.ts`) |
| Font | IBM Plex Sans (latin + greek, 400/500/600) via `@fontsource/ibm-plex-sans` |
| Tests | Vitest (`src/**/*.test.ts`) |

## Run locally

```bash
# 1. engine API (from repo root)
uv run --package atsurvey-api uvicorn atsurvey_api.main:app --port 8000
# 2. web
cd web
pnpm install
cp .env.example .env.local   # optional: Supabase keys
pnpm dev                      # http://localhost:5173
```

Without Supabase variables the app runs in **demo-only mode**: the sign-in form is hidden and
"Δοκιμή χωρίς λογαριασμό" opens a local workspace. Without a token the API treats calls as
anonymous (parse/compute/suggest work, exports limited to CSV).

Scripts: `pnpm dev`, `pnpm build` (`tsc -b && vite build`), `pnpm typecheck`, `pnpm test`, `pnpm preview`.

### Environment variables

| Variable | Meaning |
|---|---|
| `VITE_API_URL` | Engine API base URL (default `http://localhost:8000`) |
| `VITE_SUPABASE_URL` | Hosted Supabase project URL (EU). Empty → demo-only |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon key |
| `VITE_PADDLE_CLIENT_TOKEN` | Paddle client-side token (`test_…` → sandbox). Empty → billing page shows "not configured" |
| `VITE_PADDLE_PRICE_MONTHLY` / `VITE_PADDLE_PRICE_YEARLY` | Paddle price ids for the Pro plan (either or both) |

## Structure

```
src/
  app/            App providers + router (/ landing, /login, /account, /billing, /projects, /p/$projectId?section=…)
  components/     shell pieces (Logo, UserMenu, CommandPalette) and ui/ primitives
  data/           ProjectStore interface, LocalStore (demo), SupabaseStore, sample dataset, session
  features/
    landing/      public landing page (hero composition, features, pricing, FAQ)
    auth/         sign-in page (magic link, password, Google) + demo entry
    account/      account (profile, language, theme) and billing (plan, Paddle checkout) pages
    projects/     project list, create/rename/delete
    workspace/    WorkspacePage, useWorkspace (state, autosave, live compute), sections/, dialogs/, map/, grid/
  lib/            types + cogoTypes (mirrors of engine models), api client (+ cogo), apiErrors,
                  angles, geometry, leveling, linework, linePalette, runDiff, proj, tokens, theme, i18n, utils
  locales/        el.ts / en.ts, plus extra.el.ts / extra.en.ts (night-1 features, deep-merged by lib/i18n.ts;
                  extra.en.ts is typed against extra.el.ts so a missing key fails `tsc`)
  styles/         tokens.css — GENERATED, do not edit
```

## Design tokens and theming

* `src/styles/tokens.css` is generated from `design/tokens.json` (`scripts/build_tokens.py`).
  It defines colour, typography, radius, shadow, spacing, motion and layout variables for light,
  dark (`[data-theme="dark"]`) and system preference.
* `src/index.css` imports it first and maps tokens into Tailwind with `@theme inline`; Tailwind's
  default palette, fonts, radii, shadows and font sizes are reset, so only token utilities exist:
  `bg-bg`, `bg-surface`, `bg-surface-raised`, `bg-surface-sunken`, `text-fg`, `text-muted`,
  `text-subtle`, `border-border`, `border-border-strong`, `bg-accent`, `text-accent-contrast`,
  `bg-accent-subtle`, `text-success|warning|danger` (+ `-subtle` backgrounds), `bg-point-*`,
  `rounded-sm…xl`, `shadow-sm|md|lg`, `text-xs…3xl`, `h-(--topbar-height)`, `w-(--sidebar-width)`,
  `z-(--z-modal)`.
* Canvas/WebGL renderers (Glide grid, MapLibre) cannot read CSS variables, so `src/lib/tokens.ts`
  resolves them with `getComputedStyle` (normalised to `rgb()` through a 1-px canvas) and
  `useTokens()` recomputes on theme change.
* Theme = `data-theme` attribute on `<html>` (`src/lib/theme.ts`); an inline script in
  `index.html` sets it before first paint from `localStorage["ats-theme"]` or the OS preference.
* Grad values are shown with a plain `g` suffix (IBM Plex has no `ᵍ` glyph).

## Data layer

`src/data/store.ts` defines `ProjectStore`; the workspace only talks to this interface.

* **SupabaseStore** — tables and RPCs from `docs/contracts.md`. Writes are upserts by id followed by
  deleting rows of the project that no longer exist. Raw files are uploaded to the private bucket
  `raw-files` at `{workspace_id}/{project_id}/{uuid}-{filename}` and recorded in `raw_files`.
  Saved computations use `rpc('save_computation_run', {p_project_id, p_result, p_settings})`.
  A 4th project on the free plan raises `project_limit_reached` → upgrade prompt.
* **LocalStore** — `localStorage` (keys `ats:projects`, `ats:project:<id>`, `ats:run:<id>`), used in demo mode.
* `toProjectInput()` strips UI/DB-only fields before calling the engine (the engine models forbid extras).

All angles are stored and sent in **radians**; the UI converts to the project unit
(`gon` default, `deg`, `dms`) in `src/lib/angles.ts`.

### Workspace state (`useWorkspace.tsx`)

* Holds a working copy of the project; edits are saved debounced (700 ms) per collection.
* **Live compute**: the clean `ProjectInput` is hashed; when it changes and *Auto* is on, the API is
  called after 400 ms (previous request aborted). `⌘↵` computes manually; "Save result" persists a run.
* Selection is shared between tables, computation sheets and the map.

## Screens

* **Auth** — magic link, email/password, Google OAuth; "try without account" demo entry.
* **Projects** — cards with counts, search, create (name, description, angle unit), rename, delete; "open example" seeds the demo dataset.
* **Workspace** — top bar (status pill, import, compute + auto toggle, save run, export, settings, map toggle) and a
  sidebar in four groups (model: `features/workspace/sections.ts`, icons: `navigation.tsx`):
  * **Δεδομένα**: control points (Excel paste, CSV import, duplicate highlighting), observations (setups list +
    editable grid, face I/II), traverses (route editor, kind/closure options, server suggestions), levelling;
  * **Υπολογισμοί**: coordinates, adjustment, lines, computation sheets, checks (issues with navigation), history;
  * **Εφαρμογές**: Ιδιοκτησίες, Κτηματολόγιο (ΔΓΜ), Ανάγλυφο, Χαράξεις;
  * **Εργαλεία**: Γεωμετρικοί υπολογισμοί (COGO), Συστήματα συντεταγμένων, Σχεδιασμός δικτύου, Έλεγχοι οργάνων.

  Applications and tools are **module pages**: `MODULE_TOOLS` lists each page's tabs in order,
  `sections/modules/index.tsx` loads each page's tabs lazily (one chunk per feature) and refuses a page whose tabs
  drift from that list (`modules.test.ts` loads every page). The open tab is in the URL
  (`/p/<id>?section=parcels&tool=parcelSubdivide`, validated in `app/router.tsx`; `?section=tools` is an alias of
  `cogo`). `⌘K` offers every page and every tab. **Adding a tool**: export a `ToolEntry` from its feature folder,
  add its id to `MODULE_TOOLS`, add `tools.tabs.<id>` / `tools.desc.<id>` in both languages (`navigation.test.ts`
  fails otherwise).
* **Map dock** (`map/MapDock.tsx`) — beside the page on wide screens, below it on narrow ones, resizable. Shown or
  hidden **per page**: `MAP_DEFAULT` (on for data/results pages; off for applications, tools, levelling, sheets,
  history), overridden by the user's toggle for that page (`localStorage["ats-map-pages"]`). Closed, a slim
  «Χάρτης» rail reopens it, with a dot when the current tool has drawn geometry. A tool that needs the map calls
  `ws.revealMap()` (point picking, contours, ellipse scale); that lasts until the page or tab changes and is not
  remembered; a reveal from a page already left is ignored. Hiding the map cancels point picking. Once opened the
  map stays mounted while hidden, so zoom and position survive page changes.
* **Map** — points by kind, labels (name, optional Z) on a canvas overlay, traverse polylines, hover card,
  click-to-select, measure distance/azimuth between two points, EGSA87 cursor coordinates, adaptive EGSA87 grid
  (default) or OpenStreetMap / satellite basemaps, graceful message when WebGL is unavailable.
* **Dialogs** — import (drag & drop, format detection, per-file preview and warnings), export (plan-aware formats;
  HTTP 402 → upgrade hint), settings (reductions, tolerances, angle unit).
* **Command palette** — `⌘K` (every page and every tool tab); shortcuts `⌘↵` compute, `⌘I` import, `⌘E` export, `⌘⇧M`
  toggle the map on the current page.

## Demo dataset

`src/data/sample.ts` builds a deterministic EGSA87 link traverse near Athens (T1-T2-S1-S2-S3-T3-T4, 3 new
stations, 15 detail points). Observations are synthesised from true coordinates with the engine's reduction
model (EGSA87 Simpson line scale, elevation factor, curvature & refraction) plus seeded noise, faces I and II.
`sample.test.ts` independently recomputes the traverse and checks closure (< 25 cc, < 2 cm) and station
accuracy (< 15 mm).

## Feature sections (night 1)

All lazily loaded (`WorkspacePage` → `React.lazy`). Sidebar groups: see *Workspace* above.

| Section | What it does | API |
|---|---|---|
| Συνόρθωση (`adjustment`) | Turns on least squares (`settings.adjustment.method`), shows σ₀ and the χ² global test (low σ₀ is a neutral note, high is an error), observations with residual / w / redundancy (sortable by \|w\|), the suspect observation with one-click exclusion (sets `Observation.excluded`, undoable), point σX/σY/σZ and 95 % ellipse axes, and the map ellipse exaggeration (×1 … ×5000) | `/v1/compute` |
| Γραμμές (`linework`) | Feature codes detected from detail points (chips with counts) → `settings.linework.line_codes`; start/close/end control words; per-code totals and the list of lines with length and closed area. Colours come from tokens via `lib/linePalette.ts` (stable alphabetical assignment) | `/v1/compute` |
| Γεωμετρικοί υπολογισμοί (`cogo`) | Inverse, polar, intersections (angles / distances / lines), resection, chainage/offset (quick area moved to Ιδιοκτησίες, Helmert/affine to Συστήματα συντεταγμένων, single-point stakeout to Χαράξεις). Point inputs accept a project point name (autocomplete), typed `X Y [Z]`, or a click on the map (crosshair button → `ws.revealMap()` + `ws.setPick`). Inputs/results are drawn on the map (`ws.setOverlay`) and framed automatically; results can be added as control points with code `COGO` (undoable). Stakeout table downloads as CSV | `/v1/cogo/*` |
| Χωροστάθμηση (`leveling`) | Benchmarks + readings grids (BS/FS/IS, paste from Excel), tolerances and distribution, results with corrections, tolerance pill, CSV of heights, "update Z of control points". Stored in `projects.extras.leveling` | `/v1/leveling` |
| Ιστορικό (`runs`) | Saved runs (`computation_runs` / LocalStore keeps the last 10), open a run read-only (banner + "back to current"), compare any two runs or a run with the live result: ΔX/ΔY/ΔZ/Δxy per point, threshold highlighting, max / RMS | — |

Other additions: landing page at `/` (sign-in moved to `/login`), account and billing pages, undo/redo
(⌘Z / ⇧⌘Z, toolbar buttons; snapshots of control points, setups, traverses, settings and extras, coalesced
within 600 ms), keyboard-shortcut dialog (`?`), map point search, label toggles (names / Z / codes), polygon
area measuring, PNG export (map + labels composited), fullscreen, new export formats (LandXML, KML, GeoJSON)
and DXF ellipse exaggeration, friendly toasts for HTTP 429 (with Retry-After), 413 and 503.

Endpoints missing on an older API degrade gracefully: tools show "not available on this server yet" (404/405/501).

## End-to-end smoke test

`web/e2e/smoke.cjs` drives the demo flow in Chromium (Playwright) and fails on any broken step:
landing renders, demo project computes through the API, the map canvas renders, a CSV observation file
imports, the CSV export downloads, COGO inverse and levelling compute (skipped if the API lacks them),
field-code lines are built, the least-squares section appears, and no page errors are logged.

```bash
uv run --package atsurvey-api uvicorn atsurvey_api.main:app --port 8000   # repo root
cd web && pnpm build && pnpm preview &                                     # :4173
pnpm e2e                         # SCREENSHOTS=/some/dir pnpm e2e  to keep screenshots
```

## Deploy (Cloudflare Pages)

* Build command: `pnpm install --frozen-lockfile && pnpm build` · root directory: `web` · output: `dist`
* Environment: `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
* SPA fallback: `public/_redirects` contains `/* /index.html 200`.
* Add the Pages domain to the API's CORS origins and to Supabase Auth → URL configuration (site URL and redirect URLs).
