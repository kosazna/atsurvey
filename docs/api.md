# Engine API

Code: [`api/src/atsurvey_api`](../api/src/atsurvey_api). FastAPI wrapper around the engine;
**stateless**: the browser sends the project and stores results in Supabase (rationale in
[ADR 0001](adr/0001-architecture.md)). Request and response schemas: [contracts.md](contracts.md),
or `/openapi.json` and `/docs` on a running server.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | liveness, engine and parser versions |
| GET | `/v1/me` | optional | `{user_id, plan, export_formats}` (`?workspace_id=` for a specific workspace) |
| POST | `/v1/parse` | optional* | multipart `file` (+ `angle_unit`, `format`) → `ParseResult` |
| POST | `/v1/compute` | optional* | `ProjectInput` → `ProjectResult` |
| POST | `/v1/suggest-traverses` | optional* | `ProjectInput` → `{suggestions}` |
| POST | `/v1/export` | optional* | `ExportRequest` → file (`Content-Disposition`, `X-Input-Hash`) |

\* Anonymous calls are allowed while `ALLOW_ANONYMOUS_COMPUTE=true`; this powers the no-signup demo.

`ExportRequest` = `{format, project_name, input, options, workspace_id?, project_id?}`. When a
signed-in caller sends `project_id` (a stored project), the API records `project.exported` in
that workspace's audit log through the `log_export` RPC with the caller's own token
(`audit.py`; best effort: a logging failure never blocks the download).

## Authentication and plans

`Authorization: Bearer <Supabase access token>`. Tokens are verified against the project's JWKS
(`/auth/v1/.well-known/jwks.json`, ES256/RS256); HS256 tokens are accepted only when
`SUPABASE_JWT_SECRET` is set, and only against that secret. The header's `alg` selects the key type,
never the key itself (no algorithm confusion).
Audience `authenticated`.

The plan is looked up with the user's own token: `rpc/workspace_plan` when the request names a
workspace, otherwise `rpc/my_plan`. Lookups are cached for 60 s, and a failed lookup falls back to
`free`.

| Plan | Export formats |
|---|---|
| anonymous | csv |
| free | csv, xlsx |
| pro | csv, xlsx, shp, dxf, pdf |

A format outside the plan returns **402** with `{"detail": {"code": "plan_required", "plan", "format"}}`.

## Errors

| Status | When |
|---|---|
| 401 | missing/invalid/expired token where one is required |
| 402 | export format not in plan |
| 413 | upload above `MAX_UPLOAD_MB` or more than `MAX_OBSERVATIONS` |
| 422 | invalid body or unparseable file (`detail` explains) |
| 504 | computation exceeded `COMPUTE_TIMEOUT_S` |

## Configuration (environment)

| Variable | Default | Meaning |
|---|---|---|
| `SUPABASE_URL` | — | project URL (JWKS + plan lookup) |
| `SUPABASE_ANON_KEY` | — | publishable key sent as `apikey` to PostgREST |
| `SUPABASE_JWT_SECRET` | empty | legacy HS256 secret; ES256/RS256 tokens are verified through JWKS either way |
| `AUTH_DISABLED` | `false` | **dev only**: every caller is `pro` |
| `ALLOW_ANONYMOUS_COMPUTE` | `true` | demo mode without login |
| `CORS_ORIGINS` | `["http://localhost:5173","http://localhost:4173"]` | JSON list |
| `MAX_UPLOAD_MB` | `20` | upload limit |
| `MAX_OBSERVATIONS` | `200000` | request size guard |
| `COMPUTE_TIMEOUT_S` | `30` | per-request computation timeout |

## Running

```bash
uv run --package atsurvey-api uvicorn atsurvey_api.main:app --reload --port 8000
# production image
docker build -f api/Dockerfile -t atsurvey-api .
```

Deployment: [deploy.md](deploy.md).
