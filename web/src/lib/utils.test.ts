import { afterEach, describe, expect, it, vi } from "vitest";
import { uid } from "./utils";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("uid", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns a v4 UUID", () => {
    expect(uid()).toMatch(UUID);
  });

  it("returns a v4 UUID without crypto.randomUUID (plain-HTTP origins)", () => {
    const real = globalThis.crypto;
    vi.stubGlobal("crypto", { getRandomValues: (b: Uint8Array) => real.getRandomValues(b) });
    const ids = new Set(Array.from({ length: 200 }, () => uid()));
    expect(ids.size).toBe(200);
    for (const id of ids) expect(id).toMatch(UUID);
  });
});
