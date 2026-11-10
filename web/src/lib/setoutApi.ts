// Client and types for /v1/setout/* (mirror engine/src/atsurvey/core/setout.py and
// alignment_models.py). Angles in radians, distances in metres, x = Easting, y = Northing.
import { postJson } from "./api";
import type { Issue, ReductionSettings } from "./types";

export interface SPoint {
  name?: string | null;
  x: number;
  y: number;
  z?: number | null;
}

// ------------------------------------------------------------------- batch setting out

export interface SetoutRequest {
  station: SPoint;
  backsight?: SPoint | null;
  backsight_azimuth?: number | null;
  instrument_height?: number;
  target_height?: number;
  points: SPoint[];
  reduction?: ReductionSettings | null;
}

export interface SetoutRow {
  index: number;
  name: string | null;
  de: number;
  dn: number;
  azimuth: number;
  /** Horizontal direction to set, clockwise from the backsight (rad) */
  direction: number;
  distance_grid: number;
  /** Horizontal distance to set: ground distance when reduced */
  distance: number;
  scale: number | null;
  dz: number | null;
  zenith: number | null;
  slope_distance: number | null;
}

export interface SetoutResult {
  zero_azimuth: number;
  backsight_distance_grid: number | null;
  backsight_distance: number | null;
  rows: SetoutRow[];
  field_order: number[];
  issues: Issue[];
}

// --------------------------------------------------------------------- as-staked check

export interface CheckRequest {
  design: SPoint[];
  measured: SPoint[];
  tolerance_xy: number;
  tolerance_z?: number | null;
  reference_line?: { a: SPoint; b: SPoint } | null;
}

export interface CheckRow {
  name: string;
  design_x: number;
  design_y: number;
  design_z: number | null;
  x: number;
  y: number;
  z: number | null;
  dx: number;
  dy: number;
  dz: number | null;
  radial: number;
  along: number | null;
  across: number | null;
  ok_xy: boolean;
  ok_z: boolean | null;
  ok: boolean;
}

export interface CheckSummary {
  matched: number;
  out_of_tolerance: number;
  out_xy: number;
  out_z: number;
  max_radial: number;
  rms_radial: number;
  mean_dx: number;
  mean_dy: number;
  max_abs_dz: number | null;
  rms_dz: number | null;
  mean_dz: number | null;
}

export interface CheckResult {
  rows: CheckRow[];
  summary: CheckSummary | null;
  unmatched_design: string[];
  unmatched_measured: string[];
  issues: Issue[];
}

// --------------------------------------------------------------------------- alignment

export interface AlignmentVertex {
  name?: string | null;
  x: number;
  y: number;
  radius?: number | null;
  a_in?: number | null;
  l_in?: number | null;
  a_out?: number | null;
  l_out?: number | null;
}

export interface ProfilePVI {
  name?: string | null;
  chainage: number;
  elevation: number;
  length?: number | null;
  radius?: number | null;
}

export interface AlignmentRequest {
  vertices: AlignmentVertex[];
  start_chainage?: number;
  profile?: { pvis: ProfilePVI[] } | null;
}

export type MainPointCode = "BP" | "TS" | "SC" | "MC" | "CS" | "ST" | "PC" | "PT" | "EP";

export interface VertexRow {
  name: string | null;
  x: number;
  y: number;
  deflection: number | null;
  radius: number | null;
  a_in: number | null;
  l_in: number | null;
  a_out: number | null;
  l_out: number | null;
  tau_in: number | null;
  tau_out: number | null;
  shift_in: number | null;
  shift_out: number | null;
  xm_in: number | null;
  xm_out: number | null;
  t_in: number | null;
  t_out: number | null;
  arc_angle: number | null;
  arc_length: number | null;
  curve_length: number | null;
  external: number | null;
  centre_x: number | null;
  centre_y: number | null;
  chainage_start: number | null;
  chainage_end: number | null;
}

export interface AlignmentElement {
  kind: "tangent" | "clothoid" | "arc";
  vertex: string | null;
  start_chainage: number;
  end_chainage: number;
  length: number;
  start_x: number;
  start_y: number;
  end_x: number;
  end_y: number;
  start_azimuth: number;
  end_azimuth: number;
  radius: number | null;
  a: number | null;
  turn: "left" | "right" | null;
}

export interface MainPoint {
  code: MainPointCode;
  vertex: string | null;
  chainage: number;
  x: number;
  y: number;
  azimuth: number;
  z: number | null;
}

export interface VerticalCurveRow {
  name: string | null;
  chainage: number;
  elevation: number;
  kind: "crest" | "sag" | "none";
  length: number;
  radius: number | null;
  pvc_chainage: number;
  pvc_elevation: number;
  pvt_chainage: number;
  pvt_elevation: number;
  extreme_chainage: number | null;
  extreme_elevation: number | null;
}

export interface AlignmentResult {
  vertices: VertexRow[];
  elements: AlignmentElement[];
  main_points: MainPoint[];
  start_chainage: number;
  end_chainage: number;
  length: number;
  polyline: [number, number][];
  profile: { grades: { from_chainage: number; to_chainage: number; grade: number }[]; curves: VerticalCurveRow[] } | null;
  issues: Issue[];
}

export interface LocateRequest {
  alignment: AlignmentRequest;
  stations?: { name?: string | null; chainage: number; offset?: number }[];
  points?: SPoint[];
}

export interface StationRow {
  name: string | null;
  chainage: number;
  offset: number;
  x: number;
  y: number;
  azimuth: number;
  z: number | null;
  inside: boolean;
}

export interface PointRow {
  name: string | null;
  x: number;
  y: number;
  chainage: number;
  offset: number;
  azimuth: number;
  element: number | null;
  inside: boolean;
  z_design: number | null;
  dz: number | null;
}

export interface LocateResult {
  stations: StationRow[];
  points: PointRow[];
}

export interface AlignmentStakeoutRequest {
  alignment: AlignmentRequest;
  interval: number;
  offsets: number[];
  include_main_points?: boolean;
  from_chainage?: number | null;
  to_chainage?: number | null;
}

export interface AlignmentStakeoutRow {
  chainage: number;
  offset: number;
  code: MainPointCode | null;
  vertex: string | null;
  x: number;
  y: number;
  azimuth: number;
  z: number | null;
}

export const setoutApi = {
  points: (r: SetoutRequest) => postJson<SetoutResult>("/v1/setout/points", r),
  check: (r: CheckRequest) => postJson<CheckResult>("/v1/setout/check", r),
  alignment: (r: AlignmentRequest) => postJson<AlignmentResult>("/v1/setout/alignment", r),
  locate: (r: LocateRequest) => postJson<LocateResult>("/v1/setout/alignment/locate", r),
  stakeout: (r: AlignmentStakeoutRequest) => postJson<{ rows: AlignmentStakeoutRow[] }>("/v1/setout/alignment/stakeout", r),
};

// ------------------------------------------------------------------------ pure helpers

/** Chainage label in Greek road-design style: 1234.5 → "1+234.50". */
export function formatChainage(ch: number, decimals = 2): string {
  if (!Number.isFinite(ch)) return "—";
  const sign = ch < 0 ? "-" : "";
  const abs = Math.abs(ch);
  const fixed = abs.toFixed(decimals);
  const [intPart, frac] = fixed.split(".");
  const km = Math.floor(Number(intPart) / 1000);
  const m = String(Number(intPart) % 1000).padStart(3, "0");
  return `${sign}${km}+${m}${frac !== undefined ? `.${frac}` : ""}`;
}

/** Parse "1+234.50", "1234.5" or "1234,5" into metres; null if unreadable. */
export function parseChainage(text: string): number | null {
  const t = text.trim().replace(",", ".");
  if (!t) return null;
  const m = /^(-?)(\d+)\+(\d+(?:\.\d*)?)$/.exec(t);
  if (m) {
    const v = Number(m[2]) * 1000 + Number(m[3]);
    return m[1] ? -v : v;
  }
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

/**
 * Parse the vertex table typed or pasted as text, one vertex per line:
 * "name x y [R [A1 [A2]]]". Use "-" or nothing for "no value". Clothoids are given by A
 * (parameter); prefix with L (e.g. "L60") to give the length instead.
 */
export function parseVertices(text: string): { vertices: AlignmentVertex[]; bad: string[] } {
  const vertices: AlignmentVertex[] = [];
  const bad: string[] = [];
  const num = (s: string | undefined) => {
    if (s === undefined || s === "" || s === "-") return null;
    const n = Number(s.replace(",", "."));
    return Number.isFinite(n) ? n : Number.NaN;
  };
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const parts = line.split(/[\s;\t]+/).filter(Boolean);
    const hasName = !Number.isFinite(Number(parts[0]?.replace(",", ".")));
    const name = hasName ? parts.shift()! : null;
    const [x, y, r] = [num(parts[0]), num(parts[1]), num(parts[2])];
    const spiral = (s: string | undefined) => {
      if (s === undefined || s === "-") return {};
      const isLength = /^l/i.test(s);
      const v = num(isLength ? s.slice(1) : s);
      return isLength ? { l: v } : { a: v };
    };
    const s1 = spiral(parts[3]);
    const s2 = spiral(parts[4]);
    const values = [x, y, r, s1.a, s1.l, s2.a, s2.l];
    if (x === null || y === null || values.some((v) => v !== undefined && v !== null && Number.isNaN(v))) {
      bad.push(line);
      continue;
    }
    vertices.push({
      name,
      x,
      y,
      radius: r,
      a_in: s1.a ?? null,
      l_in: s1.l ?? null,
      a_out: s2.a ?? null,
      l_out: s2.l ?? null,
    });
  }
  return { vertices, bad };
}

/** Parse PVIs: "[name] chainage elevation [L | H<param>]", chainage as 1+234.5 or 1234.5. */
export function parseProfile(text: string): { pvis: ProfilePVI[]; bad: string[] } {
  const pvis: ProfilePVI[] = [];
  const bad: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const parts = line.split(/[\s;\t]+/).filter(Boolean);
    const name = parts.length >= 3 && parseChainage(parts[0]) === null ? parts.shift()! : null;
    const ch = parseChainage(parts[0] ?? "");
    const z = parseChainage(parts[1] ?? "") === null ? null : Number((parts[1] ?? "").replace(",", "."));
    const curve = parts[2];
    const isH = curve !== undefined && /^h/i.test(curve);
    const cv = curve === undefined ? null : Number((isH ? curve.slice(1) : curve).replace(",", "."));
    if (ch === null || z === null || !Number.isFinite(z) || (cv !== null && !Number.isFinite(cv))) {
      bad.push(line);
      continue;
    }
    pvis.push({ name, chainage: ch, elevation: z, length: isH ? null : cv, radius: isH ? cv : null });
  }
  return { pvis, bad };
}

const BOM = "﻿";

function csv(head: string[], body: (string | number)[][]): string {
  return BOM + [head, ...body].map((r) => r.join(";")).join("\r\n") + "\r\n";
}

const f3 = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? "" : v.toFixed(3));

/** Field CSV of a setting-out run. `angle` converts radians to the display unit text. */
export function setoutCsv(rows: SetoutRow[], order: number[], angle: (rad: number) => string, unit: string): string {
  return csv(
    ["point", `direction_${unit}`, "distance_m", "distance_grid_m", "dE_m", "dN_m", "dZ_m", `zenith_${unit}`, "slope_m"],
    order.map((k) => {
      const r = rows[k];
      return [r.name ?? String(k + 1), angle(r.direction), f3(r.distance), f3(r.distance_grid), f3(r.de), f3(r.dn), f3(r.dz), r.zenith === null ? "" : angle(r.zenith), f3(r.slope_distance)];
    }),
  );
}

export function checkCsv(rows: CheckRow[]): string {
  return csv(
    ["point", "design_x", "design_y", "design_z", "x", "y", "z", "dX_m", "dY_m", "dZ_m", "radial_m", "along_m", "across_m", "ok"],
    rows.map((r) => [r.name, f3(r.design_x), f3(r.design_y), f3(r.design_z), f3(r.x), f3(r.y), f3(r.z), f3(r.dx), f3(r.dy), f3(r.dz), f3(r.radial), f3(r.along), f3(r.across), r.ok ? "OK" : "OUT"]),
  );
}

/** Stakeout list: one row per point with a generated name "<chainage>[L|R<offset>]". */
export function stakeoutCsv(rows: AlignmentStakeoutRow[], angle: (rad: number) => string, unit: string): string {
  return csv(
    ["point", "chainage", "offset_m", "code", "x", "y", "z", `azimuth_${unit}`],
    rows.map((r) => [stakeoutName(r), formatChainage(r.chainage, 3), f3(r.offset), r.code ?? "", f3(r.x), f3(r.y), f3(r.z), angle(r.azimuth)]),
  );
}

/** Field name of a stakeout point: "0+120.00" on the axis, "0+120.00R3.50" right, "…L3.50" left. */
export function stakeoutName(r: { chainage: number; offset: number }): string {
  const base = formatChainage(r.chainage, 2);
  if (Math.abs(r.offset) < 5e-4) return base;
  return `${base}${r.offset < 0 ? "L" : "R"}${Math.abs(r.offset).toFixed(2)}`;
}

/** Fit points into an SVG viewBox with north up (SVG y grows downwards). */
export function svgFrame(xs: number[], ys: number[], pad = 0.06): { minX: number; maxY: number; width: number; height: number; toSvg: (x: number, y: number) => [number, number] } {
  const finite = (a: number[]) => a.filter(Number.isFinite);
  const fx = finite(xs);
  const fy = finite(ys);
  const minX0 = fx.length ? Math.min(...fx) : 0;
  const maxX0 = fx.length ? Math.max(...fx) : 1;
  const minY0 = fy.length ? Math.min(...fy) : 0;
  const maxY0 = fy.length ? Math.max(...fy) : 1;
  const span = Math.max(maxX0 - minX0, maxY0 - minY0, 1e-3);
  const minX = minX0 - span * pad;
  const maxY = maxY0 + span * pad;
  const width = maxX0 - minX0 + 2 * span * pad;
  const height = maxY0 - minY0 + 2 * span * pad;
  return { minX, maxY, width, height, toSvg: (x, y) => [x - minX, maxY - y] };
}
