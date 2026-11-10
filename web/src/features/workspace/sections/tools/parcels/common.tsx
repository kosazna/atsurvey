// Shared building blocks of the parcel tools: vertex list input (paste / project points / map
// picking), SVG sketch, coordinate and side tables, issues and CSV download.
import { AlertTriangle, Download, Info, MousePointerClick, XCircle } from "lucide-react";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { angleToInput, formatAngle } from "@/lib/angles";
import { formatArea } from "@/lib/geometry";
import { type CutLine, type ParcelGeometry, type ParcelVertex, sidesCsv, stremmata, svgFrame, toVertices, verticesCsv } from "@/lib/parcelsApi";
import type { Issue } from "@/lib/types";
import { cn, downloadBlob, fmtNum } from "@/lib/utils";
import { issueText } from "../../../issues";
import { type PickedPoint, useWorkspace } from "../../../useWorkspace";
import { parsePointList, PointListField, useProjectPoints } from "../shared";

/** Vertex list state: textarea text, parsed vertices and map picking (appends one line per click). */
export function useVertexList(pickId: string) {
  const ws = useWorkspace();
  const pts = useProjectPoints();
  const [text, setText] = useState("");
  const parsed = parsePointList(text, pts);
  const vertices: ParcelVertex[] = toVertices(parsed.pts);
  const picking = ws.pick !== null && ws.pick.name === pickId;
  const togglePick = useCallback(() => {
    if (picking) return ws.setPick(null);
    ws.revealMap();
    const fn = Object.defineProperty(
      (p: PickedPoint) => setText((cur) => (cur.trim() ? `${cur.trimEnd()}\n` : "") + (p.name ?? `${p.x.toFixed(3)} ${p.y.toFixed(3)}`)),
      "name",
      { value: pickId },
    ) as (p: PickedPoint) => void;
    ws.setPick(fn);
  }, [picking, pickId, ws]);
  return { text, setText, vertices, bad: parsed.bad, picking, togglePick };
}

export function VertexInput({ state, label, testId }: { state: ReturnType<typeof useVertexList>; label?: string; testId?: string }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2">
      <PointListField label={label ?? t("parcels.vertices")} value={state.text} onChange={state.setText} hint={t("parcels.verticesHint")} testId={testId} />
      {state.bad.length > 0 && <p className="text-xs text-danger">{t("tools.badLines", { lines: state.bad.slice(0, 3).join(" · ") })}</p>}
      <Button type="button" variant="outline" size="sm" aria-pressed={state.picking} className={cn(state.picking && "border-accent bg-accent-subtle text-accent")} onClick={state.togglePick}>
        <MousePointerClick /> {state.picking ? t("parcels.picking") : t("parcels.pick")}
      </Button>
    </div>
  );
}

/** "1 234.56 m² · 1.235 στρ." */
export function AreaText({ m2 }: { m2: number | null | undefined }) {
  const { t } = useTranslation();
  if (m2 === null || m2 === undefined) return <>—</>;
  return (
    <>
      {formatArea(m2, 2)} <span className="text-muted">· {stremmata(m2).toFixed(3)} {t("parcels.stremmata")}</span>
    </>
  );
}

export function IssueList({ issues }: { issues: Issue[] }) {
  if (issues.length === 0) return null;
  return (
    <ul className="space-y-1 text-sm" data-testid="parcel-issues">
      {issues.map((iss, i) => {
        const Icon = iss.severity === "error" ? XCircle : iss.severity === "warning" ? AlertTriangle : Info;
        return (
          <li key={i} className={cn("flex items-start gap-2", iss.severity === "error" ? "text-danger" : iss.severity === "warning" ? "text-warning" : "text-muted")}>
            <Icon className="mt-0.5 size-4 shrink-0" />
            <span>{issueText(iss)}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function CsvButton({ csv, filename, label = "CSV" }: { csv: string; filename: string; label?: string }) {
  return (
    <Button size="sm" variant="outline" onClick={() => downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), filename)}>
      <Download /> {label}
    </Button>
  );
}

function slug(label: string, fallback: string): string {
  const s = label.trim().replace(/[^\p{L}\p{N}_-]+/gu, "_");
  return s || fallback;
}

/** Coordinate table + side table with CSV downloads. */
export function ParcelTables({ geo, name = "parcel" }: { geo: ParcelGeometry; name?: string }) {
  const { t } = useTranslation();
  const unit = useWorkspace().data.meta.angle_unit;
  const base = slug(geo.label, name);
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium">{t("parcels.coordinates")}</span>
          <CsvButton csv={verticesCsv(geo)} filename={`${base}-coordinates.csv`} />
        </div>
        <table className="w-full text-sm tabular">
          <thead>
            <tr className="border-b text-xs text-muted">
              <th className="py-1 text-left font-medium">{t("parcels.point")}</th>
              <th className="py-1 text-right font-medium">X</th>
              <th className="py-1 text-right font-medium">Y</th>
            </tr>
          </thead>
          <tbody>
            {geo.vertices.map((v, i) => (
              <tr key={`${v.name}-${i}`} className="border-b last:border-0">
                <td className="py-1">{v.name}</td>
                <td className="py-1 text-right">{fmtNum(v.x, 3)}</td>
                <td className="py-1 text-right">{fmtNum(v.y, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium">{t("parcels.sides")}</span>
          <CsvButton csv={sidesCsv(geo, (r) => angleToInput(r, unit, 4), unit)} filename={`${base}-sides.csv`} />
        </div>
        <div className="scroll-x-visible">
          <table className="w-full text-sm tabular">
            <thead>
              <tr className="border-b text-xs text-muted">
                <th className="py-1 text-left font-medium">{t("parcels.from")}</th>
                <th className="py-1 text-left font-medium">{t("parcels.to")}</th>
                <th className="py-1 text-right font-medium">{t("parcels.length")}</th>
                <th className="py-1 text-right font-medium">{t("parcels.azimuth")}</th>
                {geo.has_arcs && <th className="py-1 text-right font-medium">{t("parcels.arcLength")}</th>}
                {geo.has_arcs && <th className="py-1 text-right font-medium">{t("parcels.radius")}</th>}
              </tr>
            </thead>
            <tbody>
              {geo.sides.map((s, i) => (
                <tr key={i} className="border-b last:border-0">
                  <td className="py-1">{s.frm}</td>
                  <td className="py-1">{s.to}</td>
                  <td className="py-1 text-right">{fmtNum(s.length, 3)}</td>
                  <td className="py-1 text-right">{formatAngle(s.azimuth, unit)}</td>
                  {geo.has_arcs && <td className="py-1 text-right">{s.arc_length ? fmtNum(s.arc_length, 3) : ""}</td>}
                  {geo.has_arcs && <td className="py-1 text-right">{s.radius ? fmtNum(s.radius, 3) : ""}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/** Inline sketch (north up): parcels filled with token colours, cut lines dashed, vertex labels. */
export function ParcelSketch({ parcels, cuts = [], highlight }: { parcels: { vertices: ParcelVertex[]; label?: string }[]; cuts?: CutLine[]; highlight?: number }) {
  const { t } = useTranslation();
  const frame = svgFrame(parcels.map((p) => p.vertices));
  if (!frame || parcels.every((p) => p.vertices.length < 2)) return null;
  const { tx, ty } = frame;
  const seen = new Set<string>();
  const labels = parcels.flatMap((p) => p.vertices).filter((v) => (seen.has(v.name) ? false : (seen.add(v.name), true)));
  return (
    <figure className="space-y-1">
      <figcaption className="text-xs text-muted">{t("parcels.preview")}</figcaption>
      <svg viewBox={frame.viewBox} className="aspect-square w-full max-w-sm rounded-lg border bg-surface-sunken" role="img" aria-label={t("parcels.preview")} data-testid="parcel-sketch">
        {parcels.map((p, i) => (
          <polygon
            key={i}
            points={p.vertices.map((v) => `${tx(v.x)},${ty(v.y)}`).join(" ")}
            className={cn("stroke-fg", i === highlight || (highlight === undefined && i % 2 === 0) ? "fill-accent-subtle" : "fill-surface")}
            strokeWidth={1.25}
            strokeLinejoin="round"
          />
        ))}
        {parcels.map((p, i) => {
          if (!p.label || p.vertices.length < 3) return null;
          const cx = p.vertices.reduce((s, v) => s + tx(v.x), 0) / p.vertices.length;
          const cy = p.vertices.reduce((s, v) => s + ty(v.y), 0) / p.vertices.length;
          return (
            <text key={`l${i}`} x={cx} y={cy} textAnchor="middle" dominantBaseline="middle" className="fill-accent text-[11px] font-semibold">
              {p.label}
            </text>
          );
        })}
        {cuts.map((c, i) => (
          <line key={`c${i}`} x1={tx(c.a.x)} y1={ty(c.a.y)} x2={tx(c.b.x)} y2={ty(c.b.y)} className="stroke-danger" strokeWidth={1.5} strokeDasharray="5 3" />
        ))}
        {labels.map((v) => (
          <g key={v.name}>
            <circle cx={tx(v.x)} cy={ty(v.y)} r={2.5} className="fill-fg" />
            <text x={tx(v.x) + 4} y={ty(v.y) - 4} className="fill-muted text-[9px]">
              {v.name}
            </text>
          </g>
        ))}
      </svg>
    </figure>
  );
}
