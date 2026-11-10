import { describe, expect, it } from "vitest";
import { breaklinesFrom, chartFrame, filterPoints, parseCodes, runPaths, ticks, toSurfacePoints, type SourcePoint } from "./surfacesApi";
import type { Polyline } from "./types";

const PTS: SourcePoint[] = [
  { name: "S1", x: 0, y: 0, z: 10, kind: "traverse", code: null },
  { name: "1", x: 1, y: 0, z: 11, kind: "detail", code: "ed" },
  { name: "2", x: 2, y: 0, z: 12, kind: "detail", code: "ΚΤ" },
  { name: "3", x: 3, y: 0, z: null, kind: "detail", code: "ED" },
  { name: "T1", x: 4, y: 0, z: 9, kind: "control", code: "Τριγ" },
];

describe("surfaces helpers", () => {
  it("parses code lists", () => {
    expect(parseCodes(" ed, κτ ;x  y")).toEqual(["ED", "ΚΤ", "X", "Y"]);
    expect(parseCodes("")).toEqual([]);
  });

  it("filters by kind and code", () => {
    const names = (f: Parameters<typeof filterPoints>[1]) => filterPoints(PTS, f).map((p) => p.name);
    expect(names({ kinds: ["detail"], onlyCodes: "", excludeCodes: "" })).toEqual(["1", "2", "3"]);
    expect(names({ kinds: ["detail", "traverse"], onlyCodes: "ed", excludeCodes: "" })).toEqual(["1", "3"]);
    expect(names({ kinds: ["detail", "traverse", "control"], onlyCodes: "", excludeCodes: "κτ, τριγ" })).toEqual(["S1", "1", "3"]);
    expect(toSurfacePoints(PTS.slice(3, 4))).toEqual([{ name: "3", x: 3, y: 0, z: null }]);
  });

  it("builds breaklines from selected line codes", () => {
    const lw: Polyline[] = [
      { code: "PRANI", name: "a", points: ["1", "2", "3"], closed: false, length: 2, area: null },
      { code: "ROAD", name: "b", points: ["4", "5"], closed: true, length: 1, area: null },
      { code: "prani", name: "c", points: ["6"], closed: false, length: 0, area: null },
    ];
    expect(breaklinesFrom(lw, ["prani"])).toEqual([{ points: ["1", "2", "3"], closed: false }]);
    expect(breaklinesFrom(lw, [])).toEqual([]);
  });

  it("frames a chart and draws one path per run", () => {
    const f = chartFrame(0, 100, [10, 20], 200, 100, 10);
    expect(f.sx(0)).toBe(10);
    expect(f.sx(100)).toBe(190);
    expect(f.z0).toBeLessThanOrEqual(10);
    expect(f.z1).toBeGreaterThanOrEqual(20);
    expect(f.sy(f.z0)).toBe(90);
    const paths = runPaths(
      [
        { chainage: 0, x: 0, y: 0, z: 10, run: 0 },
        { chainage: 50, x: 0, y: 0, z: 15, run: 0 },
        { chainage: 70, x: 0, y: 0, z: 18, run: 1 },
        { chainage: 100, x: 0, y: 0, z: 20, run: 1 },
      ],
      f,
    );
    expect(paths).toHaveLength(2);
    expect(paths[0].startsWith("M10.00,")).toBe(true);
    expect(paths[1].split("L")).toHaveLength(2);
  });

  it("makes round ticks", () => {
    expect(ticks(0, 100, 5)).toEqual([0, 20, 40, 60, 80, 100]);
    expect(ticks(12.3, 17.9, 5)).toEqual([13, 14, 15, 16, 17]);
    expect(ticks(5, 5)).toEqual([5]);
  });
});
