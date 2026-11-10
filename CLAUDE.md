# ATSurvey — notes for Claude Code

Web app for Greek surveyors (B2C/prosumer): traverses, detail surveys, levelling, COGO,
least-squares adjustment, projects, exports (CSV, XLSX, SHP, DXF, PDF, LandXML, KML, GeoJSON).
The owner is a surveyor (not practising); existing users rely on his Excel workbooks, which are
the reference the engine must reproduce.

## Working with the owner
* **Always respond in English** (data, UI strings and point names are often Greek).
* Be a direct, critical partner: question assumptions, flag blind spots, don't just agree.
* Proceed without asking permission for routine work; commit and push when a piece is done.

## Layout
```
engine/   Python package `atsurvey`: pure computations, parsers, exports (pydantic, numpy)
api/      FastAPI `atsurvey_api`: stateless, verifies Supabase JWTs, plan-gated exports
web/      Vite + React 19 + TS, TanStack Router/Query, Tailwind v4, Glide grid, MapLibre, i18n el/en
supabase/ migrations (RLS, roles, storage, audit), edge functions (paddle-webhook, delete-account,
          storage-janitor), SQL tests
deploy/   Docker Compose + Caddy for the Hetzner VM
design/   tokens.json → scripts/build_tokens.py (palette TBD, font IBM Plex Sans)
docs/     ALL documentation lives here; index in docs/README.md. Update docs with code.
          docs/features.md is the feature catalogue: EVERY new or changed feature gets an entry
          (what, where, status, docs link) and a changelog line, in the same commit.
```

## Run and check
```bash
bash scripts/dev.sh                 # whole stack: local Supabase (Docker), API :8000, web :5173
                                    # sign-up e-mails → Mailpit http://127.0.0.1:54324
uv run python scripts/seed_users.py # dummy users (free/pro/team) in LOCAL Supabase, see docs/local-setup.md
uv run pytest                       # engine + API (pyproject already passes -q; don't add another)
uv run ruff check engine api && uv run ruff format --check engine api && uv run pyright
cd web && pnpm typecheck && pnpm test && pnpm build
uv run python scripts/check_secrets.py && uv run python scripts/check_csp.py
bash supabase/tests/run.sh          # migrations + RLS tests (needs local Postgres + PostGIS)
bash supabase/tests/run_in_supabase.sh  # same tests inside the local Supabase container (macOS)
node --test supabase/functions/*/*_test.ts  # edge function unit tests
```
Chain gates with `&&` before `git commit` so a failure stops the commit.

## Engine conventions (see docs/engine.md, docs/numerics.md)
* x = Easting, y = Northing, metres, ΕΓΣΑ87 (EPSG:2100). Angles are **radians** internally;
  gon/cc/DMS only at the edges (parsers, UI, exports). `hz` is a circle reading, not an angle.
* float64 with compensated sums (`math.fsum`), **no intermediate rounding** (proven to nm level
  against Decimal). Rounding is for display only.
* Problems are reported as `Issue`s with stable codes; Greek templates in `core/messages.py`,
  mirrored in the web app. Add both when adding a code.
* Validation cases from the workbooks: `engine/tests/fixtures/excel/*.json`
  (`scripts/excel_cases.py`), results and workbook errors in docs/validation.md.

## Gotchas already learned the hard way
* Every id stored in Supabase must be a UUID (`uid()` in web/src/lib/utils.ts). Demo mode
  (LocalStore) accepts anything, so only a real-Supabase run catches this.
* Supabase CLI v2 and new hosted projects sign user tokens with **ES256** (JWKS); legacy HS256
  secret may also exist. `api/auth.py` picks the key type from the header — never verify one
  algorithm with the other key type.
* API tests ignore the repo `.env` (`api/tests/conftest.py`); keep them hermetic.
* Local Supabase is Postgres 17 (`supabase/config.toml`), same as hosted.
* New tables/functions in `public` get grants for anon/authenticated by default (Supabase default
  privileges): always `revoke` explicitly; a CHECK that evaluates to null passes (use coalesce).
* Roles: owner/admin/member write, viewer reads (`can_write_project`); project delete is
  owner/admin; moves need owner/admin on both workspaces. Storage access follows the project
  segment of the path. Audit events are append-only; add a trigger/`audit()` call for new actions.
* Anything that passes in demo mode still needs the signed-in flow against local Supabase.

## Open items (docs/PLAN.md has the full list)
* Parsers (Leica GSI, Trimble JobXML/RW5, Nikon RAW, LandXML, Topcon) were built from format
  specs and synthetic files: **validate on real instrument exports** before launch.
* Tolerance table: sloped 1/10000 constant (0.3 m) < 1/5000 (0.4 m) looks like a workbook copy
  error; awaiting the owner's confirmation.
* Surveying tools (parcels, ΔΓΜ, surfaces, setout, analysis, instruments, coords) are blocked on
  owner input listed as D1–D10 in docs/science-roadmap.md. HEPOS grids must NEVER be committed
  (licence); they are mounted via `ATSURVEY_HEPOS_GRID_DIR`. A new tool tab is a `ToolEntry` +
  its id in `MODULE_TOOLS` (web/src/features/workspace/sections.ts) + `tools.tabs/desc.<id>` in
  locales/<pkg>.{el,en}.ts; navigation.test.ts / modules.test.ts fail if any piece is missing.
* Map visibility is per page (`MAP_DEFAULT` in sections.ts + the user's toggle). Tools that need the
  map call `ws.revealMap()`, never `setMapVisible` (that is the user's remembered choice).
* Hosted Supabase (Frankfurt), custom SMTP, domain + Hetzner deploy (docs/deploy.md), Paddle.
* Colour palette not chosen yet: change design/tokens.json only, never hard-code colours.
