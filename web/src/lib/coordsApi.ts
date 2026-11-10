// Coordinate systems tools: types mirroring engine/src/atsurvey/core/coords/models.py, the API
// client (/v1/coords/*) and pure helpers to parse pasted lists and format/export results.
// Geographic coordinates travel in RADIANS (x = λ, y = φ); users type and read φ λ in degrees.
import { ApiError, postJson } from "@/lib/api";
import { formatAngle, parseAngle } from "@/lib/angles";
import type { Issue } from "@/lib/types";
import { parseNum } from "@/lib/utils";

export const SYSTEM_IDS = [
  "egsa87",
  "ggrs87_geo",
  "wgs84_geo",
  "utm34",
  "utm35",
  "tm3_west",
  "tm3_central",
  "tm3_east",
  "greek_geo",
  "hatt",
] as const;
export type SystemId = (typeof SYSTEM_IDS)[number];
export type Datum = "greek" | "ggrs87" | "wgs84";
export type HeightKind = "ellipsoidal" | "orthometric";
export type DatumMethod = "approximate" | "official";
/** How φ, λ are typed and shown: decimal degrees or degrees-minutes-seconds. */
export type GeoFormat = "deg" | "dms";

export const SYSTEM_DATUM: Record<SystemId, Datum> = {
  egsa87: "ggrs87",
  ggrs87_geo: "ggrs87",
  wgs84_geo: "wgs84",
  utm34: "wgs84",
  utm35: "wgs84",
  tm3_west: "greek",
  tm3_central: "greek",
  tm3_east: "greek",
  greek_geo: "greek",
  hatt: "greek",
};

export function isGeographic(s: SystemId): boolean {
  return s === "ggrs87_geo" || s === "wgs84_geo" || s === "greek_geo";
}

/** Old Greek datum systems whose definition comes from secondary sources (see docs/coords.md). */
export function isUnverifiedDefinition(s: SystemId): boolean {
  return SYSTEM_DATUM[s] === "greek" && s !== "greek_geo";
}

/** True when converting between the two systems changes datum (the result is then approximate
 *  unless the official method is used). */
export function changesDatum(src: SystemId, dst: SystemId): boolean {
  return SYSTEM_DATUM[src] !== SYSTEM_DATUM[dst];
}

export interface CoordPoint {
  name?: string | null;
  x: number;
  y: number;
  z?: number | null;
}

export interface HattSpec {
  sheet?: string | null;
  lat0?: number | null;
  lon0?: number | null;
  meridian?: "athens" | "greenwich";
  /** A0…A5 then B0…B5 */
  coefficients?: number[] | null;
}

export interface ConvertRequest {
  src: SystemId;
  dst: SystemId;
  points: CoordPoint[];
  src_hatt?: HattSpec | null;
  dst_hatt?: HattSpec | null;
  datum_method?: DatumMethod;
  height_in?: HeightKind;
  height_out?: HeightKind;
  geoid_undulation?: number | null;
}

export interface ConvertedPoint {
  name?: string | null;
  x: number | null;
  y: number | null;
  z?: number | null;
}

export interface ConvertResult {
  src: SystemId;
  dst: SystemId;
  points: ConvertedPoint[];
  datum_shift: string[];
  approximate: boolean;
  accuracy_m: number | null;
  issues: Issue[];
}

export interface PointInfoRequest {
  system: SystemId;
  point: CoordPoint;
  hatt?: HattSpec | null;
  height_kind?: HeightKind;
  geoid_undulation?: number | null;
}

export interface PointInfoResult {
  system: SystemId;
  lat: number;
  lon: number;
  lon_athens: number | null;
  x: number | null;
  y: number | null;
  scale_factor: number | null;
  scale_min: number | null;
  scale_max: number | null;
  convergence: number | null;
  elevation_factor: number | null;
  combined_factor: number | null;
  utm_zone: number;
  tm3_zone: "tm3_west" | "tm3_central" | "tm3_east" | null;
  inside_zone: boolean;
  issues: Issue[];
}

export const MAX_POINTS = 10_000;

export const coordsApi = {
  convert: (r: ConvertRequest) => postJson<ConvertResult>("/v1/coords/convert", r),
  pointInfo: (r: PointInfoRequest) => postJson<PointInfoResult>("/v1/coords/point-info", r),
};

/** A coded engine failure (422 {detail: {code, params}}), or null for anything else. */
export function coordsErrorCode(e: unknown): { code: string; params: Record<string, unknown> } | null {
  if (!(e instanceof ApiError) || !e.code?.startsWith("COORD_")) return null;
  const detail = (e.detail as { detail?: { params?: Record<string, unknown> } } | undefined)?.detail;
  return { code: e.code, params: detail?.params ?? {} };
}

/** Issue params ready for i18next: arrays joined. */
export function issueParams(params: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(params).map(([k, v]) => [k, Array.isArray(v) ? v.join(", ") : v]));
}

// ------------------------------------------------------------------- parse pasted lists

function splitLine(line: string): string[] {
  const parts = line.split(/[\s;\t]+/).filter(Boolean);
  // "476000,4205000" (comma as separator) when there is no other separator and no decimal point
  if (parts.length === 1 && line.includes(",") && !line.includes(".")) return line.split(",").map((p) => p.trim());
  return parts;
}

/**
 * Parse one line: "name a b [z]" or "a b [z]" (a numeric name needs all four columns). For grid systems a, b = E, N (m); for geographic
 * systems a, b = φ, λ (surveyor's order) in decimal degrees or DMS (37°58'45.6" or packed
 * 37.584560), returned in radians as x = λ, y = φ.
 */
export function parseCoordLine(line: string, geographic: boolean, fmt: GeoFormat): CoordPoint | null {
  const parts = splitLine(line.trim());
  if (parts.length < 2) return null;
  const read = (tok: string, i: number): number | null => (geographic && i < 2 ? parseAngle(tok, fmt) : parseNum(tok));
  // a name comes first when it is not a number, or when there are four columns (name a b z)
  const firstIsName = parts.length >= 4 || read(parts[0], 0) === null;
  const name = firstIsName ? parts[0] : null;
  const nums = (firstIsName ? parts.slice(1) : parts).slice(0, 3).map((p, i) => read(p, i));
  if (nums.length < 2 || nums.some((n) => n === null)) return null;
  const [a, b, z] = nums as number[];
  return geographic ? { name, x: b, y: a, z: z ?? null } : { name, x: a, y: b, z: z ?? null };
}

export function parseCoordList(text: string, geographic: boolean, fmt: GeoFormat): { pts: CoordPoint[]; bad: string[] } {
  const pts: CoordPoint[] = [];
  const bad: string[] = [];
  text.split(/\r?\n/).forEach((raw, i) => {
    const line = raw.trim();
    if (!line) return;
    const p = parseCoordLine(line, geographic, fmt);
    if (p) pts.push({ ...p, name: p.name ?? `P${i + 1}` });
    else bad.push(line);
  });
  return { pts, bad };
}

// ------------------------------------------------------------------------ formatting

/** φ or λ (radians) for display/export: DMS with 5 decimals of second (≈ 0.3 mm) or 9 decimal degrees. */
export function formatGeo(rad: number | null | undefined, fmt: GeoFormat): string {
  return formatAngle(rad, fmt, fmt === "dms" ? 5 : 9);
}

/** Column headers and cell strings of one converted point, in the target system's order. */
export function formatPoint(p: ConvertedPoint, geographic: boolean, fmt: GeoFormat): [string, string, string] {
  const z = p.z === null || p.z === undefined ? "" : p.z.toFixed(3);
  if (p.x === null || p.y === null) return ["", "", z];
  if (geographic) return [formatGeo(p.y, fmt), formatGeo(p.x, fmt), z];
  return [p.x.toFixed(3), p.y.toFixed(3), z];
}

export function coordHeaders(geographic: boolean): [string, string] {
  return geographic ? ["φ", "λ"] : ["E", "N"];
}

/** CSV (UTF-8 BOM, ";" separated, CRLF) like the other tool exports. */
export function convertCsv(result: ConvertResult, fmt: GeoFormat): string {
  const geo = isGeographic(result.dst);
  const [a, b] = coordHeaders(geo);
  const head = ["point", a, b, "z"].join(";");
  const body = result.points.map((p, i) => [p.name ?? String(i + 1), ...formatPoint(p, geo, fmt)].join(";"));
  return "﻿" + [head, ...body].join("\r\n") + "\r\n";
}
