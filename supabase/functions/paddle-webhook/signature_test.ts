// Runs on Deno (`deno test`) and Node >= 22.18 (`node --test signature_test.ts`).
import { test } from "node:test";
import assert from "node:assert/strict";
import { hmacSha256Hex, parseSignatureHeader, verifyPaddleSignature } from "./signature.ts";
import { planForStatus, toSubscriptionRow } from "./subscription.ts";

const SECRET = "pdl_ntfset_test_secret";
const BODY = '{"event_type":"subscription.created","data":{"id":"sub_1","status":"active"}}';
const NOW = 1_762_700_000;

async function header(ts: number, body = BODY, secret = SECRET) {
  return `ts=${ts};h1=${await hmacSha256Hex(secret, `${ts}:${body}`)}`;
}

test("accepts a valid signature", async () => {
  const r = await verifyPaddleSignature(await header(NOW), BODY, SECRET, NOW);
  assert.deepEqual(r, { ok: true, ts: NOW });
});

test("accepts when one of several h1 values matches (secret rotation)", async () => {
  const good = await header(NOW);
  const bad = `h1=${"0".repeat(64)}`;
  const r = await verifyPaddleSignature(`${good};${bad}`, BODY, SECRET, NOW);
  assert.equal(r.ok, true);
});

test("rejects tampered body", async () => {
  const r = await verifyPaddleSignature(await header(NOW), BODY + " ", SECRET, NOW);
  assert.deepEqual(r, { ok: false, reason: "mismatch" });
});

test("rejects wrong secret", async () => {
  const r = await verifyPaddleSignature(await header(NOW, BODY, "other"), BODY, SECRET, NOW);
  assert.deepEqual(r, { ok: false, reason: "mismatch" });
});

test("rejects signatures older than 5 minutes", async () => {
  const r = await verifyPaddleSignature(await header(NOW - 301), BODY, SECRET, NOW);
  assert.deepEqual(r, { ok: false, reason: "expired" });
});

test("rejects missing and malformed headers", async () => {
  assert.deepEqual(await verifyPaddleSignature(null, BODY, SECRET, NOW), {
    ok: false,
    reason: "missing",
  });
  assert.deepEqual(await verifyPaddleSignature("ts=abc;h1=zz", BODY, SECRET, NOW), {
    ok: false,
    reason: "malformed",
  });
  assert.equal(parseSignatureHeader("h1=" + "a".repeat(64)), null);
});

test("maps statuses to plans", () => {
  assert.equal(planForStatus("active"), "pro");
  assert.equal(planForStatus("trialing"), "pro");
  assert.equal(planForStatus("past_due"), "free");
  assert.equal(planForStatus("canceled"), "free");
  assert.equal(planForStatus("paused"), "free");
});

test("builds a subscription row from an event", () => {
  const row = toSubscriptionRow({
    event_type: "subscription.activated",
    data: {
      id: "sub_01",
      status: "active",
      customer_id: "ctm_01",
      custom_data: { workspace_id: "11111111-1111-1111-1111-111111111111" },
      current_billing_period: { starts_at: "2026-11-01T00:00:00Z", ends_at: "2026-12-01T00:00:00Z" },
    },
  });
  assert.deepEqual(row, {
    workspace_id: "11111111-1111-1111-1111-111111111111",
    provider: "paddle",
    customer_id: "ctm_01",
    subscription_id: "sub_01",
    plan: "pro",
    status: "active",
    current_period_end: "2026-12-01T00:00:00Z",
  });
});

test("ignores invalid workspace ids and incomplete payloads", () => {
  const row = toSubscriptionRow({
    data: { id: "sub_02", status: "canceled", custom_data: { workspace_id: "'; drop table" } },
  });
  assert.equal(row?.workspace_id, null);
  assert.equal(row?.plan, "free");
  assert.equal(toSubscriptionRow({ data: { status: "active" } }), null);
});
