import { describe, expect, it } from "vitest";
import { checkCsv, formatChainage, parseChainage, parseProfile, parseVertices, setoutCsv, stakeoutCsv, stakeoutName, svgFrame } from "./setoutApi";
import type { CheckRow, SetoutRow } from "./setoutApi";

describe("chainage", () => {
  it("formats in km+m style", () => {
    expect(formatChainage(0)).toBe("0+000.00");
    expect(formatChainage(1234.5)).toBe("1+234.50");
    expect(formatChainage(999.999, 2)).toBe("1+000.00");
    expect(formatChainage(-20)).toBe("-0+020.00");
    expect(formatChainage(Number.NaN)).toBe("—");
  });
  it("parses both styles", () => {
    expect(parseChainage("1+234.50")).toBeCloseTo(1234.5, 12);
    expect(parseChainage("1234,5")).toBeCloseTo(1234.5, 12);
    expect(parseChainage("-0+020")).toBe(-20);
    expect(parseChainage("abc")).toBeNull();
    expect(parseChainage("")).toBeNull();
  });
  it("round-trips", () => {
    for (const ch of [0, 12.34, 999.99, 1000, 12345.67]) expect(parseChainage(formatChainage(ch))).toBeCloseTo(ch, 2);
  });
});

describe("parseVertices", () => {
  it("reads names, radius and clothoids by A or L", () => {
    const { vertices, bad } = parseVertices("A 0 0\nK1 0 500 300 150\nK2 400 800 250 L60 -\n900 800\nbad line x");
    expect(bad).toEqual(["bad line x"]);
    expect(vertices).toHaveLength(4);
    expect(vertices[0]).toMatchObject({ name: "A", x: 0, y: 0, radius: null });
    expect(vertices[1]).toMatchObject({ name: "K1", radius: 300, a_in: 150, a_out: null, l_out: null });
    expect(vertices[2]).toMatchObject({ radius: 250, l_in: 60, a_in: null, a_out: null });
    expect(vertices[3]).toMatchObject({ name: null, x: 900, y: 800 });
  });
  it("accepts decimal commas", () => {
    expect(parseVertices("K 476000,5 4205000,25 120,5").vertices[0]).toMatchObject({ x: 476000.5, y: 4205000.25, radius: 120.5 });
  });
});

describe("csv builders", () => {
  const row: SetoutRow = { index: 0, name: "P1", de: 1, dn: 2, azimuth: 0.5, direction: 0.25, distance_grid: 10, distance: 10.001, scale: null, dz: null, zenith: null, slope_distance: null };
  it("setout CSV follows the field order with a BOM and ; separators", () => {
    const text = setoutCsv([row, { ...row, index: 1, name: "P2" }], [1, 0], (r) => r.toFixed(4), "gon");
    const lines = text.replace("﻿", "").trim().split("\r\n");
    expect(text.startsWith("﻿")).toBe(true);
    expect(lines[0]).toContain("direction_gon");
    expect(lines[1].startsWith("P2;0.2500;10.001;10.000")).toBe(true);
  });
  it("check CSV flags", () => {
    const r: CheckRow = { name: "A", design_x: 0, design_y: 0, design_z: null, x: 0.03, y: 0.04, z: null, dx: 0.03, dy: 0.04, dz: null, radial: 0.05, along: null, across: null, ok_xy: false, ok_z: null, ok: false };
    expect(checkCsv([r]).trim().split("\r\n")[1]).toContain(";0.050;;;OUT");
  });
  it("stakeout names carry the side", () => {
    expect(stakeoutName({ chainage: 120, offset: 0 })).toBe("0+120.00");
    expect(stakeoutName({ chainage: 120, offset: -3.5 })).toBe("0+120.00L3.50");
    expect(stakeoutName({ chainage: 1120, offset: 3.5 })).toBe("1+120.00R3.50");
    const text = stakeoutCsv([{ chainage: 20, offset: 3.5, code: "TS", vertex: "K1", x: 1, y: 2, z: null, azimuth: 0 }], (r) => r.toFixed(4), "gon");
    expect(text).toContain("0+020.00R3.50;0+020.000;3.500;TS;1.000;2.000;;0.0000");
  });
});

describe("svgFrame", () => {
  it("keeps north up and the aspect ratio", () => {
    const f = svgFrame([476000, 476100], [4205000, 4205050], 0);
    expect(f.width).toBeCloseTo(100);
    expect(f.height).toBeCloseTo(50);
    expect(f.toSvg(476000, 4205050)).toEqual([0, 0]);
    expect(f.toSvg(476100, 4205000)).toEqual([100, 50]);
  });
});

describe("parseProfile", () => {
  it("reads chainage styles, curve length and parameter H", () => {
    const { pvis, bad } = parseProfile("0 100\nV1 0+200 108,5 120\n500 102 H2000\nx y");
    expect(bad).toEqual(["x y"]);
    expect(pvis[0]).toMatchObject({ name: null, chainage: 0, elevation: 100, length: null, radius: null });
    expect(pvis[1]).toMatchObject({ name: "V1", chainage: 200, elevation: 108.5, length: 120 });
    expect(pvis[2]).toMatchObject({ chainage: 500, radius: 2000, length: null });
  });
});
