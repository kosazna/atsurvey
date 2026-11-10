// Least-squares adjustment: global test, observation residuals with Baarda w-test,
// suspect observation with one-click exclusion, point precision and ellipse display scale,
// and the robust-estimation (IRLS) option with its down-weighted observations.
import { AlertTriangle, ArrowDownWideNarrow, CheckCircle2, Info, Sigma, XCircle } from "lucide-react";
import { Suspense, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatAngle, radToCc } from "@/lib/angles";
import type { AdjustedObservation, AdjustmentResult, AdjustmentSettings, ResultPoint, RobustMethod } from "@/lib/types";
import { cn, fmtNum, parseNum } from "@/lib/utils";
import type { Col } from "../grid/DataGrid";
import { DataGrid } from "../grid/LazyDataGrid";
import { issueText } from "../issues";
import { useWorkspace } from "../useWorkspace";
import { SectionFrame, SectionHeader } from "./SectionLayout";

/** Residual in display units: cc for directions, mm otherwise. */
export function residualDisplay(o: Pick<AdjustedObservation, "kind" | "residual">): string {
  return o.kind === "direction" ? `${radToCc(o.residual).toFixed(1)} cc` : `${(o.residual * 1000).toFixed(1)} mm`;
}

export type GlobalState = "pass" | "high" | "low" | "none";
export function globalState(a: AdjustmentResult): GlobalState {
  const g = a.global_test;
  if (!g) return "none";
  if (g.passed) return "pass";
  return g.statistic < g.lower ? "low" : "high";
}

const SCALES = [1, 10, 100, 500, 1000, 2500, 5000];

function Metric({ label, value, hint, tone }: { label: string; value: React.ReactNode; hint?: React.ReactNode; tone?: "ok" | "bad" | "warn" | "neutral" }) {
  return (
    <div className="rounded-xl border bg-surface p-3.5">
      <div className="flex items-center gap-1.5 text-xs text-muted">
        {tone && <span className={cn("size-1.5 rounded-full", tone === "ok" ? "bg-success" : tone === "bad" ? "bg-danger" : tone === "warn" ? "bg-warning" : "bg-border-strong")} />}
        {label}
      </div>
      <div className="mt-1 text-xl font-semibold tracking-tight tabular">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted tabular">{hint}</div>}
    </div>
  );
}

const ROBUST_METHODS: RobustMethod[] = ["off", "huber", "danish"];

/** A number input that commits on blur / Enter (each commit recomputes the project). */
function CommitNumber({ label, value, onCommit, min, max, integer }: { label: string; value: number; onCommit: (v: number) => void; min: number; max: number; integer?: boolean }) {
  const [text, setText] = useState(String(value));
  const commit = () => {
    const v = parseNum(text);
    if (v === null || v < min || v > max || (integer && !Number.isInteger(v))) {
      setText(String(value));
      return;
    }
    if (v !== value) onCommit(v);
  };
  return (
    <label className="flex items-center gap-1.5 text-xs text-muted">
      {label}
      <Input value={text} onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === "Enter" && commit()} inputMode="decimal" className="h-7 w-16 tabular" />
    </label>
  );
}

/** Robust estimation option (settings.adjustment.robust*) and the outcome of the last run. */
function RobustCard({ a }: { a: AdjustmentResult | null }) {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const adj = ws.data.settings.adjustment;
  const set = (patch: Partial<AdjustmentSettings>) => ws.update({ settings: { ...ws.data.settings, adjustment: { ...adj, ...patch } } });
  const rb = a?.robust ?? null;
  return (
    <Card className="flex flex-wrap items-center gap-3 p-3.5" data-testid="robust-card">
      <div className="min-w-0 flex-1 basis-64">
        <div className="text-sm font-medium">{t("analysis.robust.title")}</div>
        <div className="text-xs text-muted">{t("analysis.robust.hint")}</div>
        {rb && (
          <div className={cn("mt-1 text-xs tabular", rb.converged ? "text-muted" : "text-warning")} data-testid="robust-summary">
            {t("analysis.robust.summary", { method: t(`analysis.robust.method.${rb.method}`), n: rb.downweighted, it: rb.iterations })}
            {!rb.converged && ` · ${t("analysis.robust.notConverged")}`}
          </div>
        )}
      </div>
      <Select<RobustMethod>
        className="w-44"
        aria-label={t("analysis.robust.title")}
        value={adj.robust ?? "off"}
        onValueChange={(robust) => set({ robust })}
        options={ROBUST_METHODS.map((m) => ({ value: m, label: t(`analysis.robust.method.${m}`) }))}
      />
      {adj.robust && adj.robust !== "off" && (
        <>
          <CommitNumber key={`k${adj.robust_threshold}`} label={t("analysis.robust.threshold")} value={adj.robust_threshold} min={1} max={10} onCommit={(robust_threshold) => set({ robust_threshold })} />
          <CommitNumber key={`n${adj.robust_max_iterations}`} label={t("analysis.robust.maxIter")} value={adj.robust_max_iterations} min={1} max={100} integer onCommit={(robust_max_iterations) => set({ robust_max_iterations })} />
        </>
      )}
    </Card>
  );
}

export default function AdjustmentSection() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const method = ws.data.settings.adjustment.method;
  const a = ws.result?.adjustment ?? null;
  const [sortByW, setSortByW] = useState(true);

  const enable = () => {
    ws.update({ settings: { ...ws.data.settings, adjustment: { ...ws.data.settings.adjustment, method: "least_squares" } } });
    toast.success(t("adj.enabled"));
  };

  const rows = useMemo(() => {
    const list = [...(a?.observations ?? [])];
    if (sortByW) list.sort((x, y) => Math.abs(y.w ?? 0) - Math.abs(x.w ?? 0));
    return list;
  }, [a, sortByW]);

  const robustOn = !!a?.robust;
  const precise = useMemo(() => (ws.result?.points ?? []).filter((p) => p.sx !== null && p.sx !== undefined), [ws.result]);
  const adjIssues = (ws.result?.issues ?? []).filter((i) => i.code.startsWith("ADJUSTMENT"));

  const obsCols = useMemo<Col<AdjustedObservation>[]>(
    () => [
      { id: "kind", title: t("adj.cols.kind"), width: 100, get: (o) => t(`adj.kind.${o.kind}`) },
      { id: "from", title: t("adj.cols.station"), width: 80, get: (o) => o.station },
      { id: "to", title: t("adj.cols.target"), width: 80, get: (o) => o.target },
      {
        id: "obs",
        title: t("adj.cols.observed"),
        width: 120,
        kind: "number",
        get: (o) => (o.kind === "direction" ? formatAngle(o.observed, unit) : fmtNum(o.observed, 4)),
      },
      { id: "v", title: t("adj.cols.residual"), width: 100, kind: "number", get: (o) => residualDisplay(o), invalid: (o) => o.flagged },
      { id: "w", title: "w", width: 70, kind: "number", get: (o) => (o.w === null ? "—" : o.w.toFixed(2)), invalid: (o) => o.flagged },
      { id: "r", title: t("adj.cols.redundancy"), width: 80, kind: "number", get: (o) => o.redundancy.toFixed(2), muted: (o) => o.redundancy < 0.1 },
      {
        id: "sigma",
        title: "σ",
        width: 80,
        kind: "number",
        get: (o) => (o.kind === "direction" ? `${radToCc(o.sigma).toFixed(1)} cc` : `${(o.sigma * 1000).toFixed(1)} mm`),
      },
      ...(robustOn
        ? [{ id: "wt", title: t("analysis.robust.weight"), width: 80, kind: "number" as const, get: (o: AdjustedObservation) => (o.weight ?? 1).toFixed(3), invalid: (o: AdjustedObservation) => (o.weight ?? 1) < 0.99 }]
        : []),
    ],
    [t, unit, robustOn],
  );

  const ptCols = useMemo<Col<ResultPoint>[]>(
    () => [
      { id: "name", title: t("results.cols.name"), width: 90, get: (p) => p.name },
      { id: "sx", title: "σX mm", width: 80, kind: "number", get: (p) => fmtNum((p.sx ?? 0) * 1000, 1) },
      { id: "sy", title: "σY mm", width: 80, kind: "number", get: (p) => fmtNum((p.sy ?? 0) * 1000, 1) },
      { id: "sz", title: "σZ mm", width: 80, kind: "number", get: (p) => (p.sz === null || p.sz === undefined ? "—" : fmtNum(p.sz * 1000, 1)) },
      { id: "a", title: t("adj.cols.a95"), width: 100, kind: "number", get: (p) => (p.ellipse ? fmtNum(p.ellipse.a * p.ellipse.k95 * 1000, 1) : "—") },
      { id: "b", title: t("adj.cols.b95"), width: 100, kind: "number", get: (p) => (p.ellipse ? fmtNum(p.ellipse.b * p.ellipse.k95 * 1000, 1) : "—") },
      { id: "th", title: t("adj.cols.theta"), width: 110, kind: "number", get: (p) => (p.ellipse ? formatAngle(p.ellipse.theta, unit, 2) : "—") },
    ],
    [t, unit],
  );

  const exclude = (o: AdjustedObservation) => {
    let n = 0;
    const setups = ws.data.setups.map((s) =>
      s.station !== o.station
        ? s
        : {
            ...s,
            observations: s.observations.map((ob) => {
              if (ob.target !== o.target || ob.excluded) return ob;
              n++;
              return { ...ob, excluded: true, edited: true };
            }),
          },
    );
    if (!n) {
      toast.warning(t("adj.excludeNone"));
      return;
    }
    ws.update({ setups });
    toast.success(t("adj.excluded", { count: n, station: o.station, target: o.target }), {
      action: { label: t("ws.undo"), onClick: () => ws.undo() },
    });
  };

  if (method !== "least_squares") {
    return (
      <SectionFrame>
        <SectionHeader title={t("adj.title")} description={t("adj.subtitle")} />
        <EmptyState
          icon={<Sigma />}
          title={t("adj.offTitle")}
          description={t("adj.offText")}
          action={
            <Button size="sm" onClick={enable} data-testid="btn-enable-lsa">
              {t("adj.enable")}
            </Button>
          }
        />
      </SectionFrame>
    );
  }

  if (!a) {
    return (
      <SectionFrame>
        <SectionHeader title={t("adj.title")} description={t("adj.subtitle")} />
        <EmptyState
          icon={<Sigma />}
          title={ws.status === "computing" ? t("ws.computing") : t("adj.noResult")}
          description={adjIssues.length ? adjIssues.map((i) => issueText(i)).join(" · ") : t("adj.noResultText")}
          action={
            <Button size="sm" variant="outline" onClick={ws.compute}>
              {t("ws.compute")}
            </Button>
          }
        />
      </SectionFrame>
    );
  }

  const gs = globalState(a);
  const g = a.global_test;

  return (
    <SectionFrame className="overflow-y-auto lg:overflow-y-auto" >
      <SectionHeader
        title={t("adj.title")}
        description={t("adj.subtitle")}
        actions={
          <Badge variant={a.converged ? "secondary" : "warning"}>
            {a.converged ? t("adj.converged", { n: a.iterations }) : t("adj.notConverged")}
          </Badge>
        }
      />
      <div className="space-y-4 p-4" data-testid="adjustment">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Metric
            label="σ₀"
            value={a.sigma0.toFixed(2)}
            tone={gs === "pass" ? "ok" : gs === "high" ? "bad" : "neutral"}
            hint={g ? t("adj.range", { lo: Math.sqrt(g.lower / Math.max(a.dof, 1)).toFixed(2), hi: Math.sqrt(g.upper / Math.max(a.dof, 1)).toFixed(2) }) : undefined}
          />
          <Metric label={t("adj.dof")} value={a.dof} hint={t("adj.obsUnknowns", { n: a.n_observations, u: a.n_unknowns })} />
          <Metric label={t("adj.maxW")} value={a.max_w === null ? "—" : a.max_w.toFixed(2)} tone={a.suspect ? "bad" : "ok"} hint={t("adj.wCrit", { w: a.w_critical.toFixed(2) })} />
          <Metric label={t("adj.flagged")} value={a.observations.filter((o) => o.flagged).length} tone={a.observations.some((o) => o.flagged) ? "warn" : "ok"} hint={t("adj.ofTotal", { n: a.observations.length })} />
        </div>

        <RobustCard a={a} />

        <Card
          className={cn(
            "flex items-start gap-3 p-3.5 text-sm",
            gs === "pass" && "border-success bg-success-subtle",
            gs === "high" && "border-danger bg-danger-subtle",
            (gs === "low" || gs === "none") && "bg-surface-sunken",
          )}
          data-testid="global-test"
        >
          {gs === "pass" ? (
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />
          ) : gs === "high" ? (
            <XCircle className="mt-0.5 size-4 shrink-0 text-danger" />
          ) : (
            <Info className="mt-0.5 size-4 shrink-0 text-muted" />
          )}
          <div>
            <div className="font-medium">{t(`adj.global.${gs}`)}</div>
            <div className="mt-0.5 text-xs text-muted">
              {g
                ? t("adj.globalDetail", { stat: g.statistic.toFixed(2), lo: g.lower.toFixed(2), hi: g.upper.toFixed(2), alpha: ws.data.settings.adjustment.alpha_global })
                : t("adj.global.noneDetail")}
            </div>
          </div>
        </Card>

        {a.suspect && (
          <Card className="flex flex-wrap items-center gap-3 border-warning bg-warning-subtle p-3.5 text-sm" data-testid="suspect">
            <AlertTriangle className="size-4 shrink-0 text-warning" />
            <div className="min-w-0 flex-1">
              <div className="font-medium">
                {t("adj.suspectTitle", { kind: t(`adj.kind.${a.suspect.kind}`), from: a.suspect.station, to: a.suspect.target })}
              </div>
              <div className="text-xs text-muted tabular">
                w = {a.suspect.w?.toFixed(2)} · v = {residualDisplay(a.suspect)} · r = {a.suspect.redundancy.toFixed(2)}
              </div>
            </div>
            <Button size="sm" variant="outline" onClick={() => exclude(a.suspect!)} data-testid="btn-exclude-suspect">
              {t("adj.exclude")}
            </Button>
          </Card>
        )}

        <Card className="flex flex-wrap items-center gap-3 p-3.5">
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium">{t("adj.ellipseScale")}</div>
            <div className="text-xs text-muted">{t("adj.ellipseScaleHint")}</div>
          </div>
          <div className="flex rounded-md border p-0.5" role="radiogroup" aria-label={t("adj.ellipseScale")}>
            {SCALES.map((s) => (
              <button
                key={s}
                role="radio"
                aria-checked={ws.ellipseScale === s}
                onClick={() => {
                  ws.setEllipseScale(s);
                  ws.revealMap();
                }}
                className={cn("h-7 cursor-pointer rounded px-2 text-xs tabular", ws.ellipseScale === s ? "bg-accent-subtle font-medium text-accent" : "text-muted hover:text-fg")}
              >
                ×{s}
              </button>
            ))}
          </div>
        </Card>

        <Tabs defaultValue="obs" className="flex flex-col rounded-xl border bg-surface">
          <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
            <TabsList>
              <TabsTrigger value="obs">
                {t("adj.observations")} <span className="tabular text-muted">{a.observations.length}</span>
              </TabsTrigger>
              <TabsTrigger value="pts">
                {t("adj.precision")} <span className="tabular text-muted">{precise.length}</span>
              </TabsTrigger>
            </TabsList>
            <Button variant="ghost" size="sm" className="ml-auto" aria-pressed={sortByW} onClick={() => setSortByW(!sortByW)}>
              <ArrowDownWideNarrow /> {sortByW ? t("adj.sortedByW") : t("adj.sortByW")}
            </Button>
          </div>
          <TabsContent value="obs" className="h-[420px] data-[state=inactive]:hidden">
            <Suspense fallback={<Skeleton className="m-4 h-64" />}>
              <DataGrid
                testId="grid-adjustment"
                rows={rows}
                columns={obsCols}
                readonly
                onSelectRow={(i) => i !== null && rows[i] && ws.setSelected(rows[i].target)}
              />
            </Suspense>
          </TabsContent>
          <TabsContent value="pts" className="h-[420px] data-[state=inactive]:hidden">
            <Suspense fallback={<Skeleton className="m-4 h-64" />}>
              <DataGrid rows={precise} columns={ptCols} readonly onSelectRow={(i) => i !== null && precise[i] && ws.setSelected(precise[i].name)} />
            </Suspense>
          </TabsContent>
        </Tabs>
      </div>
    </SectionFrame>
  );
}
