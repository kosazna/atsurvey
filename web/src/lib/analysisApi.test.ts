import { describe, expect, it } from "vitest";
import { autoEllipseScale, buildRequest, connectedPairs, derivePlan, fromCc, toCc, type PlannedRow } from "./analysisApi";
import type { ResultPoint, Setup } from "./types";

let n = 0;
const makeId = () => `id${++n}`;

const control = [
  { name: "K1", x: 0, y: 0 },
  { name: "K2", x: 500, y: 0 },
];
const rp = (name: string, x: number, y: number, kind: ResultPoint["kind"]): ResultPoint => ({ name, x, y, z: null, kind, n: 1 });
const resultPoints = [rp("K1", 0, 0, "control"), rp("S1", 200, 100, "traverse"), rp("S2", 350, 120, "traverse"), rp("d1", 210, 140, "detail")];
const setups: Setup[] = [
  {
    station: "S1",
    id: "a",
    observations: [
      { target: "K1", hz: 0, v: 1.5, sd: 223.6 },
      { target: "K1", hz: 3.14, v: 4.7, sd: 223.6 }, // face II: collapses
      { target: "S2", hz: 1, v: 1.57, sd: 151.3 },
      { target: "d1", hz: 2, sd: 41 }, // detail point: not part of the network
      { target: "K2", hz: 2.5, excluded: true },
    ],
  },
  { station: "S2", observations: [{ target: "S1", hz: 0 }, { target: "K2", hz: 1, sd: 192 }] },
];

describe("derivePlan", () => {
  it("takes control as fixed, stations/traverse points as new, and collapses faces", () => {
    const { points, rows } = derivePlan({ control_points: control, setups, resultPoints }, false, makeId);
    expect(points.map((p) => [p.name, p.fixed])).toEqual([
      ["K1", true],
      ["K2", true],
      ["S1", false],
      ["S2", false],
    ]);
    expect(rows.map((r) => `${r.kind}:${r.station}>${r.target}@${r.setup}`)).toEqual([
      "direction:S1>K1@a",
      "distance:S1>K1@a",
      "direction:S1>S2@a",
      "distance:S1>S2@a",
      "direction:S2>S1@S2#2",
      "direction:S2>K2@S2#2",
      "distance:S2>K2@S2#2",
    ]);
    expect(rows.every((r) => r.enabled)).toBe(true);
  });

  it("adds height differences only when asked and a zenith angle exists", () => {
    const { rows } = derivePlan({ control_points: control, setups, resultPoints }, true, makeId);
    expect(rows.filter((r) => r.kind === "height").map((r) => r.target)).toEqual(["K1", "S2"]);
  });
});

describe("request building", () => {
  const points = [
    { name: "K1", x: 0, y: 0, fixed: true },
    { name: "K2", x: 500, y: 0, fixed: true },
    { name: "S1", x: 200, y: 100, fixed: false },
    { name: "Z", x: 9, y: 9, fixed: false },
  ];
  const row = (kind: PlannedRow["kind"], station: string, target: string, enabled = true): PlannedRow => ({ id: makeId(), kind, station, target, enabled });

  it("connects pairs once, skips fixed–fixed and disabled rows", () => {
    const rows = [row("direction", "S1", "K1"), row("distance", "K1", "S1"), row("direction", "K1", "K2"), row("direction", "S1", "K2", false), row("height", "S1", "K2")];
    expect(connectedPairs(rows, points)).toEqual([["K1", "S1"]]);
  });

  it("sends only enabled rows and the points they use", () => {
    const req = buildRequest(points, [row("direction", "S1", "K1"), row("distance", "S1", "Z", false)], {
      sigma_direction_cc: 10,
      sigma_distance_mm: 2,
      sigma_distance_ppm: 2,
      sigma_centering_instrument_mm: 1,
      sigma_centering_target_mm: 1,
      sigma_height_mm: 5,
    });
    expect(req.points.map((p) => p.name)).toEqual(["K1", "S1"]);
    expect(req.observations).toEqual([{ kind: "direction", station: "S1", target: "K1", setup: null }]);
  });
});

describe("units and scale", () => {
  it("converts mgon and cc", () => {
    expect(toCc(0.5, "mgon")).toBe(5);
    expect(fromCc(5, "mgon")).toBe(0.5);
    expect(toCc(7, "cc")).toBe(7);
  });

  it("chooses a 1-2-5 exaggeration so the largest ellipse is visible", () => {
    // 5 mm on a 1 km plan: 4 % of 1000 m = 40 m → ×8000 → ×5000
    expect(autoEllipseScale(0.005, 1000)).toBe(5000);
    expect(autoEllipseScale(0.02, 1000)).toBe(2000);
    expect(autoEllipseScale(0, 1000)).toBe(1);
    expect(autoEllipseScale(100, 10)).toBe(1);
  });
});
