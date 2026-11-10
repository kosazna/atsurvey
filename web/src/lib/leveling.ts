// Levelling grid ↔ API request mapping and validation.
import type { LevelingRequest, LevelingSetup } from "./cogoTypes";
import type { LevelingData, LevelRow } from "@/data/store";
import type { LevelNetDatum, LevelNetRequest, LevelNetWeighting } from "./instrumentsApi";

export interface LevelingProblem {
  setup: number | null;
  key: "noBenchmark" | "noSetups" | "setupNeedsBsFs" | "missingReading" | "missingPoint" | "startNotBenchmark";
}

/** Group grid rows by setup number (in order of first appearance) into API setups. */
export function rowsToSetups(rows: LevelRow[]): LevelingSetup[] {
  const order: number[] = [];
  const groups = new Map<number, LevelRow[]>();
  for (const r of rows) {
    if (!groups.has(r.setup)) {
      groups.set(r.setup, []);
      order.push(r.setup);
    }
    groups.get(r.setup)!.push(r);
  }
  return order.map((n) => ({
    readings: groups
      .get(n)!
      .filter((r) => r.point.trim() !== "" && r.reading !== null && Number.isFinite(r.reading))
      .map((r) => ({
        point: r.point.trim(),
        reading: r.reading as number,
        kind: r.kind,
        distance: r.distance ?? null,
      })),
  }));
}

export function validateLeveling(d: LevelingData): LevelingProblem[] {
  const problems: LevelingProblem[] = [];
  const bms = d.benchmarks.filter((b) => b.name.trim() && b.h !== null && Number.isFinite(b.h));
  if (!bms.length) problems.push({ setup: null, key: "noBenchmark" });
  const setups = rowsToSetups(d.rows);
  if (!setups.some((s) => s.readings.length >= 2)) problems.push({ setup: null, key: "noSetups" });
  const setupNumbers = [...new Set(d.rows.map((r) => r.setup))];
  setups.forEach((s, i) => {
    const n = setupNumbers[i];
    const kinds = s.readings.map((r) => r.kind);
    if (!kinds.includes("bs") || !kinds.includes("fs")) problems.push({ setup: n, key: "setupNeedsBsFs" });
  });
  for (const r of d.rows) {
    if (!r.point.trim()) problems.push({ setup: r.setup, key: "missingPoint" });
    else if (r.reading === null || !Number.isFinite(r.reading)) problems.push({ setup: r.setup, key: "missingReading" });
  }
  const first = setups[0]?.readings.find((r) => r.kind === "bs");
  if (first && bms.length && !bms.some((b) => b.name.trim() === first.point)) problems.push({ setup: setupNumbers[0], key: "startNotBenchmark" });
  return problems;
}

/** Parse "Σ22, Σ23 Σ24" into point names. */
export function parseSectionPoints(text: string | undefined): string[] {
  return (text ?? "")
    .split(/[\s,;]+/)
    .map((p) => p.trim())
    .filter(Boolean);
}

export function toLevelingRequest(d: LevelingData): LevelingRequest {
  const ret = rowsToSetups(d.return_rows ?? []).filter((s) => s.readings.length >= 2);
  const sections = parseSectionPoints(d.section_points);
  return {
    return_setups: ret.length ? ret : null,
    section_points: ret.length && sections.length ? sections : null,
    benchmarks: d.benchmarks
      .filter((b) => b.name.trim() && b.h !== null && Number.isFinite(b.h))
      .map((b) => ({ name: b.name.trim(), h: b.h as number })),
    setups: rowsToSetups(d.rows).filter((s) => s.readings.length >= 2),
    tolerance_base_mm: d.tolerance_base_mm,
    tolerance_mm_per_sqrt_km: d.tolerance_mm_per_sqrt_km,
    distribute: d.distribute,
  };
}

export function emptyLeveling(): LevelingData {
  return { benchmarks: [], rows: [], tolerance_base_mm: 0, tolerance_mm_per_sqrt_km: 12, distribute: "distance" };
}

/** CSV of computed heights (name;H;correction) with a UTF-8 BOM for Excel. */
export function heightsCsv(points: { name: string; h: number; correction: number }[], sep = ";"): string {
  const lines = [["name", "H", "correction"].join(sep), ...points.map((p) => [p.name, p.h.toFixed(4), p.correction.toFixed(4)].join(sep))];
  return "﻿" + lines.join("\r\n") + "\r\n";
}

// ------------------------------------------------------------------ levelling network

/** One row of the network lines grid (persisted in extras.leveling.network). */
export interface LevelNetRow {
  id: string;
  frm: string;
  to: string;
  /** measured H(to) − H(frm), m */
  dh: number | null;
  length_km: number | null;
  setups: number | null;
}

export interface LevelNetData {
  lines: LevelNetRow[];
  weighting: LevelNetWeighting;
  sigma_mm_per_sqrt_km: number;
  sigma_mm_per_setup: number;
  datum: LevelNetDatum;
  /** Free network: points whose mean height is kept (comma/space separated; empty = benchmarks) */
  free_points: string;
}

export type LevelNetProblemKey = "noLines" | "noBenchmark" | "samePoint" | "missingDh" | "missingWeight";

export interface LevelNetProblem {
  row: number | null;
  key: LevelNetProblemKey;
}

export function emptyNetwork(): LevelNetData {
  return { lines: [], weighting: "length", sigma_mm_per_sqrt_km: 2, sigma_mm_per_setup: 0.5, datum: "fixed", free_points: "" };
}

function validBenchmarks(d: LevelingData): { name: string; h: number }[] {
  return d.benchmarks
    .filter((b) => b.name.trim() && b.h !== null && Number.isFinite(b.h))
    .map((b) => ({ name: b.name.trim(), h: b.h as number }));
}

function rowWeight(r: LevelNetRow, weighting: LevelNetWeighting): number | null {
  const v = weighting === "length" ? r.length_km : r.setups;
  return v !== null && Number.isFinite(v) && v > 0 ? v : null;
}

export function validateNetwork(d: LevelingData, net: LevelNetData): LevelNetProblem[] {
  const problems: LevelNetProblem[] = [];
  if (!net.lines.length) problems.push({ row: null, key: "noLines" });
  if (net.datum === "fixed" && !validBenchmarks(d).length) problems.push({ row: null, key: "noBenchmark" });
  net.lines.forEach((r, i) => {
    if (r.frm.trim() && r.frm.trim() === r.to.trim()) problems.push({ row: i + 1, key: "samePoint" });
    if (r.dh === null || !Number.isFinite(r.dh)) problems.push({ row: i + 1, key: "missingDh" });
    if (rowWeight(r, net.weighting) === null) problems.push({ row: i + 1, key: "missingWeight" });
  });
  return problems;
}

export function toLevelNetRequest(d: LevelingData, net: LevelNetData): LevelNetRequest {
  const free = parseSectionPoints(net.free_points);
  return {
    benchmarks: validBenchmarks(d),
    lines: net.lines
      .filter((r) => r.frm.trim() && r.to.trim() && r.dh !== null && Number.isFinite(r.dh))
      .map((r) => ({
        frm: r.frm.trim(),
        to: r.to.trim(),
        dh: r.dh as number,
        length_km: r.length_km !== null && r.length_km > 0 ? r.length_km : null,
        setups: r.setups !== null && r.setups >= 1 ? Math.round(r.setups) : null,
      })),
    weighting: net.weighting,
    sigma_mm_per_sqrt_km: net.sigma_mm_per_sqrt_km,
    sigma_mm_per_setup: net.sigma_mm_per_setup,
    datum: net.datum,
    free_points: net.datum === "free" && free.length ? free : null,
    tolerance_base_mm: d.tolerance_base_mm,
    tolerance_mm_per_sqrt_km: d.tolerance_mm_per_sqrt_km,
  };
}

type NetLine = Omit<LevelNetRow, "id">;

/**
 * Collapse one run of readings into network lines that break at the node points (benchmarks
 * and section points). Δh = Σ(bs − fs), length = Σ sight lengths (km, null if any is missing),
 * setups = number of setups. Intermediate sights do not take part. A break in the chain of
 * setups (backsight ≠ previous foresight) starts a new line; lines that return to their start
 * (Δh of a closed loop) carry no height information and are dropped.
 */
export function runToNetworkLines(rows: LevelRow[], nodes: ReadonlySet<string>): NetLine[] {
  const out: NetLine[] = [];
  let cur: { frm: string; at: string; dh: number; m: number | null; n: number } | null = null;
  const close = () => {
    if (cur && cur.n > 0 && cur.frm !== cur.at)
      out.push({ frm: cur.frm, to: cur.at, dh: cur.dh, length_km: cur.m === null ? null : cur.m / 1000, setups: cur.n });
  };
  for (const s of rowsToSetups(rows)) {
    const bs = s.readings.find((r) => r.kind === "bs");
    const fs = s.readings.find((r) => r.kind === "fs");
    if (!bs || !fs) continue;
    if (!cur || cur.at !== bs.point) {
      close();
      cur = { frm: bs.point, at: bs.point, dh: 0, m: 0, n: 0 };
    }
    const sight = bs.distance !== null && bs.distance !== undefined && fs.distance !== null && fs.distance !== undefined ? bs.distance + fs.distance : null;
    cur = { ...cur, at: fs.point, dh: cur.dh + bs.reading - fs.reading, m: cur.m === null || sight === null ? null : cur.m + sight, n: cur.n + 1 };
    if (nodes.has(fs.point)) {
      close();
      cur = { frm: fs.point, at: fs.point, dh: 0, m: 0, n: 0 };
    }
  }
  close();
  return out;
}

/** Network lines from the section's readings: forward and return runs become separate lines. */
export function readingsToNetworkLines(d: LevelingData): NetLine[] {
  const nodes = new Set([...validBenchmarks(d).map((b) => b.name), ...parseSectionPoints(d.section_points)]);
  return [...runToNetworkLines(d.rows, nodes), ...runToNetworkLines(d.return_rows ?? [], nodes)];
}

/** CSV of adjusted network heights (name;H;σH mm) with a UTF-8 BOM for Excel. */
export function networkHeightsCsv(points: { name: string; h: number; sigma_h: number }[], sep = ";"): string {
  const lines = [["name", "H", "sigma_mm"].join(sep), ...points.map((p) => [p.name, p.h.toFixed(4), (p.sigma_h * 1000).toFixed(2)].join(sep))];
  return "﻿" + lines.join("\r\n") + "\r\n";
}
