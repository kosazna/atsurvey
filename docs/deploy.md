# Going live

Three pieces: hosted Supabase (data + auth), the engine API on the Hetzner VM, and the static web
app (Cloudflare Pages).

## 1. Supabase (once)

Follow [`supabase/README.md`](../supabase/README.md): create the project in **Frankfurt
(eu-central-1)**, `supabase link`, `supabase db push`, configure Auth URLs and Google OAuth, deploy
the `paddle-webhook` function with its secret.

Note the **Project URL** and the **publishable (anon) key**.

## 2. Engine API on Hetzner

DNS: point `api.<your-domain>` (A/AAAA) to the VM. Open ports 80 and 443.

On the VM (Docker + compose plugin installed):

```bash
sudo mkdir -p /opt/atsurvey && cd /opt/atsurvey
# copy deploy/docker-compose.yml, deploy/Caddyfile and deploy/.env.example from the repo
cp .env.example .env && nano .env      # API_DOMAIN, SUPABASE_URL, SUPABASE_ANON_KEY, CORS_ORIGINS
docker compose --env-file .env up -d
curl https://api.<your-domain>/health
```

Caddy obtains TLS certificates automatically. The API container runs as a non-root user on a
read-only filesystem with a 1 GB memory limit.

### Automatic deploys

`.github/workflows/deploy.yml` builds the image on every push to `master` that touches the
engine/API, pushes it to `ghcr.io/<owner>/atsurvey-api`, and — if these repository secrets exist —
rolls it out over SSH:

| Secret | Value |
|---|---|
| `HETZNER_HOST` | VM IP or hostname |
| `HETZNER_USER` | deploy user (member of the `docker` group) |
| `HETZNER_SSH_KEY` | private key for that user |

The GHCR package must be readable by the VM: either make it public or run
`docker login ghcr.io` on the VM once with a read-only token.

## 3. Web app on Cloudflare Pages

Project → connect the GitHub repo → **root directory** `web`, build command `pnpm build`, output
`dist`. Environment variables:

| Variable | Value |
|---|---|
| `VITE_API_URL` | `https://api.<your-domain>` |
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | publishable (anon) key |
| `VITE_PADDLE_CLIENT_TOKEN` | (later) Paddle client-side token for checkout |

Add the Pages domain to `CORS_ORIGINS` on the API and to Supabase Auth → URL configuration.

## Checklist before inviting users

- [ ] Tolerances set to your specification (project settings → defaults in `Tolerances`)
- [ ] Engine validated against your Excel workbooks (see PLAN, M1 validation)
- [ ] Parsers validated with real files from each instrument family
- [ ] Supabase: email templates in Greek, SMTP provider configured (Supabase's built-in SMTP is rate-limited)
- [ ] Paddle products/prices created; webhook URL registered; test a sandbox purchase
- [ ] Terms of service, privacy policy (GDPR), disclaimer about professional responsibility
- [ ] Sentry DSN (optional) for API and web
- [ ] Backups: Supabase Pro daily backups / PITR enabled

## Optional: official HEPOS transformation grids

The coordinate converter can apply the official HTRS07 → ΕΓΣΑ87 transformation (Helmert + 2 km
correction grids) only when the grid files are installed on the API server. They are **not** in
the repository: the hepos.gr terms forbid redistribution, so install them only after Κτηματολόγιο
grants permission ([science-roadmap.md](science-roadmap.md), D1).

1. Put the two `.grd` files from the official HEPOS transformation package in a folder on the VM,
   e.g. `/opt/atsurvey/hepos`.
2. Mount it read-only into the `api` service and set the variable:
   ```yaml
   volumes:
     - /opt/atsurvey/hepos:/opt/hepos:ro
   environment:
     ATSURVEY_HEPOS_GRID_DIR: /opt/hepos
   ```
3. Without it, requests for the official method return `COORD_HEPOS_UNAVAILABLE` and the UI offers
   only the clearly labelled approximate shift. Details: [coords.md](coords.md).
