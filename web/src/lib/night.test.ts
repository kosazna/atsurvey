import { describe, expect, it } from "vitest";
import type { LevelingData } from "@/data/store";
import { ellipsePolygon, formatArea, formatChainage, polygonArea, polylineLength } from "./geometry";
import { heightsCsv, rowsToSetups, toLevelingRequest, validateLeveling } from "./leveling";
import { assignColors, detectCodes, featureCode } from "./linework";
import { diffRuns } from "./runDiff";
import type { ProjectResult, ResultPoint } from "./types";

describe("geometry", () => {
  it("shoelace area, perimeter and orientation", () => {
    const sq = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 20 },
      { x: 0, y: 20 },
    ];
    const r = polygonArea(sq);
    expect(r.area).toBeCloseTo(200);
    expect(r.perimeter).toBeCloseTo(60);
    expect(r.clockwise).toBe(false);
    expect(polygonArea([...sq].reverse()).clockwise).toBe(true);
    expect(polylineLength(sq)).toBeCloseTo(40);
  });

  it("large EGSA87 coordinates keep sub-mm² area precision", () => {
    const base = { x: 476000, y: 4205000 };
    const pts = [
      { x: base.x, y: base.y },
      { x: base.x + 0.123, y: base.y },
      { x: base.x + 0.123, y: base.y + 0.456 },
      { x: base.x, y: base.y + 0.456 },
    ];
    expect(polygonArea(pts).area).toBeCloseTo(0.123 * 0.456, 6);
  });

  it("ellipse major axis follows the azimuth", () => {
    // theta = 0 → major axis points north
    const north = ellipsePolygon(0, 0, 2, 1, 0, 1, 4);
    expect(north[0][0]).toBeCloseTo(0);
    expect(north[0][1]).toBeCloseTo(2);
    // theta = 90° → major axis points east
    const east = ellipsePolygon(0, 0, 2, 1, Math.PI / 2, 1, 4);
    expect(east[0][0]).toBeCloseTo(2);
    expect(east[0][1]).toBeCloseTo(0);
    // scale exaggerates
    const big = ellipsePolygon(0, 0, 0.002, 0.001, 0, 1000, 4);
    expect(big[0][1]).toBeCloseTo(2);
  });

  it("chainage formatting", () => {
    expect(formatChainage(0)).toBe("0+000.000");
    expect(formatChainage(1234.5678)).toBe("1+234.568");
    expect(formatChainage(87.25, 2)).toBe("0+087.25");
    expect(formatChainage(-12.5, 1)).toBe("-0+012.5");
    expect(formatChainage(999.9996)).toBe("1+000.000");
  });

  it("area formatting groups thousands", () => {
    expect(formatArea(12345.678)).toBe("12 345.68 m²");
    expect(formatArea(5)).toBe("5.00 m²");
  });
});

describe("linework", () => {
  const pts = [
    { code: "OIK", kind: "detail" },
    { code: "oik CL", kind: "detail" },
    { code: "DROM", kind: "detail" },
    { code: "TRIG", kind: "control" },
    { code: null, kind: "detail" },
  ] as Pick<ResultPoint, "code" | "kind">[];

  it("feature code is the first token", () => {
    expect(featureCode("KR ST")).toBe("KR");
    expect(featureCode("  kr  ")).toBe("KR");
    expect(featureCode("kr", true)).toBe("kr");
    expect(featureCode("")).toBeNull();
  });

  it("detects codes with counts, ignoring control points", () => {
    expect(detectCodes(pts)).toEqual([
      { code: "OIK", count: 2 },
      { code: "DROM", count: 1 },
    ]);
  });

  it("assigns stable colours independent of order", () => {
    const pal = ["a", "b", "c"];
    const c1 = assignColors(["OIK", "DROM", "FRAX", "KR"], pal);
    const c2 = assignColors(["KR", "FRAX", "OIK", "DROM"], pal);
    expect(c1).toEqual(c2);
    expect(c1.DROM).toBe("a");
    expect(c1.FRAX).toBe("b");
    expect(c1.KR).toBe("c");
    expect(c1.OIK).toBe("a"); // wraps around
    expect(assignColors(["X"], [])).toEqual({});
  });
});

describe("levelling mapping", () => {
  const data: LevelingData = {
    benchmarks: [
      { id: "1", name: "BM1", h: 100 },
      { id: "2", name: " ", h: null },
    ],
    rows: [
      { id: "a", setup: 1, point: "BM1", kind: "bs", reading: 1.5, distance: 30 },
      { id: "b", setup: 1, point: "TP1", kind: "fs", reading: 1.2, distance: 31 },
      { id: "c", setup: 2, point: "TP1", kind: "bs", reading: 1.1, distance: null },
      { id: "d", setup: 2, point: "P", kind: "is", reading: 0.9, distance: null },
      { id: "e", setup: 2, point: "BM1", kind: "fs", reading: 1.4, distance: null },
    ],
    tolerance_base_mm: 0,
    tolerance_mm_per_sqrt_km: 12,
    distribute: "distance",
  };

  it("groups rows by setup, keeps order", () => {
    const s = rowsToSetups(data.rows);
    expect(s).toHaveLength(2);
    expect(s[1].readings.map((r) => r.kind)).toEqual(["bs", "is", "fs"]);
    expect(s[0].readings[0]).toEqual({ point: "BM1", reading: 1.5, kind: "bs", distance: 30 });
  });

  it("builds the request and drops incomplete benchmarks", () => {
    const req = toLevelingRequest(data);
    expect(req.benchmarks).toEqual([{ name: "BM1", h: 100 }]);
    expect(req.setups).toHaveLength(2);
    expect(req.tolerance_mm_per_sqrt_km).toBe(12);
    expect(validateLeveling(data)).toEqual([]);
  });

  it("reports problems", () => {
    const bad: LevelingData = { ...data, benchmarks: [], rows: [{ id: "x", setup: 5, point: "A", kind: "bs", reading: null, distance: null }] };
    const keys = validateLeveling(bad).map((p) => p.key);
    expect(keys).toContain("noBenchmark");
    expect(keys).toContain("missingReading");
    expect(keys).toContain("noSetups");
  });

  it("heights csv", () => {
    const csv = heightsCsv([{ name: "TP1", h: 100.3, correction: -0.0012 }]);
    expect(csv.startsWith("﻿name;H;correction\r\nTP1;100.3000;-0.0012")).toBe(true);
  });
});

describe("run diff", () => {
  const pt = (name: string, x: number, y: number, z: number | null): ResultPoint => ({ name, x, y, z, kind: "detail", n: 1 });
  const run = (points: ResultPoint[]) => ({ points }) as unknown as ProjectResult;

  it("computes per-point deltas and summary", () => {
    const a = run([pt("1", 0, 0, 10), pt("2", 5, 5, 10), pt("3", 1, 1, null)]);
    const b = run([pt("1", 0.003, 0.004, 10.002), pt("2", 5, 5, 10), pt("4", 9, 9, 9)]);
    const d = diffRuns(a, b, 0.004);
    expect(d.common).toBe(2);
    expect(d.added).toBe(1);
    expect(d.removed).toBe(1);
    expect(d.rows[0].name).toBe("1");
    expect(d.rows[0].dxy).toBeCloseTo(0.005);
    expect(d.rows[0].dz).toBeCloseTo(0.002);
    expect(d.maxDxy).toBeCloseTo(0.005);
    expect(d.over).toBe(1);
    expect(d.rmsDxy).toBeCloseTo(Math.sqrt((0.005 ** 2) / 2));
  });
});

describe("double-run levelling request", () => {
  it("parses section points and includes the return run", async () => {
    const { parseSectionPoints, toLevelingRequest, emptyLeveling } = await import("./leveling");
    expect(parseSectionPoints("Rn, Σ22;Σ23  Σ24")).toEqual(["Rn", "Σ22", "Σ23", "Σ24"]);
    const base = emptyLeveling();
    const row = (setup: number, point: string, kind: "bs" | "fs", reading: number) => ({
      id: `${setup}${point}${kind}`,
      setup,
      point,
      kind,
      reading,
      distance: null,
    });
    const d = {
      ...base,
      benchmarks: [{ id: "b", name: "A", h: 100 }],
      rows: [row(1, "A", "bs", 1.5), row(1, "B", "fs", 1.0)],
      return_rows: [row(1, "B", "bs", 1.0), row(1, "A", "fs", 1.5)],
      section_points: "A, B",
    };
    const req = toLevelingRequest(d);
    expect(req.return_setups).toHaveLength(1);
    expect(req.section_points).toEqual(["A", "B"]);
    const single = toLevelingRequest({ ...d, return_rows: [] });
    expect(single.return_setups).toBeNull();
    expect(single.section_points).toBeNull();
  });
});
