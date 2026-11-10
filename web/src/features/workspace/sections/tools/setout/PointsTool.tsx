// Batch setting out (χάραξη σημείων) from one station.
import { ArrowRight } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { angleToInput, parseAngle } from "@/lib/angles";
import { type SetoutResult, setoutApi, setoutCsv } from "@/lib/setoutApi";
import { fmtNum, fmtSigned, parseNum } from "@/lib/utils";
import { useWorkspace } from "../../../useWorkspace";
import { AngleField, formatAngle, KV, NumberField, parsePointList, PointField, PointListField, ResultBox, resolvePoint, useOverlay, useProjectPoints, useRunner } from "../shared";
import { CsvButton, DxfImportButton, IssueList, Sketch } from "./common";

type Mode = "backsight" | "azimuth";
type Order = "field" | "input";

export function PointsTool() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const pts = useProjectPoints();
  const [st, setSt] = useState("");
  const [mode, setMode] = useState<Mode>("backsight");
  const [bs, setBs] = useState("");
  const [az, setAz] = useState("");
  const [hi, setHi] = useState("");
  const [ht, setHt] = useState("");
  const [reduce, setReduce] = useState(true);
  const [list, setList] = useState("");
  const [order, setOrder] = useState<Order>("field");
  const ps = resolvePoint(st, pts);
  const pb = resolvePoint(bs, pts);
  const azr = parseAngle(az, unit);
  const parsed = useMemo(() => parsePointList(list, pts), [list, pts]);
  const r = useRunner<SetoutResult>();
  const ready = ps && parsed.pts.length > 0 && (mode === "backsight" ? pb : azr !== null);
  useOverlay(
    [...(ps ? [{ x: ps.x, y: ps.y, label: st, role: "input" as const }] : []), ...parsed.pts.map((p) => ({ x: p.x, y: p.y, label: p.name ?? undefined, role: "result" as const }))],
    ps ? parsed.pts.map((p) => [[ps.x, ps.y], [p.x, p.y]] as [number, number][]) : [],
  );
  const res = r.result;
  const seq = useMemo(() => (res ? (order === "field" ? res.field_order : res.rows.map((_, i) => i)) : []), [res, order]);
  const csv = useMemo(() => (res ? setoutCsv(res.rows, seq, (v) => angleToInput(v, unit, 4), unit) : ""), [res, seq, unit]);
  const compute = () =>
    void r.run(() =>
      setoutApi.points({
        station: { ...ps!, name: pts.has(st.trim()) ? st.trim() : null },
        backsight: mode === "backsight" ? { ...pb!, name: pts.has(bs.trim()) ? bs.trim() : null } : null,
        backsight_azimuth: mode === "azimuth" ? azr : null,
        instrument_height: parseNum(hi) ?? 0,
        target_height: parseNum(ht) ?? 0,
        points: parsed.pts,
        reduction: reduce ? ws.data.settings.reduction : null,
      }),
    );
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-3">
          <PointField label={t("setout.station")} value={st} onChange={setSt} points={pts} testId="setout-station" />
          <Select<Mode>
            value={mode}
            onValueChange={setMode}
            options={[
              { value: "backsight", label: t("setout.byBacksight") },
              { value: "azimuth", label: t("setout.byAzimuth") },
            ]}
          />
          {mode === "backsight" ? <PointField label={t("setout.backsight")} value={bs} onChange={setBs} points={pts} testId="setout-backsight" /> : <AngleField label={t("setout.zeroAzimuth")} value={az} onChange={setAz} />}
          <div className="grid grid-cols-2 gap-3">
            <NumberField label={t("setout.hi")} suffix={`m, ${t("setout.optional")}`} value={hi} onChange={setHi} />
            <NumberField label={t("setout.ht")} suffix={`m, ${t("setout.optional")}`} value={ht} onChange={setHt} />
          </div>
          <div className="flex items-center gap-2">
            <Switch id="setout-reduce" checked={reduce} onCheckedChange={setReduce} />
            <Label htmlFor="setout-reduce" className="font-normal">
              {t("setout.reduce")}
            </Label>
          </div>
        </div>
        <div className="space-y-3">
          <PointListField label={t("setout.designPoints")} value={list} onChange={setList} hint={t("setout.designHint")} testId="setout-list" />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <DxfImportButton value={list} onChange={setList} />
            <span className="text-xs text-muted">{t("setout.count", { count: parsed.pts.length })}</span>
          </div>
          {parsed.bad.length > 0 && <p className="text-xs text-danger">{t("tools.badLines", { lines: parsed.bad.slice(0, 3).join(" · ") })}</p>}
          <Button disabled={!ready || r.busy} onClick={compute} data-testid="setout-compute">
            {t("tools.compute")} <ArrowRight />
          </Button>
        </div>
      </div>
      <ResultBox error={r.error} testId="setout-result">
        {res && (
          <div className="space-y-4">
            <IssueList issues={res.issues} />
            <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
              <KV
                items={[
                  { k: t("setout.zero"), v: formatAngle(res.zero_azimuth, unit) },
                  ...(res.backsight_distance !== null ? [{ k: t("setout.bsDistance"), v: `${fmtNum(res.backsight_distance, 3)} m`, strong: true }] : []),
                ]}
              />
              <SetoutSketch res={res} station={st} backsight={mode === "backsight" ? bs : null} />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Select<Order>
                className="w-auto min-w-56"
                value={order}
                onValueChange={setOrder}
                options={[
                  { value: "field", label: t("setout.fieldOrder") },
                  { value: "input", label: t("setout.inputOrder") },
                ]}
              />
              <CsvButton text={csv} filename={`setout-${st || "station"}.csv`} />
            </div>
            <SetoutTable res={res} seq={seq} unit={unit} />
          </div>
        )}
      </ResultBox>
    </div>
  );
}

function SetoutTable({ res, seq, unit }: { res: SetoutResult; seq: number[]; unit: Parameters<typeof formatAngle>[1] }) {
  const { t } = useTranslation();
  const hasZ = res.rows.some((r) => r.dz !== null);
  return (
    <div className="scroll-x-visible">
      <table className="w-full min-w-[640px] text-sm tabular" data-testid="setout-table">
        <thead>
          <tr className="border-b text-xs text-muted">
            <th className="py-1.5 text-left font-medium">#</th>
            <th className="py-1.5 text-left font-medium">{t("tools.point")}</th>
            <th className="py-1.5 text-right font-medium">{t("setout.direction")}</th>
            <th className="py-1.5 text-right font-medium">{t("setout.distance")}</th>
            <th className="py-1.5 text-right font-medium">ΔE</th>
            <th className="py-1.5 text-right font-medium">ΔN</th>
            {hasZ && <th className="py-1.5 text-right font-medium">ΔZ</th>}
            {hasZ && <th className="py-1.5 text-right font-medium">{t("setout.zenith")}</th>}
            {hasZ && <th className="py-1.5 text-right font-medium">{t("setout.slope")}</th>}
          </tr>
        </thead>
        <tbody>
          {seq.map((k, n) => {
            const row = res.rows[k];
            return (
              <tr key={k} className="border-b last:border-0">
                <td className="py-1.5 text-muted">{n + 1}</td>
                <td className="py-1.5 font-medium">{row.name ?? k + 1}</td>
                <td className="py-1.5 text-right font-semibold">{formatAngle(row.direction, unit)}</td>
                <td className="py-1.5 text-right font-semibold" title={`${t("setout.gridDistance")} ${fmtNum(row.distance_grid, 3)}`}>
                  {fmtNum(row.distance, 3)}
                </td>
                <td className="py-1.5 text-right text-muted">{fmtSigned(row.de, 3)}</td>
                <td className="py-1.5 text-right text-muted">{fmtSigned(row.dn, 3)}</td>
                {hasZ && <td className="py-1.5 text-right">{fmtSigned(row.dz, 3)}</td>}
                {hasZ && <td className="py-1.5 text-right">{row.zenith === null ? "—" : formatAngle(row.zenith, unit)}</td>}
                {hasZ && <td className="py-1.5 text-right text-muted">{fmtNum(row.slope_distance, 3)}</td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Station-centred sketch (ΔE, ΔN) with the backsight direction and the field order numbers. */
function SetoutSketch({ res, station, backsight }: { res: SetoutResult; station: string; backsight: string | null }) {
  const len = Math.max(...res.rows.map((r) => r.distance_grid), 1);
  const bs: [number, number] = [len * Math.sin(res.zero_azimuth), len * Math.cos(res.zero_azimuth)];
  return (
    <Sketch
      testId="setout-sketch"
      height={200}
      dashed={[[[0, 0], bs]]}
      points={[
        { x: 0, y: 0, label: station, tone: "station" },
        ...(backsight ? [{ x: bs[0], y: bs[1], label: backsight, tone: "input" as const }] : []),
        ...res.field_order.map((k, n) => ({ x: res.rows[k].de, y: res.rows[k].dn, label: `${n + 1}`, tone: "result" as const })),
      ]}
    />
  );
}
