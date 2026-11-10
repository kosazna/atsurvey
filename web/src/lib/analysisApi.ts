// Network pre-analysis (προανάλυση): TS mirrors of engine/src/atsurvey/core/preanalysis_models.py,
// the API client and pure helpers (derive a planned network from the project, auto ellipse scale).
// Angles in radians, lengths in metres, x = Easting, y = Northing.
import { postJson } from "./api";
import type { ControlPoint, ErrorEllipse, Issue, ResultPoint, Setup } from "./types";

export type PlannedKind = "direction" | "distance" | "height";
export type ObservationStatus = "ok" | "weak" | "uncontrolled" | "excluded";

export interface PlannedPoint {
  name: string;
  x: number;
  y: number;
  fixed: boolean;
}

export interface PlannedObservation {
  kind: PlannedKind;
  station: string;
  target: string;
  setup?: string | null;
}

export interface InstrumentSpec {
  sigma_direction_cc: number;
  sigma_distance_mm: number;
  sigma_distance_ppm: number;
  sigma_centering_instrument_mm: number;
  sigma_centering_target_mm: number;
  sigma_height_mm: number;
}

export interface PreanalysisRequest {
  points: PlannedPoint[];
  observations: PlannedObservation[];
  instrument: InstrumentSpec;
  relative_pairs?: [string, string][];
  alpha0?: number;
  beta0?: number;
}

export interface PointPrecision {
  name: string;
  sx: number | null;
  sy: number | null;
  spos: number | null;
  ellipse: ErrorEllipse | null;
  a95: number | null;
  b95: number | null;
  sz: number | null;
}

export interface RelativePrecision {
  frm: string;
  to: string;
  distance: number;
  s_distance: number;
  s_azimuth: number;
  s_transverse: number;
  ellipse: ErrorEllipse;
  a95: number;
  b95: number;
}

export interface ObservationReliability {
  kind: PlannedKind;
  station: string;
  target: string;
  sigma: number | null;
  redundancy: number;
  mdb: number | null;
  external: number | null;
  max_shift: number | null;
  max_shift_point: string | null;
  status: ObservationStatus;
}

export interface PreanalysisResult {
  n_observations: number;
  n_unknowns: number;
  dof: number;
  alpha0: number;
  beta0: number;
  delta0: number;
  lambda0: number;
  k95: number;
  points: PointPrecision[];
  relative: RelativePrecision[];
  /** Same order as the request's observations. */
  observations: ObservationReliability[];
  excluded_points: string[];
  issues: Issue[];
}

/** Request limits (mirrors preanalysis_models.py). */
export const PREANALYSIS_LIMITS = { points: 500, observations: 5000, pairs: 1000 } as const;

export const analysis = {
  preanalysis: (r: PreanalysisRequest, signal?: AbortSignal) => postJson<PreanalysisResult>("/v1/analysis/preanalysis", r, signal),
};

// ----------------------------------------------------------------------------- planning helpers

/** One editable row of the planned observation table. */
export interface PlannedRow extends PlannedObservation {
  id: string;
  enabled: boolean;
}

export interface PlanSource {
  control_points: ControlPoint[];
  setups: Setup[];
  /** Latest computed points (approximate coordinates of stations and traverse points). */
  resultPoints: ResultPoint[];
}

/**
 * Planned network from the project: control points are fixed; occupied stations and traverse
 * points with coordinates are new points; every non-excluded observation between them becomes a
 * planned direction, a distance (if measured) and optionally a height difference — one per
 * setup and target (faces and rounds collapse, as in the adjustment).
 */
export function derivePlan(src: PlanSource, includeHeights: boolean, makeId: () => string): { points: PlannedPoint[]; rows: PlannedRow[] } {
  const pts = new Map<string, PlannedPoint>();
  const control = new Set<string>();
  for (const c of src.control_points) {
    if (!c.name || !Number.isFinite(c.x) || !Number.isFinite(c.y)) continue;
    pts.set(c.name, { name: c.name, x: c.x, y: c.y, fixed: true });
    control.add(c.name);
  }
  const stations = new Set(src.setups.map((s) => s.station));
  for (const p of src.resultPoints) {
    if (control.has(p.name) || !Number.isFinite(p.x) || !Number.isFinite(p.y)) continue;
    if (p.kind === "traverse" || stations.has(p.name)) pts.set(p.name, { name: p.name, x: p.x, y: p.y, fixed: false });
  }
  const rows: PlannedRow[] = [];
  src.setups.forEach((s, i) => {
    if (!pts.has(s.station)) return;
    const setup = s.id ?? `${s.station}#${i + 1}`;
    const seen = new Set<string>();
    for (const o of s.observations) {
      if (o.excluded || o.target === s.station || !pts.has(o.target)) continue;
      const kinds: PlannedKind[] = ["direction"];
      if (o.sd && o.sd > 0) kinds.push("distance");
      if (includeHeights && o.sd && o.sd > 0 && o.v !== null && o.v !== undefined) kinds.push("height");
      for (const kind of kinds) {
        const key = `${kind}|${o.target}`;
        if (seen.has(key)) continue;
        seen.add(key);
        rows.push({ id: makeId(), enabled: true, kind, station: s.station, target: o.target, setup });
      }
    }
  });
  return { points: [...pts.values()], rows };
}

/** Unordered pairs connected by an enabled horizontal observation with at least one new point. */
export function connectedPairs(rows: PlannedRow[], points: PlannedPoint[]): [string, string][] {
  const fixed = new Set(points.filter((p) => p.fixed).map((p) => p.name));
  const seen = new Set<string>();
  const out: [string, string][] = [];
  for (const r of rows) {
    if (!r.enabled || r.kind === "height") continue;
    if (fixed.has(r.station) && fixed.has(r.target)) continue;
    const [a, b] = r.station < r.target ? [r.station, r.target] : [r.target, r.station];
    const key = `${a}\u0000${b}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push([a, b]);
  }
  return out.slice(0, PREANALYSIS_LIMITS.pairs);
}

/** Request from the table: enabled rows only, and only the points they use. */
export function buildRequest(points: PlannedPoint[], rows: PlannedRow[], instrument: InstrumentSpec): PreanalysisRequest {
  const used = rows.filter((r) => r.enabled);
  const names = new Set(used.flatMap((r) => [r.station, r.target]));
  return {
    points: points.filter((p) => names.has(p.name)),
    observations: used.map(({ kind, station, target, setup }) => ({ kind, station, target, setup: setup ?? null })),
    instrument,
    relative_pairs: connectedPairs(used, points),
  };
}

export type DirectionUnit = "cc" | "mgon";
/** 1 mgon = 10 cc. */
export function toCc(value: number, unit: DirectionUnit): number {
  return unit === "mgon" ? value * 10 : value;
}
export function fromCc(cc: number, unit: DirectionUnit): number {
  return unit === "mgon" ? cc / 10 : cc;
}

/**
 * Exaggeration for drawing ellipses on a plan of size `extent` (m): the largest 95 % semi-axis
 * becomes about `fraction` of the extent, rounded down to 1·2·5·10ⁿ. Returns 1 if nothing to draw.
 */
export function autoEllipseScale(maxSemiAxis: number, extent: number, fraction = 0.04): number {
  if (!(maxSemiAxis > 0) || !(extent > 0)) return 1;
  const raw = (fraction * extent) / maxSemiAxis;
  if (raw <= 1) return 1;
  const p = 10 ** Math.floor(Math.log10(raw));
  const m = raw / p;
  return (m >= 5 ? 5 : m >= 2 ? 2 : 1) * p;
}
