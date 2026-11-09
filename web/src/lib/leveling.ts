// Levelling grid ↔ API request mapping and validation.
import type { LevelingRequest, LevelingSetup } from "./cogoTypes";
import type { LevelingData, LevelRow } from "@/data/store";

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

export function toLevelingRequest(d: LevelingData): LevelingRequest {
  return {
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
