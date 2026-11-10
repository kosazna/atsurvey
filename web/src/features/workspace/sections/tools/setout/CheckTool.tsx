// As-staked check (έλεγχος χάραξης): measured against design points, matched by name.
import { ArrowRight } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { type CheckResult, checkCsv, setoutApi } from "@/lib/setoutApi";
import { cn, fmtNum, fmtSigned, parseNum } from "@/lib/utils";
import { KV, NumberField, parsePointList, PointField, PointListField, ResultBox, resolvePoint, useProjectPoints, useRunner } from "../shared";
import { CsvButton, DxfImportButton, IssueList } from "./common";

const mm = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${fmtSigned(v * 1000, 1)}`);

export function CheckTool() {
  const { t } = useTranslation();
  const pts = useProjectPoints();
  const [design, setDesign] = useState("");
  const [measured, setMeasured] = useState("");
  const [tolXy, setTolXy] = useState("0.020");
  const [tolZ, setTolZ] = useState("0.020");
  const [useLine, setUseLine] = useState(false);
  const [la, setLa] = useState("");
  const [lb, setLb] = useState("");
  const d = useMemo(() => parsePointList(design, pts), [design, pts]);
  const m = useMemo(() => parsePointList(measured, pts), [measured, pts]);
  const pa = resolvePoint(la, pts);
  const pb = resolvePoint(lb, pts);
  const txy = parseNum(tolXy);
  const tz = parseNum(tolZ);
  const r = useRunner<CheckResult>();
  const ready = d.pts.length > 0 && m.pts.length > 0 && txy !== null && txy > 0 && (!useLine || (pa && pb));
  const compute = () =>
    void r.run(() =>
      setoutApi.check({
        design: d.pts,
        measured: m.pts,
        tolerance_xy: txy!,
        tolerance_z: tz !== null && tz > 0 ? tz : null,
        reference_line: useLine && pa && pb ? { a: pa, b: pb } : null,
      }),
    );
  const res = r.result;
  const hasLine = res?.rows.some((x) => x.along !== null) ?? false;
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-2">
          <PointListField label={t("setout.designPoints")} value={design} onChange={setDesign} hint={t("setout.designHint")} testId="check-design" />
          <DxfImportButton value={design} onChange={setDesign} />
          {d.bad.length > 0 && <p className="text-xs text-danger">{t("tools.badLines", { lines: d.bad.slice(0, 3).join(" · ") })}</p>}
        </div>
        <div className="space-y-2">
          <PointListField label={t("setout.measured")} value={measured} onChange={setMeasured} hint={t("setout.measuredHint")} testId="check-measured" />
          {m.bad.length > 0 && <p className="text-xs text-danger">{t("tools.badLines", { lines: m.bad.slice(0, 3).join(" · ") })}</p>}
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <NumberField label={t("setout.tolXy")} suffix="m" value={tolXy} onChange={setTolXy} />
        <NumberField label={t("setout.tolZ")} suffix="m" value={tolZ} onChange={setTolZ} />
        <div className="flex items-end gap-2 pb-2 sm:col-span-2">
          <Switch id="check-line" checked={useLine} onCheckedChange={setUseLine} />
          <Label htmlFor="check-line" className="font-normal">
            {t("setout.useLine")}
          </Label>
        </div>
        {useLine && (
          <>
            <PointField label={t("setout.lineA")} value={la} onChange={setLa} points={pts} />
            <PointField label={t("setout.lineB")} value={lb} onChange={setLb} points={pts} />
          </>
        )}
      </div>
      <Button disabled={!ready || r.busy} onClick={compute} data-testid="check-compute">
        {t("tools.compute")} <ArrowRight />
      </Button>
      <ResultBox error={r.error} testId="check-result">
        {res && (
          <div className="space-y-4">
            <IssueList issues={res.issues} />
            {res.summary && (
              <KV
                items={[
                  { k: t("setout.matched"), v: res.summary.matched },
                  { k: t("setout.outOfTolerance"), v: res.summary.out_of_tolerance, strong: res.summary.out_of_tolerance > 0 },
                  { k: t("setout.maxRadial"), v: `${fmtNum(res.summary.max_radial * 1000, 1)} mm`, strong: true },
                  { k: t("setout.rmsRadial"), v: `${fmtNum(res.summary.rms_radial * 1000, 1)} mm` },
                  { k: t("setout.meanShift"), v: `${mm(res.summary.mean_dx)} / ${mm(res.summary.mean_dy)} mm` },
                  ...(res.summary.max_abs_dz !== null ? [{ k: t("setout.maxDz"), v: `${fmtNum(res.summary.max_abs_dz * 1000, 1)} mm` }, { k: t("setout.rmsDz"), v: `${fmtNum((res.summary.rms_dz ?? 0) * 1000, 1)} mm` }] : []),
                ]}
              />
            )}
            {res.unmatched_design.length > 0 && <p className="text-xs text-warning">{`${t("setout.unmatchedDesign")}: ${res.unmatched_design.join(", ")}`}</p>}
            {res.unmatched_measured.length > 0 && <p className="text-xs text-muted">{`${t("setout.unmatchedMeasured")}: ${res.unmatched_measured.join(", ")}`}</p>}
            {res.rows.length > 0 && (
              <>
                <div className="flex justify-end">
                  <CsvButton text={checkCsv(res.rows)} filename="as-staked-check.csv" />
                </div>
                <div className="scroll-x-visible">
                  <table className="w-full min-w-[560px] text-sm tabular" data-testid="check-table">
                    <thead>
                      <tr className="border-b text-xs text-muted">
                        <th className="py-1.5 text-left font-medium">{t("tools.point")}</th>
                        <th className="py-1.5 text-right font-medium">ΔX (mm)</th>
                        <th className="py-1.5 text-right font-medium">ΔY (mm)</th>
                        <th className="py-1.5 text-right font-medium">{t("setout.radial")} (mm)</th>
                        {hasLine && <th className="py-1.5 text-right font-medium">{t("setout.along")}</th>}
                        {hasLine && <th className="py-1.5 text-right font-medium">{t("setout.across")}</th>}
                        <th className="py-1.5 text-right font-medium">ΔZ (mm)</th>
                        <th className="py-1.5 text-right font-medium" />
                      </tr>
                    </thead>
                    <tbody>
                      {res.rows.map((row) => (
                        <tr key={row.name} className="border-b last:border-0">
                          <td className="py-1.5 font-medium">{row.name}</td>
                          <td className="py-1.5 text-right">{mm(row.dx)}</td>
                          <td className="py-1.5 text-right">{mm(row.dy)}</td>
                          <td className={cn("py-1.5 text-right font-semibold", !row.ok_xy && "text-danger")}>{fmtNum(row.radial * 1000, 1)}</td>
                          {hasLine && <td className="py-1.5 text-right">{mm(row.along)}</td>}
                          {hasLine && <td className="py-1.5 text-right">{mm(row.across)}</td>}
                          <td className={cn("py-1.5 text-right", row.ok_z === false && "font-semibold text-danger")}>{mm(row.dz)}</td>
                          <td className={cn("py-1.5 text-right text-xs", row.ok ? "text-success" : "text-danger")}>{row.ok ? t("setout.ok") : t("setout.out")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}
      </ResultBox>
    </div>
  );
}
