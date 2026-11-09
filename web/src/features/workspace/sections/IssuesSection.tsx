import { AlertTriangle, ArrowRight, Info, ShieldCheck, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty";
import type { Issue, Severity } from "@/lib/types";
import { cn } from "@/lib/utils";
import { issueText } from "../issues";
import { useWorkspace } from "../useWorkspace";
import { SectionFrame, SectionHeader } from "./SectionLayout";

const ICON: Record<Severity, React.ReactNode> = {
  error: <XCircle className="text-danger" />,
  warning: <AlertTriangle className="text-warning" />,
  info: <Info className="text-muted" />,
};

export function IssuesSection() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const issues = ws.result?.issues ?? [];
  const groups: Severity[] = ["error", "warning", "info"];

  const traverseName = (id: string | null | undefined) => {
    if (!id) return null;
    const r = ws.result?.traverses.find((x) => x.id === id || x.name === id);
    return r?.name ?? ws.data.traverses.find((x) => x.id === id)?.name ?? id;
  };
  const setupName = (id: string | null | undefined) => {
    if (!id) return null;
    const s = ws.data.setups.find((x) => x.id === id);
    return s ? s.station : id;
  };

  const go = (i: Issue) => {
    if (i.traverse) ws.goTo("reports", { traverse: i.traverse });
    else if (i.setup) ws.goTo("observations", { setup: i.setup });
    else if (typeof i.params?.point === "string") ws.setSelected(i.params.point);
  };

  return (
    <SectionFrame>
      <SectionHeader title={t("issues.title")} />
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {!ws.result ? (
          <EmptyState icon={<ShieldCheck />} title={t("results.empty")} description={t("results.emptyHint")} action={<Button size="sm" onClick={ws.compute}>{t("ws.compute")}</Button>} />
        ) : issues.length === 0 ? (
          <EmptyState icon={<ShieldCheck className="text-success" />} title={t("issues.empty")} description={t("issues.emptyHint")} />
        ) : (
          <div className="space-y-5">
            {groups.map((g) => {
              const list = issues.filter((i) => i.severity === g);
              if (!list.length) return null;
              return (
                <section key={g}>
                  <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold  text-muted">
                    {t(`issues.${g}`)} <Badge variant={g === "error" ? "destructive" : g === "warning" ? "warning" : "secondary"}>{list.length}</Badge>
                  </h3>
                  <ul className="divide-y overflow-hidden rounded-xl border bg-surface">
                    {list.map((i, k) => {
                      const tn = traverseName(i.traverse);
                      const sn = setupName(i.setup);
                      const navigable = Boolean(i.traverse || i.setup || i.params?.point);
                      return (
                        <li key={k} className={cn("flex items-start gap-3 px-3.5 py-2.5", navigable && "cursor-pointer hover:bg-surface-sunken")} onClick={() => navigable && go(i)}>
                          <span className="mt-0.5 [&_svg]:size-4">{ICON[g]}</span>
                          <div className="min-w-0 flex-1">
                            <div className="text-sm">{issueText(i)}</div>
                            <div className="mt-1 flex flex-wrap gap-1.5">
                              <code className="rounded bg-surface-sunken px-1 py-0.5 text-xs text-muted">{i.code}</code>
                              {tn && <Badge variant="outline">{tn}</Badge>}
                              {sn && <Badge variant="outline">{t("obs.station")}: {sn}</Badge>}
                            </div>
                          </div>
                          {navigable && <ArrowRight className="mt-1 size-3.5 text-muted" />}
                        </li>
                      );
                    })}
                  </ul>
                </section>
              );
            })}
          </div>
        )}
      </div>
    </SectionFrame>
  );
}
