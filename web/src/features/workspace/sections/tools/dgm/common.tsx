// Shared pieces of the ΔΓΜ tools: disclaimer, file picker, problem list with coordinates, the
// workspace/project ids for plan-gated exports.
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Info, ShieldAlert, Upload, XCircle } from "lucide-react";
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useSession, useStore } from "@/data/session";
import { issueXY } from "@/lib/dgmApi";
import type { Issue } from "@/lib/types";
import { cn, fmtNum } from "@/lib/utils";
import { issueText } from "../../../issues";
import { useWorkspace } from "../../../useWorkspace";

export function Disclaimer() {
  const { t } = useTranslation();
  return (
    <p className="flex items-start gap-2 rounded-lg border border-warning bg-warning-subtle px-3 py-2 text-sm" data-testid="dgm-disclaimer">
      <ShieldAlert className="mt-0.5 size-4 shrink-0 text-warning" />
      <span>{t("dgm.disclaimer")}</span>
    </p>
  );
}

interface FileButtonProps {
  label: string;
  accept?: string;
  busy?: boolean;
  onFile: (file: File) => void;
  testId?: string;
}

export function FileButton({ label, accept = ".dxf", busy, onFile, testId }: FileButtonProps) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={ref}
        type="file"
        accept={accept}
        className="hidden"
        data-testid={testId}
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f) onFile(f);
        }}
      />
      <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => ref.current?.click()}>
        <Upload /> {label}
      </Button>
    </>
  );
}

function severityIcon(sev: Issue["severity"]) {
  return sev === "error" ? XCircle : sev === "warning" ? AlertTriangle : Info;
}

/** Issues with the layer, entity handle and coordinates of each problem (copyable). */
export function ProblemList({ issues, testId }: { issues: Issue[]; testId?: string }) {
  const { t } = useTranslation();
  if (issues.length === 0) return null;
  return (
    <ul className="space-y-1.5 text-sm" data-testid={testId}>
      {issues.map((iss, i) => {
        const Icon = severityIcon(iss.severity);
        const xy = issueXY(iss);
        const layer = typeof iss.params?.layer === "string" ? iss.params.layer : null;
        const handle = typeof iss.params?.handle === "string" ? iss.params.handle : null;
        return (
          <li key={i} className={cn("flex items-start gap-2", iss.severity === "error" ? "text-danger" : iss.severity === "warning" ? "text-warning" : "text-muted")}>
            <Icon className="mt-0.5 size-4 shrink-0" />
            <span className="min-w-0">
              <span className="text-fg">{issueText(iss)}</span>
              {(xy || layer || handle) && (
                <span className="block text-xs text-muted tabular">
                  {layer && <span className="mr-3">{t("dgm.layer")}: {layer}</span>}
                  {handle && <span className="mr-3">{t("dgm.handle")}: {handle}</span>}
                  {xy && (
                    <span className="select-all">
                      X {fmtNum(xy.x, 3)} · Y {fmtNum(xy.y, 3)}
                    </span>
                  )}
                </span>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** Workspace id (plan gating) and stored project id (audit log) for exports. */
export function useExportIds(): { workspaceId: string | null; projectId: string | null } {
  const ws = useWorkspace();
  const store = useStore();
  const { mode } = useSession();
  const wsId = useQuery({ queryKey: ["workspace-id", mode], queryFn: () => store.workspaceId(), staleTime: Infinity });
  return { workspaceId: wsId.data ?? null, projectId: store.kind === "supabase" ? ws.projectId : null };
}
