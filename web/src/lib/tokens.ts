// Runtime access to design tokens for canvas/WebGL renderers (MapLibre, Glide grid)
// that cannot read CSS custom properties themselves.
import { useMemo } from "react";
import { useTheme } from "./theme";

let probe: CanvasRenderingContext2D | null = null;

/** Raw token value, e.g. cssVar("--color-accent") → "#2f5bd3" */
export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Token colour resolved to rgb()/rgba() so any renderer can parse it. */
export function tokenColor(name: string): string {
  const raw = cssVar(name);
  if (!raw) return "rgba(0,0,0,0)";
  if (/^#|^rgba?\(/i.test(raw)) return raw;
  try {
    probe ??= document.createElement("canvas").getContext("2d", { willReadFrequently: true });
    if (!probe) return raw;
    probe.clearRect(0, 0, 1, 1);
    probe.fillStyle = raw;
    probe.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = probe.getImageData(0, 0, 1, 1).data;
    return `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(3)})`;
  } catch {
    return raw;
  }
}

/** Token length in px (handles rem/px). */
export function tokenPx(name: string): number {
  const raw = cssVar(name);
  const n = parseFloat(raw);
  if (raw.endsWith("rem")) return n * parseFloat(getComputedStyle(document.documentElement).fontSize || "16");
  return n || 0;
}

export interface ResolvedTokens {
  bg: string;
  surface: string;
  surfaceRaised: string;
  surfaceSunken: string;
  border: string;
  borderStrong: string;
  text: string;
  textMuted: string;
  textSubtle: string;
  accent: string;
  accentContrast: string;
  accentSubtle: string;
  warning: string;
  warningSubtle: string;
  danger: string;
  dangerSubtle: string;
  pointControl: string;
  pointTraverse: string;
  pointDetail: string;
  traverseLine: string;
  mapBg: string;
  mapGrid: string;
  fontSans: string;
  textXs: number;
  textSm: number;
  weightRegular: string;
  weightMedium: string;
  weightSemibold: string;
}

export function readTokens(): ResolvedTokens {
  return {
    bg: tokenColor("--color-bg"),
    surface: tokenColor("--color-surface"),
    surfaceRaised: tokenColor("--color-surface-raised"),
    surfaceSunken: tokenColor("--color-surface-sunken"),
    border: tokenColor("--color-border"),
    borderStrong: tokenColor("--color-border-strong"),
    text: tokenColor("--color-text"),
    textMuted: tokenColor("--color-text-muted"),
    textSubtle: tokenColor("--color-text-subtle"),
    accent: tokenColor("--color-accent"),
    accentContrast: tokenColor("--color-accent-contrast"),
    accentSubtle: tokenColor("--color-accent-subtle"),
    warning: tokenColor("--color-warning"),
    warningSubtle: tokenColor("--color-warning-subtle"),
    danger: tokenColor("--color-danger"),
    dangerSubtle: tokenColor("--color-danger-subtle"),
    pointControl: tokenColor("--color-point-control"),
    pointTraverse: tokenColor("--color-point-traverse"),
    pointDetail: tokenColor("--color-point-detail"),
    traverseLine: tokenColor("--color-traverse-line"),
    mapBg: tokenColor("--color-map-bg"),
    mapGrid: tokenColor("--color-map-grid"),
    fontSans: cssVar("--font-sans") || "sans-serif",
    textXs: tokenPx("--text-xs") || 12,
    textSm: tokenPx("--text-sm") || 13,
    weightRegular: cssVar("--weight-regular") || "400",
    weightMedium: cssVar("--weight-medium") || "500",
    weightSemibold: cssVar("--weight-semibold") || "600",
  };
}

/** Resolved tokens, recomputed whenever the theme changes. */
export function useTokens(): ResolvedTokens {
  const theme = useTheme();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => readTokens(), [theme]);
}
