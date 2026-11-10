import { describe, expect, it } from "vitest";
import { folderName } from "./exportData";

describe("folderName", () => {
  it("keeps Greek names and adds the short id", () => {
    expect(folderName("Όδευση Τ2–Τ3", "25da8078-7c1c")).toBe("Όδευση Τ2–Τ3 (25da8078)");
  });

  it("removes characters that are illegal in file names", () => {
    expect(folderName('a/b\\c:d*e?"f<g>h|i', "12345678-x")).toBe("a_b_c_d_e_f_g_h_i (12345678)");
  });

  it("never returns an empty or overlong name", () => {
    expect(folderName("   ", "abcdefgh")).toBe("project (abcdefgh)");
    expect(folderName("x".repeat(200), "abcdefgh").length).toBeLessThanOrEqual(80 + 11);
  });
});
