// Small HTTP helpers shared by the edge functions. Pure functions: tested with node --test.

export const DEFAULT_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"];

export function json(status: number, body: Record<string, unknown>, headers: HeadersInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

/** Allowed browser origins from a comma-separated list (env ALLOWED_ORIGINS). */
export function parseOrigins(raw: string | undefined): string[] {
  const list = (raw ?? "")
    .split(",")
    .map((o) => o.trim())
    .filter((o) => /^https?:\/\/[^/\s]+$/.test(o));
  return list.length > 0 ? list : DEFAULT_ORIGINS;
}

/** CORS headers for an allowed origin; none (the browser blocks) for any other. */
export function corsHeaders(origin: string | null, allowed: string[]): Record<string, string> {
  if (!origin || !allowed.includes(origin)) return {};
  return {
    "access-control-allow-origin": origin,
    "access-control-allow-headers": "authorization, apikey, content-type, x-client-info",
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-max-age": "600",
    vary: "Origin",
  };
}

/** Token from an "Authorization: Bearer <token>" header, or null. */
export function bearer(header: string | null): string | null {
  const m = /^Bearer\s+(\S+)$/i.exec(header ?? "");
  return m ? m[1] : null;
}

/** Length-independent comparison so a wrong key leaks no timing information. */
export function constantTimeEqual(a: string, b: string): boolean {
  const ea = new TextEncoder().encode(a);
  const eb = new TextEncoder().encode(b);
  let diff = ea.length ^ eb.length;
  const n = Math.max(ea.length, eb.length);
  for (let i = 0; i < n; i++) diff |= (ea[i] ?? 0) ^ (eb[i] ?? 0);
  return diff === 0;
}
