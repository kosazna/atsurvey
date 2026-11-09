import type { ProjectResult } from "./types";

export interface PointDelta {
  name: string;
  status: "both" | "added" | "removed";
  dx: number | null;
  dy: number | null;
  dz: number | null;
  /** planimetric difference √(dx²+dy²) */
  dxy: number | null;
}

export interface RunDiff {
  rows: PointDelta[];
  common: number;
  added: number;
  removed: number;
  maxDxy: number;
  maxDz: number;
  rmsDxy: number;
  /** number of common points whose planimetric difference exceeds the threshold */
  over: number;
}

/** Compare two runs point-by-point (b − a). Rows are sorted by decreasing |Δxy|. */
export function diffRuns(a: ProjectResult, b: ProjectResult, threshold = 0.005): RunDiff {
  const am = new Map(a.points.map((p) => [p.name, p]));
  const bm = new Map(b.points.map((p) => [p.name, p]));
  const rows: PointDelta[] = [];
  let maxDxy = 0;
  let maxDz = 0;
  let sum2 = 0;
  let common = 0;
  let over = 0;
  for (const [name, pa] of am) {
    const pb = bm.get(name);
    if (!pb) {
      rows.push({ name, status: "removed", dx: null, dy: null, dz: null, dxy: null });
      continue;
    }
    common++;
    const dx = pb.x - pa.x;
    const dy = pb.y - pa.y;
    const dz = pa.z !== null && pb.z !== null ? pb.z - pa.z : null;
    const dxy = Math.hypot(dx, dy);
    maxDxy = Math.max(maxDxy, dxy);
    if (dz !== null) maxDz = Math.max(maxDz, Math.abs(dz));
    sum2 += dxy * dxy;
    if (dxy > threshold) over++;
    rows.push({ name, status: "both", dx, dy, dz, dxy });
  }
  for (const [name] of bm) {
    if (!am.has(name)) rows.push({ name, status: "added", dx: null, dy: null, dz: null, dxy: null });
  }
  rows.sort((r1, r2) => (r2.dxy ?? -1) - (r1.dxy ?? -1) || r1.name.localeCompare(r2.name, undefined, { numeric: true }));
  return {
    rows,
    common,
    added: rows.filter((r) => r.status === "added").length,
    removed: rows.filter((r) => r.status === "removed").length,
    maxDxy,
    maxDz,
    rmsDxy: common ? Math.sqrt(sum2 / common) : 0,
    over,
  };
}
