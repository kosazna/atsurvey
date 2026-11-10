# Development

## Repository layout

```
engine/      atsurvey: computation core, parsers, exports (Python)
api/         atsurvey-api: FastAPI service
web/         React app
supabase/    migrations, edge function, database tests
design/      tokens.json (design tokens source)
scripts/     build_tokens.py, build_report_fonts.py
deploy/      docker compose + Caddy for the Hetzner VM
docs/        all documentation (this folder)
```

## Prerequisites

* Python 3.13 and [uv](https://docs.astral.sh/uv/) (workspace with `engine` and `api`)
* Node 22.18+ and pnpm 10 (web)
* PostgreSQL 16 + PostGIS 3 for the database tests (`apt-get install postgresql-16 postgresql-16-postgis-3`)
* Docker (local Supabase via `npx supabase@2`; Postgres 17, same as hosted)

To run the whole app locally (Supabase in Docker, API, web): `bash scripts/dev.sh`, see
[local-setup.md](local-setup.md).

## Everyday commands

```bash
uv sync                                         # install engine + API (+ dev tools)
uv run pytest                                   # all Python tests
uv run ruff check engine api && uv run ruff format engine api
uv run pyright                                  # type check
uv run --package atsurvey-api uvicorn atsurvey_api.main:app --reload --port 8000

cd web && pnpm install && pnpm dev               # app on http://localhost:5173
pnpm typecheck && pnpm test && pnpm build
pnpm e2e                                         # needs API on :8000 and `pnpm preview` on :4173

bash supabase/tests/run.sh                       # migrations + RLS tests (66 checks)
node --test supabase/functions/paddle-webhook/signature_test.ts

uv run python scripts/build_tokens.py           # after editing design/tokens.json
```

## Tests

| Suite | What it proves |
|---|---|
| `engine/tests/test_traverse.py` | traverses close on perfect data (incl. randomised), misclosure sign and distribution, failure modes, legacy bug regressions |
| `engine/tests/test_detail_units.py` | detail points, check shots, radiated stations, units, azimuths on axes, EGSA87 scale factor |
| `engine/tests/test_suggest.py` | traverse suggestions compute cleanly |
| `engine/tests/test_formats.py` | each format round-trips to the true coordinates; XML attacks rejected |
| `engine/tests/test_exports.py` | every export reads back with its own library (ezdxf, pyshp, zip, pdftotext) |
| `engine/tests/test_excel_cases.py` | agreement with the reference workbooks ([validation.md](validation.md)) |
| `api/tests/test_api.py` | auth (valid, invalid, expired), plan gating, limits, uploads |
| `web/src/**/*.test.ts` (Vitest) | angle conversion/formatting, sample dataset closes |
| `web/e2e/smoke.cjs` (Playwright) | demo computes via the API, map renders, import, export download, no page errors |
| `supabase/tests/rls_test.sql` | isolation between users on every table and storage, plan limits, RPCs, role guards |

## CI

`.github/workflows/ci.yml` runs on every push and pull request:
1. Token sync check, ruff, pyright, pytest.
2. Database tests on PostgreSQL 16 + PostGIS.
3. Webhook tests.
4. Web typecheck/test/build.
5. API image build.

`deploy.yml` publishes the API image and rolls it out ([deploy.md](deploy.md)).

## Conventions

* Contracts first: change [contracts.md](contracts.md), then code on both sides.
* The engine stays pure: no I/O, no printing; problems are returned as issues with codes.
* New issue codes need an entry in `core/messages.py` (Greek), in the web app's translations and
  in [engine.md](engine.md).
* New migrations end with `revoke execute … from public, anon` for new functions.
* Never hard-code design values ([design-system.md](design-system.md)).
