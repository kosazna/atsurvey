// Line work display helpers: detected feature codes and a categorical colour palette
// derived from design tokens (no hard-coded colours).
import type { ResultPoint } from "./types";

/** Token names used, in order, for line codes. */
export const LINE_PALETTE_TOKENS = [
  "--color-accent",
  "--color-point-control",
  "--color-success",
  "--color-warning",
  "--color-danger",
  "--color-info",
  "--color-point-detail",
  "--color-text-muted",
] as const;

/** Feature code = first whitespace-separated token of a point code. */
export function featureCode(code: string | null | undefined, caseSensitive = false): string | null {
  if (!code) return null;
  const tok = code.trim().split(/\s+/)[0];
  if (!tok) return null;
  return caseSensitive ? tok : tok.toUpperCase();
}

/** Feature codes found among points, with counts, most frequent first. */
export function detectCodes(points: Pick<ResultPoint, "code" | "kind">[], caseSensitive = false): { code: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const p of points) {
    if (p.kind === "control") continue;
    const c = featureCode(p.code, caseSensitive);
    if (c) counts.set(c, (counts.get(c) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([code, count]) => ({ code, count }))
    .sort((a, b) => b.count - a.count || a.code.localeCompare(b.code));
}

/**
 * Stable colour assignment: codes are sorted alphabetically and mapped round-robin onto the
 * palette, so a code keeps its colour regardless of selection order or counts.
 */
export function assignColors(codes: string[], palette: readonly string[]): Record<string, string> {
  const out: Record<string, string> = {};
  if (!palette.length) return out;
  [...new Set(codes)].sort((a, b) => a.localeCompare(b)).forEach((c, i) => {
    out[c] = palette[i % palette.length];
  });
  return out;
}
