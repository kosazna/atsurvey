// Shared pieces of the instrument-check tools: report fields/buttons, small-angle formatting,
// issue list and a compact results table.
import { CheckCircle2, Download, Printer, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CC } from "@/lib/angles";
import { type Report, type ReportMeta, printReport, reportCsv } from "@/lib/instrumentsReport";
import type { Issue } from "@/lib/types";
import { cn, downloadBlob, fmtNum, fmtSigned } from "@/lib/utils";
import { issueText } from "../../../issues";

/** cc and mgon of a small angle (radians): "+12.3 cc · +1.23 mgon". */
export function fmtSmallAngle(rad: number | null | undefined): string {
  if (rad === null || rad === undefined || !Number.isFinite(rad)) return "—";
  const cc = rad / CC;
  return `${fmtSigned(cc, 1)} cc · ${fmtSigned(cc / 10, 2)} mgon`;
}

/** σ of a small angle in cc and mgon, or "—" without redundancy. */
export function fmtSmallSigma(rad: number | null | undefined): string {
  if (rad === null || rad === undefined || !Number.isFinite(rad)) return "—";
  const cc = rad / CC;
  return `±${fmtNum(cc, 1)} cc · ±${fmtNum(cc / 10, 2)} mgon`;
}

export function ReportMetaFields({ meta, onChange }: { meta: ReportMeta; onChange: (m: ReportMeta) => void }) {
  const { t } = useTranslation();
  const keys: (keyof ReportMeta)[] = ["model", "serial", "operator", "date"];
  return (
    <fieldset className="grid gap-3 rounded-xl border p-3 sm:grid-cols-2">
      <legend className="px-1 text-xs font-medium text-muted">{t("instruments.report.title")}</legend>
      {keys.map((k) => (
        <div key={k} className="space-y-1.5">
          <Label htmlFor={`instr-meta-${k}`}>{t(`instruments.report.${k}`)}</Label>
          <Input
            id={`instr-meta-${k}`}
            type={k === "date" ? "date" : "text"}
            maxLength={120}
            value={meta[k]}
            onChange={(e) => onChange({ ...meta, [k]: e.target.value })}
          />
        </div>
      ))}
    </fieldset>
  );
}

export function useMetaLabels(): Report["metaLabels"] {
  const { t } = useTranslation();
  return {
    model: t("instruments.report.model"),
    serial: t("instruments.report.serial"),
    operator: t("instruments.report.operator"),
    date: t("instruments.report.date"),
  };
}

export function ReportButtons({ report, filename }: { report: Report; filename: string }) {
  const { t } = useTranslation();
  const print = () => {
    if (!printReport(report)) toast.error(t("instruments.report.popupBlocked"));
  };
  const csv = () => downloadBlob(new Blob([reportCsv(report)], { type: "text/csv;charset=utf-8" }), `${filename}.csv`);
  return (
    <div className="flex flex-wrap gap-1.5">
      <Button type="button" size="sm" variant="outline" onClick={print}>
        <Printer /> {t("instruments.report.print")}
      </Button>
      <Button type="button" size="sm" variant="outline" onClick={csv}>
        <Download /> CSV
      </Button>
    </div>
  );
}

export function PassBadge({ ok, testId }: { ok: boolean; testId?: string }) {
  const { t } = useTranslation();
  return ok ? (
    <Badge variant="success" data-testid={testId}>
      <CheckCircle2 /> {t("instruments.pass")}
    </Badge>
  ) : (
    <Badge variant="destructive" data-testid={testId}>
      <XCircle /> {t("instruments.fail")}
    </Badge>
  );
}

export function IssueList({ issues }: { issues: Issue[] }) {
  if (!issues.length) return null;
  return (
    <ul className="space-y-1 text-xs">
      {issues.map((i, k) => (
        <li key={k} className={cn(i.severity === "error" ? "text-danger" : i.severity === "warning" ? "text-warning" : "text-muted")}>
          • {issueText(i)}
        </li>
      ))}
    </ul>
  );
}

export interface SimpleTableProps {
  headers: ReactNode[];
  rows: ReactNode[][];
  /** row indices to highlight */
  highlight?: (i: number) => boolean;
  testId?: string;
}

/** Compact numeric table: first column left-aligned, the rest right-aligned. */
export function SimpleTable({ headers, rows, highlight, testId }: SimpleTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs tabular" data-testid={testId}>
        <thead>
          <tr className="border-b text-muted">
            {headers.map((h, i) => (
              <th key={i} className={cn("whitespace-nowrap px-1.5 py-1 font-medium", i === 0 ? "text-left" : "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className={cn("border-b last:border-0", highlight?.(r) && "bg-danger-subtle")}>
              {row.map((c, i) => (
                <td key={i} className={cn("whitespace-nowrap px-1.5 py-1", i === 0 ? "text-left" : "text-right")}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
