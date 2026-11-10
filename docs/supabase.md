# Supabase (database, auth, storage, billing webhook)

Code: [`supabase/`](../supabase). Schema contract: [`contracts.md`](contracts.md). Everything in `supabase/` implements it.

```
supabase/
├── config.toml                         # CLI config (local dev)
├── migrations/
│   ├── 20261109000001_init.sql         # tables, RLS, triggers, RPCs, grants
│   ├── 20261109000002_storage.sql      # raw-files bucket + storage policies
│   ├── 20261109000003_my_plan.sql      # my_plan(): best plan across the caller's workspaces
│   └── 20261109000004_membership_guards.sql  # owner-role guards, project-move limit
├── seed.sql                            # intentionally empty
├── functions/paddle-webhook/           # Edge Function: Paddle Billing → subscriptions
└── tests/                              # RLS/RPC tests on plain PostgreSQL
```

## Hosted project (EU, Frankfurt)

1. Create the project in the Supabase dashboard: **Region = Central EU (Frankfurt), eu-central-1**.
2. Link and push the schema:

   ```bash
   npm i -g supabase            # or: brew install supabase/tap/supabase
   supabase login
   supabase link --project-ref <project-ref>
   supabase db push             # applies supabase/migrations/*
   ```

3. Check in **Database → Extensions** that `postgis` is enabled in schema `extensions` (the migration does it).

### Auth settings (Dashboard → Authentication)

* **URL configuration**
  * Site URL: `https://app.atsurvey.gr` (production web app)
  * Redirect URLs: `https://app.atsurvey.gr/**` (the app sends users back to its own routes, e.g.
    `/projects`; same list as `supabase/config.toml`)
* **Providers**
  * Email: enabled, confirm email on, minimum password length 10 (the sign-up form and local
    `config.toml` use the same value).
  * Google: see **Google sign-in** below.
* **Multi-factor**: TOTP enabled (enroll + verify), as in `config.toml`. The database enforces it
  (migration `20261111000005`); the web app shows the code prompt after sign-in.
* **Sessions**: JWT expiry **900 s** (same as `config.toml`), refresh-token rotation on.
* **Bot protection**: Authentication → Bot and Abuse Protection → Cloudflare Turnstile with the
  site's secret key; build the web app with `VITE_TURNSTILE_SITE_KEY` (the widget shows only then).
* **Email templates**: translate *Confirm signup*, *Magic link* and *Reset password* to Greek; keep
  `{{ .ConfirmationURL }}`. Configure a custom SMTP sender (e.g. Postmark/Resend, EU region) — the
  built-in sender is rate-limited and not meant for production.
* **JWT signing keys**: enable asymmetric signing keys (Settings → JWT Keys). The engine API
  verifies tokens via `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`;
  the legacy HS256 secret is supported as a fallback (`SUPABASE_JWT_SECRET`).

Sign-up metadata read by the `handle_new_user` trigger: `full_name` (or `name`) and `locale`
(`el`/`en`) in `options.data` of `supabase.auth.signUp`.

### Google sign-in

One OAuth client serves local development and production.

1. [Google Cloud Console](https://console.cloud.google.com/) → create (or pick) a project →
   **APIs & Services → OAuth consent screen**: user type *External*, app name *ATSurvey*, support
   e-mail, authorised domain `atsurvey.gr`, scopes `openid`, `email`, `profile` (no sensitive
   scopes, so no Google review). While the app is in *Testing*, add your Google accounts as test
   users; publish it before launch.
2. **Credentials → Create credentials → OAuth client ID → Web application**:
   * Authorised JavaScript origins: `http://localhost:5173`, `https://app.atsurvey.gr`
   * Authorised redirect URIs: `http://127.0.0.1:54321/auth/v1/callback` (local) and
     `https://<project-ref>.supabase.co/auth/v1/callback` (hosted)
3. **Local:** `cp supabase/.env.example supabase/.env.local`, paste the client id and secret, set
   `GOOGLE_AUTH_ENABLED=true`, then restart Supabase (`npx supabase stop && bash scripts/dev.sh`).
   `supabase/.env.local` is git-ignored and overrides the committed defaults in `supabase/.env`
   (Google off), so a fresh checkout starts without any credentials.
4. **Hosted:** Dashboard → Authentication → Providers → Google: enable, paste id and secret.

The sign-in page asks the auth server which providers are on (`/auth/v1/settings`) and shows
"Continue with Google" only when Google is enabled. A Google account whose e-mail matches an
existing (confirmed) account is linked to it; two-factor applies to Google sign-ins too.

### Edge Function: `paddle-webhook`

```bash
supabase secrets set PADDLE_WEBHOOK_SECRET=pdl_ntfset_...
supabase functions deploy paddle-webhook --no-verify-jwt
```

* `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are injected by the platform.
* In Paddle → Developer tools → Notifications, add destination
  `https://<project-ref>.supabase.co/functions/v1/paddle-webhook` with the `subscription.*` events.
* Checkout must pass `customData: { workspace_id }` (the current workspace id). Later events
  without custom data are matched by `subscription_id`.
* Plan mapping: `active`/`trialing` → `pro`; anything else → `free`. Paddle keeps a cancelled
  subscription `active` until the period ends, then sends `subscription.canceled`.
* Not handled yet: out-of-order delivery (an older event arriving after a newer one overwrites it).
  Paddle retries in order in practice; add an `occurred_at` guard column if it becomes a problem.

### Edge Function: `delete-account`

The signed-in user deletes their own account (Account page). `POST {"confirm": true}` with the
user's access token; answers `401 reauth_required` unless they signed in within the last 10
minutes, `409 sole_owner` (with the team names) while they alone own a team that has other
members. Otherwise it calls `delete_account_data()` (every workspace they are the only member of,
personal included, with projects, runs and audit events), erases their files at once and deletes
the auth user (profile and memberships cascade).

```bash
supabase secrets set ALLOWED_ORIGINS=https://app.atsurvey.gr
supabase functions deploy delete-account --no-verify-jwt   # token checked with auth.getUser()
```

### Edge Function: `storage-janitor`

Service-role only (the caller must present the service-role key). Erases queued Storage objects
(`storage_deletions`, filled when `raw_files` rows are deleted, including cascades), objects no
row references (older than a day) and workspaces nobody belongs to. Schedule it on the hosted
project (store the key in Vault first: `select vault.create_secret('<service-role-key>', 'service_role_key');`):

```sql
select cron.schedule('storage-janitor', '*/15 * * * *', $$
  select net.http_post(
    url := 'https://<project-ref>.supabase.co/functions/v1/storage-janitor',
    headers := jsonb_build_object('Authorization', 'Bearer ' ||
      (select decrypted_secret from vault.decrypted_secrets where name = 'service_role_key')));
$$);
```

```bash
supabase functions deploy storage-janitor --no-verify-jwt
# locally (functions are served by `supabase start`):
curl -X POST http://127.0.0.1:54321/functions/v1/storage-janitor -H "Authorization: Bearer $SERVICE_ROLE_KEY"
```

Tests for all functions: `node --test supabase/functions/*/*_test.ts` (Node ≥ 22.18; CI runs it).
Pure logic lives beside each `index.ts` (`signature.ts`, `account.ts`, `_shared/*.ts`).

## Local development

```bash
supabase start            # needs Docker; API on :54321, Studio on :54323, Inbucket on :54324
supabase db reset         # re-apply migrations + seed
supabase functions serve paddle-webhook --no-verify-jwt --env-file supabase/.env.local
```

## Tests inside the local Supabase (macOS, no PostGIS install needed)

```bash
bash supabase/tests/run_in_supabase.sh     # after `npx supabase start`
```

Same shim, migrations and tests as below, in a throwaway database inside the running Supabase
container (Postgres 17 + PostGIS). The app database is not touched.

## Tests (plain PostgreSQL, no Docker)

```bash
sudo apt-get install -y postgresql-16 postgresql-16-postgis-3
supabase/tests/run.sh
```

`run.sh` creates a throwaway cluster, applies `tests/00_supabase_shim.sql` (roles `anon`,
`authenticated`, `service_role`; `auth.users`, `auth.uid()`; `storage.buckets/objects`,
`storage.foldername()`), applies all migrations and runs `tests/rls_test.sql` (123 checks: signup
trigger, cross-user isolation on every table and storage, free-plan limit, subscriptions write
protection, `save_computation_run` geometry, immutability, cascades, anon lockout, owner-role guards,
viewer/member limits, project moves, storage path rules, audit log, file and account erasure). It exits
non-zero on the first failure. Env: `PG_BIN`, `PGTEST_DIR`, `PGTEST_PORT`, `KEEP_CLUSTER=1`.
As root it runs PostgreSQL as the `postgres` user, so `PGTEST_DIR` must be traversable by that user
(the default `mktemp -d` under `/tmp` is).

## API surface for clients

| Call | Notes |
|---|---|
| `rpc('save_computation_run', { p_project_id, p_result, p_settings })` → `uuid` | `p_result` = engine `ProjectResult` JSON; stores the run plus one `computed_points` row per `p_result.points[]` (`name, kind, code, x, y, z`). Security invoker: fails with `42501` for projects the caller cannot access. |
| `rpc('workspace_plan', { p_workspace_id })` → `'free' \| 'pro'` | Security invoker: returns `'free'` for workspaces the caller is not a member of. |
| `rpc('my_plan')` → `'free' \| 'pro'` | Best plan across all the caller's workspaces (used by the engine API when no workspace is given). |
| `rpc('is_workspace_member', { p_workspace_id })`, `rpc('can_access_project', { p_project_id })` | Helpers used by RLS; callable but only reveal the caller's own access. |
| Insert into `projects` | Raises SQLSTATE `P0001`, message `project_limit_reached` when a free workspace already has 3 active (non-archived) projects. Unarchiving is checked too. |
| Insert into `observations` | `project_id` may be omitted — derived from `setup_id` by trigger. Same for `computed_points` from `run_id`. |
| Storage `raw-files` | Path must start with `{workspace_id}/`; other paths are rejected by policy. 20 MB limit. |

The current user's personal workspace: `from('workspaces').select('*').eq('personal', true)`
(RLS limits it to the caller's own). `profiles` has a row per user (`id = auth.uid()`).

## Deviations from / additions to `docs/contracts.md`

* **Extra helpers**: `has_workspace_role(uuid, workspace_role[])`, `storage_path_workspace(text)`
  (safe uuid parsing of the first path segment, so malformed paths are denied instead of erroring).
* **Membership trigger**: inserting a workspace makes its `created_by` the owner
  (`add_workspace_owner`); the signup trigger relies on this. Users may create non-personal
  workspaces only; personal workspaces cannot be deleted.
* **Composite foreign keys** keep children in the same project: `setups(raw_file_id, project_id)`,
  `observations(setup_id, project_id)`, `computed_points(run_id, project_id)`. A deleted raw file
  sets `setups.raw_file_id` to null only (PostgreSQL ≥ 15 column-list `SET NULL`).
* **Immutability**: `computation_runs` and `computed_points` have no UPDATE privilege/policy.
* `subscriptions.status` defaults to `'inactive'`; `subscriptions.updated_at` and
  `projects.updated_at` are maintained by triggers. `profiles.locale` is limited to `el`/`en`.
* `angle_unit` columns also allow `'rad'` (matches the engine's `AngleUnit`).
* **Membership guards** (`20261109000004`): only owners grant or revoke `owner`; personal-workspace
  memberships cannot be deleted; a workspace always keeps an owner; the free-plan project limit
  also applies when a project's `workspace_id` changes.
* Hosted Supabase grants EXECUTE on new `public` functions to `anon` by default privileges:
  future migrations that add functions should repeat the `revoke execute ... from public, anon`
  pattern at the end of `20261109000001_init.sql`.
* **Isolation, audit and erasure** (`20261111000001…4`, docs/security.md DB-7 … DB-13):
  * Role `viewer` (read-only). `can_write_project(uuid)` (owner/admin/member) guards every write
    policy; `projects_delete` is owner/admin; trigger `guard_project_move` requires owner/admin in
    both workspaces for a `workspace_id` change.
  * Storage: `storage_path_project(text)`, `storage_path_in_project(text)`; object access follows
    the project segment; uploads must name the project's current workspace; bucket
    `allowed_mime_types` = text/plain, text/csv, application/xml, text/xml, application/dxf,
    application/octet-stream. Check `raw_files_path_matches_project`.
  * `audit_events(id, workspace_id, project_id, actor, action, details, created_at)`: written by
    triggers on projects, workspace_members, workspaces, raw_files, computation_runs and by RPC
    `log_export(project_id, format)` (authenticated); select for owner/admin; no update/delete
    for any role. Actions: `project.{created,renamed,archived,restored,moved_out,moved_in,deleted,exported}`,
    `member.{added,removed,role_changed}`, `workspace.{created,renamed}`, `file.{uploaded,deleted}`,
    `run.{saved,deleted}`.
  * Service-role only: `storage_deletions` (queue), `claim_storage_deletions(limit)`,
    `storage_orphans(limit)`, `purge_memberless_workspaces()`, `account_deletion_blockers(user)`,
    `delete_account_data(user)`. Authenticated: `my_account_deletion_blockers()`.
