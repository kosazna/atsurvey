import { AlertTriangle, CheckCircle2, CircleDashed, Loader2, WifiOff, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/tooltip";
import { env } from "@/lib/env";
import { cn } from "@/lib/utils";
import { useWorkspace } from "./useWorkspace";

export function StatusPill() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const r = ws.result;
  const warnings = r?.issues.filter((i) => i.severity === "warning").length ?? 0;
  const errors = r?.issues.filter((i) => i.severity === "error").length ?? 0;

  let icon = <CircleDashed />;
  let text = t("ws.status.idle");
  let tone = "text-muted bg-surface-sunken";
  if (ws.status === "computing") {
    icon = <Loader2 className="animate-spin" />;
    text = t("ws.status.computing");
  } else if (ws.status === "offline") {
    icon = <WifiOff />;
    text = t("ws.status.offline");
    tone = "text-danger bg-danger-subtle";
  } else if (ws.status === "error" && !r) {
    icon = <XCircle />;
    text = ws.error ?? t("errors.generic");
    tone = "text-danger bg-danger-subtle";
  } else if (r) {
    if (errors > 0) {
      icon = <XCircle />;
      text = t("ws.status.error", { count: errors });
      tone = "text-danger bg-danger-subtle";
    } else if (r.summary.n_traverses > 0 && r.summary.n_traverses_ok === r.summary.n_traverses && warnings === 0) {
      icon = <CheckCircle2 />;
      text = t("ws.status.ok", { ok: r.summary.n_traverses_ok, total: r.summary.n_traverses });
      tone = "text-success bg-success-subtle";
    } else if (warnings > 0 || r.summary.n_traverses_ok < r.summary.n_traverses) {
      icon = <AlertTriangle />;
      text = r.summary.n_traverses > 0 ? t("ws.status.ok", { ok: r.summary.n_traverses_ok, total: r.summary.n_traverses }) : t("ws.status.warn", { count: warnings });
      tone = "text-warning bg-warning-subtle";
    } else {
      icon = <CheckCircle2 />;
      text = t("ws.status.okNoTrav");
      tone = "text-success bg-success-subtle";
    }
  }

  const pill = (
    <button
      onClick={() => (errors || warnings ? ws.goTo("issues") : ws.goTo("reports"))}
      className={cn("inline-flex h-6 max-w-[22rem] cursor-pointer items-center gap-1.5 truncate rounded-full px-2.5 text-xs font-medium [&_svg]:size-3.5 [&_svg]:shrink-0", tone)}
      data-testid="status-pill"
    >
      {icon}
      <span className="truncate">{text}</span>
    </button>
  );
  if (ws.status === "offline") return <Tooltip content={t("errors.offline", { url: env.apiUrl })}>{pill}</Tooltip>;
  return pill;
}
