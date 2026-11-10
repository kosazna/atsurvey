// Supabase Edge Function: storage-janitor (service role only).
//
// Removes the stored files of deleted projects and workspaces (queue public.storage_deletions),
// objects that no raw_files row references, and workspaces nobody belongs to any more.
// Scheduled every 15 minutes with pg_cron + pg_net on the hosted project (docs/supabase.md);
// locally: curl -X POST $API_URL/functions/v1/storage-janitor -H "Authorization: Bearer $SERVICE_ROLE_KEY"
//
// JWT verification is off at the gateway (config.toml): the caller must present the service-role
// key itself, compared in constant time.

import { createClient } from "npm:@supabase/supabase-js@2";
import { bearer, constantTimeEqual, json } from "../_shared/http.ts";
import { drainDeletions, sweepOrphans } from "../_shared/storage.ts";

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json(405, { error: "method_not_allowed" });

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !serviceKey) {
    console.error("storage-janitor: missing configuration");
    return json(500, { error: "not_configured" });
  }
  const token = bearer(req.headers.get("authorization"));
  if (!token || !constantTimeEqual(token, serviceKey)) return json(401, { error: "unauthorized" });

  const admin = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false } });
  try {
    const purge = await admin.rpc("purge_memberless_workspaces");
    if (purge.error) throw new Error(`purge_memberless_workspaces: ${purge.error.message}`);
    const queue = await drainDeletions(admin);
    const orphans = await sweepOrphans(admin);
    const result = { workspaces_purged: purge.data ?? 0, ...queue, orphans_removed: orphans };
    console.log("storage-janitor", JSON.stringify(result));
    return json(200, result);
  } catch (e) {
    console.error("storage-janitor failed", e instanceof Error ? e.message : e);
    return json(500, { error: "janitor_failed" });
  }
});
