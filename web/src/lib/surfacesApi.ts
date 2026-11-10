// Surfaces (ανάγλυφο): TypeScript mirrors of engine/src/atsurvey/core/surfaces/models.py, the
// /v1/surfaces/* client and small pure helpers (point selection, breaklines, profile chart).
// x = Easting, y = Northing, z = orthometric height, metres (ΕΓΣΑ87).
import { filenameFrom, postJson, request } from "./api";
import type { Issue, PointKind, Polyline } from "./types";

export const MAX_SURFACE_POINTS = 50_000;

export interface SurfacePoint {
  name?: string | null;
  x: number;
  y: number;
  z?: number | null;
}

export interface PlanXY {
  x: number;
  y: number;
}

export interface NamedXY extends PlanXY {
  name?: string | null;
}

export interface Breakline {
  points: string[];
  closed?: boolean;
}

export interface SurfaceSpec {
  points: SurfacePoint[];
  breaklines?: Breakline[];
  boundary?: PlanXY[] | null;
  max_edge?: number | null;
  duplicate_tolerance?: number;
}

export interface DuplicateGroup {
  kept: string | null;
  merged: (string | null)[];
  dz: number;
}

export interface SurfaceStats {
  points_in: number;
  points_without_z: number;
  duplicates_merged: number;
  vertices: number;
  triangles: number;
  z_min: number;
  z_max: number;
  area_2d: number;
  area_3d: number;
  breakline_segments: number;
  trimmed_triangles: number;
}

export interface SurfaceResult {
  stats: SurfaceStats;
  outline: [number, number][][];
  duplicates: DuplicateGroup[];
  issues: Issue[];
}

export interface ContoursRequest {
  surface: SurfaceSpec;
  interval: number;
  base?: number;
  index_every?: number;
}

export interface ContourLine {
  z: number;
  index: boolean;
  closed: boolean;
  points: [number, number][];
}

export interface ContoursResult {
  surface: SurfaceResult;
  interval: number;
  base: number;
  levels: number[];
  lines: ContourLine[];
  issues: Issue[];
}

export interface HeightsRequest {
  surface: SurfaceSpec;
  points: NamedXY[];
}

export interface HeightRow {
  name: string | null;
  x: number;
  y: number;
  z: number | null;
  inside: boolean;
}

export interface HeightsResult {
  surface: SurfaceResult;
  rows: HeightRow[];
  issues: Issue[];
}

export interface LevelVolumeRequest {
  surface: SurfaceSpec;
  level: number;
}

export interface SurfaceVolumeRequest {
  existing: SurfaceSpec;
  design: SurfaceSpec;
  boundary?: PlanXY[] | null;
}

export interface VolumeResult {
  method: string;
  reference: "level" | "surface";
  level: number | null;
  cut: number;
  fill: number;
  net: number;
  cut_area: number;
  fill_area: number;
  area: number;
  surfaces: SurfaceResult[];
  issues: Issue[];
}

export interface ProfileRequest {
  surface: SurfaceSpec;
  alignment: PlanXY[];
  section_interval?: number | null;
  half_width?: number;
}

export interface ProfileStation {
  chainage: number;
  x: number;
  y: number;
  z: number;
  run: number;
}

export interface CrossSection {
  chainage: number;
  x: number;
  y: number;
  z: number | null;
  azimuth: number;
  stations: ProfileStation[];
}

export interface ProfileResult {
  surface: SurfaceResult;
  length: number;
  stations: ProfileStation[];
  sections: CrossSection[];
  issues: Issue[];
}

export type SurfaceExportContent = "contours" | "heights" | "volume" | "profile";

export interface SurfaceExportRequest {
  format: "dxf" | "csv";
  content: SurfaceExportContent;
  project_name?: string;
  contours?: ContoursRequest | null;
  heights?: HeightsRequest | null;
  volume_level?: LevelVolumeRequest | null;
  volume_surfaces?: SurfaceVolumeRequest | null;
  profile?: ProfileRequest | null;
  include_tin?: boolean;
  include_points?: boolean;
  text_height?: number;
  vertical_exaggeration?: number;
  decimals?: number;
  workspace_id?: string | null;
  project_id?: string | null;
}

export const surfacesApi = {
  tin: (surface: SurfaceSpec) => postJson<SurfaceResult>("/v1/surfaces/tin", { surface }),
  contours: (r: ContoursRequest) => postJson<ContoursResult>("/v1/surfaces/contours", r),
  heights: (r: HeightsRequest) => postJson<HeightsResult>("/v1/surfaces/heights", r),
  volumeLevel: (r: LevelVolumeRequest) => postJson<VolumeResult>("/v1/surfaces/volume/level", r),
  volumeSurfaces: (r: SurfaceVolumeRequest) => postJson<VolumeResult>("/v1/surfaces/volume/surfaces", r),
  profile: (r: ProfileRequest) => postJson<ProfileResult>("/v1/surfaces/profile", r),
  async exportFile(r: SurfaceExportRequest): Promise<{ blob: Blob; filename: string }> {
    const res = await request("/v1/surfaces/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(r),
    });
    return { blob: await res.blob(), filename: filenameFrom(res, `surface.${r.format}`) };
  },
};

// ------------------------------------------------------------------------ point selection

/** A project point as the surface tools see it (control points have kind "control"). */
export interface SourcePoint {
  name: string;
  x: number;
  y: number;
  z: number | null;
  kind: PointKind;
  code: string | null;
}

export interface PointFilter {
  kinds: PointKind[];
  /** comma/space separated; empty = every code */
  onlyCodes: string;
  /** comma/space separated codes to leave out */
  excludeCodes: string;
}

export function parseCodes(text: string): string[] {
  return text
    .split(/[,;\s]+/)
    .map((c) => c.trim().toUpperCase())
    .filter(Boolean);
}

/** Points that pass the kind / code filter (codes compared case-insensitively). */
export function filterPoints(points: SourcePoint[], f: PointFilter): SourcePoint[] {
  const kinds = new Set(f.kinds);
  const only = new Set(parseCodes(f.onlyCodes));
  const exclude = new Set(parseCodes(f.excludeCodes));
  return points.filter((p) => {
    if (!kinds.has(p.kind)) return false;
    const code = (p.code ?? "").trim().toUpperCase();
    if (only.size && !only.has(code)) return false;
    return !exclude.has(code);
  });
}

export function toSurfacePoints(points: SourcePoint[]): SurfacePoint[] {
  return points.map((p) => ({ name: p.name, x: p.x, y: p.y, z: p.z }));
}

/** Breaklines from field-coded line work whose code is selected. */
export function breaklinesFrom(linework: Polyline[], codes: string[]): Breakline[] {
  const wanted = new Set(codes.map((c) => c.toUpperCase()));
  return linework
    .filter((l) => wanted.has(l.code.toUpperCase()) && l.points.length >= 2)
    .map((l) => ({ points: l.points, closed: l.closed }));
}

// ------------------------------------------------------------------------------ charts

export interface ChartFrame {
  width: number;
  height: number;
  pad: number;
  x0: number;
  x1: number;
  z0: number;
  z1: number;
  sx: (x: number) => number;
  sy: (z: number) => number;
}

/** Map chainage/height to an SVG box (y down), with "nice" height bounds. */
export function chartFrame(x0: number, x1: number, zs: number[], width = 640, height = 220, pad = 36): ChartFrame {
  const lo = zs.length ? Math.min(...zs) : 0;
  const hi = zs.length ? Math.max(...zs) : 1;
  const span = Math.max(hi - lo, 0.5);
  const z0 = Math.floor(lo - span * 0.1);
  const z1 = Math.ceil(hi + span * 0.1);
  const dx = Math.max(x1 - x0, 1e-9);
  const dz = Math.max(z1 - z0, 1e-9);
  return {
    width,
    height,
    pad,
    x0,
    x1,
    z0,
    z1,
    sx: (x) => pad + ((x - x0) / dx) * (width - 2 * pad),
    sy: (z) => height - pad - ((z - z0) / dz) * (height - 2 * pad),
  };
}

/** SVG path ("M … L …") per continuous run of stations. */
export function runPaths(stations: ProfileStation[], frame: ChartFrame): string[] {
  const out: string[] = [];
  let cur: string[] = [];
  let run = -1;
  for (const s of stations) {
    if (s.run !== run && cur.length) {
      out.push(cur.join(" "));
      cur = [];
    }
    run = s.run;
    cur.push(`${cur.length ? "L" : "M"}${frame.sx(s.chainage).toFixed(2)},${frame.sy(s.z).toFixed(2)}`);
  }
  if (cur.length) out.push(cur.join(" "));
  return out;
}

/** Round tick values covering [a, b] (about `n` of them). */
export function ticks(a: number, b: number, n = 5): number[] {
  const span = b - a;
  if (!(span > 0)) return [a];
  const raw = span / n;
  const p = 10 ** Math.floor(Math.log10(raw));
  const f = raw / p;
  const step = (f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * p;
  const out: number[] = [];
  for (let v = Math.ceil(a / step) * step; v <= b + step * 1e-9; v += step) out.push(Math.round(v / step) * step);
  return out;
}
