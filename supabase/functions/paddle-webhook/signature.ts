// Paddle Billing webhook signature verification.
// Header format: "ts=1671552777;h1=<hex hmac>" (several h1 values may be present during
// secret rotation). Signed payload: `${ts}:${rawBody}`, HMAC-SHA256 with the endpoint secret.
// Uses only Web Crypto so it runs on Deno (edge runtime) and Node.

export const MAX_SIGNATURE_AGE_SECONDS = 5 * 60;

export type SignatureResult =
  | { ok: true; ts: number }
  | { ok: false; reason: "missing" | "malformed" | "expired" | "mismatch" };

export function parseSignatureHeader(header: string | null): { ts: number; h1: string[] } | null {
  if (!header) return null;
  let ts: number | null = null;
  const h1: string[] = [];
  for (const part of header.split(";")) {
    const idx = part.indexOf("=");
    if (idx < 0) continue;
    const key = part.slice(0, idx).trim();
    const value = part.slice(idx + 1).trim();
    if (key === "ts" && /^\d+$/.test(value)) ts = Number(value);
    if (key === "h1" && /^[0-9a-fA-F]{64}$/.test(value)) h1.push(value.toLowerCase());
  }
  if (ts === null || h1.length === 0) return null;
  return { ts, h1 };
}

export async function hmacSha256Hex(secret: string, message: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Constant-time comparison of two equal-length hex strings. */
export function timingSafeEqualHex(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function verifyPaddleSignature(
  header: string | null,
  rawBody: string,
  secret: string,
  nowSeconds: number = Math.floor(Date.now() / 1000),
): Promise<SignatureResult> {
  if (!header) return { ok: false, reason: "missing" };
  const parsed = parseSignatureHeader(header);
  if (!parsed) return { ok: false, reason: "malformed" };
  if (Math.abs(nowSeconds - parsed.ts) > MAX_SIGNATURE_AGE_SECONDS) {
    return { ok: false, reason: "expired" };
  }
  const expected = await hmacSha256Hex(secret, `${parsed.ts}:${rawBody}`);
  // compare against every candidate without short-circuiting
  let match = false;
  for (const candidate of parsed.h1) {
    if (timingSafeEqualHex(candidate, expected)) match = true;
  }
  return match ? { ok: true, ts: parsed.ts } : { ok: false, reason: "mismatch" };
}
