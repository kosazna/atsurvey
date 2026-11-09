# ATSurvey

Web platform for surveyors (τοπογράφοι): import total-station raw data, compute traverses and
detail points in ΕΓΣΑ87, see the points on a map and export CSV / Excel / Shapefile / DXF / PDF.

| Folder | What | Stack |
|---|---|---|
| [`engine/`](engine) | Computation core: reductions, traverses, detail points, instrument parsers, exports | Python 3.13, pydantic, ezdxf, pyshp, XlsxWriter, Typst |
| [`api/`](api) | Stateless HTTP API around the engine | FastAPI, Supabase JWT |
| [`web/`](web) | The application | Vite, React 19, TanStack, Tailwind v4, MapLibre, Glide Data Grid |
| [`supabase/`](supabase) | Database schema, RLS, storage, billing webhook | Postgres + PostGIS, Edge Functions |
| [`deploy/`](deploy) | Production stack for the Hetzner VM | Docker Compose, Caddy |
| [`docs/`](docs) | Plan, contracts, decisions | |

```
browser (web/) ──► Supabase (auth, Postgres+PostGIS with RLS, storage)
       └────────► Engine API (api/ on Hetzner) ─ parse · compute · suggest · export
```

## Quick start (local)

```bash
# engine + API
uv sync
uv run pytest                    # engine + API tests
uv run --package atsurvey-api uvicorn atsurvey_api.main:app --reload --port 8000

# web app (demo mode works without Supabase)
cd web && pnpm install && pnpm dev   # http://localhost:5173

# database tests (needs PostgreSQL 16 + PostGIS)
bash supabase/tests/run.sh
```

See [`docs/PLAN.md`](docs/PLAN.md) for the roadmap and status, [`docs/contracts.md`](docs/contracts.md)
for the API and database contracts, and [`docs/deploy.md`](docs/deploy.md) to go live.

The original 2020 desktop prototype is preserved on the `master` branch history (tag `legacy-2020`
locally).
