// Results of the levelling network adjustment: statistics, heights, residuals/w-test, loops.
import { AlertTriangle, CheckCircle2, Download, Network, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { LevelNetResult } from "@/lib/instrumentsApi";
import { networkHeightsCsv } from "@/lib/leveling";
import { downloadBlob, fmtNum, fmtSigned } from "@/lib/utils";
import { useWorkspace } from "../useWorkspace";
import { IssueList, SimpleTable } from "./tools/instruments/common";

const mm = (m: number | null | undefined, d = 1) => (m === null || m === undefined ? "—" : fmtSigned(m * 1000, d));

function Metric({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="rounded-xl border bg-surface p-3">
      <div className="text-xs text-muted">{k}</div>
      <div className="mt-1 whitespace-nowrap text-lg font-semibold tabular">{v}</div>
    </div>
  );
}

function useApplyHeights(res: LevelNetResult | null) {
  const { t } = useTranslation();
  const ws = useWorkspace();
  return () => {
    if (!res) return;
    const h = new Map(res.points.filter((p) => p.kind === "adjusted" && p.known_h === null).map((p) => [p.name, p.h]));
    const n = ws.data.control_points.filter((c) => h.has(c.name)).length;
    if (!n) return toast.info(t("lev.noMatches"));
    ws.update({ control_points: ws.data.control_points.map((c) => (h.has(c.name) ? { ...c, z: Math.round(h.get(c.name)! * 10000) / 10000 } : c)) });
    toast.success(t("lev.applied", { count: n }), { action: { label: t("ws.undo"), onClick: () => ws.undo() } });
  };
}

export function LevelNetResults({ res, err }: { res: LevelNetResult | null; err: string | null }) {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const apply = useApplyHeights(res);
  if (err) return <div className="h-fit rounded-lg border border-danger bg-danger-subtle px-3 py-2 text-sm text-danger">{err}</div>;
  if (!res)
    return (
      <Card className="flex h-fit flex-col items-center gap-2 p-8 text-center text-sm text-muted">
        <Network className="size-5" />
        {t("instruments.levnet.empty")}
      </Card>
    );
  const gt = res.global_test;
  const suspect = res.suspect_line === null ? null : res.lines.find((l) => l.index === res.suspect_line);
  return (
    <div className="space-y-4" data-testid="levnet-result">
      <div className="grid grid-cols-2 gap-3 2xl:grid-cols-4">
        <Metric k={t("instruments.levnet.sigma0")} v={fmtNum(res.sigma0, 2)} />
        <Metric k={t("instruments.dof")} v={res.dof} />
        <Metric k={t("instruments.levnet.wCrit")} v={fmtNum(res.w_critical, 2)} />
        <Metric k={t("instruments.levnet.obsUnknowns")} v={`${res.n_observations} / ${res.n_unknowns}`} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted">{t("instruments.levnet.globalTest")}</span>
        {gt === null ? (
          <Badge variant="secondary">{t("instruments.levnet.noTest")}</Badge>
        ) : gt.passed ? (
          <Badge variant="success" data-testid="levnet-status">
            <CheckCircle2 /> {t("instruments.levnet.passed")}
          </Badge>
        ) : (
          <Badge variant="destructive" data-testid="levnet-status">
            <XCircle /> {t("instruments.levnet.failed")}
          </Badge>
        )}
        {gt && (
          <span className="text-xs text-muted tabular">
            Ω = {fmtNum(gt.statistic, 2)} ∈ [{fmtNum(gt.lower, 2)}, {fmtNum(gt.upper, 2)}]
          </span>
        )}
        <div className="ml-auto flex gap-1.5">
          <Button size="sm" variant="outline" onClick={apply}>
            {t("instruments.levnet.apply")}
          </Button>
          <Button size="sm" variant="outline" onClick={() => downloadBlob(new Blob([networkHeightsCsv(res.points)], { type: "text/csv;charset=utf-8" }), `${ws.data.meta.name}-network-heights.csv`)}>
            <Download /> CSV
          </Button>
        </div>
      </div>
      {suspect && (
        <p className="flex items-start gap-1.5 text-sm text-danger">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          {t("instruments.levnet.suspect", { line: suspect.index + 1, frm: suspect.frm, to: suspect.to })}
        </p>
      )}
      <IssueList issues={res.issues.filter((i) => i.code !== "LEVNET_BLUNDER")} />
      <Card className="p-3">
        <div className="mb-2 text-sm font-medium">{t("instruments.levnet.points")}</div>
        <SimpleTable
          headers={[t("instruments.levnet.point"), t("instruments.levnet.h"), t("instruments.levnet.sigmaH"), ...(res.datum === "free" ? [t("instruments.levnet.knownDiff")] : [])]}
          rows={res.points.map((p) => [
            p.name,
            fmtNum(p.h, 4),
            p.kind === "fixed" ? t("instruments.levnet.fixed") : fmtNum(p.sigma_h * 1000, 2),
            ...(res.datum === "free" ? [mm(p.known_diff)] : []),
          ])}
        />
      </Card>
      <Card className="p-3">
        <div className="mb-2 text-sm font-medium">{t("instruments.levnet.residuals")}</div>
        <SimpleTable
          testId="levnet-lines"
          headers={[t("instruments.levnet.line"), t("instruments.levnet.dh"), t("instruments.levnet.v"), t("instruments.levnet.r"), t("instruments.levnet.w"), <span title={t("instruments.levnet.mdbHint")}>{t("instruments.levnet.mdb")}</span>]}
          rows={res.lines.map((l) => [`${l.index + 1}. ${l.frm} → ${l.to}`, fmtSigned(l.dh, 4), mm(l.residual), fmtNum(l.redundancy, 2), l.w === null ? "—" : fmtSigned(l.w, 2), l.mdb === null ? "—" : fmtNum(l.mdb * 1000, 1)])}
          highlight={(i) => res.lines[i].flagged}
        />
      </Card>
      {res.loops.length > 0 && (
        <Card className="p-3">
          <div className="mb-2 text-sm font-medium">{t("instruments.levnet.loops")}</div>
          <SimpleTable
            testId="levnet-loops"
            headers={[t("instruments.levnet.path"), t("instruments.levnet.misclosure"), t("instruments.levnet.tolerance"), "L km"]}
            rows={res.loops.map((lp) => [
              `${lp.kind === "loop" ? t("instruments.levnet.loop") : t("instruments.levnet.connection")}: ${lp.points.join(" → ")}`,
              mm(lp.misclosure),
              lp.tolerance === null ? "—" : `±${fmtNum(lp.tolerance * 1000, 1)}`,
              fmtNum(lp.length_km, 3),
            ])}
            highlight={(i) => res.loops[i].within_tolerance === false}
          />
        </Card>
      )}
      {res.excluded_points.length > 0 && <p className="text-xs text-danger">{t("instruments.levnet.excluded", { points: res.excluded_points.join(", ") })}</p>}
    </div>
  );
}
