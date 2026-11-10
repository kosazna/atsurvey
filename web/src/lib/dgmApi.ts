// ΔΓΜ (Διάγραμμα Γεωμετρικών Μεταβολών, Hellenic Cadastre): TypeScript mirrors of
// engine/src/atsurvey/core/dgm/models.py, the /v1/dgm/* client and small pure helpers.
// x = Easting, y = Northing, metres (ΕΓΣΑ87). The Cadastre's own system is authoritative.
import { filenameFrom, postJson, request } from "./api";
import type { AreaToleranceRule, Parcel, ParcelVertex } from "./parcelsApi";
import type { Issue } from "./types";

export type DgmMode = "subdivision" | "merge" | "correction";
/** ΤΔ, ΔΓΜ για πράξη, ΔΓΜ για διόρθωση / ΤΔΓΜ */
export type DiagramKind = "topo" | "deed" | "correction";

export interface Polyline {
  vertices: ParcelVertex[];
}

export interface FinalPolygon {
  kaek: string | null;
  label?: string;
  vertices: ParcelVertex[];
}

export interface TitleBlock {
  title: string;
  author: string;
  author_details: string;
  client: string;
  location: string;
  municipality: string;
  scale: number;
  date: string;
  method: "hepos" | "other";
  method_other: string;
  notes: string;
  tdgm: boolean;
}

export const EMPTY_TITLE: TitleBlock = {
  title: "",
  author: "",
  author_details: "",
  client: "",
  location: "",
  municipality: "",
  scale: 500,
  date: "",
  method: "hepos",
  method_other: "",
  notes: "",
  tdgm: false,
};

export interface DgmRequest {
  mode: DgmMode;
  parcels: Parcel[];
  subject?: string | null;
  partition_lines?: Polyline[];
  extend_lines?: boolean;
  part_labels?: string[] | null;
  merge?: string[];
  subjects?: string[];
  finals?: FinalPolygon[];
  topo_prop?: Parcel[];
  topo_prop_new?: Parcel[];
  buildings?: Parcel[];
  boundary?: "implemented" | "unimplemented";
  snap_tolerance?: number;
  tolerance?: AreaToleranceRule | null;
  new_point_prefix?: string;
  title?: TitleBlock;
}

export interface DgmPolygon {
  layer: string;
  label: string;
  kaek: string | null;
  vertices: ParcelVertex[];
  area: number;
  perimeter: number;
}

export interface DgmLine {
  layer: string;
  vertices: ParcelVertex[];
}

export interface DgmPoint {
  name: string;
  x: number;
  y: number;
  new: boolean;
}

export interface AreaRow {
  label: string;
  kaek: string | null;
  before: number | null;
  after: number | null;
  difference: number | null;
}

export interface AreaComparison {
  label: string;
  kaek: string | null;
  against: "survey" | "final";
  cadastre_area: number;
  other_area: number;
  difference: number;
  difference_percent: number;
  perimeter: number;
  tolerance: number | null;
  within: boolean | null;
}

export interface ChangeRow {
  part: string;
  kind: "A" | "D";
  description: string[];
  area: number;
  from_kaek: string;
  to_kaek: string;
}

export interface DgmResult {
  mode: DgmMode;
  kind: DiagramKind;
  polygons: DgmPolygon[];
  lines: DgmLine[];
  points: DgmPoint[];
  areas: AreaRow[];
  comparisons: AreaComparison[];
  changes: ChangeRow[];
  total_before: number;
  total_after: number;
  ok: boolean;
  issues: Issue[];
}

export interface KdParcel {
  kaek: string | null;
  layer: string;
  handle: string | null;
  vertices: ParcelVertex[];
  area: number;
}

export interface KdReadResult {
  parcels: KdParcel[];
  issues: Issue[];
}

export type CheckStatus = "pass" | "fail" | "warn" | "skip";

export interface CheckResult {
  id: string;
  status: CheckStatus;
  issues: Issue[];
}

export interface LayerSummary {
  name: string;
  table_no: number | null;
  counts: Record<string, number>;
}

export interface PreviewShape {
  layer: string;
  closed: boolean;
  coords: [number, number][];
}

export interface ValidationReport {
  kind: DiagramKind;
  filename: string | null;
  size: number;
  sha512: string;
  dxf_version: string | null;
  ok: boolean;
  checks: CheckResult[];
  layers: LayerSummary[];
  preview: PreviewShape[];
  preview_truncated: boolean;
}

export interface DgmExport {
  blob: Blob;
  filename: string;
  sha512: string;
}

export const dgmApi = {
  sample: async (): Promise<Parcel[]> => (await request("/v1/dgm/sample")).json(),
  build: (r: DgmRequest) => postJson<DgmResult>("/v1/dgm/build", r),
  async readKd(file: File, layer?: string): Promise<KdReadResult> {
    const fd = new FormData();
    fd.append("file", file);
    if (layer) fd.append("layer", layer);
    return (await request("/v1/dgm/kd", { method: "POST", body: fd })).json();
  },
  async validate(file: File, kind: DiagramKind): Promise<ValidationReport> {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", kind);
    return (await request("/v1/dgm/validate", { method: "POST", body: fd })).json();
  },
  async exportDxf(req: DgmRequest, filename: string | null, workspaceId: string | null, projectId: string | null): Promise<DgmExport> {
    const res = await request("/v1/dgm/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: req, filename, workspace_id: workspaceId, project_id: projectId }),
    });
    const blob = await res.blob();
    // computed here from the bytes we received: this is the hash of the file the user keeps
    return { blob, filename: filenameFrom(res, "dgm_v01.dxf"), sha512: await sha512Hex(await blob.arrayBuffer()) };
  },
  async hashPdf(sha512: string, workspaceId: string | null): Promise<Blob> {
    const res = await request("/v1/dgm/hash-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sha512, workspace_id: workspaceId }),
    });
    return res.blob();
  },
};

/** Lowercase hexadecimal SHA-512 (Web Crypto). */
export async function sha512Hex(data: ArrayBuffer | Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-512", data as BufferSource);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

// ------------------------------------------------------------------------- pure helpers

const KAEK_RE = /^\d{12}$/;

/** «ΚΑΕΚ: 05068 1703001» → 050681703001 (mirror of spec.normalize_kaek). */
export function normalizeKaek(text: string): string {
  return text
    .trim()
    .replace(/^(ΚΑΕΚ|KAEK)\s*[:.]?\s*/i, "")
    .replace(/[\s.\-/]/g, "");
}

export function isKaek(text: string): boolean {
  return KAEK_RE.test(text);
}

const FILE_PREFIX: Record<DiagramKind, string> = { topo: "topo_", deed: "dgm_", correction: "dgm_" };

/** File-name rules of the Cadastre's specification §4.3 (mirror of spec.check_file_name). */
export function checkFileName(filename: string, kind: DiagramKind): string[] {
  const out: string[] = [];
  const dot = filename.lastIndexOf(".");
  const base = dot >= 0 ? filename.slice(0, dot) : filename;
  const ext = dot >= 0 ? filename.slice(dot + 1) : "";
  if (ext.toLowerCase() !== "dxf") out.push("DGM_FILE_EXTENSION");
  if (!/^[A-Za-z0-9_]+$/.test(base)) out.push("DGM_FILE_CHARS");
  if (base.length > 15) out.push("DGM_FILE_LENGTH");
  if (!base.toLowerCase().startsWith(FILE_PREFIX[kind])) out.push("DGM_FILE_PREFIX");
  if (!/_v\d+$/i.test(base)) out.push("DGM_FILE_VERSION_WARN");
  return out;
}

export type LayerTone = "cadastre" | "final" | "cut" | "claimed" | "line" | "survey" | "surveyNew" | "building" | "other";

/** Visual role of a Table I layer in the sketches (styles come from design tokens). */
export function layerTone(layer: string): LayerTone {
  switch (layer) {
    case "PST_KAEK":
      return "cadastre";
    case "DGM_PROP_FINAL":
      return "final";
    case "AREA_A":
      return "cut";
    case "AREA_D":
      return "claimed";
    case "LINE_XM":
    case "LINE_XM_VST":
      return "line";
    case "TOPO_PROP":
      return "survey";
    case "TOPO_PROP_NEW":
      return "surveyNew";
    case "BLD":
      return "building";
    default:
      return "other";
  }
}

/** Order in which layers are drawn (later on top). */
export const DRAW_ORDER: LayerTone[] = ["other", "building", "survey", "surveyNew", "cadastre", "claimed", "cut", "final", "line"];

function csvCell(v: string | number | null): string {
  if (v === null) return "";
  const s = typeof v === "number" ? String(v) : v;
  const safe = /^[=+\-@\t\r]/.test(s) ? `'${s}` : s;
  return /[;"\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

function csv(rows: (string | number | null)[][]): string {
  return "﻿" + rows.map((r) => r.map(csvCell).join(";")).join("\r\n") + "\r\n";
}

/** Change table «ΤΜΗΜΑ;ΠΕΡΙΓΡΑΦΗ;ΕΜΒΑΔΟ;ΑΠΟ ΚΑΕΚ;ΣΕ ΚΑΕΚ» (areas 2 decimals). */
export function changesCsv(rows: ChangeRow[]): string {
  return csv([["ΤΜΗΜΑ", "ΠΕΡΙΓΡΑΦΗ", "ΕΜΒΑΔΟ", "ΑΠΟ ΚΑΕΚ", "ΣΕ ΚΑΕΚ"], ...rows.map((r) => [r.part, `(${r.description.join(",")})`, r.area.toFixed(2), r.from_kaek, r.to_kaek])]);
}

/** Coordinate table (3 decimals). */
export function pointsCsv(points: DgmPoint[]): string {
  return csv([["Σ", "X", "Y"], ...points.map((p) => [p.name, p.x.toFixed(3), p.y.toFixed(3)])]);
}

/** Areas before/after (2 decimals). */
export function areasCsv(rows: AreaRow[]): string {
  const f = (v: number | null) => (v === null ? null : v.toFixed(2));
  return csv([["ΓΕΩΤΕΜΑΧΙΟ", "ΑΡΧΙΚΟ", "ΤΕΛΙΚΟ", "ΔΙΑΦΟΡΑ"], ...rows.map((r) => [r.kaek ?? r.label, f(r.before), f(r.after), f(r.difference)])]);
}

/** Vertex list text ("name x y" per line) for editing a polygon in a textarea. */
export function verticesText(vertices: ParcelVertex[]): string {
  return vertices.map((v) => `${v.name} ${v.x.toFixed(3)} ${v.y.toFixed(3)}`).join("\n");
}

/** Split a textarea into blocks separated by blank lines (several polygons in one field). */
export function splitBlocks(text: string): string[] {
  return text
    .split(/\n\s*\n/)
    .map((b) => b.trim())
    .filter(Boolean);
}

/** Problem coordinates of an issue, if any. */
export function issueXY(issue: Issue): { x: number; y: number } | null {
  const p = issue.params ?? {};
  const x = p.x;
  const y = p.y;
  return typeof x === "number" && typeof y === "number" && Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
}

export interface VertexParse {
  vertices: ParcelVertex[];
  bad: string[];
}

const num = (s: string): number | null => {
  const n = Number(s.replace(",", "."));
  return s !== "" && Number.isFinite(n) ? n : null;
};

/** ΕΓΣΑ87 magnitudes: a coordinate pair, not a height. */
const isGridCoord = (v: number) => Math.abs(v) >= 1000;

/**
 * Vertex lines of a cadastral diagram: "name x y" (names are usually numbers: «12 476200.123
 * 4205100.456»), "x y", or a single project point name. Three numbers are read as name x y when
 * the last two are grid coordinates, otherwise as x y z.
 */
export function parseVertices(text: string, lookup: (name: string) => { x: number; y: number } | undefined): VertexParse {
  const vertices: ParcelVertex[] = [];
  const bad: string[] = [];
  text.split(/\r?\n/).forEach((line) => {
    const l = line.trim();
    if (!l) return;
    const toks = l.split(/[\s;\t]+/).filter(Boolean);
    const auto = `P${vertices.length + 1}`;
    if (toks.length === 1) {
      const p = lookup(toks[0]);
      if (p) vertices.push({ name: toks[0], x: p.x, y: p.y });
      else bad.push(l);
      return;
    }
    const nums = toks.map(num);
    if (toks.length >= 3 && nums[1] !== null && nums[2] !== null && (nums[0] === null || (isGridCoord(nums[1]) && isGridCoord(nums[2])))) {
      vertices.push({ name: toks[0], x: nums[1], y: nums[2] });
    } else if (nums[0] !== null && nums[1] !== null && toks.length <= 3) {
      vertices.push({ name: auto, x: nums[0], y: nums[1] });
    } else {
      bad.push(l);
    }
  });
  return { vertices, bad };
}
