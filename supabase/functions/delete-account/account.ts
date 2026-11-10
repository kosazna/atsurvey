// Pure rules of account deletion. Tested with node --test (account_test.ts).

/** The user must have signed in (password, magic link, OAuth) within this window. */
export const REAUTH_WINDOW_MS = 10 * 60 * 1000;

export function isRecentSignIn(lastSignInAt: string | null | undefined, now: Date): boolean {
  if (!lastSignInAt) return false;
  const t = Date.parse(lastSignInAt);
  if (Number.isNaN(t)) return false;
  const age = now.getTime() - t;
  return age >= -60_000 && age <= REAUTH_WINDOW_MS; // tolerate a minute of clock skew
}

/** Body must be exactly {"confirm": true}: no accidental or replayed empty requests. */
export function isConfirmed(body: unknown): boolean {
  return typeof body === "object" && body !== null && (body as { confirm?: unknown }).confirm === true;
}

export type Outcome =
  | { status: 200; body: { deleted: true; workspaces: number } }
  | { status: 401; body: { error: "reauth_required" } }
  | { status: 409; body: { error: "sole_owner"; workspaces: { id: string; name: string }[] } };

export function blockedOutcome(blockers: { workspace_id: string; name: string }[]): Outcome | null {
  if (blockers.length === 0) return null;
  return {
    status: 409,
    body: { error: "sole_owner", workspaces: blockers.map((b) => ({ id: b.workspace_id, name: b.name })) },
  };
}
