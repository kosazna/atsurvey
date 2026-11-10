// Account deletion and shared HTTP helper tests. Node >= 22.18: `node --test account_test.ts`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { blockedOutcome, isConfirmed, isRecentSignIn, REAUTH_WINDOW_MS } from "./account.ts";
import { bearer, constantTimeEqual, corsHeaders, DEFAULT_ORIGINS, parseOrigins } from "../_shared/http.ts";
import { batches } from "../_shared/storage.ts";

const now = new Date("2026-11-11T12:00:00Z");
const ago = (ms: number) => new Date(now.getTime() - ms).toISOString();

test("a sign-in within ten minutes is recent", () => {
  assert.equal(isRecentSignIn(ago(60_000), now), true);
  assert.equal(isRecentSignIn(ago(REAUTH_WINDOW_MS), now), true);
});

test("an older, missing or malformed sign-in requires re-authentication", () => {
  assert.equal(isRecentSignIn(ago(REAUTH_WINDOW_MS + 1), now), false);
  assert.equal(isRecentSignIn(null, now), false);
  assert.equal(isRecentSignIn("yesterday", now), false);
  assert.equal(isRecentSignIn(new Date(now.getTime() + 3_600_000).toISOString(), now), false);
});

test("only an explicit confirm: true is accepted", () => {
  assert.equal(isConfirmed({ confirm: true }), true);
  for (const body of [null, {}, { confirm: "true" }, { confirm: 1 }, [true], "confirm"]) {
    assert.equal(isConfirmed(body), false, JSON.stringify(body));
  }
});

test("sole-owner teams block deletion and are named", () => {
  assert.equal(blockedOutcome([]), null);
  assert.deepEqual(blockedOutcome([{ workspace_id: "w1", name: "Team" }]), {
    status: 409,
    body: { error: "sole_owner", workspaces: [{ id: "w1", name: "Team" }] },
  });
});

test("bearer tokens are parsed strictly", () => {
  assert.equal(bearer("Bearer abc.def"), "abc.def");
  assert.equal(bearer("bearer abc"), "abc");
  assert.equal(bearer("Basic abc"), null);
  assert.equal(bearer("Bearer a b"), null);
  assert.equal(bearer(null), null);
});

test("constant-time comparison", () => {
  assert.equal(constantTimeEqual("secret-key", "secret-key"), true);
  assert.equal(constantTimeEqual("secret-key", "secret-kez"), false);
  assert.equal(constantTimeEqual("secret", "secret-key"), false);
  assert.equal(constantTimeEqual("", ""), true);
});

test("CORS answers allowed origins only", () => {
  const allowed = parseOrigins("https://app.atsurvey.gr, javascript:alert(1), http://localhost:5173");
  assert.deepEqual(allowed, ["https://app.atsurvey.gr", "http://localhost:5173"]);
  assert.equal(corsHeaders("https://app.atsurvey.gr", allowed)["access-control-allow-origin"], "https://app.atsurvey.gr");
  assert.deepEqual(corsHeaders("https://evil.example", allowed), {});
  assert.deepEqual(corsHeaders(null, allowed), {});
  assert.deepEqual(parseOrigins(undefined), DEFAULT_ORIGINS);
});

test("storage removals are batched", () => {
  assert.deepEqual(batches([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]);
  assert.deepEqual(batches([], 2), []);
});
