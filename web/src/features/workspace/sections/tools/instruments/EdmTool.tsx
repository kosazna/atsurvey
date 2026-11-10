// EDM additive constant (and scale with a certified baseline) from collinear pillars.
import { ArrowRight, ListPlus } from "lucide-react";
import { Suspense, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { type EdmRequest, type EdmResult, instrumentsApi, pillarPairs } from "@/lib/instrumentsApi";
import { emptyMeta, type Report, type ReportMeta } from "@/lib/instrumentsReport";
import { parseSectionPoints } from "@/lib/leveling";
import { fmtNum, fmtSigned, parseNum, uid } from "@/lib/utils";
import type { Col } from "../../../grid/DataGrid";
import { DataGrid } from "../../../grid/LazyDataGrid";
import { KV, ResultBox, useRunner } from "../shared";
import { IssueList, ReportButtons, ReportMetaFields, SimpleTable, useMetaLabels } from "./common";

interface ObsRow {
  id: string;
  frm: string;
  to: string;
  distance: number | null;
}

const mm = (m: number | null | undefined, d = 1) => (m === null || m === undefined ? "—" : fmtSigned(m * 1000, d));

/** Parse whitespace/;-separated numbers; null if any token is not a number. */
function parseNumbers(text: string): number[] | null {
  const parts = text.split(/[\s;]+/).filter(Boolean);
  const nums = parts.map(parseNum);
  return nums.every((x): x is number => x !== null) ? nums : null;
}

export function EdmTool() {
  const { t } = useTranslation();
  const [pillarText, setPillarText] = useState("B0 B1 B2 B3");
  const [posText, setPosText] = useState("");
  const [rows, setRows] = useState<ObsRow[]>([]);
  const [meta, setMeta] = useState<ReportMeta>(() => emptyMeta());
  const labels = useMetaLabels();
  const r = useRunner<EdmResult>();
  const pillars = parseSectionPoints(pillarText);
  const positions = posText.trim() ? parseNumbers(posText) : null;
  const posInvalid = posText.trim() !== "" && (positions === null || positions.length !== pillars.length);
  const obs = rows.filter((x) => x.frm && x.to && x.distance !== null && x.distance > 0);
  const ready = pillars.length >= 3 && obs.length >= 3 && !posInvalid;

  const cols = useMemo<Col<ObsRow>[]>(
    () => [
      { id: "frm", title: t("instruments.edm.from"), width: 90, get: (x) => x.frm, set: (x, v) => ({ ...x, frm: String(v).trim() }) },
      { id: "to", title: t("instruments.edm.to"), width: 90, get: (x) => x.to, set: (x, v) => ({ ...x, to: String(v).trim() }) },
      {
        id: "distance",
        title: t("instruments.edm.distance"),
        width: 130,
        kind: "number",
        get: (x) => (x.distance === null ? "" : x.distance.toFixed(4)),
        set: (x, v) => {
          if (String(v).trim() === "") return { ...x, distance: null };
          const d = parseNum(String(v));
          return d === null || d <= 0 ? null : { ...x, distance: d };
        },
        invalid: (x) => x.distance === null,
      },
    ],
    [t],
  );

  const fillPairs = () => {
    const have = new Set(rows.map((x) => `${x.frm}|${x.to}`));
    const add = pillarPairs(pillars)
      .filter(([a, b]) => !have.has(`${a}|${b}`))
      .map(([frm, to]) => ({ id: uid(), frm, to, distance: null }));
    setRows([...rows.filter((x) => x.frm || x.to || x.distance !== null), ...add]);
  };

  const go = () => {
    if (!ready) return;
    const req: EdmRequest = {
      pillars,
      observations: obs.map((x) => ({ frm: x.frm, to: x.to, distance: x.distance! })),
      positions: positions && positions.length === pillars.length ? positions : null,
    };
    void r.run(() => instrumentsApi.edmConstant(req));
  };

  const res = r.result;
  const report: Report | null = res && {
    title: t("instruments.edm.title"),
    metaLabels: labels,
    meta,
    summary: [
      [t("instruments.edm.constant"), `${mm(res.constant, 2)} mm${res.sigma_constant === null ? "" : ` ± ${fmtNum(res.sigma_constant * 1000, 2)} mm`}`],
      [t("instruments.edm.scale"), res.scale_ppm === null ? t("instruments.notEstimated") : `${fmtSigned(res.scale_ppm, 1)} ppm${res.sigma_scale_ppm === null ? "" : ` ± ${fmtNum(res.sigma_scale_ppm, 1)} ppm`}`],
      [t("instruments.edm.s0"), res.s0 === null ? "—" : `${fmtNum(res.s0 * 1000, 2)} mm`],
      [t("instruments.dof"), String(res.dof)],
    ],
    tables: [
      {
        title: t("instruments.edm.observations"),
        headers: [t("instruments.edm.from"), t("instruments.edm.to"), "d (m)", `${t("instruments.edm.adjusted")} (m)`, "v (mm)"],
        rows: res.rows.map((x) => [x.frm, x.to, fmtNum(x.distance, 4), fmtNum(x.adjusted, 4), mm(x.residual, 2)]),
      },
      {
        title: t("instruments.edm.position"),
        headers: ["", `${t("instruments.edm.position")} (m)`, "σ (mm)"],
        rows: res.positions.map((p, i) => [pillars[i] ?? String(i + 1), fmtNum(p, 4), res.sigma_positions[i] === null ? "—" : fmtNum((res.sigma_positions[i] ?? 0) * 1000, 2)]),
      },
    ],
    notes: [t("instruments.edm.hint"), t("instruments.edm.formula")],
  };

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <div className="space-y-3">
        <ReportMetaFields meta={meta} onChange={setMeta} />
        <div className="space-y-1.5">
          <Label htmlFor="edm-pillars">{t("instruments.edm.pillars")}</Label>
          <Input id="edm-pillars" value={pillarText} placeholder={t("instruments.edm.pillarsHint")} onChange={(e) => setPillarText(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="edm-pos">{t("instruments.edm.positions")}</Label>
          <Input id="edm-pos" className={posInvalid ? "border-danger tabular" : "tabular"} value={posText} placeholder={t("instruments.edm.positionsHint")} onChange={(e) => setPosText(e.target.value)} />
        </div>
        <div className="overflow-hidden rounded-xl border">
          <div className="flex items-center justify-between border-b px-3 py-2">
            <span className="text-sm font-medium">{t("instruments.edm.observations")}</span>
            <Button type="button" size="sm" variant="ghost" onClick={fillPairs} disabled={pillars.length < 2}>
              <ListPlus /> {t("instruments.edm.fillPairs")}
            </Button>
          </div>
          <div className="h-64" data-testid="grid-edm">
            <Suspense fallback={<Skeleton className="m-3 h-48" />}>
              <DataGrid rows={rows} columns={cols} onChange={setRows} makeRow={() => ({ id: uid(), frm: "", to: "", distance: null })} appendLabel={t("instruments.edm.distance")} />
            </Suspense>
          </div>
        </div>
        <p className="text-xs text-muted">{t("instruments.edm.hint")}</p>
        <div className="flex items-center gap-3">
          <Button type="button" onClick={go} disabled={!ready || r.busy} data-testid="btn-edm">
            {t("tools.compute")} <ArrowRight />
          </Button>
          {!ready && <span className="text-xs text-muted">{t("instruments.edm.tooFew")}</span>}
        </div>
      </div>
      <ResultBox error={r.error} testId="edm-result">
        {res && report && (
          <div className="space-y-4">
            <KV items={report.summary.map(([k, v], i) => ({ k, v, strong: i < 2 }))} />
            <IssueList issues={res.issues} />
            <SimpleTable
              headers={[t("instruments.edm.from"), t("instruments.edm.to"), "d (m)", `${t("instruments.edm.adjusted")} (m)`, "v (mm)"]}
              rows={report.tables[0].rows}
            />
            <SimpleTable headers={report.tables[1].headers} rows={report.tables[1].rows} />
            <p className="text-xs text-muted">{t("instruments.edm.formula")}</p>
            <ReportButtons report={report} filename={`edm-constant-${meta.date}`} />
          </div>
        )}
      </ResultBox>
    </div>
  );
}
