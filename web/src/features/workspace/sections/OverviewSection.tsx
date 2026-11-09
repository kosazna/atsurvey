import { ArrowRight, Check, Crosshair, FileDown, History, ListOrdered, Mountain, Route as RouteIcon, ShieldCheck, Sigma, Spline, Telescope, Triangle, Upload } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { formatMisclosure } from "@/lib/angles";
import { fmtInt, relativeTime } from "@/lib/utils";
import { useWorkspace } from "../useWorkspace";
import { TraverseStatusBadge } from "./ReportsSection";

function Stat({ label, value, icon, onClick }: { label: string; value: React.ReactNode; icon: React.ReactNode; onClick?: () => void }) {
  return (
    <button onClick={onClick} className="group flex cursor-pointer flex-col gap-2 rounded-xl border bg-surface p-3.5 text-left transition-colors hover:border-border-strong">
      <span className="flex min-h-8 items-start gap-1.5 text-xs leading-4 text-muted [&_svg]:mt-0.5 [&_svg]:size-3.5 [&_svg]:shrink-0">
        {icon}
        {label}
      </span>
      <span className="text-2xl font-semibold tracking-tight tabular">{value}</span>
    </button>
  );
}

export function OverviewSection() {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const d = ws.data;
  const r = ws.result;
  const nObs = d.setups.reduce((n, s) => n + s.observations.length, 0);
  const computed = r ? r.points.filter((p) => p.kind !== "control").length : 0;
  const issues = r?.issues.filter((i) => i.severity !== "info").length ?? 0;
  const unit = d.meta.angle_unit;

  const steps = [
    { done: d.setups.length > 0, label: t("overview.step1"), action: () => ws.setDialog("import"), icon: <Upload /> },
    { done: d.control_points.length > 0, label: t("overview.step2"), action: () => ws.goTo("control"), icon: <Triangle /> },
    { done: d.traverses.length > 0, label: t("overview.step3"), action: () => ws.goTo("traverses"), icon: <RouteIcon /> },
    { done: Boolean(r && r.summary.n_errors === 0 && r.points.length > 0), label: t("overview.step4"), action: () => ws.setDialog("export"), icon: <FileDown /> },
  ];

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl space-y-6 p-4 sm:p-6">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">{d.meta.name}</h2>
          {d.meta.description && <p className="mt-1 text-sm text-muted">{d.meta.description}</p>}
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Stat label={t("overview.control")} value={d.control_points.length} icon={<Triangle />} onClick={() => ws.goTo("control")} />
          <Stat label={t("overview.setups")} value={d.setups.length} icon={<Telescope />} onClick={() => ws.goTo("observations")} />
          <Stat label={t("overview.observations")} value={nObs} icon={<Telescope />} onClick={() => ws.goTo("observations")} />
          <Stat label={t("overview.traverses")} value={d.traverses.length} icon={<RouteIcon />} onClick={() => ws.goTo("traverses")} />
          <Stat label={t("overview.computed")} value={computed} icon={<ListOrdered />} onClick={() => ws.goTo("results")} />
          <Stat label={t("overview.issues")} value={issues} icon={<ShieldCheck />} onClick={() => ws.goTo("issues")} />
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card className="p-4">
            <div className="mb-3 text-sm font-semibold">{t("overview.steps")}</div>
            <ol className="space-y-1">
              {steps.map((s, i) => (
                <li key={i}>
                  <button onClick={s.action} className="group flex w-full cursor-pointer items-center gap-3 rounded-lg px-2 py-2 text-left text-sm hover:bg-surface-sunken">
                    <span
                      className={
                        s.done
                          ? "flex size-6 shrink-0 items-center justify-center rounded-full bg-success-subtle text-success"
                          : "flex size-6 shrink-0 items-center justify-center rounded-full border text-xs text-muted"
                      }
                    >
                      {s.done ? <Check className="size-3.5" /> : i + 1}
                    </span>
                    <span className={s.done ? "text-muted" : ""}>{s.label}</span>
                    <ArrowRight className="ml-auto size-3.5 text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                  </button>
                </li>
              ))}
            </ol>
          </Card>

          <Card className="p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-sm font-semibold">{t("ws.sections.traverses")}</span>
              {r && (
                <Button variant="ghost" size="sm" onClick={() => ws.goTo("reports")}>
                  {t("ws.sections.reports")} <ArrowRight />
                </Button>
              )}
            </div>
            {r && r.traverses.length > 0 ? (
              <div className="space-y-2">
                {r.traverses.map((tr) => (
                  <button
                    key={tr.id ?? tr.name}
                    onClick={() => ws.goTo("reports", { traverse: tr.id ?? tr.name })}
                    className="flex w-full cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-left hover:bg-surface-sunken"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{tr.name}</div>
                      <div className="truncate text-xs text-muted tabular">
                        {tr.angular_misclosure !== null && `${formatMisclosure(tr.angular_misclosure, unit)} · `}
                        {tr.linear_misclosure !== null && `w ${(tr.linear_misclosure * 100).toFixed(1)} cm · `}
                        {tr.relative_precision ? `1:${fmtInt(tr.relative_precision)}` : t(`traverseKind.${tr.kind}`)}
                      </div>
                    </div>
                    <TraverseStatusBadge status={tr.status} />
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted">{t("reports.empty")}</p>
            )}
          </Card>
        </div>

        <div>
          <div className="mb-2 text-sm font-semibold">{t("overview.more")}</div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
            {(
              [
                { id: "adjustment", icon: <Sigma /> },
                { id: "linework", icon: <Spline /> },
                { id: "tools", icon: <Crosshair /> },
                { id: "leveling", icon: <Mountain /> },
                { id: "runs", icon: <History /> },
              ] as const
            ).map((x) => (
              <button
                key={x.id}
                onClick={() => ws.goTo(x.id)}
                className="group flex cursor-pointer flex-col gap-1.5 rounded-xl border bg-surface p-3 text-left transition-colors hover:border-border-strong [&_svg]:size-4"
                data-testid={`quick-${x.id}`}
              >
                <span className="flex items-center gap-2 text-sm font-medium text-fg">
                  <span className="text-muted group-hover:text-accent">{x.icon}</span>
                  {t(`ws.sections.${x.id}`)}
                </span>
                <span className="text-xs leading-snug text-muted">{t(`overview.moreHints.${x.id}`)}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
          {r && <Badge variant="secondary">{t("overview.engine", { version: r.engine_version })}</Badge>}
          {ws.lastRun && <span>{t("overview.lastRun", { when: relativeTime(ws.lastRun.created_at, i18n.language) })}</span>}
          <span className="ml-auto hidden sm:inline">{t("overview.shortcutsHint")}</span>
          {r?.summary.extent && (
            <span className="tabular">
              {t("overview.extent")}: {r.summary.extent.map((v) => v.toFixed(0)).join(" · ")}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
