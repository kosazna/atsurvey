// Supabase Edge Function: Paddle Billing webhook → public.subscriptions
//
// Secrets (supabase secrets set ...):
//   PADDLE_WEBHOOK_SECRET      endpoint secret from Paddle → Developer tools → Notifications
//   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   provided automatically by the platform
//
// Checkout must pass `customData: { workspace_id: "<uuid>" }` so events can be mapped.
// Deploy with JWT verification off (see config.toml): Paddle signs requests itself.

import { createClient } from "npm:@supabase/supabase-js@2";
import { BodyTooLarge, readBodyLimited } from "./limits.ts";
import { verifyPaddleSignature } from "./signature.ts";
import {
  decide,
  HANDLED_EVENTS,
  occurredAt,
  type PaddleEvent,
  toSubscriptionRow,
} from "./subscription.ts";

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

  let rawBody: string;
  try {
    rawBody = await readBodyLimited(req);
  } catch (e) {
    if (e instanceof BodyTooLarge) return json(413, { error: "too_large" });
    throw e;
  }
  const sig = await verifyPaddleSignature(req.headers.get("paddle-signature"), rawBody, secret);
  if (!sig.ok) {
    console.warn("paddle-webhook: rejected signature", sig.reason);
    return json(401, { error: "invalid_signature" }); // no detail for the caller
  }

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

  const { data: existing, error: readError } = await db
    .from("subscriptions")
    .select("subscription_id, plan, last_event_at")
    .eq("workspace_id", workspaceId)
    .maybeSingle();
  if (readError) {
    console.error("paddle-webhook: read failed", readError);
    return json(500, { error: "lookup_failed" });
  }
  const eventAt = occurredAt(event);
  const decision = decide(existing, row, eventAt);
  if (!decision.apply) {
    console.warn("paddle-webhook: skipped", decision.reason, row.subscription_id);
    return json(200, { ignored: decision.reason });
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
      last_event_at: eventAt,
    },
    { onConflict: "workspace_id" },
  );
  if (error) {
    if (error.code === "23503") {
      // unknown workspace id in custom_data: acknowledge so Paddle stops retrying
      console.warn("paddle-webhook: workspace does not exist", workspaceId);
      return json(200, { ignored: "unknown_workspace" });
    }
    console.error("paddle-webhook: upsert failed", error);
    return json(500, { error: "upsert_failed" });
  }

  return json(200, { ok: true });
});
