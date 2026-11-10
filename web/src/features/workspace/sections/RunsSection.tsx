// Saved computation runs: list, open read-only, compare two runs (or a run with the live result).
import { useQuery } from "@tanstack/react-query";
import { Eye, GitCompareArrows, History, Save, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useStore } from "@/data/session";
import type { RunSummary, StoredRun } from "@/data/store";
import { RunLabel } from "./RunLabel";
import { diffRuns } from "@/lib/runDiff";
import type { ProjectResult } from "@/lib/types";
import { cn, fmtNum, fmtSigned, parseNum, relativeTime } from "@/lib/utils";
import { useWorkspace } from "../useWorkspace";
import { SectionFrame, SectionHeader } from "./SectionLayout";

const LIVE = "live";

export default function RunsSection() {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const store = useStore();
  const runs = useQuery({
    queryKey: ["runs", store.kind, ws.projectId, ws.runsVersion],
    queryFn: () => store.listRuns(ws.projectId),
  });
  const [a, setA] = useState<string | null>(null);
  const [b, setB] = useState<string | null>(LIVE);
  const [thresholdMm, setThresholdMm] = useState("5");
  const thr = (parseNum(thresholdMm) ?? 5) / 1000;

  const load = async (id: string): Promise<ProjectResult | null> => {
    if (id === LIVE) return ws.liveResult;
    return (await store.getRun(ws.projectId, id))?.result ?? null;
  };
  const cmp = useQuery({
    queryKey: ["run-diff", ws.projectId, a, b, a === LIVE || b === LIVE ? ws.liveResult?.input_hash : null],
    queryFn: async () => {
      const [ra, rb] = await Promise.all([load(a!), load(b!)]);
      return ra && rb ? { ra, rb } : null;
    },
    enabled: Boolean(a && b && a !== b),
  });
  const diff = useMemo(() => (cmp.data ? diffRuns(cmp.data.ra, cmp.data.rb, thr) : null), [cmp.data, thr]);

  const open = async (r: RunSummary) => {
    const run = await store.getRun(ws.projectId, r.id);
    if (!run) return toast.error(t("runs.notFound"));
    ws.setViewing(run as StoredRun);
    toast.info(t("runs.viewing"));
  };

  const label = (id: string | null) => {
    if (id === LIVE) return t("runs.live");
    const r = runs.data?.find((x) => x.id === id);
    return r ? new Date(r.created_at).toLocaleString(i18n.language) : "—";
  };

  const list = runs.data ?? [];

  return (
    <SectionFrame className="overflow-y-auto">
      <SectionHeader
        title={t("runs.title")}
        description={t("runs.subtitle")}
        actions={
          <Button size="sm" variant="outline" onClick={() => void ws.saveRun()} disabled={!ws.liveResult} data-testid="btn-save-run">
            <Save /> {t("ws.saveRun")}
          </Button>
        }
      />
      <div className="space-y-4 p-4">
        {runs.isLoading ? (
          <Skeleton className="h-40" />
        ) : list.length === 0 ? (
          <Card>
            <EmptyState icon={<History />} title={t("runs.empty")} description={t("runs.emptyHint")} />
          </Card>
        ) : (
          <Card className="overflow-hidden" data-testid="runs-list">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-surface-sunken text-xs text-muted">
                  <th className="w-16 px-3 py-2 text-center font-medium">A / B</th>
                  <th className="px-3 py-2 text-left font-medium">{t("runs.when")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("runs.points")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("runs.traverses")}</th>
                  <th className="hidden px-3 py-2 text-left font-medium md:table-cell">{t("runs.id")}</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {list.map((r) => {
                  const s = r.summary;
                  const pts = s ? s.n_control + s.n_traverse_points + s.n_detail_points : null;
                  return (
                    <tr key={r.id} className={cn("border-b last:border-0", ws.viewing?.id === r.id && "bg-accent-subtle")}>
                      <td className="px-3 py-1.5">
                        <div className="flex justify-center gap-1">
                          {(["A", "B"] as const).map((slot) => {
                            const sel = slot === "A" ? a === r.id : b === r.id;
                            return (
                              <button
                                key={slot}
                                aria-pressed={sel}
                                onClick={() => (slot === "A" ? setA(sel ? null : r.id) : setB(sel ? null : r.id))}
                                className={cn("size-6 cursor-pointer rounded border text-xs font-medium", sel ? "border-accent bg-accent text-accent-contrast" : "text-muted hover:text-fg")}
                              >
                                {slot}
                              </button>
                            );
                          })}
                        </div>
                      </td>
                      <td className="px-3 py-1.5">
                        <RunLabel
                          label={r.label}
                          readOnly={ws.readOnly}
                          onSave={async (label) => {
                            await store.labelRun(ws.projectId, r.id, label);
                            await runs.refetch();
                          }}
                        />
                        <div className={r.label ? "text-xs text-muted" : "font-medium"}>{relativeTime(r.created_at, i18n.language)}</div>
                        <div className="text-xs text-muted">{new Date(r.created_at).toLocaleString(i18n.language)}</div>
                      </td>
                      <td className="px-3 py-1.5 text-right tabular">{pts ?? "—"}</td>
                      <td className="px-3 py-1.5 text-right tabular">{s ? `${s.n_traverses_ok}/${s.n_traverses}` : "—"}</td>
                      <td className="hidden px-3 py-1.5 font-mono text-xs text-muted md:table-cell">
                        {r.input_hash.slice(0, 10)} · v{r.engine_version}
                        {ws.liveResult?.input_hash === r.input_hash && (
                          <Badge variant="success" className="ml-2">
                            {t("runs.matchesLive")}
                          </Badge>
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        <Button size="sm" variant="ghost" onClick={() => void open(r)}>
                          <Eye /> {t("runs.open")}
                        </Button>
                        {!ws.readOnly && (
                          <Button
                            size="icon-sm"
                            variant="ghost"
                            aria-label={t("life.runs.delete")}
                            onClick={() =>
                              toast(t("life.runs.delete"), {
                                action: {
                                  label: t("common.delete"),
                                  onClick: () =>
                                    void store
                                      .deleteRun(ws.projectId, r.id)
                                      .then(() => runs.refetch())
                                      .then(() => toast.success(t("life.runs.deleted")))
                                      .catch((e: Error) => toast.error(e.message)),
                                },
                              })
                            }
                          >
                            <Trash2 />
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
                <tr className="bg-surface-sunken/50">
                  <td className="px-3 py-1.5">
                    <div className="flex justify-center gap-1">
                      {(["A", "B"] as const).map((slot) => {
                        const sel = slot === "A" ? a === LIVE : b === LIVE;
                        return (
                          <button
                            key={slot}
                            aria-pressed={sel}
                            onClick={() => (slot === "A" ? setA(sel ? null : LIVE) : setB(sel ? null : LIVE))}
                            className={cn("size-6 cursor-pointer rounded border text-xs font-medium", sel ? "border-accent bg-accent text-accent-contrast" : "text-muted hover:text-fg")}
                          >
                            {slot}
                          </button>
                        );
                      })}
                    </div>
                  </td>
                  <td className="px-3 py-1.5 font-medium" colSpan={5}>
                    {t("runs.live")} <span className="text-xs font-normal text-muted">· {t("runs.liveHint")}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </Card>
        )}

        {a && b && a !== b && (
          <Card className="space-y-4 p-4" data-testid="run-compare">
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex min-w-0 flex-1 items-center gap-2 text-sm">
                <GitCompareArrows className="size-4 shrink-0 text-muted" />
                <span className="truncate">
                  <span className="font-medium">A</span> {label(a)} → <span className="font-medium">B</span> {label(b)}
                </span>
              </div>
              <div className="w-36 space-y-1.5">
                <Label htmlFor="thr">{t("runs.threshold")}</Label>
                <Input id="thr" value={thresholdMm} onChange={(e) => setThresholdMm(e.target.value)} className="tabular" inputMode="decimal" />
              </div>
            </div>
            {cmp.isLoading && <Skeleton className="h-24" />}
            {diff && (
              <>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
                  {[
                    { k: t("runs.common"), v: diff.common },
                    { k: t("runs.added"), v: diff.added },
                    { k: t("runs.removed"), v: diff.removed },
                    { k: t("runs.maxDxy"), v: `${(diff.maxDxy * 1000).toFixed(1)} mm` },
                    { k: "RMS Δxy", v: `${(diff.rmsDxy * 1000).toFixed(1)} mm` },
                    { k: t("runs.over"), v: diff.over, bad: diff.over > 0 },
                  ].map((m) => (
                    <div key={m.k} className={cn("rounded-lg border p-2.5", m.bad && "border-warning bg-warning-subtle")}>
                      <div className="text-xs text-muted">{m.k}</div>
                      <div className="text-base font-semibold tabular">{m.v}</div>
                    </div>
                  ))}
                </div>
                <div className="max-h-96 overflow-y-auto rounded-lg border">
                  <table className="w-full text-sm tabular">
                    <thead className="sticky top-0 bg-surface-sunken">
                      <tr className="border-b text-xs text-muted">
                        <th className="px-3 py-2 text-left font-medium">{t("runs.point")}</th>
                        <th className="px-3 py-2 text-right font-medium">ΔX mm</th>
                        <th className="px-3 py-2 text-right font-medium">ΔY mm</th>
                        <th className="px-3 py-2 text-right font-medium">ΔZ mm</th>
                        <th className="px-3 py-2 text-right font-medium">Δxy mm</th>
                      </tr>
                    </thead>
                    <tbody>
                      {diff.rows.map((row) => {
                        const over = row.dxy !== null && row.dxy > thr;
                        return (
                          <tr key={row.name} className={cn("cursor-pointer border-b last:border-0 hover:bg-surface-sunken", over && "bg-warning-subtle")} onClick={() => ws.setSelected(row.name)}>
                            <td className="px-3 py-1.5 font-medium">
                              {row.name}
                              {row.status !== "both" && (
                                <Badge variant={row.status === "added" ? "success" : "destructive"} className="ml-2">
                                  {t(`runs.${row.status}One`)}
                                </Badge>
                              )}
                            </td>
                            <td className="px-3 py-1.5 text-right">{row.dx === null ? "—" : fmtSigned(row.dx * 1000, 1)}</td>
                            <td className="px-3 py-1.5 text-right">{row.dy === null ? "—" : fmtSigned(row.dy * 1000, 1)}</td>
                            <td className="px-3 py-1.5 text-right">{row.dz === null ? "—" : fmtSigned(row.dz * 1000, 1)}</td>
                            <td className={cn("px-3 py-1.5 text-right", over && "font-semibold text-warning")}>{row.dxy === null ? "—" : fmtNum(row.dxy * 1000, 1)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            {cmp.data === null && <p className="text-xs text-muted">{t("runs.cannotCompare")}</p>}
          </Card>
        )}
        {(!a || !b) && list.length > 0 && <p className="text-xs text-muted">{t("runs.pickTwo")}</p>}
      </div>
    </SectionFrame>
  );
}
