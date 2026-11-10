// "Έλεγχος DXF": upload any DXF (from ATSurvey or CAD), choose the diagram kind, see the
// Cadastre's checks with pass/fail and the coordinates of every problem.
import { CheckCircle2, CircleDashed, Copy, XCircle, AlertTriangle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { type CheckResult, type CheckStatus, type DiagramKind, dgmApi, issueXY, type ValidationReport } from "@/lib/dgmApi";
import { cn, fmtNum } from "@/lib/utils";
import { ResultBox, useRunner } from "../shared";
import { Disclaimer, FileButton, ProblemList } from "./common";
import { DgmSketch } from "./DgmSketch";

const STATUS_ICON: Record<CheckStatus, typeof CheckCircle2> = { pass: CheckCircle2, fail: XCircle, warn: AlertTriangle, skip: CircleDashed };
const STATUS_CLS: Record<CheckStatus, string> = { pass: "text-success", fail: "text-danger", warn: "text-warning", skip: "text-muted" };

export function KindSelect({ value, onChange }: { value: DiagramKind; onChange: (v: DiagramKind) => void }) {
  const { t } = useTranslation();
  return (
    <div className="w-72 space-y-1.5">
      <Label>{t("dgm.kind")}</Label>
      <Select<DiagramKind>
        value={value}
        onValueChange={onChange}
        options={(["deed", "correction", "topo"] as const).map((k) => ({ value: k, label: t(`dgm.kinds.${k}`) }))}
      />
    </div>
  );
}

export function ValidateTool() {
  const { t } = useTranslation();
  const [kind, setKind] = useState<DiagramKind>("deed");
  const [file, setFile] = useState<File | null>(null);
  const r = useRunner<ValidationReport>();
  const run = (f: File, k: DiagramKind) => void r.run(() => dgmApi.validate(f, k));
  return (
    <div className="space-y-5">
      <Disclaimer />
      <div className="flex flex-wrap items-end gap-3">
        <KindSelect
          value={kind}
          onChange={(k) => {
            setKind(k);
            if (file) run(file, k);
          }}
        />
        <FileButton
          label={t("dgm.validate.upload")}
          busy={r.busy}
          testId="dgm-validate-file"
          onFile={(f) => {
            setFile(f);
            run(f, kind);
          }}
        />
        {file && <span className="text-sm text-muted">{file.name}</span>}
      </div>
      <p className="text-xs text-muted">{t("dgm.validate.hint")}</p>
      <ResultBox error={r.error} testId="dgm-validate-result">
        {r.result && <ReportView rep={r.result} />}
      </ResultBox>
    </div>
  );
}

function ReportView({ rep }: { rep: ValidationReport }) {
  const { t } = useTranslation();
  const marks = rep.checks.flatMap((c) => c.issues.filter((i) => i.severity === "error").map(issueXY)).filter((m): m is { x: number; y: number } => m !== null);
  const fails = rep.checks.filter((c) => c.status === "fail").length;
  return (
    <div className="space-y-5">
      <div className={cn("flex items-center gap-2 font-medium", rep.ok ? "text-success" : "text-danger")} data-testid="dgm-validate-verdict">
        {rep.ok ? <CheckCircle2 className="size-5" /> : <XCircle className="size-5" />}
        {rep.ok ? t("dgm.validate.ok") : t("dgm.validate.failed", { count: fails })}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
        <dt className="text-muted">{t("dgm.validate.version")}</dt>
        <dd>{rep.dxf_version ?? "—"}</dd>
        <dt className="text-muted">{t("dgm.validate.size")}</dt>
        <dd className="tabular">{fmtNum(rep.size / (1024 * 1024), 2)} MB</dd>
        <dt className="text-muted">SHA-512</dt>
        <dd className="flex min-w-0 items-center gap-1">
          <code className="truncate text-xs">{rep.sha512}</code>
          <Button
            size="sm"
            variant="ghost"
            aria-label={t("dgm.copy")}
            onClick={() => void navigator.clipboard.writeText(rep.sha512).then(() => toast.success(t("dgm.copied")))}
          >
            <Copy />
          </Button>
        </dd>
      </dl>
      <div className="grid gap-6 xl:grid-cols-[1fr_auto]">
        <ul className="space-y-2" data-testid="dgm-checklist">
          {rep.checks.map((c) => (
            <CheckRow key={c.id} check={c} />
          ))}
        </ul>
        {rep.preview.length > 0 && (
          <div className="space-y-1">
            <DgmSketch shapes={rep.preview} marks={marks} testId="dgm-validate-sketch" />
            {rep.preview_truncated && <p className="text-xs text-muted">{t("dgm.validate.truncated")}</p>}
          </div>
        )}
      </div>
      {rep.layers.length > 0 && <LayersTable rep={rep} />}
    </div>
  );
}

function CheckRow({ check }: { check: CheckResult }) {
  const { t } = useTranslation();
  const Icon = STATUS_ICON[check.status];
  return (
    <li className="rounded-lg border px-3 py-2">
      <div className={cn("flex items-center gap-2 text-sm font-medium", STATUS_CLS[check.status])}>
        <Icon className="size-4 shrink-0" />
        <span className="text-fg">{t(`dgm.checks.${check.id}`)}</span>
        <span className="ml-auto text-xs">{t(`dgm.status.${check.status}`)}</span>
      </div>
      {check.issues.length > 0 && (
        <div className="mt-2 pl-6">
          <ProblemList issues={check.issues} />
        </div>
      )}
    </li>
  );
}

function LayersTable({ rep }: { rep: ValidationReport }) {
  const { t } = useTranslation();
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-muted">{t("dgm.validate.layers", { count: rep.layers.length })}</summary>
      <table className="mt-2 w-full tabular">
        <thead>
          <tr className="border-b text-xs text-muted">
            <th className="py-1 text-left font-medium">#</th>
            <th className="py-1 text-left font-medium">{t("dgm.layer")}</th>
            <th className="py-1 text-left font-medium">{t("dgm.validate.entities")}</th>
          </tr>
        </thead>
        <tbody>
          {rep.layers.map((l) => (
            <tr key={l.name} className="border-b last:border-0">
              <td className="py-1 text-muted">{l.table_no ?? "—"}</td>
              <td className="py-1">{l.name}</td>
              <td className="py-1 text-muted">
                {Object.entries(l.counts)
                  .map(([k, n]) => `${k} ${n}`)
                  .join(" · ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
