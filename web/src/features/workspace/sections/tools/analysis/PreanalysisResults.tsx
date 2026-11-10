// Pre-analysis results: summary, issues, and tables of point precision, observation
// reliability (r, MDB, external reliability) and relative ellipses.
import { AlertTriangle, Info, XCircle } from "lucide-react";
import { Suspense, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatAngle, radToCc } from "@/lib/angles";
import { type DirectionUnit, fromCc, type ObservationReliability, type PointPrecision, type PreanalysisResult, type RelativePrecision } from "@/lib/analysisApi";
import type { Severity } from "@/lib/types";
import { fmtNum } from "@/lib/utils";
import type { Col } from "../../../grid/DataGrid";
import { DataGrid } from "../../../grid/LazyDataGrid";
import { issueText } from "../../../issues";
import { useWorkspace } from "../../../useWorkspace";

const ICON: Record<Severity, React.ReactNode> = {
  error: <XCircle className="mt-0.5 size-3.5 shrink-0 text-danger" />,
  warning: <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" />,
  info: <Info className="mt-0.5 size-3.5 shrink-0 text-muted" />,
};

const mm = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : fmtNum(v * 1000, d));

/** σ or MDB in display units: directions in cc/mgon, lengths in mm. */
export function obsValue(kind: ObservationReliability["kind"], v: number | null, unit: DirectionUnit): string {
  if (v === null) return "—";
  return kind === "direction" ? `${fmtNum(fromCc(radToCc(v), unit), unit === "cc" ? 1 : 2)} ${unit}` : `${mm(v)} mm`;
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-xl border bg-surface p-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-0.5 text-lg font-semibold tabular">{value}</div>
    </div>
  );
}

export function PreanalysisResults({ result, unit }: { result: PreanalysisResult; unit: DirectionUnit }) {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const angleUnit = ws.data.meta.angle_unit;
  const withPos = result.points.filter((p) => p.a95 !== null);
  const worst = withPos.reduce<PointPrecision | null>((w, p) => (!w || (p.a95 ?? 0) > (w.a95 ?? 0) ? p : w), null);
  const used = result.observations.filter((o) => o.status !== "excluded");
  const minR = used.length ? Math.min(...used.map((o) => o.redundancy)) : null;

  const ptCols = useMemo<Col<PointPrecision>[]>(
    () => [
      { id: "name", title: t("analysis.cols.point"), width: 90, get: (p) => p.name },
      { id: "sx", title: "σX mm", width: 76, kind: "number", get: (p) => mm(p.sx) },
      { id: "sy", title: "σY mm", width: 76, kind: "number", get: (p) => mm(p.sy) },
      { id: "spos", title: t("analysis.cols.spos"), width: 92, kind: "number", get: (p) => mm(p.spos) },
      { id: "a95", title: t("analysis.cols.a95"), width: 92, kind: "number", get: (p) => mm(p.a95) },
      { id: "b95", title: t("analysis.cols.b95"), width: 92, kind: "number", get: (p) => mm(p.b95) },
      { id: "th", title: t("analysis.cols.theta"), width: 100, kind: "number", get: (p) => (p.ellipse ? formatAngle(p.ellipse.theta, angleUnit, 2) : "—") },
      { id: "sz", title: t("analysis.cols.sz"), width: 76, kind: "number", get: (p) => mm(p.sz) },
    ],
    [t, angleUnit],
  );

  const obsCols = useMemo<Col<ObservationReliability>[]>(
    () => [
      { id: "kind", title: t("analysis.cols.kind"), width: 110, get: (o) => t(`analysis.kind.${o.kind}`) },
      { id: "from", title: t("analysis.cols.from"), width: 80, get: (o) => o.station },
      { id: "to", title: t("analysis.cols.to"), width: 80, get: (o) => o.target },
      { id: "sigma", title: t("analysis.cols.sigma"), width: 90, kind: "number", get: (o) => obsValue(o.kind, o.sigma, unit) },
      { id: "r", title: t("analysis.cols.r"), width: 64, kind: "number", get: (o) => (o.status === "excluded" ? "—" : o.redundancy.toFixed(2)), invalid: (o) => o.status === "uncontrolled" },
      { id: "mdb", title: t("analysis.cols.mdb"), width: 100, kind: "number", get: (o) => obsValue(o.kind, o.mdb, unit) },
      { id: "ext", title: t("analysis.cols.ext"), width: 64, kind: "number", get: (o) => fmtNum(o.external, 1) },
      { id: "shift", title: t("analysis.cols.shift"), width: 110, kind: "number", get: (o) => mm(o.max_shift) },
      { id: "at", title: t("analysis.cols.shiftAt"), width: 90, get: (o) => o.max_shift_point ?? "—" },
      { id: "status", title: t("analysis.cols.status"), width: 110, get: (o) => t(`analysis.status.${o.status}`), invalid: (o) => o.status === "uncontrolled", muted: (o) => o.status === "excluded" },
    ],
    [t, unit],
  );

  const relCols = useMemo<Col<RelativePrecision>[]>(
    () => [
      { id: "from", title: t("analysis.cols.from"), width: 80, get: (r) => r.frm },
      { id: "to", title: t("analysis.cols.to"), width: 80, get: (r) => r.to },
      { id: "d", title: t("analysis.cols.dist"), width: 90, kind: "number", get: (r) => fmtNum(r.distance, 3) },
      { id: "sd", title: t("analysis.cols.sDist"), width: 80, kind: "number", get: (r) => mm(r.s_distance) },
      { id: "st", title: t("analysis.cols.sTrans"), width: 120, kind: "number", get: (r) => mm(r.s_transverse) },
      { id: "a95", title: t("analysis.cols.a95"), width: 92, kind: "number", get: (r) => mm(r.a95) },
      { id: "b95", title: t("analysis.cols.b95"), width: 92, kind: "number", get: (r) => mm(r.b95) },
    ],
    [t],
  );

  return (
    <div className="space-y-3" data-testid="preanalysis-result">
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Metric label={t("analysis.summary.obs")} value={`${result.n_observations} / ${result.n_unknowns}`} />
        <Metric label={t("analysis.summary.dof")} value={result.dof} />
        <Metric label={t("analysis.summary.worst")} value={worst ? `${worst.name} · ${mm(worst.a95)} mm` : "—"} />
        <Metric label={t("analysis.summary.minR")} value={minR === null ? "—" : minR.toFixed(2)} />
      </div>
      <p className="text-xs text-muted tabular">
        {t("analysis.constants", {
          alpha: +(result.alpha0 * 100).toFixed(3),
          beta: +(result.beta0 * 100).toFixed(1),
          delta: result.delta0.toFixed(2),
          lambda: result.lambda0.toFixed(2),
          k: result.k95.toFixed(4),
        })}
      </p>
      {result.issues.length > 0 && (
        <ul className="space-y-1 rounded-lg border bg-surface-sunken p-2.5 text-xs" data-testid="preanalysis-issues">
          {result.issues.map((i, k) => (
            <li key={k} className="flex gap-2">
              {ICON[i.severity]} <span>{issueText(i)}</span>
            </li>
          ))}
        </ul>
      )}
      <Tabs defaultValue="pts" className="flex flex-col rounded-xl border bg-surface">
        <div className="border-b px-3 py-2">
          <TabsList>
            <TabsTrigger value="pts">{t("analysis.tabsPoints")}</TabsTrigger>
            <TabsTrigger value="obs">{t("analysis.tabsObs")}</TabsTrigger>
            <TabsTrigger value="rel">{t("analysis.tabsRelative")}</TabsTrigger>
          </TabsList>
        </div>
        {(
          [
            ["pts", <DataGrid key="p" testId="grid-preanalysis-points" rows={result.points} columns={ptCols} readonly onSelectRow={(i) => i !== null && result.points[i] && ws.setSelected(result.points[i].name)} />],
            ["obs", <DataGrid key="o" testId="grid-preanalysis-obs" rows={result.observations} columns={obsCols} readonly />],
            ["rel", <DataGrid key="r" rows={result.relative} columns={relCols} readonly />],
          ] as const
        ).map(([id, grid]) => (
          <TabsContent key={id} value={id} className="h-[360px] data-[state=inactive]:hidden">
            <Suspense fallback={<Skeleton className="m-4 h-56" />}>{grid}</Suspense>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
