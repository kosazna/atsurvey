import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** RFC 4122 v4 UUID. Ids are stored in Postgres uuid columns, so the fallback must be one too
 * (`crypto.randomUUID` is missing on plain-HTTP origins other than localhost, e.g. a LAN IP). */
export function uid(): string {
  const c: Partial<Crypto> | undefined = typeof crypto !== "undefined" ? crypto : undefined;
  if (typeof c?.randomUUID === "function") return c.randomUUID();
  const b = new Uint8Array(16);
  if (typeof c?.getRandomValues === "function") c.getRandomValues(b);
  else for (let i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export function fmtNum(v: number | null | undefined, decimals = 3): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toFixed(decimals);
}

export function fmtSigned(v: number | null | undefined, decimals = 3): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  // values that round to zero print as +0.0, never "-0.0"
  if (Math.abs(v) < 0.5 * 10 ** -decimals) v = 0;
  return `${v >= 0 ? "+" : ""}${v.toFixed(decimals)}`;
}

/** Parse a number typed by a Greek user: accepts comma decimal separator. */
export function parseNum(text: string): number | null {
  const t = text.trim().replace(/\s/g, "").replace(",", ".");
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function relativeTime(iso: string, locale: string): string {
  const d = new Date(iso).getTime();
  const diff = (d - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 60) return rtf.format(Math.round(diff), "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  if (abs < 86400 * 30) return rtf.format(Math.round(diff / 86400), "day");
  return new Date(iso).toLocaleDateString(locale);
}

/** 368377 → "368 377" (narrow no-break space; unambiguous in Greek and English). */
export function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return Math.round(v)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, "\u202f");
}
