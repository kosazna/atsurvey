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
  * Google: create an OAuth client in Google Cloud Console (type *Web*), authorised redirect URI
    `https://<project-ref>.supabase.co/auth/v1/callback`, then paste client id/secret into the
    Google provider. Locally: export `SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID` / `..._SECRET` and set
    `enabled = true` in `config.toml`.
* **Email templates**: translate *Confirm signup*, *Magic link* and *Reset password* to Greek; keep
  `{{ .ConfirmationURL }}`. Configure a custom SMTP sender (e.g. Postmark/Resend, EU region) — the
  built-in sender is rate-limited and not meant for production.
* **JWT signing keys**: enable asymmetric signing keys (Settings → JWT Keys). The engine API
  verifies tokens via `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`;
  the legacy HS256 secret is supported as a fallback (`SUPABASE_JWT_SECRET`).

Sign-up metadata read by the `handle_new_user` trigger: `full_name` (or `name`) and `locale`
(`el`/`en`) in `options.data` of `supabase.auth.signUp`.

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

Tests: `node --test supabase/functions/paddle-webhook/signature_test.ts` (Node ≥ 22.18) or
`deno test` inside the function folder.

## Local development

```bash
supabase start            # needs Docker; API on :54321, Studio on :54323, Inbucket on :54324
supabase db reset         # re-apply migrations + seed
supabase functions serve paddle-webhook --no-verify-jwt --env-file supabase/.env.local
```

## Tests (plain PostgreSQL, no Docker)

```bash
sudo apt-get install -y postgresql-16 postgresql-16-postgis-3
supabase/tests/run.sh
```

`run.sh` creates a throwaway cluster, applies `tests/00_supabase_shim.sql` (roles `anon`,
`authenticated`, `service_role`; `auth.users`, `auth.uid()`; `storage.buckets/objects`,
`storage.foldername()`), applies all migrations and runs `tests/rls_test.sql` (66 checks: signup
trigger, cross-user isolation on every table and storage, free-plan limit, subscriptions write
protection, `save_computation_run` geometry, immutability, cascades, anon lockout, owner-role guards). It exits
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
