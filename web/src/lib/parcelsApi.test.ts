import { describe, expect, it } from "vitest";
import { AREA_TOLERANCE_PRESETS, describeRule, parseParts, partsCsv, sidesCsv, stremmata, svgFrame, toleranceFor, toVertices, verticesCsv, type ParcelGeometry, type SubdivisionResult } from "./parcelsApi";

const GEO: ParcelGeometry = {
  label: "1",
  kaek: null,
  vertices: [
    { name: "A", x: 476000, y: 4205000 },
    { name: "B", x: 476100, y: 4205000 },
    { name: "C", x: 476100, y: 4205050 },
  ],
  sides: [
    { frm: "A", to: "B", length: 100, azimuth: Math.PI / 2 },
    { frm: "B", to: "C", length: 50, azimuth: 0, arc_length: 52.1234, radius: 40 },
  ],
  area: 2500,
  perimeter: 261.8,
  orientation: "counterclockwise",
  centroid: { x: 476066.667, y: 4205016.667 },
  has_arcs: true,
  valid: true,
  issues: [],
};

describe("parcels helpers", () => {
  it("stremmata", () => {
    expect(stremmata(12345.6)).toBeCloseTo(12.3456, 10);
  });

  it("tolerance rules mirror the engine", () => {
    expect(toleranceFor({ kind: "fixed", value: 12, source: "" }, 1000)).toBe(12);
    expect(toleranceFor({ kind: "percent", value: 2, source: "" }, 1000)).toBeCloseTo(20, 12);
    expect(toleranceFor({ kind: "formula", a: 1, b: 0.5, source: "" }, 1600)).toBeCloseTo(21, 12);
    expect(toleranceFor({ kind: "formula", a: 1, source: "" }, 1600)).toBeNull();
    expect(toleranceFor({ kind: "percent", source: "" }, 1600)).toBeNull();
  });

  it("describes rules", () => {
    expect(describeRule({ kind: "fixed", value: 5, source: "" })).toBe("5 m²");
    expect(describeRule({ kind: "percent", value: 2.5, source: "" })).toBe("2.5 % · E");
    expect(describeRule({ kind: "formula", a: 1, b: 0.5, source: "" })).toBe("1 + 0.5·√E m²");
    expect(describeRule({ kind: "formula", a: 1, source: "" })).toBe("1 + ?·√E m²");
  });

  it("cadastral rule: worked example (500 m² square, urban U0 = 0.50 m) and 7 % cap", () => {
    const perimeter = 4 * Math.sqrt(500);
    const rule = { kind: "cadastre" as const, u0: 0.5, source: "" };
    expect(toleranceFor(rule, 500, perimeter)).toBeCloseTo(45.72, 2);
    expect(toleranceFor({ ...rule, cap_percent: 7 }, 500, perimeter)).toBeCloseTo(35, 10);
    expect(toleranceFor(rule, 500)).toBeNull();
    expect(describeRule({ ...rule, cap_percent: 7 })).toBe("U0·Π·(1 + U0/√E), U0 = 0.5 m, ≤ 7 % · E");
  });

  it("presets mirror the engine", () => {
    expect(AREA_TOLERANCE_PRESETS.map((p) => [p.id, p.rule.u0, !!p.to_be_confirmed])).toEqual([
      ["cadastre_urban", 0.5, false],
      ["cadastre_rural", 2, true],
      ["cadastre_rural_dgm_guide", 2.5, true],
    ]);
    expect(AREA_TOLERANCE_PRESETS.every((p) => p.rule.source.length > 0)).toBe(true);
  });

  it("parses part lists", () => {
    expect(parseParts("500 750,5; 1")).toEqual([500, 750.5, 1]);
    expect(parseParts("1 0")).toBeNull();
    expect(parseParts("1 x")).toBeNull();
    expect(parseParts("  ")).toBeNull();
  });

  it("names unnamed vertices", () => {
    expect(toVertices([{ x: 1, y: 2, name: " K1 " }, { x: 3, y: 4 }])).toEqual([
      { name: "K1", x: 1, y: 2 },
      { name: "P2", x: 3, y: 4 },
    ]);
  });

  it("vertex and side CSV", () => {
    expect(verticesCsv(GEO)).toBe("﻿point;X;Y\r\nA;476000.000;4205000.000\r\nB;476100.000;4205000.000\r\nC;476100.000;4205050.000\r\n");
    const sides = sidesCsv(GEO, (r) => ((r * 200) / Math.PI).toFixed(4), "gon").split("\r\n");
    expect(sides[0]).toBe("﻿from;to;length_m;azimuth_gon;arc_length_m;radius_m");
    expect(sides[1]).toBe("A;B;100.000;100.0000;;");
    expect(sides[2]).toBe("B;C;50.000;0.0000;52.123;40.000");
  });

  it("parts CSV", () => {
    const result: SubdivisionResult = {
      original: GEO,
      parts: [
        { geometry: { ...GEO, label: "Α" }, requested_area: 2500, area_error: 1.2e-10, frontage: 20 },
        { geometry: { ...GEO, label: "Β", area: 1000 }, requested_area: null, area_error: null, frontage: null },
      ],
      cut_lines: [],
      new_points: [],
      issues: [],
    };
    const lines = partsCsv(result).split("\r\n");
    expect(lines[1]).toBe("Α;2500.00;2500.00;2.500;1.20e-10;20.00;A B C");
    expect(lines[2]).toBe("Β;;1000.00;1.000;;;A B C");
  });

  it("svg frame keeps north up and equal scale", () => {
    const f = svgFrame([[{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 50 }]], 300, 10)!;
    expect(f.scale).toBeCloseTo(2.8, 12);
    expect(f.tx(0)).toBeCloseTo(10, 12);
    expect(f.tx(100)).toBeCloseTo(290, 12);
    // y = 50 (north) is above y = 0 → smaller SVG y; the 50 m span is centred vertically
    expect(f.ty(50)).toBeCloseTo(80, 12);
    expect(f.ty(0)).toBeCloseTo(220, 12);
    expect(svgFrame([])).toBeNull();
  });
});
