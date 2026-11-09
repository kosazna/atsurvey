// Webhook hardening tests. Node >= 22.18: `node --test security_test.ts`; Deno: `deno test`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { BodyTooLarge, MAX_BODY_BYTES, readBodyLimited } from "./limits.ts";
import { decide, occurredAt, type SubscriptionRow } from "./subscription.ts";

const row = (over: Partial<SubscriptionRow> = {}): SubscriptionRow => ({
  workspace_id: "11111111-1111-1111-1111-111111111111",
  provider: "paddle",
  customer_id: "ctm_1",
  subscription_id: "sub_1",
  plan: "pro",
  status: "active",
  current_period_end: null,
  ...over,
});

test("first event for a workspace is applied", () => {
  assert.deepEqual(decide(null, row(), "2026-11-10T10:00:00Z"), { apply: true });
});

test("older or replayed events for the same subscription are ignored", () => {
  const existing = { subscription_id: "sub_1", plan: "free", last_event_at: "2026-11-10T10:00:00.000Z" };
  assert.deepEqual(decide(existing, row(), "2026-11-10T09:59:59Z"), { apply: false, reason: "stale" });
  assert.deepEqual(decide(existing, row(), "2026-11-10T10:00:00Z"), { apply: false, reason: "stale" });
  assert.deepEqual(decide(existing, row(), "2026-11-10T10:00:01Z"), { apply: true });
});

test("another subscription cannot downgrade an active one (buy-then-cancel griefing)", () => {
  const existing = { subscription_id: "sub_victim", plan: "pro", last_event_at: null };
  const attacker = row({ subscription_id: "sub_attacker", plan: "free", status: "canceled" });
  assert.deepEqual(decide(existing, attacker, "2026-11-10T10:00:00Z"), {
    apply: false,
    reason: "foreign_downgrade",
  });
  // ... but a new active subscription may take over, and the owner's own cancellation applies
  assert.equal(decide(existing, row({ subscription_id: "sub_new" }), null).apply, true);
  assert.equal(
    decide(existing, row({ subscription_id: "sub_victim", plan: "free", status: "canceled" }), null).apply,
    true,
  );
});

test("occurred_at is normalised and garbage ignored", () => {
  assert.equal(occurredAt({ occurred_at: "2026-11-10T10:00:00.123456Z" }), "2026-11-10T10:00:00.123Z");
  assert.equal(occurredAt({ occurred_at: "yesterday" }), null);
  assert.equal(occurredAt({}), null);
});

test("body limit via Content-Length", async () => {
  const req = new Request("https://x/", {
    method: "POST",
    body: "x",
    headers: { "content-length": String(MAX_BODY_BYTES + 1) },
  });
  await assert.rejects(readBodyLimited(req), BodyTooLarge);
});

test("body limit while streaming (no Content-Length)", async () => {
  const chunk = new Uint8Array(64 * 1024);
  let sent = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (sent > MAX_BODY_BYTES * 2) controller.close();
      else {
        sent += chunk.byteLength;
        controller.enqueue(chunk);
      }
    },
  });
  const req = new Request("https://x/", { method: "POST", body: stream, duplex: "half" } as RequestInit);
  await assert.rejects(readBodyLimited(req), BodyTooLarge);
});

test("normal bodies are read intact (UTF-8)", async () => {
  const body = '{"event_type":"subscription.created","note":"Αφίδνες"}';
  assert.equal(await readBodyLimited(new Request("https://x/", { method: "POST", body })), body);
});
