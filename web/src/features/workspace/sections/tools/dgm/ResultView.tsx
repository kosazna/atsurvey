// Result of "Σύνταξη ΔΓΜ": checks, sketch, area / change / coordinate tables and the DXF export
// with its SHA-512 and the unsigned hash PDF.
import { CheckCircle2, Download, FileSignature, XCircle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import { apiErrorMessage } from "@/lib/apiErrors";
import { areasCsv, changesCsv, checkFileName, type DgmRequest, type DgmResult, dgmApi, issueXY, pointsCsv } from "@/lib/dgmApi";
import { cn, downloadBlob, fmtNum } from "@/lib/utils";
import { CsvButton } from "../parcels/common";
import { Disclaimer, ProblemList, useExportIds } from "./common";
import { DgmSketch, type SketchShape } from "./DgmSketch";

const fmt = (v: number | null, d = 2) => (v === null ? "—" : fmtNum(v, d));

function shapesOf(res: DgmResult): SketchShape[] {
  return [
    ...res.polygons
      .filter((p) => !p.layer.startsWith("BOUND"))
      .map((p) => ({ layer: p.layer, closed: true, coords: p.vertices.map((v) => [v.x, v.y] as [number, number]), label: p.layer === "PST_KAEK" ? undefined : p.layer === "DGM_PROP_FINAL" || p.layer.startsWith("AREA") ? p.label : undefined })),
    ...res.lines.map((l) => ({ layer: l.layer, closed: false, coords: l.vertices.map((v) => [v.x, v.y] as [number, number]) })),
  ];
}

export function ResultView({ res, req }: { res: DgmResult; req: DgmRequest }) {
  const { t } = useTranslation();
  const marks = res.issues.filter((i) => i.severity === "error").map(issueXY).filter((m): m is { x: number; y: number } => m !== null);
  return (
    <div className="space-y-6">
      <div className={cn("flex items-center gap-2 font-medium", res.ok ? "text-success" : "text-danger")} data-testid="dgm-build-verdict">
        {res.ok ? <CheckCircle2 className="size-5" /> : <XCircle className="size-5" />}
        {res.ok ? t("dgm.build.ok") : t("dgm.build.failed")}
      </div>
      <ProblemList issues={res.issues} testId="dgm-build-issues" />
      <div className="grid gap-6 xl:grid-cols-[auto_1fr]">
        <DgmSketch shapes={shapesOf(res)} marks={marks} testId="dgm-build-sketch" />
        <div className="space-y-6">
          <AreasTable res={res} />
          {res.changes.length > 0 && <ChangesTable res={res} />}
          {res.comparisons.length > 0 && <Comparisons res={res} />}
        </div>
      </div>
      <PointsTable res={res} />
      <ExportPanel res={res} req={req} />
    </div>
  );
}

function AreasTable({ res }: { res: DgmResult }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{t("dgm.tables.areas")}</span>
        <CsvButton csv={areasCsv(res.areas)} filename="dgm-areas.csv" />
      </div>
      <table className="w-full text-sm tabular" data-testid="dgm-areas">
        <thead>
          <tr className="border-b text-xs text-muted">
            <th className="py-1 text-left font-medium">{t("dgm.tables.parcel")}</th>
            <th className="py-1 text-right font-medium">{t("dgm.tables.before")}</th>
            <th className="py-1 text-right font-medium">{t("dgm.tables.after")}</th>
            <th className="py-1 text-right font-medium">{t("dgm.tables.difference")}</th>
          </tr>
        </thead>
        <tbody>
          {res.areas.map((a, i) => (
            <tr key={i} className="border-b last:border-0">
              <td className="py-1">{a.kaek ?? `${t("dgm.tables.final")} ${a.label}`}</td>
              <td className="py-1 text-right">{fmt(a.before)}</td>
              <td className="py-1 text-right">{fmt(a.after)}</td>
              <td className="py-1 text-right">{fmt(a.difference)}</td>
            </tr>
          ))}
          <tr className="font-semibold">
            <td className="py-1">{t("dgm.tables.total")}</td>
            <td className="py-1 text-right">{fmt(res.total_before)}</td>
            <td className="py-1 text-right">{fmt(res.total_after)}</td>
            <td className="py-1 text-right">{fmt(res.total_after - res.total_before, 4)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function ChangesTable({ res }: { res: DgmResult }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{t("dgm.tables.changes")}</span>
        <CsvButton csv={changesCsv(res.changes)} filename="dgm-changes.csv" />
      </div>
      <div className="scroll-x-visible">
        <table className="w-full text-sm tabular" data-testid="dgm-changes">
          <thead>
            <tr className="border-b text-xs text-muted">
              <th className="py-1 text-left font-medium">ΤΜΗΜΑ</th>
              <th className="py-1 text-left font-medium">ΠΕΡΙΓΡΑΦΗ</th>
              <th className="py-1 text-right font-medium">ΕΜΒΑΔΟ</th>
              <th className="py-1 text-left font-medium">ΑΠΟ ΚΑΕΚ</th>
              <th className="py-1 text-left font-medium">ΣΕ ΚΑΕΚ</th>
            </tr>
          </thead>
          <tbody>
            {res.changes.map((c) => (
              <tr key={c.part} className="border-b last:border-0">
                <td className={cn("py-1 font-medium", c.kind === "A" ? "text-danger" : "text-success")}>{c.part}</td>
                <td className="py-1">({c.description.join(",")})</td>
                <td className="py-1 text-right">{fmt(c.area)}</td>
                <td className="py-1">{c.from_kaek}</td>
                <td className="py-1">{c.to_kaek}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Comparisons({ res }: { res: DgmResult }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2">
      <span className="text-sm font-medium">{t("dgm.tables.comparisons")}</span>
      <table className="w-full text-sm tabular">
        <thead>
          <tr className="border-b text-xs text-muted">
            <th className="py-1 text-left font-medium">{t("dgm.tables.parcel")}</th>
            <th className="py-1 text-right font-medium">{t("dgm.tables.cadastre")}</th>
            <th className="py-1 text-right font-medium">{t("dgm.tables.other")}</th>
            <th className="py-1 text-right font-medium">Δ (m²)</th>
            <th className="py-1 text-right font-medium">{t("dgm.tables.tolerance")}</th>
          </tr>
        </thead>
        <tbody>
          {res.comparisons.map((c, i) => (
            <tr key={i} className="border-b last:border-0">
              <td className="py-1">
                {c.kaek ?? c.label} <span className="text-xs text-muted">({t(`dgm.tables.against.${c.against}`)})</span>
              </td>
              <td className="py-1 text-right">{fmt(c.cadastre_area)}</td>
              <td className="py-1 text-right">{fmt(c.other_area)}</td>
              <td className="py-1 text-right">
                {fmt(c.difference)} <span className="text-xs text-muted">({fmtNum(c.difference_percent, 1)} %)</span>
              </td>
              <td className={cn("py-1 text-right", c.within === false && "text-warning", c.within === true && "text-success")}>
                {c.tolerance === null ? "—" : `${fmt(c.tolerance)} ${c.within ? "✓" : "✗"}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-muted">{t("dgm.tables.toleranceNote")}</p>
    </div>
  );
}

function PointsTable({ res }: { res: DgmResult }) {
  const { t } = useTranslation();
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-muted">{t("dgm.tables.points", { count: res.points.length })}</summary>
      <div className="mt-2 flex justify-end">
        <CsvButton csv={pointsCsv(res.points)} filename="dgm-coordinates.csv" />
      </div>
      <table className="mt-2 w-full tabular">
        <thead>
          <tr className="border-b text-xs text-muted">
            <th className="py-1 text-left font-medium">Σ</th>
            <th className="py-1 text-right font-medium">X</th>
            <th className="py-1 text-right font-medium">Y</th>
          </tr>
        </thead>
        <tbody>
          {res.points.map((p) => (
            <tr key={p.name} className="border-b last:border-0">
              <td className={cn("py-1", p.new && "font-medium text-accent")}>{p.name}</td>
              <td className="py-1 text-right">{fmtNum(p.x, 3)}</td>
              <td className="py-1 text-right">{fmtNum(p.y, 3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function ExportPanel({ res, req }: { res: DgmResult; req: DgmRequest }) {
  const { t } = useTranslation();
  const ids = useExportIds();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<"dxf" | "pdf" | null>(null);
  const [sha, setSha] = useState<string | null>(null);
  const nameIssues = name ? checkFileName(name, res.kind) : [];
  const fail = (e: unknown) => {
    if (e instanceof ApiError && (e.status === 402 || e.code === "plan_required")) toast.warning(t("exp.upgrade"));
    else toast.error(t("errors.api", { message: apiErrorMessage(e, t) }));
  };
  const exportDxf = async () => {
    setBusy("dxf");
    try {
      const out = await dgmApi.exportDxf(req, name || null, ids.workspaceId, ids.projectId);
      downloadBlob(out.blob, out.filename);
      setSha(out.sha512);
      toast.success(t("exp.done", { file: out.filename }));
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  };
  const exportPdf = async () => {
    if (!sha) return;
    setBusy("pdf");
    try {
      downloadBlob(await dgmApi.hashPdf(sha, ids.workspaceId), "hash_sha512.pdf");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  };
  return (
    <section className="space-y-3 border-t pt-4">
      <h3 className="text-sm font-semibold">{t("dgm.export.heading")}</h3>
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-64 space-y-1.5">
          <Label>{t("dgm.export.filename")}</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="dgm_onoma_v01.dxf" maxLength={64} />
        </div>
        <Button size="sm" onClick={() => void exportDxf()} disabled={busy !== null} data-testid="dgm-export">
          <Download /> {t("dgm.export.dxf")}
        </Button>
        <Button size="sm" variant="outline" onClick={() => void exportPdf()} disabled={busy !== null || !sha}>
          <FileSignature /> {t("dgm.export.hashPdf")}
        </Button>
      </div>
      {nameIssues.length > 0 && <p className="text-xs text-warning">{nameIssues.map((c) => t(`dgm.export.name.${c}`)).join(" · ")}</p>}
      {!res.ok && <p className="text-xs text-danger">{t("dgm.export.notValid")}</p>}
      {sha && (
        <p className="break-all text-xs text-muted">
          SHA-512: <code className="select-all">{sha}</code>
        </p>
      )}
      <p className="text-xs text-muted">{t("dgm.export.signHint")}</p>
      <Disclaimer />
    </section>
  );
}
