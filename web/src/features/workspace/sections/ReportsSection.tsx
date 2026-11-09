import { AlertTriangle, CheckCircle2, ChevronDown, FileText, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty";
import { formatAngle, formatCc, formatMisclosure } from "@/lib/angles";
import type { TraverseResult } from "@/lib/types";
import { cn, fmtInt, fmtNum, fmtSigned } from "@/lib/utils";
import { useWorkspace } from "../useWorkspace";
import { RouteChips } from "./TraversesSection";
import { SectionFrame, SectionHeader } from "./SectionLayout";

export function TraverseStatusBadge({ status }: { status: TraverseResult["status"] }) {
  const { t } = useTranslation();
  if (status === "ok")
    return (
      <Badge variant="success">
        <CheckCircle2 /> {t("trav.status.ok")}
      </Badge>
    );
  if (status === "warning")
    return (
      <Badge variant="warning">
        <AlertTriangle /> {t("trav.status.warning")}
      </Badge>
    );
  return (
    <Badge variant="destructive">
      <XCircle /> {t("trav.status.failed")}
    </Badge>
  );
}

type Tone = "ok" | "bad" | "none";

function Metric({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone: Tone }) {
  return (
    <div className="rounded-lg border bg-background/50 px-3 py-2">
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span className={cn("size-1.5 rounded-full", tone === "ok" ? "bg-success" : tone === "bad" ? "bg-destructive" : "bg-border")} />
        {label}
      </div>
      <div className={cn("mt-0.5 text-base font-semibold tabular", tone === "bad" && "text-destructive")}>{value}</div>
      {sub && <div className="text-[11px] tabular text-muted-foreground">{sub}</div>}
    </div>
  );
}

function tone(value: number | null, tol: number | null): Tone {
  if (value === null || tol === null) return "none";
  return Math.abs(value) <= tol ? "ok" : "bad";
}

const th = "px-2 py-1.5 text-right text-[11px] font-medium text-muted-foreground whitespace-nowrap";
const td = "px-2 py-1 text-right tabular whitespace-nowrap";

function Sheet({ tr }: { tr: TraverseResult }) {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  return (
    <div className="space-y-4 border-t px-4 py-3">
      <div className="overflow-x-auto">
        <div className="mb-1 text-xs font-medium">{t("reports.stations")}</div>
        <table className="w-full text-xs">
          <thead className="border-b">
            <tr>
              <th className={cn(th, "text-left")}>{t("reports.cols.station")}</th>
              <th className={cn(th, "text-left")}>{t("reports.cols.bs")}</th>
              <th className={cn(th, "text-left")}>{t("reports.cols.fs")}</th>
              <th className={th}>{t("reports.cols.measured")}</th>
              <th className={th}>{t("reports.cols.correction")}</th>
              <th className={th}>{t("reports.cols.corrected")}</th>
              <th className={th}>{t("reports.cols.azimuth")}</th>
              <th className={th}>X</th>
              <th className={th}>Y</th>
              <th className={th}>Z</th>
            </tr>
          </thead>
          <tbody>
            {tr.stations.map((s, i) => (
              <tr
                key={i}
                className={cn("cursor-pointer border-b border-border/50 hover:bg-accent/60", ws.selected === s.station && "bg-primary/8")}
                onClick={() => ws.setSelected(s.station)}
              >
                <td className={cn(td, "text-left font-medium")}>
                  {s.station}
                  {s.known && <span className="ml-1 text-pt-control">▲</span>}
                </td>
                <td className={cn(td, "text-left text-muted-foreground")}>{s.backsight}</td>
                <td className={cn(td, "text-left text-muted-foreground")}>{s.foresight}</td>
                <td className={td}>{formatAngle(s.angle_measured, unit)}</td>
                <td className={cn(td, "text-muted-foreground")}>{unit === "gon" ? formatCc(s.angle_correction) : formatMisclosure(s.angle_correction, unit)}</td>
                <td className={td}>{formatAngle(s.angle_corrected, unit)}</td>
                <td className={td}>{formatAngle(s.azimuth, unit)}</td>
                <td className={td}>{fmtNum(s.x, 3)}</td>
                <td className={td}>{fmtNum(s.y, 3)}</td>
                <td className={td}>{fmtNum(s.z, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="overflow-x-auto">
        <div className="mb-1 text-xs font-medium">{t("reports.legs")}</div>
        <table className="w-full text-xs">
          <thead className="border-b">
            <tr>
              <th className={cn(th, "text-left")}>{t("reports.cols.from")}</th>
              <th className={cn(th, "text-left")}>{t("reports.cols.to")}</th>
              <th className={th}>{t("reports.cols.hd")}</th>
              <th className={th}>{t("reports.cols.fb")}</th>
              <th className={th}>{t("reports.cols.ef")}</th>
              <th className={th}>{t("reports.cols.k")}</th>
              <th className={th}>{t("reports.cols.grid")}</th>
              <th className={th}>{t("reports.cols.dx")}</th>
              <th className={th}>{t("reports.cols.dy")}</th>
              <th className={th}>{t("reports.cols.cx")} mm</th>
              <th className={th}>{t("reports.cols.cy")} mm</th>
              <th className={th}>{t("reports.cols.dh")}</th>
              <th className={th}>{t("reports.cols.ch")} mm</th>
            </tr>
          </thead>
          <tbody>
            {tr.legs.map((l, i) => (
              <tr key={i} className="border-b border-border/50">
                <td className={cn(td, "text-left font-medium")}>{l.frm}</td>
                <td className={cn(td, "text-left font-medium")}>{l.to}</td>
                <td className={td}>
                  {fmtNum(l.hd_measured, 3)}
                  <span className="ml-1 text-[10px] text-muted-foreground">×{l.n_measurements}</span>
                </td>
                <td className={cn(td, "text-muted-foreground")}>{l.distance_fb_diff === null ? "—" : fmtSigned(l.distance_fb_diff, 3)}</td>
                <td className={cn(td, "text-muted-foreground")}>{fmtNum(l.elevation_factor, 7)}</td>
                <td className={cn(td, "text-muted-foreground")}>{fmtNum(l.reduction_scale, 7)}</td>
                <td className={td}>{fmtNum(l.distance_grid, 3)}</td>
                <td className={td}>{fmtSigned(l.dx, 3)}</td>
                <td className={td}>{fmtSigned(l.dy, 3)}</td>
                <td className={cn(td, "text-muted-foreground")}>{fmtSigned(l.corr_x * 1000, 1)}</td>
                <td className={cn(td, "text-muted-foreground")}>{fmtSigned(l.corr_y * 1000, 1)}</td>
                <td className={td}>{l.dh === null ? "—" : fmtSigned(l.dh, 3)}</td>
                <td className={cn(td, "text-muted-foreground")}>{fmtSigned(l.corr_h * 1000, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TraverseReport({ tr, defaultOpen }: { tr: TraverseResult; defaultOpen: boolean }) {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const [open, setOpen] = useState(defaultOpen);
  const ref = useRef<HTMLDivElement>(null);
  const known = new Set(ws.data.control_points.map((p) => p.name));
  const minRel = ws.data.settings.tolerances.min_relative_precision;

  useEffect(() => {
    if (defaultOpen) ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [defaultOpen]);

  const relTone: Tone = tr.relative_precision === null || !minRel ? "none" : tr.relative_precision >= minRel ? "ok" : "bad";
  const hasClosure = tr.linear_misclosure !== null;

  return (
    <div ref={ref} className="overflow-hidden rounded-xl border bg-card shadow-xs" data-testid="traverse-report">
      <div className="flex flex-wrap items-start gap-3 px-4 pt-3.5">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-sm font-semibold">{tr.name}</h3>
            <Badge variant="secondary">{t(`traverseKind.${tr.kind}`)}</Badge>
          </div>
          <RouteChips route={tr.route} known={known} className="mt-1.5" />
        </div>
        <TraverseStatusBadge status={tr.status} />
      </div>
      <div className="grid grid-cols-2 gap-2 px-4 py-3 sm:grid-cols-3 xl:grid-cols-6">
        <Metric label={t("reports.length")} value={`${tr.length.toFixed(2)} m`} sub={`${t("reports.nAngles")}: ${tr.n_angles}`} tone="none" />
        <Metric
          label={t("reports.angular")}
          value={formatMisclosure(tr.angular_misclosure, unit)}
          sub={tr.angular_tolerance !== null ? t("reports.tolerance", { value: formatMisclosure(tr.angular_tolerance, unit).replace("+", "±") }) : undefined}
          tone={tone(tr.angular_misclosure, tr.angular_tolerance)}
        />
        <Metric
          label={t("reports.linear")}
          value={tr.linear_misclosure === null ? "—" : `${(tr.linear_misclosure * 100).toFixed(1)} cm`}
          sub={tr.linear_tolerance !== null ? t("reports.tolerance", { value: `${(tr.linear_tolerance * 100).toFixed(1)} cm` }) : undefined}
          tone={tone(tr.linear_misclosure, tr.linear_tolerance)}
        />
        <Metric
          label="wX · wY"
          value={tr.wx === null ? "—" : `${fmtSigned((tr.wx ?? 0) * 100, 1)} · ${fmtSigned((tr.wy ?? 0) * 100, 1)}`}
          sub="cm"
          tone="none"
        />
        <Metric
          label={t("reports.relative")}
          value={tr.relative_precision ? `1:${fmtInt(tr.relative_precision)}` : "—"}
          sub={minRel ? t("reports.tolerance", { value: `1:${fmtInt(minRel)}` }) : undefined}
          tone={relTone}
        />
        <Metric
          label={t("reports.height")}
          value={tr.wz === null ? "—" : `${fmtSigned(tr.wz * 100, 1)} cm`}
          sub={tr.height_tolerance !== null ? t("reports.tolerance", { value: `${(tr.height_tolerance * 100).toFixed(1)} cm` }) : undefined}
          tone={tone(tr.wz, tr.height_tolerance)}
        />
      </div>
      {!hasClosure && <p className="px-4 pb-2 text-xs text-muted-foreground">{t("reports.noClosure")}</p>}
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full cursor-pointer items-center gap-1.5 border-t px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-accent/50 hover:text-foreground"
        aria-expanded={open}
      >
        <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
        {open ? t("reports.hideSheet") : t("reports.showSheet")}
      </button>
      {open && <Sheet tr={tr} />}
    </div>
  );
}

export function ReportsSection() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const travs = ws.result?.traverses ?? [];
  return (
    <SectionFrame>
      <SectionHeader title={t("reports.title")} />
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {travs.length === 0 ? (
          <EmptyState icon={<FileText />} title={t("reports.empty")} action={<Button size="sm" onClick={() => ws.goTo("traverses")}>{t("ws.sections.traverses")}</Button>} />
        ) : (
          <div className="space-y-4">
            {travs.map((tr, i) => (
              <TraverseReport key={tr.id ?? tr.name} tr={tr} defaultOpen={ws.focus.traverse ? ws.focus.traverse === (tr.id ?? tr.name) : i === 0 && travs.length === 1} />
            ))}
          </div>
        )}
      </div>
    </SectionFrame>
  );
}
