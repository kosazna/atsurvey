import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import {
  changesDatum,
  convertCsv,
  coordsErrorCode,
  formatGeo,
  formatPoint,
  isGeographic,
  isUnverifiedDefinition,
  issueParams,
  parseCoordLine,
  parseCoordList,
  type ConvertResult,
} from "./coordsApi";

const DEG = Math.PI / 180;

describe("system helpers", () => {
  it("classifies systems", () => {
    expect(isGeographic("wgs84_geo")).toBe(true);
    expect(isGeographic("egsa87")).toBe(false);
    expect(changesDatum("wgs84_geo", "egsa87")).toBe(true);
    expect(changesDatum("utm34", "wgs84_geo")).toBe(false);
    expect(changesDatum("tm3_west", "hatt")).toBe(false);
    expect(isUnverifiedDefinition("tm3_central")).toBe(true);
    expect(isUnverifiedDefinition("hatt")).toBe(true);
    expect(isUnverifiedDefinition("egsa87")).toBe(false);
  });
});

describe("parseCoordLine", () => {
  it("reads grid lines with and without a name", () => {
    expect(parseCoordLine("476000.123 4205000.456", false, "deg")).toEqual({ name: null, x: 476000.123, y: 4205000.456, z: null });
    expect(parseCoordLine("S1 476000,5 4205000 12,3", false, "deg")).toEqual({ name: "S1", x: 476000.5, y: 4205000, z: 12.3 });
    expect(parseCoordLine("1009;566296.538;4529332.307;6.501", false, "deg")).toEqual({ name: "1009", x: 566296.538, y: 4529332.307, z: 6.501 });
    expect(parseCoordLine("476000,4205000", false, "deg")).toEqual({ name: null, x: 476000, y: 4205000, z: null });
  });

  it("reads φ λ (latitude first) in decimal degrees and DMS, into radians x = λ, y = φ", () => {
    const d = parseCoordLine("A 37.9838 23.7275 150", true, "deg")!;
    expect(d.name).toBe("A");
    expect(d.y).toBeCloseTo(37.9838 * DEG, 14);
    expect(d.x).toBeCloseTo(23.7275 * DEG, 14);
    expect(d.z).toBe(150);
    const s = parseCoordLine(`40°54'44.68247" 24°47'14.08874"`, true, "dms")!;
    expect(s.y / DEG).toBeCloseTo(40 + 54 / 60 + 44.68247 / 3600, 12);
    expect(s.x / DEG).toBeCloseTo(24 + 47 / 60 + 14.08874 / 3600, 12);
    const packed = parseCoordLine("40.544468247 24.471408874", true, "dms")!;
    expect(packed.y).toBeCloseTo(s.y, 11);
  });

  it("rejects incomplete or non-numeric lines", () => {
    expect(parseCoordLine("476000", false, "deg")).toBeNull();
    expect(parseCoordLine("A B C", false, "deg")).toBeNull();
    expect(parseCoordLine("", true, "dms")).toBeNull();
  });
});

describe("parseCoordList", () => {
  it("names unnamed points by line and collects bad lines", () => {
    const r = parseCoordList("476000 4205000\n\nfoo\nK2 476100 4205100", false, "deg");
    expect(r.pts.map((p) => p.name)).toEqual(["P1", "K2"]);
    expect(r.bad).toEqual(["foo"]);
  });
});

describe("formatting and CSV", () => {
  it("formats geographic values with sub-millimetre resolution", () => {
    const lat = (40 + 54 / 60 + 44.68247 / 3600) * DEG;
    expect(formatGeo(lat, "dms")).toBe(`40°54'44.68247"`);
    expect(formatGeo(lat, "deg")).toBe(`${(lat / DEG).toFixed(9)}°`);
  });

  it("puts φ before λ and keeps failed points empty", () => {
    expect(formatPoint({ x: 24 * DEG, y: 38 * DEG }, true, "deg")).toEqual(["38.000000000°", "24.000000000°", ""]);
    expect(formatPoint({ x: 1.23456, y: 2.5, z: 3 }, false, "deg")).toEqual(["1.235", "2.500", "3.000"]);
    expect(formatPoint({ x: null, y: null }, false, "deg")).toEqual(["", "", ""]);
  });

  it("builds a BOM-prefixed semicolon CSV", () => {
    const res: ConvertResult = {
      src: "wgs84_geo",
      dst: "egsa87",
      points: [{ name: "A", x: 476000.12345, y: 4205000, z: null }],
      datum_shift: [],
      approximate: true,
      accuracy_m: 1.5,
      issues: [],
    };
    expect(convertCsv(res, "dms")).toBe("﻿point;E;N;z\r\nA;476000.123;4205000.000;\r\n");
  });
});

describe("errors and issues", () => {
  it("extracts coded engine failures", () => {
    const e = new ApiError(422, "COORD_HATT_TABLE_MISSING", { detail: { code: "COORD_HATT_TABLE_MISSING", params: { sheet: "61" } } });
    e.code = "COORD_HATT_TABLE_MISSING";
    expect(coordsErrorCode(e)).toEqual({ code: "COORD_HATT_TABLE_MISSING", params: { sheet: "61" } });
    expect(coordsErrorCode(new ApiError(422, "x"))).toBeNull();
    expect(coordsErrorCode(new Error("x"))).toBeNull();
  });

  it("joins list params", () => {
    expect(issueParams({ points: ["A", "B"], count: 2 })).toEqual({ points: "A, B", count: 2 });
  });
});
