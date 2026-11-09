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

## Structure

```
src/
  app/            App providers + router (/, /projects, /p/$projectId?section=…)
  components/     shell pieces (Logo, UserMenu, CommandPalette) and ui/ primitives
  data/           ProjectStore interface, LocalStore (demo), SupabaseStore, sample dataset, session
  features/
    auth/         sign-in page (magic link, password, Google) + demo entry
    projects/     project list, create/rename/delete
    workspace/    WorkspacePage, useWorkspace (state, autosave, live compute), sections/, dialogs/, map/, grid/
  lib/            types (mirror of engine models), api client, angles, proj, tokens, theme, i18n, utils
  locales/        el.ts (source of truth for keys), en.ts
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
* **Workspace** — top bar (status pill, import, compute + auto toggle, save run, export, settings, map toggle); sections:
  overview, control points (Excel paste, CSV import, duplicate highlighting), observations (setups list + editable grid,
  face I/II shown), traverses (route editor with autocomplete, kind/closure options, server suggestions),
  coordinates (points / detail shots), computation sheets (misclosures vs tolerances, station and leg tables),
  checks (translated issues with navigation). Resizable map panel on the right (stacks below on small screens).
* **Map** — points by kind, labels (name, optional Z) on a canvas overlay, traverse polylines, hover card,
  click-to-select, measure distance/azimuth between two points, EGSA87 cursor coordinates, adaptive EGSA87 grid
  (default) or OpenStreetMap / satellite basemaps, graceful message when WebGL is unavailable.
* **Dialogs** — import (drag & drop, format detection, per-file preview and warnings), export (plan-aware formats;
  HTTP 402 → upgrade hint), settings (reductions, tolerances, angle unit).
* **Command palette** — `⌘K`; shortcuts `⌘↵` compute, `⌘I` import, `⌘E` export, `⌘⇧M` toggle map.

## Demo dataset

`src/data/sample.ts` builds a deterministic EGSA87 link traverse near Athens (T1-T2-S1-S2-S3-T3-T4, 3 new
stations, 15 detail points). Observations are synthesised from true coordinates with the engine's reduction
model (EGSA87 Simpson line scale, elevation factor, curvature & refraction) plus seeded noise, faces I and II.
`sample.test.ts` independently recomputes the traverse and checks closure (< 25 cc, < 2 cm) and station
accuracy (< 15 mm).

## End-to-end smoke test

`web/e2e/smoke.cjs` drives the demo flow in Chromium (Playwright) and fails on any broken step:
demo project computes through the API, the map canvas renders, a CSV observation file imports,
the CSV export downloads, and no page errors are logged.

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
