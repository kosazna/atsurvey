"""Create dummy users, plans and a team workspace in the LOCAL Supabase stack.

    uv run python scripts/seed_users.py            (after `npx supabase start`)

Users go through the Auth admin API, so the signup trigger creates their profile and personal
workspace exactly as a real sign-up does. Re-running replaces the previous seed data. Refuses to
run against anything but a local stack: it uses the service-role key and a shared password.
Guide: docs/local-setup.md
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

PASSWORD = "atsurvey-dev-pass"  # local only; satisfies minimum_password_length = 10
DOMAIN = "atsurvey.test"  # reserved TLD: mail can never leave Mailpit
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
TEAM_NAME = "Τοπογραφικό Γραφείο Κωνσταντίνου"
PRO_PERIOD = timedelta(days=365)


@dataclass(frozen=True)
class Persona:
    key: str
    full_name: str
    locale: str
    note: str


PERSONAS = (
    Persona("free", "Ελένη Παπαδοπούλου", "el", "free plan, personal workspace only"),
    Persona("pro", "Γιώργος Νικολάου", "el", "Pro on the personal workspace"),
    Persona("owner", "Μαρία Κωνσταντίνου", "el", "owner of the Pro team workspace"),
    Persona("admin", "Νίκος Αλεξίου", "el", "admin in the team (Pro through the team)"),
    Persona("member", "Anna Schmidt", "en", "member in the team, English UI"),
)
TEAM_ROLES = {"admin": "admin", "member": "member"}


def email(persona: Persona) -> str:
    return f"{persona.key}@{DOMAIN}"


def local_stack() -> tuple[str, str]:
    out = subprocess.run(
        ["npx", "--yes", "supabase@2", "status", "-o", "env"],
        capture_output=True,
        text=True,
        check=False,
    )
    values = dict(
        line.split("=", 1)
        for line in out.stdout.splitlines()
        if "=" in line and not line.startswith("#")
    )
    api_url = values.get("API_URL", "").strip('"')
    key = values.get("SERVICE_ROLE_KEY", "").strip('"')
    if not api_url or not key:
        sys.exit("local Supabase is not running — start it with: npx supabase start")
    host = urllib.parse.urlparse(api_url).hostname
    if host not in LOCAL_HOSTS:
        sys.exit(f"refusing to seed {api_url}: this script only runs against a local stack")
    return api_url, key


class Client:
    def __init__(self, api_url: str, key: str) -> None:
        self.api_url = api_url
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def call(
        self, method: str, path: str, body: object | None = None, prefer: str = ""
    ) -> Any:  # decoded JSON
        headers = {**self.headers, **({"Prefer": prefer} if prefer else {})}
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            f"{self.api_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            sys.exit(f"{method} {path} failed ({exc.code}): {detail}")
        return json.loads(raw) if raw else None


def existing_seed_users(client: Client) -> list[dict]:
    page = client.call("GET", "/auth/v1/admin/users?per_page=1000")
    users = page.get("users", []) if isinstance(page, dict) else []
    return [u for u in users if str(u.get("email", "")).endswith(f"@{DOMAIN}")]


def reset(client: Client) -> None:
    users = existing_seed_users(client)
    if not users:
        return
    ids = ",".join(u["id"] for u in users)
    # team workspaces survive their creator (created_by is set null), so remove them first
    client.call("DELETE", f"/rest/v1/workspaces?created_by=in.({ids})")
    for user in users:
        client.call("DELETE", f"/auth/v1/admin/users/{user['id']}")
    print(f"removed {len(users)} previous seed users")


def create_user(client: Client, persona: Persona) -> str:
    user = client.call(
        "POST",
        "/auth/v1/admin/users",
        {
            "email": email(persona),
            "password": PASSWORD,
            "email_confirm": True,
            "user_metadata": {"full_name": persona.full_name, "locale": persona.locale},
        },
    )
    return user["id"]


def personal_workspace(client: Client, user_id: str) -> str:
    rows = client.call(
        "GET", f"/rest/v1/workspaces?select=id&personal=is.true&created_by=eq.{user_id}"
    )
    if not rows:
        sys.exit(f"signup trigger did not create a personal workspace for {user_id}")
    return rows[0]["id"]


def make_pro(client: Client, workspace_id: str, tag: str) -> None:
    period_end = (datetime.now(UTC) + PRO_PERIOD).isoformat()
    client.call(
        "POST",
        "/rest/v1/subscriptions?on_conflict=workspace_id",
        {
            "workspace_id": workspace_id,
            "provider": "seed",
            "customer_id": f"seed_cus_{tag}",
            "subscription_id": f"seed_sub_{tag}",
            "plan": "pro",
            "status": "active",
            "current_period_end": period_end,
        },
        prefer="resolution=merge-duplicates",
    )


def create_team(client: Client, ids: dict[str, str]) -> str:
    rows = client.call(
        "POST",
        "/rest/v1/workspaces",
        {"name": TEAM_NAME, "personal": False, "created_by": ids["owner"]},
        prefer="return=representation",
    )
    team_id = rows[0]["id"]  # the owner membership is added by the workspaces_add_owner trigger
    members = [
        {"workspace_id": team_id, "user_id": ids[k], "role": role} for k, role in TEAM_ROLES.items()
    ]
    client.call("POST", "/rest/v1/workspace_members", members)
    make_pro(client, team_id, "team")
    return team_id


def main() -> int:
    client = Client(*local_stack())
    reset(client)
    ids = {p.key: create_user(client, p) for p in PERSONAS}
    make_pro(client, personal_workspace(client, ids["pro"]), "pro")
    create_team(client, ids)

    print(f"\nSeeded {len(PERSONAS)} confirmed users, password for all: {PASSWORD}\n")
    width = max(len(email(p)) for p in PERSONAS)
    for p in PERSONAS:
        print(f"  {email(p):<{width}}  {p.full_name:<20}  {p.note}")
    print(f"\n  Team workspace: {TEAM_NAME} (Pro)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
