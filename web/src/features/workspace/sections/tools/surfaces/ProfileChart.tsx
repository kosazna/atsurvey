// Small inline SVG of a ground line (long profile or cross-section). Token colours only.
import { chartFrame, type ProfileStation, runPaths, ticks } from "@/lib/surfacesApi";

interface Props {
  stations: ProfileStation[];
  x0: number;
  x1: number;
  title: string;
  /** draw a vertical axis line at x = 0 (cross-section centre line) */
  centre?: boolean;
  testId?: string;
}

export function ProfileChart({ stations, x0, x1, title, centre, testId }: Props) {
  const f = chartFrame(x0, x1, stations.map((s) => s.z));
  const xt = ticks(x0, x1, 6);
  const zt = ticks(f.z0, f.z1, 4);
  const decimals = (vals: number[]) => (vals.length > 1 && Math.abs(vals[1] - vals[0]) < 1 ? 1 : 0);
  const dx = decimals(xt);
  const dz = decimals(zt);
  return (
    <figure className="space-y-1" data-testid={testId}>
      <figcaption className="text-xs font-medium text-muted">{title}</figcaption>
      <svg viewBox={`0 0 ${f.width} ${f.height}`} className="h-auto w-full text-accent" role="img" aria-label={title}>
        <g stroke="var(--color-border)" strokeWidth={1}>
          {zt.map((z) => (
            <line key={`z${z}`} x1={f.pad} x2={f.width - f.pad} y1={f.sy(z)} y2={f.sy(z)} />
          ))}
          {xt.map((x) => (
            <line key={`x${x}`} x1={f.sx(x)} x2={f.sx(x)} y1={f.pad / 2} y2={f.height - f.pad} />
          ))}
        </g>
        {centre && x0 < 0 && x1 > 0 && <line x1={f.sx(0)} x2={f.sx(0)} y1={f.pad / 2} y2={f.height - f.pad} stroke="var(--color-text-subtle)" strokeDasharray="4 3" />}
        <g fill="var(--color-text-muted)" fontSize={10} className="tabular">
          {zt.map((z) => (
            <text key={`tz${z}`} x={f.pad - 4} y={f.sy(z) + 3} textAnchor="end">
              {z.toFixed(dz)}
            </text>
          ))}
          {xt.map((x) => (
            <text key={`tx${x}`} x={f.sx(x)} y={f.height - f.pad + 13} textAnchor="middle">
              {x.toFixed(dx)}
            </text>
          ))}
        </g>
        {runPaths(stations, f).map((d, i) => (
          <path key={i} d={d} fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinejoin="round" />
        ))}
      </svg>
    </figure>
  );
}
