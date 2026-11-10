// Queries on a computed road axis: stakeout list and chainage/offset ↔ coordinates.
import { ArrowRight, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { angleToInput } from "@/lib/angles";
import { type AlignmentRequest, type AlignmentResult, type AlignmentStakeoutRow, formatChainage, type LocateResult, parseChainage, setoutApi, stakeoutCsv, stakeoutName } from "@/lib/setoutApi";
import { cn, fmtNum, fmtSigned, parseNum } from "@/lib/utils";
import { useWorkspace } from "../../../useWorkspace";
import { NumberField, parsePointList, PointListField, ResultBox, useAddToProject, useProjectPoints, useRunner } from "../shared";
import { CsvButton, Sketch } from "./common";

const MAX_SHOWN = 300;

function parseOffsets(text: string): number[] | null {
  const parts = text.replace(/−/g, "-").split(/[\s;]+/).filter(Boolean);
  const nums = parts.map((p) => parseNum(p));
  return nums.length && nums.every((n) => n !== null) ? (nums as number[]) : null;
}

export function AlignmentQueries({ req, res }: { req: AlignmentRequest; res: AlignmentResult }) {
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <StakeoutPanel req={req} res={res} />
      <LocatePanel req={req} />
    </div>
  );
}

function StakeoutPanel({ req, res }: { req: AlignmentRequest; res: AlignmentResult }) {
  const { t } = useTranslation();
  const unit = useWorkspace().data.meta.angle_unit;
  const add = useAddToProject();
  const [interval, setStepText] = useState("20");
  const [offsets, setOffsets] = useState("0");
  const [main, setMain] = useState(true);
  const r = useRunner<{ rows: AlignmentStakeoutRow[] }>();
  const step = parseNum(interval);
  const offs = parseOffsets(offsets);
  const rows = r.result?.rows ?? [];
  const csv = useMemo(() => (rows.length ? stakeoutCsv(rows, (v) => angleToInput(v, unit, 4), unit) : ""), [rows, unit]);
  return (
    <section className="space-y-3 rounded-xl border p-4">
      <h3 className="text-sm font-medium">{t("setout.stakeout")}</h3>
      <div className="grid grid-cols-2 gap-3">
        <NumberField label={t("setout.interval")} suffix="m" value={interval} onChange={setStepText} />
        <NumberField label={t("setout.offsets")} suffix="m" value={offsets} onChange={setOffsets} />
      </div>
      <p className="text-xs text-muted">{t("setout.offsetsHint")}</p>
      <div className="flex items-center gap-2">
        <Switch id="align-main" checked={main} onCheckedChange={setMain} />
        <Label htmlFor="align-main" className="font-normal">
          {t("setout.mainToo")}
        </Label>
      </div>
      <Button
        disabled={!step || step <= 0 || !offs || r.busy}
        onClick={() => void r.run(() => setoutApi.stakeout({ alignment: req, interval: step!, offsets: offs!, include_main_points: main }))}
        data-testid="align-stakeout"
      >
        {t("tools.compute")} <ArrowRight />
      </Button>
      <ResultBox error={r.error}>
        {rows.length > 0 && (
          <div className="space-y-3">
            <Sketch
              height={220}
              lines={[res.polyline]}
              points={rows.map((x) => ({ x: x.x, y: x.y, tone: x.code ? ("station" as const) : ("result" as const) }))}
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium">{t("setout.rows", { count: rows.length })}</span>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => add(rows.map((x) => ({ x: x.x, y: x.y, z: x.z, name: stakeoutName(x) })), "X")}>
                  <Plus /> {t("tools.addAll", { count: rows.length })}
                </Button>
                <CsvButton text={csv} filename="axis-stakeout.csv" />
              </div>
            </div>
            <div className="scroll-x-visible max-h-96 overflow-y-auto">
              <table className="w-full min-w-[480px] text-xs tabular">
                <thead>
                  <tr className="border-b text-muted">
                    <th className="py-1 text-left font-medium">{t("setout.chainage")}</th>
                    <th className="py-1 text-right font-medium">{t("setout.offset")}</th>
                    <th className="py-1 text-right font-medium">X</th>
                    <th className="py-1 text-right font-medium">Y</th>
                    <th className="py-1 text-right font-medium">Z</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, MAX_SHOWN).map((x, i) => (
                    <tr key={i} className={cn("border-b last:border-0", x.code && "font-medium")}>
                      <td className="py-1">
                        {formatChainage(x.chainage)} {x.code && <span className="text-accent">{x.code}</span>}
                      </td>
                      <td className="py-1 text-right">{fmtSigned(x.offset, 2)}</td>
                      <td className="py-1 text-right">{fmtNum(x.x, 3)}</td>
                      <td className="py-1 text-right">{fmtNum(x.y, 3)}</td>
                      <td className="py-1 text-right">{fmtNum(x.z, 3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {rows.length > MAX_SHOWN && <p className="text-xs text-muted">{t("setout.showing", { count: MAX_SHOWN })}</p>}
          </div>
        )}
      </ResultBox>
    </section>
  );
}

function parseStations(text: string): { chainage: number; offset: number; name: string }[] {
  return text
    .split(/\r?\n/)
    .map((l) => l.trim().split(/[\s;\t]+/).filter(Boolean))
    .filter((p) => p.length > 0)
    .map((p) => ({ ch: parseChainage(p[0]), off: p[1] === undefined ? 0 : parseNum(p[1].replace(/−/g, "-")) }))
    .filter((p): p is { ch: number; off: number } => p.ch !== null && p.off !== null)
    .map((p) => ({ chainage: p.ch, offset: p.off, name: stakeoutName({ chainage: p.ch, offset: p.off }) }));
}

function LocatePanel({ req }: { req: AlignmentRequest }) {
  const { t } = useTranslation();
  const pts = useProjectPoints();
  const [stext, setStext] = useState("");
  const [ptext, setPtext] = useState("");
  const stations = useMemo(() => parseStations(stext), [stext]);
  const points = useMemo(() => parsePointList(ptext, pts).pts, [ptext, pts]);
  const r = useRunner<LocateResult>();
  const res = r.result;
  return (
    <section className="space-y-3 rounded-xl border p-4">
      <h3 className="text-sm font-medium">{t("setout.locate")}</h3>
      <div className="space-y-1.5">
        <Label htmlFor="align-to-xy">{t("setout.toXy")}</Label>
        <Textarea id="align-to-xy" rows={3} value={stext} onChange={(e) => setStext(e.target.value)} className="font-mono text-xs" placeholder={t("setout.toXyHint")} />
      </div>
      <PointListField label={t("setout.toStation")} value={ptext} onChange={setPtext} />
      <Button
        disabled={(!stations.length && !points.length) || r.busy}
        onClick={() => void r.run(() => setoutApi.locate({ alignment: req, stations, points }))}
        data-testid="align-locate"
      >
        {t("tools.compute")} <ArrowRight />
      </Button>
      <ResultBox error={r.error}>
        {res && (res.stations.length > 0 || res.points.length > 0) && (
          <table className="w-full text-xs tabular" data-testid="align-locate-table">
            <thead>
              <tr className="border-b text-muted">
                <th className="py-1 text-left font-medium">{t("tools.point")}</th>
                <th className="py-1 text-right font-medium">{t("setout.chainage")}</th>
                <th className="py-1 text-right font-medium">{t("setout.offset")}</th>
                <th className="py-1 text-right font-medium">X</th>
                <th className="py-1 text-right font-medium">Y</th>
                <th className="py-1 text-right font-medium">{t("setout.designZ")}</th>
                <th className="py-1 text-right font-medium">{t("setout.cutFill")}</th>
              </tr>
            </thead>
            <tbody>
              {[...res.stations.map((s) => ({ ...s, zd: s.z, dz: null })), ...res.points.map((p) => ({ ...p, zd: p.z_design }))].map((x, i) => (
                <tr key={i} className="border-b last:border-0">
                  <td className="py-1">
                    {x.name} {!x.inside && <span className="text-warning">({t("setout.outside")})</span>}
                  </td>
                  <td className="py-1 text-right">{formatChainage(x.chainage, 3)}</td>
                  <td className="py-1 text-right">{fmtSigned(x.offset, 3)}</td>
                  <td className="py-1 text-right">{fmtNum(x.x, 3)}</td>
                  <td className="py-1 text-right">{fmtNum(x.y, 3)}</td>
                  <td className="py-1 text-right">{fmtNum(x.zd, 3)}</td>
                  <td className="py-1 text-right">{fmtSigned(x.dz, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </ResultBox>
    </section>
  );
}
