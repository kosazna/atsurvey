// Request body limits for the webhook: Paddle notifications are a few KB.
export const MAX_BODY_BYTES = 256 * 1024;

export class BodyTooLarge extends Error {}

/** Read the request body as text, refusing more than `max` bytes even without Content-Length. */
export async function readBodyLimited(req: Request, max = MAX_BODY_BYTES): Promise<string> {
  const declared = Number(req.headers.get("content-length") ?? "0");
  if (Number.isFinite(declared) && declared > max) throw new BodyTooLarge();
  if (!req.body) return "";
  const reader = req.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > max) {
      await reader.cancel();
      throw new BodyTooLarge();
    }
    chunks.push(value);
  }
  const all = new Uint8Array(total);
  let offset = 0;
  for (const c of chunks) {
    all.set(c, offset);
    offset += c.byteLength;
  }
  return new TextDecoder().decode(all);
}
