// Parcels (ιδιοκτησίες): TypeScript mirrors of engine/src/atsurvey/core/parcels_models.py, the
// /v1/parcels/* client and small pure helpers (CSV tables, SVG framing, tolerance text).
// x = Easting, y = Northing, metres; azimuths in radians clockwise from grid north.
import { postJson, request } from "./api";
import type { XY } from "./cogoTypes";
import type { Issue } from "./types";

export interface ArcSpec {
  radius: number;
  side: "left" | "right";
  large?: boolean;
}

export interface ParcelVertex {
  name: string;
  x: number;
  y: number;
  arc?: ArcSpec | null;
}

export interface Parcel {
  label?: string;
  kaek?: string | null;
  vertices: ParcelVertex[];
}

export interface SideRow {
  frm: string;
  to: string;
  length: number;
  azimuth: number;
  arc_length?: number | null;
  radius?: number | null;
  central_angle?: number | null;
  segment_area?: number | null;
}

export interface ParcelGeometry {
  label: string;
  kaek: string | null;
  vertices: ParcelVertex[];
  sides: SideRow[];
  area: number | null;
  perimeter: number | null;
  orientation: "clockwise" | "counterclockwise" | null;
  centroid: { x: number; y: number } | null;
  has_arcs: boolean;
  valid: boolean;
  issues: Issue[];
}

export type ToleranceKind = "fixed" | "percent" | "formula" | "cadastre";

/**
 * T(E) in m² (E = reference area): fixed `value`, `value` % of E, a + b·√E, or the Hellenic
 * Cadastre rule U0·Π·(1 + U0/√E) with Π the parcel perimeter. `cap_percent` caps T at % of E.
 */
export interface AreaToleranceRule {
  kind: ToleranceKind;
  value?: number | null;
  a?: number | null;
  b?: number | null;
  u0?: number | null;
  cap_percent?: number | null;
  source: string;
}

export interface AreaTolerancePreset {
  id: string;
  label: string;
  rule: AreaToleranceRule;
  /** value still awaiting the owner's confirmation */
  to_be_confirmed?: boolean;
}

const CADASTRE_SOURCE = "ΟΚΧΕ 461/03/21.7.2008 (ΦΕΚ Β΄ 1510/31.7.2008), κεφ. 7 §3.6 της 460/03/12.6.2008 (ΦΕΚ Β΄ 1156/2008)";
const DGM_GUIDE_SOURCE = "Κτηματολόγιο Α.Ε., οδηγός ΔΓΜ (ενδεικτικά, εμπιστοσύνη 99,7 %)";

/** 7 % cap for areas surveyed under the 2007 specifications. */
export const CADASTRE_CAP_PERCENT = 7;

/** Mirror of engine/src/atsurvey/core/parcels.py AREA_TOLERANCE_PRESETS (keep in sync). */
export const AREA_TOLERANCE_PRESETS: AreaTolerancePreset[] = [
  { id: "cadastre_urban", label: "Κτηματολόγιο — αστική (U0 = 0,50 m)", rule: { kind: "cadastre", u0: 0.5, source: CADASTRE_SOURCE } },
  { id: "cadastre_rural", label: "Κτηματολόγιο — αγροτική (U0 = 2,00 m)", rule: { kind: "cadastre", u0: 2.0, source: CADASTRE_SOURCE }, to_be_confirmed: true },
  { id: "cadastre_rural_dgm_guide", label: "Κτηματολόγιο — αγροτική κατά οδηγό ΔΓΜ (U0 = 2,50 m)", rule: { kind: "cadastre", u0: 2.5, source: DGM_GUIDE_SOURCE }, to_be_confirmed: true },
];

export interface AreaCompareRequest {
  surveyed_area?: number | null;
  parcel?: Parcel | null;
  deed_area?: number | null;
  cadastre_area?: number | null;
  perimeter?: number | null;
  tolerance?: AreaToleranceRule | null;
}

export type CompareKind = "surveyed_vs_deed" | "surveyed_vs_cadastre" | "cadastre_vs_deed";

export interface AreaCompareRow {
  kind: CompareKind;
  area: number;
  reference_area: number;
  difference: number;
  difference_percent: number | null;
  tolerance: number | null;
  within: boolean | null;
}

export interface AreaCompareResult {
  surveyed_area: number;
  perimeter: number | null;
  rows: AreaCompareRow[];
  tolerance: AreaToleranceRule | null;
  issues: Issue[];
}

export type SubdivideMethod = "parallel" | "perpendicular" | "pivot";

export interface SubdivideRequest {
  parcel: Parcel;
  method: SubdivideMethod;
  mode: "areas" | "ratios";
  parts: number[];
  side?: number | null;
  from_end?: "start" | "end";
  pivot?: string | null;
  pivot_point?: { x: number; y: number } | null;
  towards?: string | null;
  new_point_prefix?: string;
  new_point_start?: number;
  part_labels?: string[] | null;
  frontage_side?: number | null;
  min_frontage?: number | null;
}

export interface CutLine {
  a: ParcelVertex;
  b: ParcelVertex;
  length: number;
  azimuth: number;
}

export interface SubdivisionPart {
  geometry: ParcelGeometry;
  requested_area: number | null;
  area_error: number | null;
  frontage: number | null;
}

export interface SubdivisionResult {
  original: ParcelGeometry;
  parts: SubdivisionPart[];
  cut_lines: CutLine[];
  new_points: ParcelVertex[];
  issues: Issue[];
}

export interface MergeRequest {
  parcels: Parcel[];
  snap_tolerance?: number;
  label?: string;
}

export interface MergeResult {
  merged: ParcelGeometry | null;
  max_snap: number;
  inserted: string[];
  area_sum: number;
  issues: Issue[];
}

export interface CoverageRequest {
  outline: Parcel;
  parts: Parcel[];
  tolerance?: number;
  area_tolerance?: number;
}

export interface CoverageResult {
  ok: boolean;
  outline_area: number | null;
  parts_area: number;
  difference: number | null;
  issues: Issue[];
}

export const parcelsApi = {
  compute: (r: Parcel) => postJson<ParcelGeometry>("/v1/parcels/compute", r),
  compare: (r: AreaCompareRequest) => postJson<AreaCompareResult>("/v1/parcels/compare", r),
  subdivide: (r: SubdivideRequest) => postJson<SubdivisionResult>("/v1/parcels/subdivide", r),
  merge: (r: MergeRequest) => postJson<MergeResult>("/v1/parcels/merge", r),
  coverage: (r: CoverageRequest) => postJson<CoverageResult>("/v1/parcels/coverage", r),
  async tolerancePresets(): Promise<AreaTolerancePreset[]> {
    const res = await request("/v1/parcels/tolerance-presets");
    return res.json();
  },
};

// ------------------------------------------------------------------------------- helpers

/** 1 στρέμμα = 1000 m². */
export function stremmata(m2: number): number {
  return m2 / 1000;
}

/** "500 750,5; 1" → [500, 750.5, 1]; null if empty or any token is not a positive number. */
export function parseParts(text: string): number[] | null {
  const toks = text.split(/[\s;]+/).filter(Boolean);
  if (toks.length === 0) return null;
  const nums = toks.map((x) => Number(x.replace(",", ".")));
  return nums.every((n) => Number.isFinite(n) && n > 0) ? nums : null;
}

/** Points from the shared point-list parser → parcel vertices (unnamed points get P1, P2…). */
export function toVertices(pts: XY[]): ParcelVertex[] {
  return pts.map((p, i) => ({ name: (p.name ?? "").trim() || `P${i + 1}`, x: p.x, y: p.y }));
}

const isNum = (v: number | null | undefined): v is number => v !== null && v !== undefined && Number.isFinite(v);

function rawTolerance(rule: AreaToleranceRule, reference: number, perimeter: number | null): number | null {
  if (rule.kind === "fixed") return isNum(rule.value) ? rule.value : null;
  if (rule.kind === "percent") return isNum(rule.value) ? (rule.value / 100) * reference : null;
  if (rule.kind === "cadastre") {
    if (!isNum(rule.u0) || !isNum(perimeter) || reference <= 0) return null;
    return rule.u0 * perimeter * (1 + rule.u0 / Math.sqrt(reference));
  }
  return isNum(rule.a) && isNum(rule.b) ? rule.a + rule.b * Math.sqrt(reference) : null;
}

/** Mirror of engine area_tolerance() (cap included); null when the rule is incomplete. */
export function toleranceFor(rule: AreaToleranceRule, reference: number, perimeter: number | null = null): number | null {
  const t = rawTolerance(rule, reference, perimeter);
  if (t === null) return null;
  return isNum(rule.cap_percent) ? Math.min(t, (rule.cap_percent / 100) * reference) : t;
}

/** Human formula of a rule: "5 m²", "2 % · E", "1 + 0.5·√E m²", "0.5·Π·(1 + 0.5/√E)". */
export function describeRule(rule: AreaToleranceRule): string {
  const n = (v: number | null | undefined) => (isNum(v) ? String(+v.toFixed(6)) : "?");
  const cap = isNum(rule.cap_percent) ? `, ≤ ${n(rule.cap_percent)} % · E` : "";
  if (rule.kind === "fixed") return `${n(rule.value)} m²${cap}`;
  if (rule.kind === "percent") return `${n(rule.value)} % · E${cap}`;
  if (rule.kind === "cadastre") return `U0·Π·(1 + U0/√E), U0 = ${n(rule.u0)} m${cap}`;
  return `${n(rule.a)} + ${n(rule.b)}·√E m²${cap}`;
}

const BOM = "﻿";

function csv(rows: (string | number)[][]): string {
  return BOM + rows.map((r) => r.join(";")).join("\r\n") + "\r\n";
}

/** Vertex coordinate table (πίνακας συντεταγμένων). */
export function verticesCsv(geo: ParcelGeometry, decimals = 3): string {
  return csv([["point", "X", "Y"], ...geo.vertices.map((v) => [v.name, v.x.toFixed(decimals), v.y.toFixed(decimals)])]);
}

/** Side table: from;to;length;azimuth (in the given unit);arc length;radius. */
export function sidesCsv(geo: ParcelGeometry, formatAzimuth: (rad: number) => string, unitLabel: string): string {
  return csv([
    ["from", "to", "length_m", `azimuth_${unitLabel}`, "arc_length_m", "radius_m"],
    ...geo.sides.map((s) => [s.frm, s.to, s.length.toFixed(3), formatAzimuth(s.azimuth), s.arc_length?.toFixed(3) ?? "", s.radius?.toFixed(3) ?? ""]),
  ]);
}

/** One row per part: label;requested;area;στρέμματα;error;frontage;vertices. */
export function partsCsv(result: SubdivisionResult): string {
  return csv([
    ["part", "requested_m2", "area_m2", "stremmata", "error_m2", "frontage_m", "vertices"],
    ...result.parts.map((p) => [
      p.geometry.label,
      p.requested_area === null ? "" : p.requested_area.toFixed(2),
      p.geometry.area === null ? "" : p.geometry.area.toFixed(2),
      p.geometry.area === null ? "" : stremmata(p.geometry.area).toFixed(3),
      p.area_error === null ? "" : p.area_error.toExponential(2),
      p.frontage === null ? "" : p.frontage.toFixed(2),
      p.geometry.vertices.map((v) => v.name).join(" "),
    ]),
  ]);
}

/** Coordinates of all points of a result (original + new), for "add to project" / CSV. */
export function pointsCsv(points: ParcelVertex[], decimals = 3): string {
  return csv([["point", "X", "Y"], ...points.map((v) => [v.name, v.x.toFixed(decimals), v.y.toFixed(decimals)])]);
}

export interface SvgFrame {
  viewBox: string;
  /** map ΕΓΣΑ87 (x east, y north) → SVG user units (y down) */
  tx: (x: number) => number;
  ty: (y: number) => number;
  /** one metre in SVG units */
  scale: number;
}

/** Fit a set of rings in a size × size box (equal scale, north up, with a margin). */
export function svgFrame(rings: { x: number; y: number }[][], size = 300, margin = 16): SvgFrame | null {
  const pts = rings.flat();
  if (pts.length === 0) return null;
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const span = Math.max(maxX - minX, maxY - minY, 1e-9);
  const scale = (size - 2 * margin) / span;
  const offX = margin + (size - 2 * margin - (maxX - minX) * scale) / 2;
  const offY = margin + (size - 2 * margin - (maxY - minY) * scale) / 2;
  return {
    viewBox: `0 0 ${size} ${size}`,
    tx: (x) => offX + (x - minX) * scale,
    ty: (y) => offY + (maxY - y) * scale,
    scale,
  };
}
