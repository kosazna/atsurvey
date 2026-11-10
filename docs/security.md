# Security

Audit date: 2026-11-10. Scope: engine API, exports, parsers, Supabase schema/RLS/storage,
billing webhook, web app headers, containers and deployment, supply chain.

## Threat model

| Asset | Why it matters |
|---|---|
| Clients' survey data (coordinates, raw files, projects) | Confidential professional data; tenant isolation is the core promise |
| Paid features (exports, project limit) | Revenue: the paywall must not be bypassable |
| Accounts and sessions | Takeover gives access to all of a user's projects |
| Service availability | The engine is CPU-bound; one heavy request must not starve everyone |
| Billing state (`subscriptions`) | Self-upgrading to Pro would be fraud |

| Actor | Capability |
|---|---|
| Anonymous visitor | Demo: parse, compute, suggest, CSV export |
| Signed-in user (free or pro) | Own workspaces through Supabase (RLS) and the API |
| Malicious user | Crafted uploads, oversized or odd payloads, direct PostgREST calls with their own JWT |
| Network attacker | Only HTTPS endpoints (Cloudflare Pages, Caddy, Supabase) |
| Paddle | Signed webhooks |

**Trust boundaries:** browser ↔ Supabase (RLS is the only gate, because the browser holds the
anon key); browser ↔ engine API (JWT verified on every request; the API holds no database
credentials); Paddle ↔ edge function (HMAC signature); CI ↔ VM (SSH key, environment-protected).

## Controls by layer

**Database (Supabase)**
* RLS on every table (tested: "RLS enabled on every public table"); access through workspace
  membership; helpers are `security definer` with `search_path = ''`.
* `subscriptions` writable only by `service_role`; `computation_runs` / `computed_points` immutable.
* `created_by` forced to the caller; owner-role guards; personal workspaces can't be orphaned.
* Value limits (finite numbers, sane magnitudes, text/jsonb sizes, rows per project/run).
* Free plan limits enforced in triggers: 3 active projects **and** no extra team workspaces.
* Storage: private bucket, the path must start with a workspace the caller belongs to, 20 MB.
* Tests: `supabase/tests/run.sh`, **80 checks** (cross-tenant isolation on every table and storage).

**Engine API**
* JWT: JWKS (ES256/RS256 only) or HS256 secret; issuer `{SUPABASE_URL}/auth/v1`, audience
  `authenticated`, `exp` and `sub` required, 30 s leeway; generic error messages.
* Refuses to start with unsafe production config (`ENVIRONMENT=production` with auth disabled,
  non-HTTPS Supabase URL, `http://` CORS origins, or rate limiting off).
* Rate limiting: token buckets per user id (verified JWT) or client IP, stricter for
  `/v1/export` and `/v1/parse`, 429 with `Retry-After`. `X-Forwarded-For` is used only with
  `TRUSTED_PROXY=true`.
* Body size limits enforced before buffering (Content-Length and streamed), plus count limits on
  observations, setups, control points, traverses and route length.
* CPU protection: concurrency semaphore (503 when saturated), timeouts, and traverse suggestions
  in a killable child process.
* Response headers: nosniff, `Referrer-Policy: no-referrer`, CORP, `Cache-Control: no-store` on
  `/v1/*`. Explicit CORS origins (no `*`). Generic 500 handler.
* Paywall: export formats checked server-side per plan; the plan is looked up with the caller's
  own JWT (RLS applies) and fails closed to `free`.

**Parsers and exports**
* XML via `defusedxml` (entity expansion, external entities and DTD retrieval rejected; tested).
* Input guards: 64 MB, 2 M lines, binary rejection (binary DXF excepted), UTF-16 handling.
* Hypothesis fuzzing of every parser: only `ParseError`/`ValueError`, time-boxed.
* CSV/XLSX formula-injection neutralisation for user text (`exports/sanitize.py`, CWE-1236).
* PDF data passed to Typst as JSON, never as markup (no template injection).
* Download filenames are ASCII slugs plus RFC 5987 `filename*` (header-injection test with CR/LF
  and quotes).

**Web**
* `web/public/_headers`: strict CSP (self; hashed inline script; API, Supabase, map tiles and
  Paddle allow-listed; `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'none'`), HSTS,
  nosniff, Referrer-Policy, Permissions-Policy. `scripts/check_csp.py` keeps the inline-script
  hash in sync (CI).
* React escaping throughout; no `dangerouslySetInnerHTML`. Tokens are held by the Supabase client
  only.

**Billing webhook**
* HMAC-SHA256 (`ts:body`) with constant-time compare, 5-minute replay window, multiple signatures
  accepted during secret rotation, 256 KB body limit (streamed), no internal details in errors.
  16 tests.

**Containers and deployment**
* API image: non-root (uid 10001), no build tools in the runtime stage, healthcheck.
* Compose: `read_only`, `tmpfs /tmp`, `no-new-privileges`, `cap_drop: ALL`, PID and memory
  limits, rotated logs. Caddy: automatic TLS, HSTS, body limit, `Server` header removed.

**Supply chain (CI job `security`)**
* `pip-audit` on the locked Python environment: 109 packages, **no known vulnerabilities**.
* `pnpm audit --prod`: one moderate advisory (minimatch ReDoS, GHSA-g3hv-75wg-m249) reached
  through the data grid's build tooling. It was not present in the shipped bundle. Fixed with a
  pnpm override to `^11.0.1`; now **clean**.
* `scripts/check_secrets.py` scans tracked files for credentials (private keys, JWTs, Paddle,
  AWS, Stripe, GitHub tokens, assigned secrets).

## Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| DB-5 | High | Free users could create unlimited team workspaces, each with 3 free projects (bypass of the project limit) | Fixed (trigger + test) |
| DB-1 | Medium | `created_by` could be set to another user's id (attribution spoofing) | Fixed |
| DB-6 | Medium | `save_computation_run` accepted unbounded payloads and malformed point arrays | Fixed |
| DB-2 | Medium | Float columns accepted NaN/±Infinity and absurd magnitudes | Fixed (check constraints) |
| DB-3 / DB-4 | Medium | Unbounded text/jsonb sizes and rows per project/run (storage abuse) | Fixed |
| M-1 | Medium | Admin could promote themselves to owner; personal workspace could be orphaned | Fixed (night 1, migration 4) |
| API-1 | Medium | No rate limiting; one client could saturate the CPU | Fixed |
| API-2 | Medium | `asyncio.wait_for` did not stop runaway threads (CPU exhaustion) | Fixed (semaphore + killable process for suggestions) |
| API-3 | Medium | JWT issuer not verified; JWKS path didn't pin the algorithm family | Fixed |
| API-4 | Low | Request bodies buffered before size checks | Fixed (ASGI limit) |
| API-5 | Low | `AUTH_DISABLED` could reach production by mistake | Fixed (startup refusal) |
| EXP-1 | Medium | CSV/XLSX formula injection via point names, codes, messages | Fixed (`sanitize.py`) |
| PAR-1 | Low | Parsers unbounded on huge or binary input | Fixed (guards + fuzzing) |
| WH-1 | Low | Webhook read unbounded bodies | Fixed (streamed limit) |
| WEB-1 | Medium | No CSP or security headers on the static site | Fixed (`_headers`) |
| DEP-1 | Moderate | minimatch ReDoS in a transitive build dependency | Fixed (override) |

Open items and accepted risks:
* **Rate limiting is per API instance** (in-memory). It's fine for one VM; with several replicas,
  move it to Redis or enforce it at Cloudflare.
* **Anonymous compute is public by design** (demo). It's bounded by rate limits and size and
  concurrency guards. Set `ALLOW_ANONYMOUS_COMPUTE=false` if it is abused.
* **The KML/GeoJSON datum shift is approximate (~1 m).** This is documented and labelled in the
  files; it isn't a security issue, but users must not stake out from them.
* **Point names starting with `-`** are prefixed with `'` in CSV exports (the formula-injection
  rule). This is intentional.

## Operational checklist

- [ ] `ENVIRONMENT=production`, `TRUSTED_PROXY=true` behind Caddy, `CORS_ORIGINS` = the app's origin only
- [ ] Supabase: asymmetric JWT signing keys on; leaked-password protection on; email confirmation on; custom SMTP
- [ ] Supabase Pro backups/PITR enabled; test a restore once
- [ ] Rotate `PADDLE_WEBHOOK_SECRET` and the deploy SSH key yearly (the webhook accepts two signatures during rotation)
- [ ] GitHub: branch protection on `master`, required CI, secret scanning and Dependabot alerts enabled
- [ ] Review `pnpm audit` / `pip-audit` failures within a week; rerun `supabase/tests/run.sh` after every migration
- [ ] Keep the CSP in sync when adding third-party services (CI checks inline scripts only)

## Reporting a vulnerability

Email the maintainer (address to be published on the website's `/.well-known/security.txt`)
with steps to reproduce. Please don't open public issues for security reports.
