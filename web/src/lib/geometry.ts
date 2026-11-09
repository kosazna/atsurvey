// Small client-side geometry helpers for display (the engine/API does the authoritative maths).

export interface Pt {
  x: number;
  y: number;
}

/** Shoelace area (absolute, m²) and perimeter (m) of a closed polygon. */
export function polygonArea(pts: Pt[]): { area: number; perimeter: number; clockwise: boolean } {
  if (pts.length < 3) return { area: 0, perimeter: pts.length === 2 ? 2 * Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y) : 0, clockwise: false };
  // Centre on the first vertex: with raw EGSA87 values x·y ≈ 2·10¹² and the cross products
  // cancel catastrophically (≈ 0.3 mm² error on a 6 dm² polygon).
  const ox = pts[0].x;
  const oy = pts[0].y;
  let s = 0;
  let per = 0;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % pts.length];
    s += (a.x - ox) * (b.y - oy) - (b.x - ox) * (a.y - oy);
    per += Math.hypot(b.x - a.x, b.y - a.y);
  }
  return { area: Math.abs(s) / 2, perimeter: per, clockwise: s < 0 };
}

/** Length of an open polyline. */
export function polylineLength(pts: Pt[]): number {
  let l = 0;
  for (let i = 1; i < pts.length; i++) l += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
  return l;
}

/**
 * Error ellipse outline in EGSA87 metres. `theta` is the azimuth of the major axis
 * (clockwise from grid north), `scale` exaggerates the axes for display.
 */
export function ellipsePolygon(cx: number, cy: number, a: number, b: number, theta: number, scale = 1, n = 48): [number, number][] {
  const out: [number, number][] = [];
  const sa = Math.sin(theta);
  const ca = Math.cos(theta);
  for (let i = 0; i <= n; i++) {
    const t = (i / n) * 2 * Math.PI;
    // local frame: u along the major axis, v along the minor axis
    const u = a * scale * Math.cos(t);
    const v = b * scale * Math.sin(t);
    // major axis direction (sa, ca) in (east, north); minor axis is perpendicular (ca, -sa)
    out.push([cx + u * sa + v * ca, cy + u * ca - v * sa]);
  }
  return out;
}

/** Chainage in the usual km+m form: 1234.567 → "1+234.567". */
export function formatChainage(m: number, decimals = 3): string {
  if (!Number.isFinite(m)) return "—";
  const sign = m < 0 ? "-" : "";
  const abs = Math.abs(m);
  const fixed = abs.toFixed(decimals);
  const [int, frac] = fixed.split(".");
  const km = Math.floor(Number(int) / 1000);
  const rest = (Number(int) % 1000).toString().padStart(3, "0");
  return `${sign}${km}+${rest}${frac !== undefined ? `.${frac}` : ""}`;
}

/** Area with Greek-friendly grouping: 12345.678 → "12 345.68 m²" (+ στρέμματα when large). */
export function formatArea(m2: number, decimals = 2): string {
  if (!Number.isFinite(m2)) return "—";
  const [int, frac] = m2.toFixed(decimals).split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return `${grouped}${frac ? `.${frac}` : ""} m²`;
}

/** 1 στρέμμα = 1000 m² */
export function toStremmata(m2: number): number {
  return m2 / 1000;
}
