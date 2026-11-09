// Supabase Edge Function: Paddle Billing webhook → public.subscriptions
//
// Secrets (supabase secrets set ...):
//   PADDLE_WEBHOOK_SECRET      endpoint secret from Paddle → Developer tools → Notifications
//   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   provided automatically by the platform
//
// Checkout must pass `customData: { workspace_id: "<uuid>" }` so events can be mapped.
// Deploy with JWT verification off (see config.toml): Paddle signs requests itself.

import { createClient } from "npm:@supabase/supabase-js@2";
import { verifyPaddleSignature } from "./signature.ts";
import { HANDLED_EVENTS, type PaddleEvent, toSubscriptionRow } from "./subscription.ts";

const json = (status: number, body: Record<string, unknown>) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json(405, { error: "method_not_allowed" });

  const secret = Deno.env.get("PADDLE_WEBHOOK_SECRET");
  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!secret || !supabaseUrl || !serviceKey) {
    console.error("paddle-webhook: missing configuration");
    return json(500, { error: "not_configured" });
  }

  const rawBody = await req.text();
  const sig = await verifyPaddleSignature(req.headers.get("paddle-signature"), rawBody, secret);
  if (!sig.ok) return json(401, { error: "invalid_signature", reason: sig.reason });

  let event: PaddleEvent;
  try {
    event = JSON.parse(rawBody);
  } catch {
    return json(400, { error: "invalid_json" });
  }

  const type = event.event_type ?? "";
  if (!HANDLED_EVENTS.has(type)) return json(200, { ignored: type });

  const row = toSubscriptionRow(event);
  if (!row) return json(400, { error: "invalid_subscription_payload" });

  const db = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  let workspaceId = row.workspace_id;
  if (!workspaceId) {
    // Events after creation may lack custom_data: resolve from the stored subscription.
    const { data, error } = await db
      .from("subscriptions")
      .select("workspace_id")
      .eq("subscription_id", row.subscription_id)
      .maybeSingle();
    if (error) {
      console.error("paddle-webhook: lookup failed", error);
      return json(500, { error: "lookup_failed" });
    }
    workspaceId = data?.workspace_id ?? null;
  }
  if (!workspaceId) {
    console.warn("paddle-webhook: no workspace for subscription", row.subscription_id);
    return json(200, { ignored: "unknown_workspace" });
  }

  const { error } = await db.from("subscriptions").upsert(
    {
      workspace_id: workspaceId,
      provider: row.provider,
      customer_id: row.customer_id,
      subscription_id: row.subscription_id,
      plan: row.plan,
      status: row.status,
      current_period_end: row.current_period_end,
    },
    { onConflict: "workspace_id" },
  );
  if (error) {
    console.error("paddle-webhook: upsert failed", error);
    return json(500, { error: "upsert_failed" });
  }

  return json(200, { ok: true, event: type, workspace_id: workspaceId, plan: row.plan });
});
