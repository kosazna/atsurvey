# ATSurvey

Web platform for surveyors (τοπογράφοι): import total-station raw data, compute traverses and
detail points in ΕΓΣΑ87, see the points on a map, and export CSV / Excel / Shapefile / DXF / PDF.

```
browser (web/) ──► Supabase (auth, Postgres + PostGIS with RLS, storage)
       └────────► Engine API (api/ on Hetzner) ─ parse · compute · suggest · export
```

| Folder | What |
|---|---|
| `engine/` | computation core, instrument parsers, exports (Python) |
| `api/` | stateless FastAPI service around the engine |
| `web/` | the application (React 19, Vite, Tailwind v4, MapLibre) |
| `supabase/` | schema, row-level security, storage, billing webhook |
| `design/` | design tokens: the single source for app and report styling |
| `deploy/` | Docker Compose + Caddy for the Hetzner VM |
| `docs/` | **all documentation** |

```bash
uv sync && uv run pytest                                              # engine + API
uv run --package atsurvey-api uvicorn atsurvey_api.main:app --port 8000
cd web && pnpm install && pnpm dev                                     # http://localhost:5173 (demo mode)
```

Start with [docs/README.md](docs/README.md): plan, architecture, engine methods, formats, API,
database, web app, design system, development and deployment.
