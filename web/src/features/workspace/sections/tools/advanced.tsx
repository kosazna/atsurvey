// Resection, area, 2D transformation (Helmert / affine) and stakeout tools.
import { AlertTriangle, ArrowRight, Download, MousePointerClick, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { angleToInput, parseAngle, radToCc } from "@/lib/angles";
import { cogo } from "@/lib/api";
import type { AreaResult, CommonPoint, ResectionResult, StakeoutResult, TransformMethod, TransformResult, XY } from "@/lib/cogoTypes";
import { formatArea, polygonArea, toStremmata } from "@/lib/geometry";
import { cn, downloadBlob, fmtNum, fmtSigned, parseNum, uid } from "@/lib/utils";
import { type PickedPoint, useWorkspace } from "../../useWorkspace";
import {
  AngleField,
  formatAngle,
  KV,
  NumberField,
  parsePointList,
  PointField,
  PointListField,
  ResultBox,
  resolvePoint,
  useAddToProject,
  useOverlay,
  useProjectPoints,
  useRunner,
} from "./shared";

// ---------------------------------------------------------------------------- resection

interface ResRow {
  id: string;
  point: string;
  dir: string;
  dist: string;
}

export function ResectionTool() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const pts = useProjectPoints();
  const add = useAddToProject();
  const [name, setName] = useState("Σ1");
  const [rows, setRows] = useState<ResRow[]>(() => [0, 1, 2].map(() => ({ id: uid(), point: "", dir: "", dist: "" })));
  const r = useRunner<ResectionResult>();
  const obs = rows
    .map((row) => ({ p: resolvePoint(row.point, pts), d: parseAngle(row.dir, unit), s: parseNum(row.dist), row }))
    .filter((o) => o.p && o.d !== null);
  useOverlay(
    [...obs.map((o) => ({ x: o.p!.x, y: o.p!.y, label: o.row.point, role: "input" as const })), ...(r.result ? [{ x: r.result.station.x, y: r.result.station.y, label: name, role: "result" as const }] : [])],
    r.result ? obs.map((o) => [[r.result!.station.x, r.result!.station.y], [o.p!.x, o.p!.y]] as [number, number][]) : [],
  );
  const set = (id: string, patch: Partial<ResRow>) => setRows((rs) => rs.map((x) => (x.id === id ? { ...x, ...patch } : x)));
  return (
    <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (obs.length >= 2)
            void r.run(() =>
              cogo.resection({
                station_name: name || null,
                observations: obs.map((o) => ({ point: { ...o.p!, name: o.row.point }, direction: o.d!, distance: o.s })),
              }),
            );
        }}
      >
        <NumberField label={t("tools.res.stationName")} value={name} onChange={setName} />
        <div className="space-y-2">
          <div className="grid grid-cols-[1.4fr_1fr_0.8fr_auto] gap-2 text-xs font-medium text-muted">
            <span>{t("tools.res.known")}</span>
            <span>{t("tools.res.direction")}</span>
            <span>{t("tools.res.distance")}</span>
            <span className="w-7" />
          </div>
          {rows.map((row) => (
            <div key={row.id} className="grid grid-cols-[1.4fr_1fr_0.8fr_auto] items-center gap-2">
              <Input list="res-pts" value={row.point} onChange={(e) => set(row.id, { point: e.target.value })} className={cn("tabular", row.point && !resolvePoint(row.point, pts) && "border-danger")} />
              <Input value={row.dir} inputMode="decimal" onChange={(e) => set(row.id, { dir: e.target.value })} className="tabular" placeholder={unit === "gon" ? "0.0000" : "0.00000"} />
              <Input value={row.dist} inputMode="decimal" onChange={(e) => set(row.id, { dist: e.target.value })} className="tabular" placeholder="—" />
              <Button type="button" variant="ghost" size="icon-sm" onClick={() => setRows((rs) => rs.filter((x) => x.id !== row.id))} aria-label={t("common.remove")}>
                <Trash2 />
              </Button>
            </div>
          ))}
          <datalist id="res-pts">
            {[...pts.keys()].map((n) => (
              <option key={n} value={n} />
            ))}
          </datalist>
          <Button type="button" variant="ghost" size="sm" onClick={() => setRows((rs) => [...rs, { id: uid(), point: "", dir: "", dist: "" }])}>
            <Plus /> {t("tools.res.addRow")}
          </Button>
        </div>
        <Button type="submit" disabled={obs.length < 2 || r.busy}>
          {t("tools.compute")} <ArrowRight />
        </Button>
      </form>
      <ResultBox error={r.error}>
        {r.result && (
          <div className="space-y-3">
            {r.result.danger_circle && (
              <div className="flex items-start gap-2 rounded-lg bg-warning-subtle px-3 py-2 text-xs text-warning">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> {t("tools.res.danger")}
              </div>
            )}
            <KV
              items={[
                { k: "X", v: fmtNum(r.result.station.x, 3), strong: true },
                { k: "Y", v: fmtNum(r.result.station.y, 3), strong: true },
                { k: t("tools.res.orientation"), v: formatAngle(r.result.orientation, unit) },
                ...(r.result.sigma0 !== null && r.result.sigma0 !== undefined ? [{ k: "σ₀", v: r.result.sigma0.toFixed(2) }] : []),
                ...(r.result.sx ? [{ k: "σX · σY", v: `${(r.result.sx * 1000).toFixed(1)} · ${((r.result.sy ?? 0) * 1000).toFixed(1)} mm` }] : []),
                { k: t("tools.res.method"), v: r.result.method },
              ]}
            />
            <table className="w-full text-xs tabular">
              <thead>
                <tr className="border-b text-muted">
                  <th className="py-1 text-left font-medium">{t("tools.point")}</th>
                  <th className="py-1 text-right font-medium">v (cc)</th>
                  <th className="py-1 text-right font-medium">v (mm)</th>
                </tr>
              </thead>
              <tbody>
                {r.result.residuals.map((res, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="py-1">{res.name ?? i + 1}</td>
                    <td className="py-1 text-right">{fmtSigned(radToCc(res.direction_residual), 1)}</td>
                    <td className="py-1 text-right">{res.distance_residual === null || res.distance_residual === undefined ? "—" : fmtSigned(res.distance_residual * 1000, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Button size="sm" variant="outline" onClick={() => add([{ ...r.result!.station, name }], "Σ")}>
              <Plus /> {t("tools.addToProject")}
            </Button>
          </div>
        )}
      </ResultBox>
    </div>
  );
}

// --------------------------------------------------------------------------------- area

export function AreaTool() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const pts = useProjectPoints();
  const [list, setList] = useState("");
  const parsed = parsePointList(list, pts);
  const r = useRunner<AreaResult>();
  const live = polygonArea(parsed.pts);
  const picking = ws.pick !== null && ws.pick.name === "area-pick";
  const togglePick = () => {
    if (picking) return ws.setPick(null);
    ws.revealMap();
    const fn = Object.defineProperty(
      (p: PickedPoint) => setList((cur) => (cur.trim() ? `${cur.trimEnd()}\n` : "") + (p.name ?? `${p.x.toFixed(3)} ${p.y.toFixed(3)}`)),
      "name",
      { value: "area-pick" },
    ) as (p: PickedPoint) => void;
    ws.setPick(fn);
  };
  const ring = parsed.pts.map((p) => [p.x, p.y] as [number, number]);
  useOverlay(
    parsed.pts.map((p) => ({ x: p.x, y: p.y, label: p.name ?? undefined, role: "input" as const })),
    [],
    ring.length >= 3 ? [ring] : [],
  );
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (parsed.pts.length >= 3) void r.run(() => cogo.area({ points: parsed.pts, reduction: ws.data.settings.reduction }));
        }}
      >
        <PointListField label={t("tools.area.vertices")} value={list} onChange={setList} hint={t("tools.area.hint")} testId="area-list" />
        {parsed.bad.length > 0 && <p className="text-xs text-danger">{t("tools.badLines", { lines: parsed.bad.slice(0, 3).join(" · ") })}</p>}
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" aria-pressed={picking} className={cn(picking && "border-accent bg-accent-subtle text-accent")} onClick={togglePick}>
            <MousePointerClick /> {picking ? t("tools.area.picking") : t("tools.area.pick")}
          </Button>
          <Button type="submit" size="sm" disabled={parsed.pts.length < 3 || r.busy}>
            {t("tools.compute")} <ArrowRight />
          </Button>
        </div>
        {parsed.pts.length >= 3 && (
          <p className="text-xs text-muted tabular">
            {t("tools.area.preview")}: {formatArea(live.area)} · {fmtNum(live.perimeter, 3)} m
          </p>
        )}
      </form>
      <ResultBox error={r.error} testId="area-result">
        {r.result && (
          <KV
            items={[
              { k: t("tools.area.area"), v: formatArea(r.result.area, 2), strong: true },
              { k: t("tools.area.stremmata"), v: `${toStremmata(r.result.area).toFixed(3)} στρ.` },
              { k: t("tools.area.perimeter"), v: `${fmtNum(r.result.perimeter, 3)} m` },
              { k: t("tools.area.orientation"), v: t(`tools.area.${r.result.orientation}`) },
              { k: t("tools.area.centroid"), v: `${fmtNum(r.result.centroid.x, 3)} · ${fmtNum(r.result.centroid.y, 3)}` },
              ...(r.result.area_ellipsoid ? [{ k: t("tools.area.ellipsoid"), v: formatArea(r.result.area_ellipsoid, 2) }] : []),
              ...(r.result.scale_factor_mean ? [{ k: "k", v: r.result.scale_factor_mean.toFixed(7) }] : []),
            ]}
          />
        )}
      </ResultBox>
    </div>
  );
}

// ------------------------------------------------------------------------ transformation

interface CommonRow {
  id: string;
  name: string;
  sx: string;
  sy: string;
  dst: string;
  use: boolean;
}

export function TransformTool() {
  const { t } = useTranslation();
  const pts = useProjectPoints();
  const add = useAddToProject();
  const [method, setMethod] = useState<TransformMethod>("helmert");
  const [rows, setRows] = useState<CommonRow[]>(() => [0, 1, 2].map(() => ({ id: uid(), name: "", sx: "", sy: "", dst: "", use: true })));
  const [paste, setPaste] = useState("");
  const [list, setList] = useState("");
  const parsed = parsePointList(list, new Map());
  const r = useRunner<TransformResult>();
  const common: CommonPoint[] = rows
    .map((row) => {
      const sx = parseNum(row.sx);
      const sy = parseNum(row.sy);
      const dst = resolvePoint(row.dst || row.name, pts);
      if (sx === null || sy === null || !dst) return null;
      return { name: row.name || row.dst, src: { x: sx, y: sy }, dst: { x: dst.x, y: dst.y }, use: row.use };
    })
    .filter(Boolean) as CommonPoint[];
  const need = method === "helmert" ? 2 : 3;
  const set = (id: string, patch: Partial<CommonRow>) => setRows((rs) => rs.map((x) => (x.id === id ? { ...x, ...patch } : x)));
  const importPaste = () => {
    const lines = paste.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const out: CommonRow[] = [];
    for (const l of lines) {
      const p = l.split(/[\s;\t]+/);
      if (p.length >= 5) out.push({ id: uid(), name: p[0], sx: p[1], sy: p[2], dst: `${p[3]} ${p[4]}`, use: true });
      else if (p.length >= 3) out.push({ id: uid(), name: p[0], sx: p[1], sy: p[2], dst: p[0], use: true });
    }
    if (out.length) {
      setRows(out);
      setPaste("");
    }
  };
  useOverlay((r.result?.points ?? []).map((p) => ({ x: p.x, y: p.y, label: p.name ?? undefined, role: "result" as const })));
  const params = r.result?.params ?? {};
  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[1.3fr_1fr]">
        <div className="space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-56 space-y-1.5">
              <Label>{t("tools.tr.method")}</Label>
              <Select<TransformMethod>
                value={method}
                onValueChange={setMethod}
                options={[
                  { value: "helmert", label: t("tools.tr.helmert"), hint: t("tools.tr.helmertHint") },
                  { value: "affine", label: t("tools.tr.affine"), hint: t("tools.tr.affineHint") },
                ]}
              />
            </div>
            <p className="pb-1.5 text-xs text-muted">{t("tools.tr.need", { n: need, have: common.filter((c) => c.use).length })}</p>
          </div>
          <div className="space-y-2">
            <div className="grid grid-cols-[auto_0.9fr_1fr_1fr_1.3fr_auto] gap-2 text-xs font-medium text-muted">
              <span className="w-4" />
              <span>{t("tools.point")}</span>
              <span>{t("tools.tr.srcX")}</span>
              <span>{t("tools.tr.srcY")}</span>
              <span>{t("tools.tr.dst")}</span>
              <span className="w-7" />
            </div>
            {rows.map((row) => {
              const dst = resolvePoint(row.dst || row.name, pts);
              const res = r.result?.residuals.find((x) => x.name === (row.name || row.dst));
              return (
                <div key={row.id} className="grid grid-cols-[auto_0.9fr_1fr_1fr_1.3fr_auto] items-center gap-2">
                  <Checkbox checked={row.use} onCheckedChange={(c) => set(row.id, { use: c === true })} aria-label={t("tools.tr.use")} />
                  <Input value={row.name} onChange={(e) => set(row.id, { name: e.target.value })} />
                  <Input value={row.sx} inputMode="decimal" className="tabular" onChange={(e) => set(row.id, { sx: e.target.value })} />
                  <Input value={row.sy} inputMode="decimal" className="tabular" onChange={(e) => set(row.id, { sy: e.target.value })} />
                  <div className="relative">
                    <Input value={row.dst} list="tr-pts" placeholder={t("tools.tr.dstHint")} className={cn("tabular", (row.dst || row.name) && !dst && "border-danger")} onChange={(e) => set(row.id, { dst: e.target.value })} />
                    {res && <span className={cn("absolute -bottom-4 right-1 text-xs tabular", res.used ? "text-muted" : "text-subtle")}>v {(res.v * 1000).toFixed(1)} mm</span>}
                  </div>
                  <Button type="button" variant="ghost" size="icon-sm" onClick={() => setRows((rs) => rs.filter((x) => x.id !== row.id))} aria-label={t("common.remove")}>
                    <Trash2 />
                  </Button>
                </div>
              );
            })}
            <datalist id="tr-pts">
              {[...pts.keys()].map((n) => (
                <option key={n} value={n} />
              ))}
            </datalist>
            <div className="flex flex-wrap gap-2 pt-3">
              <Button type="button" variant="ghost" size="sm" onClick={() => setRows((rs) => [...rs, { id: uid(), name: "", sx: "", sy: "", dst: "", use: true }])}>
                <Plus /> {t("tools.res.addRow")}
              </Button>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tr-paste">{t("tools.tr.paste")}</Label>
            <div className="flex gap-2">
              <Textarea id="tr-paste" rows={2} value={paste} onChange={(e) => setPaste(e.target.value)} className="font-mono text-xs" placeholder={t("tools.tr.pasteHint")} />
              <Button type="button" variant="outline" size="sm" onClick={importPaste} disabled={!paste.trim()}>
                {t("common.import")}
              </Button>
            </div>
          </div>
        </div>
        <div className="space-y-3">
          <PointListField label={t("tools.tr.toTransform")} value={list} onChange={setList} hint={t("tools.tr.toTransformHint")} />
          <Button
            disabled={common.filter((c) => c.use).length < need || r.busy}
            onClick={() => void r.run(() => cogo.transform({ method, common, points: parsed.pts }))}
          >
            {t("tools.compute")} <ArrowRight />
          </Button>
        </div>
      </div>
      <ResultBox error={r.error}>
        {r.result && (
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="space-y-3">
              <KV
                items={[
                  ...(method === "helmert"
                    ? [
                        { k: "tx", v: fmtNum(params.tx, 3) },
                        { k: "ty", v: fmtNum(params.ty, 3) },
                        { k: t("tools.tr.scale"), v: params.scale !== undefined ? `${params.scale.toFixed(8)} (${((params.scale - 1) * 1e6).toFixed(1)} ppm)` : "—" },
                        { k: t("tools.tr.rotation"), v: params.rotation !== undefined ? `${radToCc(params.rotation).toFixed(1)} cc` : "—" },
                      ]
                    : Object.entries(params).map(([k, v]) => ({ k, v: v.toFixed(Math.abs(v) > 100 ? 3 : 8) }))),
                  { k: "RMS", v: r.result.rms === null ? "—" : `${(r.result.rms * 1000).toFixed(1)} mm`, strong: true },
                ]}
              />
            </div>
            <div className="space-y-2">
              {r.result.points.length > 0 ? (
                <>
                  <table className="w-full text-xs tabular">
                    <thead>
                      <tr className="border-b text-muted">
                        <th className="py-1 text-left font-medium">{t("tools.point")}</th>
                        <th className="py-1 text-right font-medium">X</th>
                        <th className="py-1 text-right font-medium">Y</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.result.points.map((p, i) => (
                        <tr key={i} className="border-b last:border-0">
                          <td className="py-1">{p.name ?? i + 1}</td>
                          <td className="py-1 text-right">{fmtNum(p.x, 3)}</td>
                          <td className="py-1 text-right">{fmtNum(p.y, 3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <Button size="sm" variant="outline" onClick={() => add(r.result!.points, "T")}>
                    <Plus /> {t("tools.addAll", { count: r.result.points.length })}
                  </Button>
                </>
              ) : (
                <p className="text-xs text-muted">{t("tools.tr.noPoints")}</p>
              )}
            </div>
          </div>
        )}
      </ResultBox>
    </div>
  );
}

// ------------------------------------------------------------------------------ stakeout

export function StakeoutTool() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const pts = useProjectPoints();
  const [st, setSt] = useState("");
  const [mode, setMode] = useState<"backsight" | "azimuth">("backsight");
  const [bs, setBs] = useState("");
  const [az, setAz] = useState("");
  const [hi, setHi] = useState("1.550");
  const [ht, setHt] = useState("1.800");
  const [list, setList] = useState("");
  const ps = resolvePoint(st, pts);
  const pb = resolvePoint(bs, pts);
  const azr = parseAngle(az, unit);
  const parsed = parsePointList(list, pts);
  const r = useRunner<StakeoutResult>();
  const ready = ps && parsed.pts.length > 0 && (mode === "backsight" ? pb : azr !== null);
  useOverlay(
    [...(ps ? [{ x: ps.x, y: ps.y, label: st, role: "input" as const }] : []), ...(mode === "backsight" && pb ? [{ x: pb.x, y: pb.y, label: bs, role: "input" as const }] : []), ...parsed.pts.map((p) => ({ x: p.x, y: p.y, label: p.name ?? undefined, role: "result" as const }))],
    ps ? parsed.pts.map((p) => [[ps.x, ps.y], [p.x, p.y]] as [number, number][]) : [],
  );
  const rows = r.result?.rows ?? [];
  const csv = useMemo(() => {
    if (!rows.length) return "";
    const head = ["point", `angle_${unit}`, "distance_ground_m", "distance_grid_m", "dz_m", `zenith_${unit}`, "slope_m"];
    const body = rows.map((row) =>
      [
        row.name ?? "",
        angleToInput(row.angle, unit, 4),
        fmtNum(row.distance_ground ?? row.distance, 3),
        fmtNum(row.distance, 3),
        row.dz === null || row.dz === undefined ? "" : row.dz.toFixed(3),
        row.zenith === null || row.zenith === undefined ? "" : angleToInput(row.zenith, unit, 4),
        row.slope_distance === null || row.slope_distance === undefined ? "" : row.slope_distance.toFixed(3),
      ].join(";"),
    );
    return "﻿" + [head.join(";"), ...body].join("\r\n") + "\r\n";
  }, [rows, unit]);
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-3">
          <PointField label={t("tools.station")} value={st} onChange={setSt} points={pts} />
          <Select<"backsight" | "azimuth">
            value={mode}
            onValueChange={setMode}
            options={[
              { value: "backsight", label: t("tools.so.byBacksight") },
              { value: "azimuth", label: t("tools.so.byAzimuth") },
            ]}
          />
          {mode === "backsight" ? <PointField label={t("tools.backsight")} value={bs} onChange={setBs} points={pts} /> : <AngleField label={t("tools.so.zeroAzimuth")} value={az} onChange={setAz} />}
          <div className="grid grid-cols-2 gap-3">
            <NumberField label={t("tools.so.hi")} suffix="m" value={hi} onChange={setHi} />
            <NumberField label={t("tools.so.ht")} suffix="m" value={ht} onChange={setHt} />
          </div>
        </div>
        <div className="space-y-3">
          <PointListField label={t("tools.so.points")} value={list} onChange={setList} hint={t("tools.so.pointsHint")} />
          {parsed.bad.length > 0 && <p className="text-xs text-danger">{t("tools.badLines", { lines: parsed.bad.slice(0, 3).join(" · ") })}</p>}
          <Button
            disabled={!ready || r.busy}
            onClick={() =>
              void r.run(() =>
                cogo.stakeout({
                  station: ps!,
                  backsight: mode === "backsight" ? pb : null,
                  backsight_azimuth: mode === "azimuth" ? azr : null,
                  instrument_height: parseNum(hi) ?? 0,
                  target_height: parseNum(ht) ?? 0,
                  points: parsed.pts,
                  reduction: ws.data.settings.reduction,
                }),
              )
            }
          >
            {t("tools.compute")} <ArrowRight />
          </Button>
        </div>
      </div>
      <ResultBox error={r.error}>
        {rows.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium">{t("tools.so.table", { count: rows.length })}</span>
              <Button size="sm" variant="outline" onClick={() => downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), `stakeout-${st || "station"}.csv`)}>
                <Download /> CSV
              </Button>
            </div>
            <div className="scroll-x-visible">
              <table className="w-full min-w-[560px] text-sm tabular">
                <thead>
                  <tr className="border-b text-xs text-muted">
                    <th className="py-1.5 text-left font-medium">{t("tools.point")}</th>
                    <th className="py-1.5 text-right font-medium">{t("tools.so.angle")}</th>
                    <th className="py-1.5 text-right font-medium">{t("tools.so.ground")}</th>
                    <th className="py-1.5 text-right font-medium">{t("tools.so.grid")}</th>
                    <th className="py-1.5 text-right font-medium">ΔZ</th>
                    <th className="py-1.5 text-right font-medium">{t("tools.so.zenith")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-1.5 font-medium">{row.name ?? i + 1}</td>
                      <td className="py-1.5 text-right font-semibold">{formatAngle(row.angle, unit)}</td>
                      <td className="py-1.5 text-right font-semibold">{fmtNum(row.distance_ground ?? row.distance, 3)}</td>
                      <td className="py-1.5 text-right text-muted">{fmtNum(row.distance, 3)}</td>
                      <td className="py-1.5 text-right">{row.dz === null || row.dz === undefined ? "—" : fmtSigned(row.dz, 3)}</td>
                      <td className="py-1.5 text-right text-muted">{row.zenith === null || row.zenith === undefined ? "—" : formatAngle(row.zenith, unit)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </ResultBox>
    </div>
  );
}

export type { XY };
