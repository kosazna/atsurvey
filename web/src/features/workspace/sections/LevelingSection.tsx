// Geometric levelling: benchmarks + spreadsheet-style readings grid, computed via /v1/leveling.
// Data persists in projects.extras.leveling.
import { ArrowRight, CheckCircle2, Download, Mountain, RefreshCw, XCircle } from "lucide-react";
import { Suspense, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type { LevelingData, LevelRow } from "@/data/store";
import { cogo, isNotAvailable } from "@/lib/api";
import { apiErrorMessage } from "@/lib/apiErrors";
import type { LevelingResult, ReadingKind } from "@/lib/cogoTypes";
import { emptyLeveling, heightsCsv, toLevelingRequest, validateLeveling } from "@/lib/leveling";
import { cn, downloadBlob, fmtNum, fmtSigned, parseNum, uid } from "@/lib/utils";
import type { Col } from "../grid/DataGrid";
import { DataGrid } from "../grid/LazyDataGrid";
import { useWorkspace } from "../useWorkspace";
import { SectionFrame, SectionHeader } from "./SectionLayout";

type Bm = LevelingData["benchmarks"][number];
const KINDS: ReadingKind[] = ["bs", "is", "fs"];

export default function LevelingSection() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const lv = ws.data.extras.leveling ?? emptyLeveling();
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<LevelingResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const save = (patch: Partial<LevelingData>) => ws.update({ extras: { ...ws.data.extras, leveling: { ...lv, ...patch } } });
  const problems = validateLeveling(lv);

  const bmCols = useMemo<Col<Bm>[]>(
    () => [
      { id: "name", title: t("lev.bmName"), width: 120, get: (b) => b.name, set: (b, v) => ({ ...b, name: String(v).trim() }) },
      {
        id: "h",
        title: t("lev.bmH"),
        width: 120,
        kind: "number",
        get: (b) => (b.h === null ? "" : b.h.toFixed(3)),
        set: (b, v) => {
          const n = parseNum(String(v));
          return String(v).trim() === "" ? { ...b, h: null } : n === null ? null : { ...b, h: n };
        },
        invalid: (b) => b.name !== "" && b.h === null,
      },
    ],
    [t],
  );

  const rowCols = useMemo<Col<LevelRow>[]>(
    () => [
      {
        id: "setup",
        title: t("lev.setup"),
        width: 60,
        kind: "number",
        get: (r) => String(r.setup),
        set: (r, v) => {
          const n = parseNum(String(v));
          return n === null || n < 1 ? null : { ...r, setup: Math.round(n) };
        },
      },
      { id: "point", title: t("lev.point"), width: 110, get: (r) => r.point, set: (r, v) => ({ ...r, point: String(v).trim() }), invalid: (r) => !r.point },
      {
        id: "kind",
        title: t("lev.kind"),
        width: 120,
        get: (r) => r.kind.toUpperCase(),
        display: (r) => t(`lev.kinds.${r.kind}`),
        set: (r, v) => {
          const s = String(v).trim().toLowerCase();
          const map: Record<string, ReadingKind> = { bs: "bs", fs: "fs", is: "is", π: "bs", ε: "fs", ο: "is", b: "bs", f: "fs", i: "is" };
          const k = map[s];
          return k ? { ...r, kind: k } : null;
        },
      },
      {
        id: "reading",
        title: t("lev.reading"),
        width: 110,
        kind: "number",
        get: (r) => (r.reading === null ? "" : r.reading.toFixed(4)),
        set: (r, v) => {
          const n = parseNum(String(v));
          return String(v).trim() === "" ? { ...r, reading: null } : n === null ? null : { ...r, reading: n };
        },
        invalid: (r) => r.reading === null,
      },
      {
        id: "distance",
        title: t("lev.distance"),
        width: 100,
        kind: "number",
        get: (r) => (r.distance === null ? "" : r.distance.toFixed(2)),
        set: (r, v) => {
          const n = parseNum(String(v));
          return String(v).trim() === "" ? { ...r, distance: null } : n === null ? null : { ...r, distance: n };
        },
      },
    ],
    [t],
  );

  const makeRow = (): LevelRow => {
    const last = lv.rows[lv.rows.length - 1];
    const setup = last ? (last.kind === "fs" ? last.setup + 1 : last.setup) : 1;
    const kind: ReadingKind = !last || last.kind === "fs" ? "bs" : "fs";
    return { id: uid(), setup, point: kind === "bs" && last?.kind === "fs" ? last.point : "", kind, reading: null, distance: null };
  };

  const compute = async () => {
    setBusy(true);
    setErr(null);
    try {
      setRes(await cogo.leveling(toLevelingRequest(lv)));
    } catch (e) {
      setRes(null);
      setErr(isNotAvailable(e) ? t("tools.notAvailable") : apiErrorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  const applyHeights = () => {
    if (!res) return;
    const h = new Map(res.points.map((p) => [p.name, p.h]));
    let n = 0;
    const cps = ws.data.control_points.map((c) => {
      const v = h.get(c.name);
      if (v === undefined || res.points.find((p) => p.name === c.name)?.kind === "benchmark") return c;
      n++;
      return { ...c, z: Math.round(v * 10000) / 10000 };
    });
    if (!n) return toast.info(t("lev.noMatches"));
    ws.update({ control_points: cps });
    toast.success(t("lev.applied", { count: n }), { action: { label: t("ws.undo"), onClick: () => ws.undo() } });
  };

  const empty = lv.rows.length === 0 && lv.benchmarks.length === 0;

  return (
    <SectionFrame className="overflow-y-auto">
      <SectionHeader
        title={t("lev.title")}
        description={t("lev.subtitle")}
        actions={
          <Button size="sm" onClick={() => void compute()} disabled={busy || problems.some((p) => p.key === "noBenchmark" || p.key === "noSetups")} data-testid="btn-level">
            {busy ? <RefreshCw className="animate-spin" /> : <Mountain />} {t("lev.compute")}
          </Button>
        }
      />
      <div className="grid gap-4 p-4 xl:grid-cols-[1fr_1.1fr]">
        <div className="space-y-4">
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b px-3 py-2">
              <span className="text-sm font-medium">{t("lev.benchmarks")}</span>
              {empty && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => save({ benchmarks: [{ id: uid(), name: "", h: null }], rows: [makeRow()] })}
                >
                  {t("lev.start")}
                </Button>
              )}
            </div>
            <div className="h-36">
              <Suspense fallback={<Skeleton className="m-3 h-24" />}>
                <DataGrid rows={lv.benchmarks} columns={bmCols} onChange={(benchmarks) => save({ benchmarks })} makeRow={() => ({ id: uid(), name: "", h: null })} appendLabel={t("lev.addBm")} />
              </Suspense>
            </div>
          </Card>
          <Card className="overflow-hidden">
            <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
              <span className="text-sm font-medium">{t("lev.readings")}</span>
              <span className="text-xs text-muted">{t("lev.readingsHint")}</span>
            </div>
            <div className="h-80" data-testid="grid-leveling">
              <Suspense fallback={<Skeleton className="m-3 h-64" />}>
                <DataGrid rows={lv.rows} columns={rowCols} onChange={(rows) => save({ rows })} makeRow={makeRow} appendLabel={t("lev.addReading")} />
              </Suspense>
            </div>
          </Card>
          <Card className="grid gap-3 p-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="lv-tb">{t("lev.tolBase")}</Label>
              <Input id="lv-tb" className="tabular" inputMode="decimal" value={lv.tolerance_base_mm} onChange={(e) => save({ tolerance_base_mm: parseNum(e.target.value) ?? 0 })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lv-tk">{t("lev.tolKm")}</Label>
              <Input id="lv-tk" className="tabular" inputMode="decimal" value={lv.tolerance_mm_per_sqrt_km} onChange={(e) => save({ tolerance_mm_per_sqrt_km: parseNum(e.target.value) ?? 12 })} />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label>{t("lev.distribute")}</Label>
              <Select<"distance" | "setups">
                value={lv.distribute}
                onValueChange={(v) => save({ distribute: v })}
                options={[
                  { value: "distance", label: t("lev.byDistance") },
                  { value: "setups", label: t("lev.bySetups") },
                ]}
              />
            </div>
          </Card>
          {problems.length > 0 && !empty && (
            <ul className="space-y-1 text-xs text-warning">
              {[...new Map(problems.map((p) => [`${p.key}${p.setup}`, p])).values()].slice(0, 5).map((p) => (
                <li key={`${p.key}${p.setup}`}>• {t(`lev.problems.${p.key}`, { setup: p.setup })}</li>
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-4" data-testid="leveling-result">
          {err && <div className="rounded-lg border border-danger bg-danger-subtle px-3 py-2 text-sm text-danger">{err}</div>}
          {!res && !err && (
            <Card className="flex flex-col items-center gap-2 p-8 text-center text-sm text-muted">
              <Mountain className="size-5" />
              {t("lev.emptyResult")}
            </Card>
          )}
          {res && (
            <>
              <div className="grid grid-cols-2 gap-3 2xl:grid-cols-4">
                {[
                  { k: t("lev.misclosure"), v: res.misclosure === null ? "—" : `${fmtSigned(res.misclosure * 1000, 1)} mm` },
                  { k: t("lev.tolerance"), v: res.tolerance === null ? "—" : `±${(res.tolerance * 1000).toFixed(1)} mm` },
                  { k: t("lev.length"), v: res.length_km === null ? "—" : `${res.length_km.toFixed(3)} km` },
                  { k: t("lev.setups"), v: res.n_setups },
                ].map((m) => (
                  <div key={m.k} className="rounded-xl border bg-surface p-3">
                    <div className="text-xs text-muted">{m.k}</div>
                    <div className="mt-1 whitespace-nowrap text-lg font-semibold tabular">{m.v}</div>
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {res.within_tolerance === null ? (
                  <Badge variant="secondary">{t("lev.open")}</Badge>
                ) : res.within_tolerance ? (
                  <Badge variant="success" data-testid="lev-status">
                    <CheckCircle2 /> {t("lev.within")}
                  </Badge>
                ) : (
                  <Badge variant="destructive" data-testid="lev-status">
                    <XCircle /> {t("lev.outside")}
                  </Badge>
                )}
                <span className="text-xs text-muted">
                  {res.start} <ArrowRight className="inline size-3" /> {res.end}
                </span>
                {res.message && <span className="text-xs text-muted">· {res.message}</span>}
                <div className="ml-auto flex gap-1.5">
                  <Button size="sm" variant="outline" onClick={applyHeights}>
                    {t("lev.apply")}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => downloadBlob(new Blob([heightsCsv(res.points)], { type: "text/csv;charset=utf-8" }), `${ws.data.meta.name}-heights.csv`)}>
                    <Download /> CSV
                  </Button>
                </div>
              </div>
              <Card className="overflow-hidden">
                <table className="w-full text-sm tabular">
                  <thead>
                    <tr className="border-b bg-surface-sunken text-xs text-muted">
                      <th className="px-3 py-2 text-left font-medium">{t("lev.point")}</th>
                      <th className="px-3 py-2 text-left font-medium">{t("lev.pointKind")}</th>
                      <th className="px-3 py-2 text-right font-medium">{t("lev.hRaw")}</th>
                      <th className="px-3 py-2 text-right font-medium">δH mm</th>
                      <th className="px-3 py-2 text-right font-medium">H</th>
                    </tr>
                  </thead>
                  <tbody>
                    {res.points.map((p) => (
                      <tr key={p.name} className={cn("border-b last:border-0", p.kind === "benchmark" && "text-muted")}>
                        <td className="px-3 py-1.5 font-medium">{p.name}</td>
                        <td className="px-3 py-1.5 text-xs">{t(`lev.pointKinds.${p.kind}`)}</td>
                        <td className="px-3 py-1.5 text-right">{fmtNum(p.h_unadjusted, 4)}</td>
                        <td className="px-3 py-1.5 text-right">{fmtSigned(p.correction * 1000, 1)}</td>
                        <td className="px-3 py-1.5 text-right font-semibold">{fmtNum(p.h, 4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </>
          )}
          <p className="text-xs text-muted">{t("lev.kindsHelp")}</p>
        </div>
      </div>
    </SectionFrame>
  );
}

export { KINDS };
