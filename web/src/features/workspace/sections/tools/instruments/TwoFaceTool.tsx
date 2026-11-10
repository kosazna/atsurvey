// Total station two-face test: collimation c, vertical index i and trunnion-axis error a.
import { ArrowRight } from "lucide-react";
import { Suspense, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { angleToInput, CC, formatAngle, parseAngle } from "@/lib/angles";
import { instrumentsApi, type TwoFaceRequest, type TwoFaceResult } from "@/lib/instrumentsApi";
import { emptyMeta, type Report, type ReportMeta } from "@/lib/instrumentsReport";
import { fmtSigned, uid } from "@/lib/utils";
import type { Col } from "../../../grid/DataGrid";
import { DataGrid } from "../../../grid/LazyDataGrid";
import { useWorkspace } from "../../../useWorkspace";
import { KV, ResultBox, useRunner } from "../shared";
import { fmtSmallAngle, fmtSmallSigma, IssueList, ReportButtons, ReportMetaFields, SimpleTable, useMetaLabels } from "./common";

interface FaceRow {
  id: string;
  name: string;
  hz1: number | null;
  hz2: number | null;
  v1: number | null;
  v2: number | null;
}

type AngleKey = "hz1" | "hz2" | "v1" | "v2";
const ANGLES: AngleKey[] = ["hz1", "hz2", "v1", "v2"];
type Trunnion = TwoFaceRequest["trunnion"];

const emptyRow = (): FaceRow => ({ id: uid(), name: "", hz1: null, hz2: null, v1: null, v2: null });
const complete = (r: FaceRow): boolean => r.name.trim() !== "" && ANGLES.every((k) => r[k] !== null);
const cc = (rad: number) => fmtSigned(rad / CC, 1);

export function TwoFaceTool() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const [rows, setRows] = useState<FaceRow[]>([emptyRow(), emptyRow(), emptyRow()]);
  const [trunnion, setTrunnion] = useState<Trunnion>("auto");
  const [meta, setMeta] = useState<ReportMeta>(() => emptyMeta());
  const labels = useMetaLabels();
  const r = useRunner<TwoFaceResult>();
  const ready = rows.filter(complete);
  const [input, setInput] = useState<FaceRow[]>([]);

  const cols = useMemo<Col<FaceRow>[]>(
    () => [
      { id: "name", title: t("instruments.twoFace.target"), width: 100, get: (x) => x.name, set: (x, v) => ({ ...x, name: String(v).trim() }) },
      ...ANGLES.map<Col<FaceRow>>((k) => ({
        id: k,
        title: t(`instruments.twoFace.${k}`),
        width: 110,
        kind: "number",
        get: (x) => angleToInput(x[k], unit),
        set: (x, v) => {
          if (String(v).trim() === "") return { ...x, [k]: null };
          const a = parseAngle(String(v), unit);
          return a === null ? null : { ...x, [k]: a };
        },
        invalid: (x) => x.name.trim() !== "" && x[k] === null,
      })),
    ],
    [t, unit],
  );

  const go = () => {
    setInput(ready);
    void r.run(() =>
      instrumentsApi.twoFace({
        trunnion,
        targets: ready.map((x) => ({ name: x.name.trim(), hz1: x.hz1!, hz2: x.hz2!, v1: x.v1!, v2: x.v2! })),
      }),
    );
  };

  const res = r.result;
  const report: Report | null = res && {
    title: t("instruments.twoFace.title"),
    metaLabels: labels,
    meta,
    summary: [
      [t("instruments.twoFace.collimation"), `${fmtSmallAngle(res.collimation)}  (${fmtSmallSigma(res.sigma_collimation)})`],
      [t("instruments.twoFace.index"), `${fmtSmallAngle(res.index)}  (${fmtSmallSigma(res.sigma_index)})`],
      [t("instruments.twoFace.trunnionError"), res.trunnion === null ? t("instruments.notEstimated") : `${fmtSmallAngle(res.trunnion)}  (${fmtSmallSigma(res.sigma_trunnion)})`],
      [t("instruments.dof"), `Hz ${res.dof_hz} · V ${res.dof_v}`],
    ],
    tables: [
      {
        title: t("instruments.twoFace.targets"),
        headers: [t("instruments.twoFace.target"), ...ANGLES.map((k) => t(`instruments.twoFace.${k}`)), t("instruments.twoFace.zenith"), `${t("instruments.twoFace.delta")} cc`, `${t("instruments.twoFace.vHz")} cc`, `i cc`],
        rows: res.rows.map((row, i) => [row.name, ...ANGLES.map((k) => formatAngle(input[i]?.[k] ?? null, unit)), formatAngle(row.zenith, unit), cc(row.delta), cc(row.residual_hz), cc(row.index)]),
      },
    ],
    notes: [t("instruments.twoFace.formula"), t("instruments.twoFace.sign")],
  };

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <div className="space-y-3">
        <ReportMetaFields meta={meta} onChange={setMeta} />
        <div className="overflow-hidden rounded-xl border">
          <div className="border-b px-3 py-2 text-sm font-medium">{t("instruments.twoFace.targets")}</div>
          <div className="h-64" data-testid="grid-two-face">
            <Suspense fallback={<Skeleton className="m-3 h-48" />}>
              <DataGrid rows={rows} columns={cols} onChange={setRows} makeRow={emptyRow} appendLabel={t("instruments.twoFace.target")} />
            </Suspense>
          </div>
        </div>
        <p className="text-xs text-muted">{t("instruments.twoFace.hint")}</p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-56 flex-1 space-y-1.5">
            <Label>{t("instruments.twoFace.trunnion")}</Label>
            <Select<Trunnion>
              value={trunnion}
              onValueChange={setTrunnion}
              options={(["auto", "always", "never"] as const).map((v) => ({ value: v, label: t(`instruments.twoFace.trunnionModes.${v}`) }))}
            />
          </div>
          <Button type="button" onClick={go} disabled={!ready.length || r.busy} data-testid="btn-two-face">
            {t("tools.compute")} <ArrowRight />
          </Button>
        </div>
      </div>
      <ResultBox error={r.error} testId="two-face-result">
        {res && report && (
          <div className="space-y-4">
            <KV
              items={[
                { k: t("instruments.twoFace.collimation"), v: fmtSmallAngle(res.collimation), strong: true },
                { k: "σc", v: fmtSmallSigma(res.sigma_collimation) },
                { k: t("instruments.twoFace.index"), v: fmtSmallAngle(res.index), strong: true },
                { k: "σi", v: fmtSmallSigma(res.sigma_index) },
                { k: t("instruments.twoFace.trunnionError"), v: res.trunnion === null ? t("instruments.notEstimated") : fmtSmallAngle(res.trunnion), strong: true },
                ...(res.trunnion !== null ? [{ k: "σa", v: fmtSmallSigma(res.sigma_trunnion) }] : []),
                { k: t("instruments.twoFace.s0Hz"), v: fmtSmallSigma(res.s0_hz) },
                { k: t("instruments.twoFace.s0V"), v: fmtSmallSigma(res.s0_v) },
                { k: t("instruments.dof"), v: `Hz ${res.dof_hz} · V ${res.dof_v}` },
              ]}
            />
            <IssueList issues={res.issues} />
            <SimpleTable
              headers={[t("instruments.twoFace.target"), t("instruments.twoFace.zenith"), `${t("instruments.twoFace.delta")} cc`, `${t("instruments.twoFace.vHz")} cc`, "i cc", `${t("instruments.twoFace.vV")} cc`]}
              rows={res.rows.map((row) => [row.name, formatAngle(row.zenith, unit), cc(row.delta), cc(row.residual_hz), cc(row.index), cc(row.residual_v)])}
            />
            <p className="text-xs text-muted">{t("instruments.twoFace.sign")}</p>
            <ReportButtons report={report} filename={`two-face-${meta.date}`} />
          </div>
        )}
      </ResultBox>
    </div>
  );
}
