import { describe, expect, it } from "vitest";
import { daysUntilPurge, TRASH_DAYS } from "./lifecycle";

describe("daysUntilPurge", () => {
  const now = new Date("2026-11-11T12:00:00Z");

  it("is the full window right after deletion", () => {
    expect(daysUntilPurge("2026-11-11T12:00:00Z", now)).toBe(TRASH_DAYS);
  });

  it("counts down and never goes negative", () => {
    expect(daysUntilPurge("2026-11-01T12:00:00Z", now)).toBe(20);
    expect(daysUntilPurge("2026-09-01T12:00:00Z", now)).toBe(0);
  });
});
