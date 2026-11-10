// Supabase Edge Function: delete-account (the signed-in user deletes their own account).
//
// POST {"confirm": true} with the user's access token. Requires a sign-in within the last
// 10 minutes. Refuses (409) while the user alone owns a team workspace with other members.
// Deletes every workspace the user is the only member of (personal included: projects, runs,
// audit events), then their stored files, then the auth user (profile and memberships cascade).
//
// JWT verification is off at the gateway (config.toml) because the token is validated here with
// auth.getUser(), which also rejects signed-out sessions.
// Env: ALLOWED_ORIGINS (comma-separated web origins; defaults to the local dev server).

import { createClient } from "npm:@supabase/supabase-js@2";
import { bearer, corsHeaders, json, parseOrigins } from "../_shared/http.ts";
import { drainDeletions } from "../_shared/storage.ts";
import { blockedOutcome, isConfirmed, isRecentSignIn } from "./account.ts";

const MAX_BODY_BYTES = 1024;

Deno.serve(async (req: Request) => {
  const cors = corsHeaders(req.headers.get("origin"), parseOrigins(Deno.env.get("ALLOWED_ORIGINS")));
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (req.method !== "POST") return json(405, { error: "method_not_allowed" }, cors);

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !anonKey || !serviceKey) {
    console.error("delete-account: missing configuration");
    return json(500, { error: "not_configured" }, cors);
  }
  const token = bearer(req.headers.get("authorization"));
  if (!token) return json(401, { error: "unauthorized" }, cors);

  const raw = await req.text();
  let body: unknown = null;
  try {
    body = raw.length <= MAX_BODY_BYTES ? JSON.parse(raw) : null;
  } catch {
    body = null;
  }
  if (!isConfirmed(body)) return json(400, { error: "confirmation_required" }, cors);

  const admin = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false } });
  const { data: who, error: whoErr } = await admin.auth.getUser(token);
  if (whoErr || !who.user) return json(401, { error: "unauthorized" }, cors);
  const userId = who.user.id;

  const { data: full, error: fullErr } = await admin.auth.admin.getUserById(userId);
  if (fullErr || !full.user) return json(401, { error: "unauthorized" }, cors);
  if (!isRecentSignIn(full.user.last_sign_in_at, new Date())) {
    return json(401, { error: "reauth_required" }, cors);
  }

  const { data: blockers, error: blockErr } = await admin.rpc("account_deletion_blockers", { p_user: userId });
  if (blockErr) {
    console.error("delete-account: blockers", blockErr.message);
    return json(500, { error: "deletion_failed" }, cors);
  }
  const blocked = blockedOutcome((blockers ?? []) as { workspace_id: string; name: string }[]);
  if (blocked) return json(blocked.status, blocked.body, cors);

  const { data: removed, error: dataErr } = await admin.rpc("delete_account_data", { p_user: userId });
  if (dataErr) {
    console.error("delete-account: data", dataErr.message);
    return json(500, { error: "deletion_failed" }, cors);
  }
  try {
    await drainDeletions(admin); // erase files now; the janitor retries anything left over
  } catch (e) {
    console.error("delete-account: storage", e instanceof Error ? e.message : e);
  }
  const { error: userErr } = await admin.auth.admin.deleteUser(userId);
  if (userErr) {
    console.error("delete-account: auth user", userErr.message);
    return json(500, { error: "deletion_failed" }, cors);
  }
  console.log("delete-account: deleted", userId, "workspaces", removed);
  return json(200, { deleted: true, workspaces: removed ?? 0 }, cors);
});
