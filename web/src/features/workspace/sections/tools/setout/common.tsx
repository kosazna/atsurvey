// Shared pieces of the setting-out tools: DXF import into a point list, issue list, CSV
// button and a small north-up SVG sketch (token colours only).
import { AlertTriangle, Download, FileUp, Info } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { apiErrorMessage } from "@/lib/apiErrors";
import { svgFrame } from "@/lib/setoutApi";
import type { Issue } from "@/lib/types";
import { cn, downloadBlob } from "@/lib/utils";
import { issueText } from "../../../issues";

/** Reads a DXF with the existing importer (/v1/parse) and appends "name X Y [Z]" lines. */
export function DxfImportButton({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    try {
      const res = await api.parse(file, { format: "dxf" });
      const lines = res.control_points.map((p) => [p.name, p.x.toFixed(4), p.y.toFixed(4), ...(p.z === null || p.z === undefined ? [] : [p.z.toFixed(4)])].join(" "));
      onChange((value.trim() ? `${value.trimEnd()}\n` : "") + lines.join("\n"));
      toast.success(t("setout.imported", { count: lines.length }));
    } catch (e) {
      toast.error(apiErrorMessage(e, t));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };
  return (
    <>
      <input ref={input} type="file" accept=".dxf" className="hidden" onChange={(e) => void onFile(e.target.files?.[0])} />
      <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={() => input.current?.click()}>
        <FileUp /> {t("setout.importDxf")}
      </Button>
    </>
  );
}

export function IssueList({ issues }: { issues: Issue[] }) {
  if (!issues.length) return null;
  return (
    <ul className="space-y-1">
      {issues.map((i, k) => (
        <li
          key={k}
          className={cn(
            "flex items-start gap-2 rounded-lg px-3 py-1.5 text-xs",
            i.severity === "error" ? "bg-danger-subtle text-danger" : i.severity === "warning" ? "bg-warning-subtle text-warning" : "bg-info-subtle text-info",
          )}
        >
          {i.severity === "info" ? <Info className="mt-0.5 size-3.5 shrink-0" /> : <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />}
          {issueText(i)}
        </li>
      ))}
    </ul>
  );
}

export function CsvButton({ text, filename }: { text: string; filename: string }) {
  return (
    <Button size="sm" variant="outline" disabled={!text} onClick={() => downloadBlob(new Blob([text], { type: "text/csv;charset=utf-8" }), filename)}>
      <Download /> CSV
    </Button>
  );
}

export interface SketchPoint {
  x: number;
  y: number;
  label?: string;
  tone: "station" | "input" | "result" | "danger";
}

const TONE: Record<SketchPoint["tone"], string> = {
  station: "text-accent",
  input: "text-muted",
  result: "text-fg",
  danger: "text-danger",
};

/** North-up sketch: lines (solid or dashed) and labelled points, scaled to fit. */
export function Sketch({
  lines = [],
  dashed = [],
  points = [],
  height = 260,
  testId,
}: {
  lines?: [number, number][][];
  dashed?: [number, number][][];
  points?: SketchPoint[];
  height?: number;
  testId?: string;
}) {
  const xs = [...lines.flat(), ...dashed.flat()].map((p) => p[0]).concat(points.map((p) => p.x));
  const ys = [...lines.flat(), ...dashed.flat()].map((p) => p[1]).concat(points.map((p) => p.y));
  if (!xs.length) return null;
  const f = svgFrame(xs, ys);
  const unit = Math.max(f.width, f.height) / 100; // 1 % of the drawing
  const path = (pl: [number, number][]) => pl.map((p, i) => `${i ? "L" : "M"}${f.toSvg(p[0], p[1]).map((v) => v.toFixed(3)).join(" ")}`).join(" ");
  return (
    <svg viewBox={`0 0 ${f.width} ${f.height}`} className="w-full rounded-lg border bg-surface-sunken" style={{ height }} data-testid={testId} role="img">
      {dashed.map((pl, i) => (
        <path key={`d${i}`} d={path(pl)} fill="none" className="text-muted" stroke="currentColor" strokeWidth={unit * 0.3} strokeDasharray={`${unit} ${unit}`} />
      ))}
      {lines.map((pl, i) => (
        <path key={`l${i}`} d={path(pl)} fill="none" className="text-accent" stroke="currentColor" strokeWidth={unit * 0.5} strokeLinejoin="round" />
      ))}
      {points.map((p, i) => {
        const [sx, sy] = f.toSvg(p.x, p.y);
        return (
          <g key={`p${i}`} className={TONE[p.tone]}>
            <circle cx={sx} cy={sy} r={unit * (p.tone === "station" ? 1.2 : 0.8)} fill="currentColor" />
            {p.label && (
              <text x={sx + unit * 1.2} y={sy - unit * 1.2} fontSize={unit * 2.6} fill="currentColor">
                {p.label}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
