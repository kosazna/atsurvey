# Running ATSurvey on your laptop

The full stack runs locally: a local Supabase (Postgres, Auth, Storage in Docker), the engine API
and the web app. Nothing touches the hosted Supabase project. The steps are for macOS; Windows
notes are at the end.

## 1. Install once

| Tool | Install | Check |
|---|---|---|
| Docker Desktop | [docker.com](https://www.docker.com/products/docker-desktop/), then open it | `docker info` |
| Node 22 | `brew install node@22` | `node -v` → v22.x |
| pnpm | `corepack enable` | `pnpm -v` |
| uv (Python) | `brew install uv` (it fetches Python 3.13 itself) | `uv --version` |

Give Docker Desktop at least 4 GB of memory (Settings → Resources).

## 2. Start everything

```bash
git clone https://github.com/kosazna/atsurvey.git && cd atsurvey
git checkout claude/exciting-noether-gbqlos      # until it is merged
bash scripts/dev.sh
```

`scripts/dev.sh` starts Supabase, applies the migrations, writes `.env` and `web/.env.local`
(`scripts/local-env.sh`), installs the dependencies and runs the API and the app. The first run
downloads the Supabase images (≈ 2 GB, a few minutes). `Ctrl-C` stops the API and the app;
`npx supabase stop` stops the database (data is kept; `npx supabase db reset` wipes it).

| URL | What |
|---|---|
| http://localhost:5173 | the app |
| http://127.0.0.1:54324 | Mailpit: every e-mail the app sends (sign-up confirmation, password reset) |
| http://127.0.0.1:54323 | Supabase Studio: tables, users, storage |
| http://localhost:8000/docs | engine API (OpenAPI) |

Prefer separate terminals? The script is three commands:

```bash
npx supabase start && bash scripts/local-env.sh
uv run --package atsurvey-api uvicorn atsurvey_api.main:app --reload --port 8000
cd web && pnpm install && pnpm dev
```

## 3. What to test

1. **Without an account.** Open the app → "Δοκιμή χωρίς λογαριασμό" (demo mode, data stays in the
   browser). Open the example project: traverse, detail points, map, exports.
2. **Sign up.** Create an account with any e-mail (e.g. `you@example.com`). The confirmation e-mail
   appears in Mailpit (http://127.0.0.1:54324); click the link and you are signed in.
3. **Projects.** Open the example as a signed-in user, or create a project and import a field file
   (GSI, JobXML, RAW, RW5, CSV, DXF). Reload the page: everything is stored in the local database.
4. **Runs and exports.** Compute, save a run (history), export CSV / XLSX (free plan). PDF, DXF and
   Shapefile are on the Pro plan; to try them, make your workspace Pro in Studio
   (`subscriptions` table, `plan = 'pro'`, `status = 'active'`) or with SQL:
   ```sql
   insert into subscriptions (workspace_id, plan, status)
   select id, 'pro', 'active' from workspaces
   on conflict (workspace_id) do update set plan = 'pro', status = 'active';
   ```
   The API caches the plan for a minute, so the new formats unlock within 60 s.
5. **Your own data.** Re-enter one of your Excel cases and compare: [validation.md](validation.md)
   lists the agreement already proven for the workbooks you sent.

Report what feels wrong, slow or missing; screenshots help.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot connect to the Docker daemon` | open Docker Desktop and wait until it says *running* |
| `port 54321 already allocated` | another Supabase project runs: `npx supabase stop --all` |
| "Invalid or expired token" in the app | restart the API after `supabase start` re-created its keys (re-run `bash scripts/dev.sh`) |
| No confirmation e-mail | it is in Mailpit, not your inbox |
| Port 5173 busy | stop the other dev server, or `pnpm dev --port 5174` (add the origin to `CORS_ORIGINS` in `.env`) |
| Tests fail after editing `.env` | they should not: API tests ignore `.env`. Report it |

**Windows:** use Docker Desktop with WSL 2 and run the same commands inside WSL (recommended), or
from PowerShell run `npx supabase start`, then `scripts\local-env.ps1`, then the API and web
commands above.

## Notes

* Auth runs with e-mail confirmation on, the same as production. Local tokens are signed with
  ES256 keys (like new hosted projects); the API verifies them through the JWKS endpoint, and
  still accepts the legacy HS256 secret.
* `.env` and `web/.env.local` are git-ignored and generated; never commit them.
