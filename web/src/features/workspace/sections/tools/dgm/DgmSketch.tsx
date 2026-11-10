// Inline SVG of the ΔΓΜ layers (north up) in design-token colours, with problem markers.
import { useTranslation } from "react-i18next";
import { DRAW_ORDER, type LayerTone, layerTone } from "@/lib/dgmApi";
import { svgFrame } from "@/lib/parcelsApi";

export interface SketchShape {
  layer: string;
  closed: boolean;
  coords: [number, number][];
  label?: string;
}

const TONE: Record<LayerTone, { cls: string; width: number; dash?: string }> = {
  other: { cls: "stroke-muted fill-none", width: 0.75 },
  building: { cls: "stroke-muted fill-surface-sunken", width: 0.75 },
  survey: { cls: "stroke-warning fill-none", width: 1, dash: "3 2" },
  surveyNew: { cls: "stroke-info fill-none", width: 1, dash: "1 2" },
  cadastre: { cls: "stroke-fg fill-none", width: 1.5 },
  claimed: { cls: "stroke-success fill-success-subtle", width: 1 },
  cut: { cls: "stroke-danger fill-danger-subtle", width: 1 },
  final: { cls: "stroke-accent fill-accent-subtle", width: 2 },
  line: { cls: "stroke-danger fill-none", width: 1.75, dash: "6 3" },
};

const LEGEND_LAYERS: Record<LayerTone, string> = {
  other: "",
  building: "BLD",
  survey: "TOPO_PROP",
  surveyNew: "TOPO_PROP_NEW",
  cadastre: "PST_KAEK",
  claimed: "AREA_D",
  cut: "AREA_A",
  final: "DGM_PROP_FINAL",
  line: "LINE_XM",
};

interface DgmSketchProps {
  shapes: SketchShape[];
  marks?: { x: number; y: number }[];
  testId?: string;
}

export function DgmSketch({ shapes, marks = [], testId }: DgmSketchProps) {
  const { t } = useTranslation();
  const frame = svgFrame(
    shapes.map((s) => s.coords.map(([x, y]) => ({ x, y }))),
    420,
    18,
  );
  if (!frame) return null;
  const { tx, ty } = frame;
  const sorted = [...shapes].sort((a, b) => DRAW_ORDER.indexOf(layerTone(a.layer)) - DRAW_ORDER.indexOf(layerTone(b.layer)));
  const tones = DRAW_ORDER.filter((tone) => tone !== "other" && shapes.some((s) => layerTone(s.layer) === tone));
  return (
    <figure className="space-y-2">
      <svg viewBox={frame.viewBox} className="aspect-square w-full max-w-md rounded-lg border bg-surface-sunken" role="img" aria-label={t("dgm.sketch")} data-testid={testId}>
        {sorted.map((s, i) => {
          const tone = TONE[layerTone(s.layer)];
          const pts = s.coords.map(([x, y]) => `${tx(x)},${ty(y)}`).join(" ");
          const common = { className: tone.cls, strokeWidth: tone.width, strokeDasharray: tone.dash, strokeLinejoin: "round" as const, fillOpacity: 0.6 };
          return s.closed ? <polygon key={i} points={pts} {...common} /> : <polyline key={i} points={pts} {...common} fill="none" />;
        })}
        {sorted
          .filter((s) => s.label && s.closed && s.coords.length >= 3)
          .map((s, i) => {
            const cx = s.coords.reduce((a, [x]) => a + tx(x), 0) / s.coords.length;
            const cy = s.coords.reduce((a, [, y]) => a + ty(y), 0) / s.coords.length;
            return (
              <text key={`l${i}`} x={cx} y={cy} textAnchor="middle" dominantBaseline="middle" className="fill-fg text-[10px] font-semibold">
                {s.label}
              </text>
            );
          })}
        {marks.map((m, i) => (
          <circle key={`m${i}`} cx={tx(m.x)} cy={ty(m.y)} r={6} className="fill-none stroke-danger" strokeWidth={2} />
        ))}
      </svg>
      <figcaption className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {tones.map((tone) => (
          <span key={tone} className="inline-flex items-center gap-1.5">
            <svg viewBox="0 0 16 8" className="h-2 w-4" aria-hidden>
              <line x1={0} y1={4} x2={16} y2={4} className={TONE[tone].cls} strokeWidth={2} strokeDasharray={TONE[tone].dash} />
            </svg>
            {LEGEND_LAYERS[tone]}
          </span>
        ))}
        {marks.length > 0 && <span className="text-danger">○ {t("dgm.problem")}</span>}
      </figcaption>
    </figure>
  );
}
