// Angle conversions and formatting. Internally everything is radians.
import type { AngleUnit, DisplayAngleUnit } from "./types";

export const TWO_PI = Math.PI * 2;
export const GON = Math.PI / 200;
export const DEG = Math.PI / 180;
/** one centesimal second (cc) = 1e-4 gon */
export const CC = 1e-4 * GON;

export function wrap2pi(a: number): number {
  let r = a % TWO_PI;
  if (r < 0) r += TWO_PI;
  return r >= TWO_PI ? 0 : r;
}

export function wrapPi(a: number): number {
  return wrap2pi(a + Math.PI) - Math.PI;
}

/** Packed DDD.MMSSss → decimal degrees */
export function dmsToDeg(value: number): number {
  const sign = value < 0 ? -1 : 1;
  const v = Math.abs(value);
  const d = Math.floor(v);
  const rest = (v - d) * 100;
  const m = Math.floor(rest + 1e-9);
  const s = (rest - m) * 100;
  return sign * (d + m / 60 + s / 3600);
}

/** decimal degrees → packed DDD.MMSSss */
export function degToDms(value: number): number {
  const sign = value < 0 ? -1 : 1;
  const v = Math.abs(value);
  let d = Math.floor(v);
  const mFull = (v - d) * 60;
  let m = Math.floor(mFull + 1e-12);
  let s = (mFull - m) * 60;
  if (s >= 59.99999999) {
    s = 0;
    m += 1;
  }
  if (m >= 60) {
    m = 0;
    d += 1;
  }
  return sign * (d + m / 100 + s / 10000);
}

export function toRad(value: number, unit: AngleUnit): number {
  switch (unit) {
    case "gon":
      return value * GON;
    case "deg":
      return value * DEG;
    case "dms":
      return dmsToDeg(value) * DEG;
    case "rad":
      return value;
  }
}

export function fromRad(value: number, unit: AngleUnit): number {
  switch (unit) {
    case "gon":
      return value / GON;
    case "deg":
      return value / DEG;
    case "dms":
      return degToDms(value / DEG);
    case "rad":
      return value;
  }
}

export function radToCc(value: number): number {
  return value / CC;
}

/** Split decimal degrees into DMS parts with rounding carried correctly. */
function dmsParts(deg: number, secDecimals: number): { sign: string; d: number; m: number; s: string } {
  const sign = deg < 0 ? "-" : "";
  const totalSec = Math.abs(deg) * 3600;
  const factor = 10 ** secDecimals;
  const rounded = Math.round(totalSec * factor) / factor;
  let d = Math.floor(rounded / 3600);
  let m = Math.floor((rounded - d * 3600) / 60);
  let s = rounded - d * 3600 - m * 60;
  if (s >= 60 - 1e-9) {
    s = 0;
    m += 1;
  }
  if (m >= 60) {
    m = 0;
    d += 1;
  }
  return { sign, d, m, s: s.toFixed(secDecimals).padStart(secDecimals > 0 ? secDecimals + 3 : 2, "0") };
}

/**
 * Format an angle (radians) for display.
 * gon → "123.4567g" (plain g: IBM Plex has no ᵍ glyph), deg → "123.45678°", dms → 123°45'30.0"
 */
export function formatAngle(rad: number | null | undefined, unit: DisplayAngleUnit, decimals?: number): string {
  if (rad === null || rad === undefined || !Number.isFinite(rad)) return "—";
  switch (unit) {
    case "gon":
      return `${(rad / GON).toFixed(decimals ?? 4)}g`;
    case "deg":
      return `${(rad / DEG).toFixed(decimals ?? 5)}°`;
    case "dms": {
      const p = dmsParts(rad / DEG, decimals ?? 1);
      return `${p.sign}${p.d}°${String(p.m).padStart(2, "0")}'${p.s}"`;
    }
  }
}

/** Plain numeric value in display unit, for editable grid cells (no unit symbol). */
export function angleToInput(rad: number | null | undefined, unit: DisplayAngleUnit, decimals = 5): string {
  if (rad === null || rad === undefined || !Number.isFinite(rad)) return "";
  if (unit === "dms") return fromRad(rad, "dms").toFixed(decimals + 1);
  return fromRad(rad, unit).toFixed(decimals);
}

/**
 * Parse user input in the given unit. Accepts "123.4567", "123,4567", and for DMS
 * either packed "123.4530" or "123°45'30"" / "123 45 30".
 */
export function parseAngle(text: string, unit: DisplayAngleUnit): number | null {
  const t = text.trim().replace(/gon$|g$|°$/i, "").replace(",", ".");
  if (t === "") return null;
  if (unit === "dms") {
    const parts = t.split(/[°'"\s:]+/).filter(Boolean);
    if (parts.length >= 2) {
      const nums = parts.map(Number);
      if (nums.some((n) => !Number.isFinite(n))) return null;
      const [d, m = 0, s = 0] = nums;
      const sign = d < 0 || t.startsWith("-") ? -1 : 1;
      return sign * (Math.abs(d) + m / 60 + s / 3600) * DEG;
    }
  }
  const n = Number(t);
  if (!Number.isFinite(n)) return null;
  return toRad(n, unit);
}

/** Misclosure display in cc (centesimal seconds) with sign. */
export function formatCc(rad: number | null | undefined, decimals = 0): string {
  if (rad === null || rad === undefined || !Number.isFinite(rad)) return "—";
  const v = radToCc(rad);
  return `${v >= 0 ? "+" : ""}${v.toFixed(decimals)}cc`;
}

/** Misclosure in the user's unit: cc for gon, seconds for deg/dms. */
export function formatMisclosure(rad: number | null | undefined, unit: DisplayAngleUnit): string {
  if (rad === null || rad === undefined || !Number.isFinite(rad)) return "—";
  if (unit === "gon") return formatCc(rad);
  const sec = rad / DEG * 3600;
  return `${sec >= 0 ? "+" : ""}${sec.toFixed(1)}"`;
}

export function unitLabel(unit: DisplayAngleUnit): string {
  return unit === "gon" ? "grad" : unit === "deg" ? "deg" : "DMS";
}

/** Grid azimuth from p1 to p2 (radians, clockwise from north) */
export function gridAzimuth(x1: number, y1: number, x2: number, y2: number): number {
  const a = Math.atan2(x2 - x1, y2 - y1);
  return a < 0 ? a + TWO_PI : a;
}
