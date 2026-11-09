# Contracts: database schema and engine API

This file is the single source of truth shared by `engine/`, `api/`, `supabase/` and `web/`.
Change it first, then the code.

## Units and conventions

* Coordinates: `x` = Easting, `y` = Northing, `z` = orthometric height, metres. CRS EPSG:2100 (EGSA87).
* **All angles are stored and transported in radians.** The UI converts to the project's
  display unit (`gon` default, also `deg`, `dms`).
* `hz` = horizontal circle reading (direction). `v` = zenith angle. Face II readings (v > π) are allowed;
  the engine reduces them.

## Engine API (FastAPI, `api/`)

Base URL is `VITE_API_URL` (e.g. `https://api.atsurvey.gr`). All `/v1/*` routes require
`Authorization: Bearer <supabase access token>` unless the API runs with `AUTH_DISABLED=true` (dev/demo).

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/health` | – | `{ "status": "ok", "engine_version": "0.1.0" }` |
| GET | `/v1/me` | – | `{ "user_id", "plan": "free" \| "pro", "export_formats": ["csv","xlsx",...] }` |
| POST | `/v1/parse` | multipart: `file`, optional `angle_unit` (`gon`/`deg`/`dms`), optional `format` | `ParseResult` |
| POST | `/v1/compute` | `ProjectInput` | `ProjectResult` |
| POST | `/v1/suggest-traverses` | `ProjectInput` | `{ "suggestions": TraverseSpec[] }` |
| POST | `/v1/export` | `ExportRequest` | file download (`Content-Disposition: attachment`) |

`ProjectInput`, `ProjectResult`, `TraverseSpec`, etc. are defined in `engine/src/atsurvey/core/models.py`
and exposed as OpenAPI at `/openapi.json`.

```jsonc
// ParseResult
{
  "format": "leica_gsi" | "trimble_jobxml" | "landxml" | "nikon_raw" | "rw5" | "csv",
  "angle_unit": "gon" | "deg" | "dms" | null,      // unit used to read the file
  "setups": Setup[],                                 // radians
  "control_points": ControlPoint[],                  // coordinates found in the file, if any
  "warnings": string[],
  "stats": { "setups": 12, "observations": 340 }
}

// ExportRequest
{
  "format": "csv" | "xlsx" | "shp" | "dxf" | "pdf",
  "project_name": "Afidnes",
  "input": ProjectInput,
  "options": {
    "angle_unit": "gon",
    "decimals": 3,
    "csv_delimiter": ",",
    "csv_header": true,
    "include": ["control", "traverse", "detail"],
    "dxf_text_height": 0.5
  }
}
```

## Database (Supabase Postgres + PostGIS)

Everything is scoped by **workspace**. A personal workspace is created for each new user by trigger.
Row-level security: a user can access rows whose workspace they are a member of.

| Table | Columns |
|---|---|
| `profiles` | `id uuid pk = auth.users.id`, `full_name text`, `locale text default 'el'`, `created_at` |
| `workspaces` | `id uuid pk`, `name text`, `personal bool`, `created_by uuid`, `created_at` |
| `workspace_members` | `workspace_id`, `user_id`, `role` (`owner`/`admin`/`member`), pk(workspace_id,user_id) |
| `projects` | `id uuid pk`, `workspace_id`, `name`, `description`, `crs_epsg int default 2100`, `angle_unit text default 'gon'`, `settings jsonb default '{}'` (= `ComputeSettings`), `created_by`, `created_at`, `updated_at`, `archived_at` |
| `control_points` | `id uuid pk`, `project_id`, `name`, `x`, `y`, `z` (nullable), `code`, `note`, `created_at`; unique(project_id, name) |
| `raw_files` | `id uuid pk`, `project_id`, `storage_path`, `filename`, `format`, `size_bytes`, `sha256`, `angle_unit`, `parser_version`, `created_by`, `created_at` |
| `setups` | `id uuid pk`, `project_id`, `raw_file_id` (nullable, on delete set null), `ordinal int`, `station`, `instrument_height float8 default 0`, `backsight` (nullable), `note`, `created_at` |
| `observations` | `id uuid pk`, `setup_id` (on delete cascade), `project_id`, `ordinal int`, `target`, `hz float8` (rad), `v float8` (rad, nullable), `sd float8` (nullable), `target_height float8 default 0`, `code`, `excluded bool default false`, `edited bool default false`, `created_at` |
| `traverses` | `id uuid pk`, `project_id`, `ordinal int`, `name`, `route text[]`, `kind text default 'auto'`, `end_orientation bool` (nullable), `enabled bool default true`, `created_at` |
| `computation_runs` | `id uuid pk`, `project_id`, `engine_version`, `input_hash`, `settings jsonb`, `summary jsonb`, `result jsonb`, `created_by`, `created_at` |
| `computed_points` | `id uuid pk`, `run_id` (cascade), `project_id`, `name`, `kind` (`control`/`traverse`/`detail`), `code`, `x`, `y`, `z`, `geom geometry(PointZ, 2100)` |
| `subscriptions` | `workspace_id pk`, `provider text default 'paddle'`, `customer_id`, `subscription_id`, `plan text` (`free`/`pro`), `status text`, `current_period_end timestamptz`, `updated_at` — written by service role only |

RPC (security invoker, so RLS applies):

* `save_computation_run(p_project_id uuid, p_result jsonb, p_settings jsonb) returns uuid` — inserts the
  run and its `computed_points` (from `p_result->'points'`) in one transaction.
* `workspace_plan(p_workspace_id uuid) returns text` — `'pro'` if an active subscription exists, otherwise `'free'`.

Storage bucket `raw-files` (private). Object path: `{workspace_id}/{project_id}/{uuid}-{filename}`.
Policy: members of the workspace in the first path segment can read and write.

## Entitlements

| Plan | Export formats | Projects |
|---|---|---|
| free | csv, xlsx | 3 active |
| pro | csv, xlsx, shp, dxf, pdf | unlimited |

## Additions (night 1): least squares, COGO, levelling, linework

Engine models: `engine/src/atsurvey/core/models.py` (`AdjustmentSettings`, `LineworkSettings`,
`ErrorEllipse`, `AdjustedObservation`, `GlobalTest`, `AdjustmentResult`, `Polyline`) and
`engine/src/atsurvey/core/cogo_models.py` (COGO and levelling requests/results).

* `ComputeSettings.adjustment.method`: `"bowditch"` (default) or `"least_squares"`. With least
  squares, `ProjectResult.adjustment` is filled and network points carry `sx`, `sy`, `sz`, `ellipse`.
* `ComputeSettings.linework.line_codes`: feature codes joined into `ProjectResult.linework`.

| Method | Path | Body → Response |
|---|---|---|
| POST | `/v1/cogo/inverse` | `InverseRequest` → `InverseResult` |
| POST | `/v1/cogo/polar` | `PolarRequest` → `PolarResult` |
| POST | `/v1/cogo/intersection/angles` | `IntersectionAnglesRequest` → `IntersectionResult` |
| POST | `/v1/cogo/intersection/distances` | `IntersectionDistancesRequest` → `IntersectionResult` |
| POST | `/v1/cogo/intersection/lines` | `IntersectionLinesRequest` → `IntersectionResult` |
| POST | `/v1/cogo/resection` | `ResectionRequest` → `ResectionResult` |
| POST | `/v1/cogo/area` | `AreaRequest` → `AreaResult` |
| POST | `/v1/cogo/transform` | `TransformRequest` → `TransformResult` |
| POST | `/v1/cogo/offset` | `OffsetRequest` → `OffsetResult` |
| POST | `/v1/leveling` | `LevelingRequest` → `LevelingResult` |

All are stateless, available to anonymous callers (same rules as `/v1/compute`), and return 422 with a
`detail` message for degenerate geometry.
