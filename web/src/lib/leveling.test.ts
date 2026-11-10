import { describe, expect, it } from "vitest";
import type { LevelingData, LevelRow } from "@/data/store";
import { emptyLeveling, emptyNetwork, networkHeightsCsv, readingsToNetworkLines, runToNetworkLines, toLevelNetRequest, validateNetwork } from "./leveling";

let n = 0;
const row = (setup: number, point: string, kind: "bs" | "fs" | "is", reading: number, distance: number | null = 25): LevelRow => ({
  id: String(n++),
  setup,
  point,
  kind,
  reading,
  distance,
});

// RM1 → K1 → A → K2 → RM2, A is a section point
const FORWARD: LevelRow[] = [
  row(1, "RM1", "bs", 1.5),
  row(1, "X", "is", 1.0),
  row(1, "K1", "fs", 1.2),
  row(2, "K1", "bs", 1.4),
  row(2, "A", "fs", 1.0),
  row(3, "A", "bs", 1.3),
  row(3, "K2", "fs", 1.1),
  row(4, "K2", "bs", 1.6),
  row(4, "RM2", "fs", 1.5),
];

describe("runToNetworkLines", () => {
  it("collapses setups into lines between node points", () => {
    const lines = runToNetworkLines(FORWARD, new Set(["RM1", "RM2", "A"]));
    expect(lines).toHaveLength(2);
    expect(lines[0]).toMatchObject({ frm: "RM1", to: "A", setups: 2 });
    expect(lines[0].dh).toBeCloseTo(0.3 + 0.4, 12);
    expect(lines[0].length_km).toBeCloseTo(0.1, 12);
    expect(lines[1]).toMatchObject({ frm: "A", to: "RM2", setups: 2 });
    expect(lines[1].dh).toBeCloseTo(0.2 + 0.1, 12);
  });

  it("ends an open run on its last point and drops length when a distance is missing", () => {
    const rows = [...FORWARD.slice(0, 5), row(3, "A", "bs", 1.3, null), row(3, "Z", "fs", 1.1)];
    const lines = runToNetworkLines(rows, new Set(["RM1"]));
    expect(lines).toEqual([{ frm: "RM1", to: "Z", dh: expect.closeTo(0.9, 12), length_km: null, setups: 3 }]);
  });

  it("drops lines that return to their start", () => {
    const loop = [row(1, "RM1", "bs", 1.5), row(1, "K", "fs", 1.2), row(2, "K", "bs", 1.1), row(2, "RM1", "fs", 1.4)];
    expect(runToNetworkLines(loop, new Set(["RM1"]))).toEqual([]);
  });
});

describe("network request", () => {
  const base: LevelingData = {
    ...emptyLeveling(),
    benchmarks: [
      { id: "1", name: "RM1", h: 100 },
      { id: "2", name: "RM2", h: 101 },
      { id: "3", name: "", h: null },
    ],
    rows: FORWARD,
    section_points: "A",
  };

  it("builds lines from forward and return runs", () => {
    const back = [row(1, "RM2", "bs", 1.5), row(1, "RM1", "fs", 2.5)];
    const lines = readingsToNetworkLines({ ...base, return_rows: back });
    expect(lines.map((l) => `${l.frm}-${l.to}`)).toEqual(["RM1-A", "A-RM2", "RM2-RM1"]);
  });

  it("maps to the API request and validates rows", () => {
    const net = {
      ...emptyNetwork(),
      lines: [
        { id: "a", frm: " RM1 ", to: "A", dh: 0.7, length_km: 0.1, setups: 2 },
        { id: "b", frm: "A", to: "A", dh: null, length_km: null, setups: null },
      ],
    };
    const req = toLevelNetRequest(base, net);
    expect(req.benchmarks).toEqual([
      { name: "RM1", h: 100 },
      { name: "RM2", h: 101 },
    ]);
    expect(req.lines).toEqual([{ frm: "RM1", to: "A", dh: 0.7, length_km: 0.1, setups: 2 }]);
    expect(req.free_points).toBeNull();
    expect(validateNetwork(base, net).map((p) => `${p.key}${p.row}`)).toEqual(["samePoint2", "missingDh2", "missingWeight2"]);
    expect(validateNetwork({ ...base, benchmarks: [] }, { ...net, lines: [] }).map((p) => p.key)).toEqual(["noLines", "noBenchmark"]);
    const free = toLevelNetRequest(base, { ...net, datum: "free", free_points: "RM1, A" });
    expect(free.free_points).toEqual(["RM1", "A"]);
  });

  it("writes a heights CSV with σ in mm", () => {
    expect(networkHeightsCsv([{ name: "A", h: 100.70004, sigma_h: 0.00123 }])).toBe("﻿name;H;sigma_mm\r\nA;100.7000;1.23\r\n");
  });
});
