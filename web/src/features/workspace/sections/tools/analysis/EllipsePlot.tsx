// Inline SVG plan of the planned network: points, observation lines (coloured by reliability)
// and 95 % absolute error ellipses at an exaggeration that is shown on the plot.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { autoEllipseScale, type ObservationStatus, type PlannedPoint, type PointPrecision } from "@/lib/analysisApi";

export interface PlotLine {
  a: string;
  b: string;
  status?: ObservationStatus;
}

const LINE_CLASS: Record<ObservationStatus, string> = {
  ok: "text-border-strong",
  weak: "text-warning",
  uncontrolled: "text-danger",
  excluded: "text-border-strong opacity-40",
};

export function EllipsePlot({ points, lines, precision }: { points: PlannedPoint[]; lines: PlotLine[]; precision: PointPrecision[] }) {
  const { t } = useTranslation();
  const geo = useMemo(() => {
    if (!points.length) return null;
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const extent = Math.max(maxX - minX, maxY - minY, 1);
    const pad = extent * 0.08;
    const maxA = Math.max(0, ...precision.map((p) => p.a95 ?? 0));
    return { minX: minX - pad, maxY: maxY + pad, w: maxX - minX + 2 * pad, h: maxY - minY + 2 * pad, extent, scale: autoEllipseScale(maxA, extent) };
  }, [points, precision]);
  if (!geo) return null;
  const byName = new Map(points.map((p) => [p.name, p]));
  const sx = (x: number) => x - geo.minX;
  const sy = (y: number) => geo.maxY - y; // north up
  const r = geo.extent * 0.008;
  const font = geo.extent * 0.022;
  return (
    <figure className="space-y-1">
      <svg viewBox={`0 0 ${geo.w} ${geo.h}`} className="h-auto max-h-[480px] w-full rounded-lg border bg-surface-sunken" role="img" aria-label={t("analysis.plot")} data-testid="preanalysis-plot">
        {lines.map((l, i) => {
          const a = byName.get(l.a);
          const b = byName.get(l.b);
          if (!a || !b) return null;
          return <line key={i} x1={sx(a.x)} y1={sy(a.y)} x2={sx(b.x)} y2={sy(b.y)} stroke="currentColor" strokeWidth={1} vectorEffect="non-scaling-stroke" className={LINE_CLASS[l.status ?? "ok"]} />;
        })}
        {precision.map((p) => {
          const pt = byName.get(p.name);
          if (!pt || !p.ellipse || p.a95 === null || p.b95 === null) return null;
          const rot = (p.ellipse.theta * 180) / Math.PI - 90; // azimuth of the major axis → SVG angle
          return (
            <ellipse
              key={p.name}
              cx={sx(pt.x)}
              cy={sy(pt.y)}
              rx={Math.max(p.a95 * geo.scale, 1e-9)}
              ry={Math.max(p.b95 * geo.scale, 1e-9)}
              transform={`rotate(${rot} ${sx(pt.x)} ${sy(pt.y)})`}
              fill="currentColor"
              fillOpacity={0.12}
              stroke="currentColor"
              strokeWidth={1.5}
              vectorEffect="non-scaling-stroke"
              className="text-accent"
            />
          );
        })}
        {points.map((p) => (
          <g key={p.name} className={p.fixed ? "text-fg" : "text-accent"}>
            {p.fixed ? (
              <path d={`M ${sx(p.x)} ${sy(p.y) - r * 1.3} l ${r * 1.2} ${r * 2} h ${-r * 2.4} Z`} fill="currentColor" />
            ) : (
              <circle cx={sx(p.x)} cy={sy(p.y)} r={r} fill="currentColor" />
            )}
            <text x={sx(p.x) + r * 1.6} y={sy(p.y) - r * 1.2} fontSize={font} fill="currentColor" className="text-fg">
              {p.name}
            </text>
          </g>
        ))}
      </svg>
      <figcaption className="flex flex-wrap justify-between gap-2 text-xs text-muted">
        <span data-testid="preanalysis-scale">{t("analysis.plotScale", { k: geo.scale })}</span>
        <span>{t("analysis.plotLegend")}</span>
      </figcaption>
    </figure>
  );
}
