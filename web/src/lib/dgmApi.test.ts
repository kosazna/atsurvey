import { describe, expect, it } from "vitest";
import { areasCsv, changesCsv, checkFileName, isKaek, issueXY, layerTone, normalizeKaek, parseVertices, sha512Hex, splitBlocks, verticesText } from "./dgmApi";

describe("dgm helpers", () => {
  it("normalizes and validates KAEK", () => {
    expect(normalizeKaek("ΚΑΕΚ: 05068 17 03 001")).toBe("050681703001");
    expect(normalizeKaek("KAEK 05-068-170-3001")).toBe("050681703001");
    expect(isKaek("050681703001")).toBe(true);
    expect(isKaek("05068170300")).toBe(false);
  });

  it("checks file names like the Cadastre (§4.3)", () => {
    expect(checkFileName("dgm_name_v01.dxf", "deed")).toEqual([]);
    expect(checkFileName("topo_name_v01.dxf", "topo")).toEqual([]);
    expect(checkFileName("dgm_x.dxf", "correction")).toEqual(["DGM_FILE_VERSION_WARN"]);
    expect(checkFileName("ΔΓΜ αγρός.v1.dxf", "deed")).toEqual(expect.arrayContaining(["DGM_FILE_CHARS", "DGM_FILE_PREFIX"]));
    expect(checkFileName("dgm_averyverylongname_v01.dxf", "deed")).toContain("DGM_FILE_LENGTH");
    expect(checkFileName("dgm_a_v01.pdf", "deed")).toContain("DGM_FILE_EXTENSION");
  });

  it("writes the change table with Greek headings and 2-decimal areas", () => {
    const text = changesCsv([{ part: "A1", kind: "A", description: ["1", "b", "a", "1"], area: 53.233361, from_kaek: "050681703001", to_kaek: "ΝΕΟ" }]);
    expect(text.startsWith("﻿ΤΜΗΜΑ;ΠΕΡΙΓΡΑΦΗ;ΕΜΒΑΔΟ;ΑΠΟ ΚΑΕΚ;ΣΕ ΚΑΕΚ\r\n")).toBe(true);
    expect(text).toContain("A1;(1,b,a,1);53.23;050681703001;ΝΕΟ");
    expect(areasCsv([{ label: "x", kaek: null, before: null, after: 10, difference: null }])).toContain("x;;10.00;");
  });

  it("neutralises formula injection in CSV cells", () => {
    const text = changesCsv([{ part: "=cmd", kind: "A", description: ["1"], area: 1, from_kaek: "a", to_kaek: "b" }]);
    expect(text).toContain("'=cmd;");
  });

  it("maps layers to tones and parses blocks", () => {
    expect(layerTone("AREA_A")).toBe("cut");
    expect(layerTone("DGM_PROP_FINAL")).toBe("final");
    expect(layerTone("ATS_TAB")).toBe("other");
    expect(splitBlocks("a\nb\n\n  \nc\n")).toEqual(["a\nb", "c"]);
    expect(verticesText([{ name: "1", x: 476200.1234, y: 4205100.5 }])).toBe("1 476200.123 4205100.500");
  });

  it("reads problem coordinates from issue params", () => {
    expect(issueXY({ severity: "error", code: "X", message: "", params: { x: 1.5, y: 2 } })).toEqual({ x: 1.5, y: 2 });
    expect(issueXY({ severity: "error", code: "X", message: "", params: { x: null, y: 2 } })).toBeNull();
  });

  it("hashes with SHA-512 (FIPS 180-2 test vector)", async () => {
    const h = await sha512Hex(new TextEncoder().encode("abc"));
    expect(h).toBe(
      "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
    );
  });
});

describe("parseVertices", () => {
  const lookup = (n: string) => (n === "Τ2" ? { x: 476100, y: 4205100 } : undefined);
  it("reads numeric point names of a cadastral diagram", () => {
    const r = parseVertices("12 476200.123 4205100.456\n13;476230,5;4205101\nΤ2\n476000.1 4205000.2\n476000.1 4205000.2 15.3\nxx", lookup);
    expect(r.vertices).toEqual([
      { name: "12", x: 476200.123, y: 4205100.456 },
      { name: "13", x: 476230.5, y: 4205101 },
      { name: "Τ2", x: 476100, y: 4205100 },
      { name: "P4", x: 476000.1, y: 4205000.2 },
      { name: "P5", x: 476000.1, y: 4205000.2 },
    ]);
    expect(r.bad).toEqual(["xx"]);
  });
});
