// Inverse, polar, intersections and chainage/offset tools.
import { ArrowRight, Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { parseAngle } from "@/lib/angles";
import { cogo } from "@/lib/api";
import type { InverseResult, IntersectionResult, OffsetResult, PolarResult, XY } from "@/lib/cogoTypes";
import { formatChainage } from "@/lib/geometry";
import { fmtNum, fmtSigned, parseNum } from "@/lib/utils";
import { useWorkspace } from "../../useWorkspace";
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

const ll = (p: XY | null | undefined): [number, number] | null => (p ? [p.x, p.y] : null);
const ov = (p: XY | null, label: string | undefined, role: "input" | "result") => (p ? [{ x: p.x, y: p.y, label, role }] : []);

export function InverseTool() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const pts = useProjectPoints();
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const pa = resolvePoint(a, pts);
  const pb = resolvePoint(b, pts);
  const r = useRunner<InverseResult>();
  useOverlay([...ov(pa, a, "input"), ...ov(pb, b, "input")], pa && pb ? [[ll(pa)!, ll(pb)!]] : []);
  const go = () => pa && pb && void r.run(() => cogo.inverse({ a: pa, b: pb, reduction: ws.data.settings.reduction }));
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          go();
        }}
      >
        <PointField label={t("tools.from")} value={a} onChange={setA} points={pts} testId="inv-a" />
        <PointField label={t("tools.to")} value={b} onChange={setB} points={pts} testId="inv-b" />
        <Button type="submit" disabled={!pa || !pb || r.busy} data-testid="btn-inverse">
          {t("tools.compute")} <ArrowRight />
        </Button>
      </form>
      <ResultBox error={r.error} testId="inverse-result">
        {r.result && (
          <KV
            items={[
              { k: t("tools.inv.distance"), v: `${fmtNum(r.result.distance, 3)} m`, strong: true },
              { k: t("tools.inv.azimuth"), v: formatAngle(r.result.azimuth, unit), strong: true },
              { k: t("tools.inv.azimuthBack"), v: formatAngle(r.result.azimuth_back, unit) },
              { k: "ΔX", v: fmtSigned(r.result.dx, 3) },
              { k: "ΔY", v: fmtSigned(r.result.dy, 3) },
              { k: "ΔZ", v: r.result.dz === null ? "—" : fmtSigned(r.result.dz, 3) },
              ...(r.result.distance_ground ? [{ k: t("tools.inv.ground"), v: `${fmtNum(r.result.distance_ground, 3)} m` }] : []),
              ...(r.result.slope_distance ? [{ k: t("tools.inv.slope"), v: `${fmtNum(r.result.slope_distance, 3)} m` }] : []),
              ...(r.result.gradient_percent !== null && r.result.gradient_percent !== undefined ? [{ k: t("tools.inv.gradient"), v: `${fmtSigned(r.result.gradient_percent, 2)} %` }] : []),
            ]}
          />
        )}
      </ResultBox>
    </div>
  );
}

export function PolarTool() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const pts = useProjectPoints();
  const add = useAddToProject();
  const [st, setSt] = useState("");
  const [mode, setMode] = useState<"azimuth" | "angle">("azimuth");
  const [bs, setBs] = useState("");
  const [ang, setAng] = useState("");
  const [dist, setDist] = useState("");
  const [dz, setDz] = useState("");
  const [name, setName] = useState("");
  const ps = resolvePoint(st, pts);
  const pb = resolvePoint(bs, pts);
  const a = parseAngle(ang, unit);
  const d = parseNum(dist);
  const r = useRunner<PolarResult>();
  const ready = ps && a !== null && d !== null && d > 0 && (mode === "azimuth" || pb);
  useOverlay(
    [...ov(ps, st, "input"), ...(mode === "angle" ? ov(pb, bs, "input") : []), ...ov(r.result?.point ?? null, name || "P", "result")],
    ps && r.result ? [[ll(ps)!, ll(r.result.point)!]] : [],
  );
  const go = () =>
    ready &&
    void r.run(() =>
      cogo.polar({
        station: ps!,
        distance: d!,
        azimuth: mode === "azimuth" ? a : null,
        backsight: mode === "angle" ? pb : null,
        angle: mode === "angle" ? a : null,
        dz: parseNum(dz),
        name: name || null,
      }),
    );
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          go();
        }}
      >
        <PointField label={t("tools.station")} value={st} onChange={setSt} points={pts} />
        <div className="space-y-1.5">
          <Select<"azimuth" | "angle">
            value={mode}
            onValueChange={setMode}
            options={[
              { value: "azimuth", label: t("tools.polar.byAzimuth") },
              { value: "angle", label: t("tools.polar.byAngle") },
            ]}
          />
        </div>
        {mode === "angle" && <PointField label={t("tools.backsight")} value={bs} onChange={setBs} points={pts} />}
        <div className="grid gap-3 sm:grid-cols-2">
          <AngleField label={mode === "azimuth" ? t("tools.inv.azimuth") : t("tools.polar.angle")} value={ang} onChange={setAng} />
          <NumberField label={t("tools.polar.distance")} suffix="m" value={dist} onChange={setDist} />
          <NumberField label="ΔZ" suffix="m" value={dz} onChange={setDz} />
          <NumberField label={t("tools.newName")} value={name} onChange={setName} />
        </div>
        <Button type="submit" disabled={!ready || r.busy}>
          {t("tools.compute")} <ArrowRight />
        </Button>
      </form>
      <ResultBox error={r.error}>
        {r.result && (
          <div className="space-y-3">
            <KV
              items={[
                { k: "X", v: fmtNum(r.result.point.x, 3), strong: true },
                { k: "Y", v: fmtNum(r.result.point.y, 3), strong: true },
                { k: "Z", v: fmtNum(r.result.point.z, 3) },
                { k: t("tools.inv.azimuth"), v: formatAngle(r.result.azimuth, unit) },
              ]}
            />
            <Button size="sm" variant="outline" onClick={() => add([{ ...r.result!.point, name: name || r.result!.point.name }], "P")}>
              <Plus /> {t("tools.addToProject")}
            </Button>
          </div>
        )}
      </ResultBox>
    </div>
  );
}

type IxMode = "angles" | "distances" | "lines";

export function IntersectionTool() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const pts = useProjectPoints();
  const add = useAddToProject();
  const [mode, setMode] = useState<IxMode>("angles");
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [c, setC] = useState("");
  const [d, setD] = useState("");
  const [v1, setV1] = useState("");
  const [v2, setV2] = useState("");
  const pa = resolvePoint(a, pts);
  const pb = resolvePoint(b, pts);
  const pc = resolvePoint(c, pts);
  const pd = resolvePoint(d, pts);
  const r = useRunner<IntersectionResult>();
  const sols = r.result?.solutions ?? [];
  useOverlay(
    [...ov(pa, a, "input"), ...ov(pb, b, "input"), ...(mode === "lines" ? [...ov(pc, c, "input"), ...ov(pd, d, "input")] : []), ...sols.map((s, i) => ({ x: s.x, y: s.y, label: `P${i + 1}`, role: "result" as const }))],
    mode === "lines"
      ? ([pa && pb ? [ll(pa)!, ll(pb)!] : null, pc && pd ? [ll(pc)!, ll(pd)!] : null].filter(Boolean) as [number, number][][])
      : sols.flatMap((s) => [pa ? [ll(pa)!, [s.x, s.y] as [number, number]] : null, pb ? [ll(pb)!, [s.x, s.y] as [number, number]] : null]).filter(Boolean) as [number, number][][],
  );
  const go = () => {
    if (mode === "angles") {
      const aa = parseAngle(v1, unit);
      const ab = parseAngle(v2, unit);
      if (pa && pb && aa !== null && ab !== null) void r.run(() => cogo.intersectionAngles({ a: pa, b: pb, angle_a: aa, angle_b: ab }));
    } else if (mode === "distances") {
      const ra = parseNum(v1);
      const rb = parseNum(v2);
      if (pa && pb && ra && rb) void r.run(() => cogo.intersectionDistances({ a: pa, r_a: ra, b: pb, r_b: rb }));
    } else if (pa && pb && pc && pd) void r.run(() => cogo.intersectionLines({ p1: pa, p2: pb, p3: pc, p4: pd }));
  };
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          go();
        }}
      >
        <Select<IxMode>
          value={mode}
          onValueChange={(m) => {
            setMode(m);
            r.setResult(null);
          }}
          options={[
            { value: "angles", label: t("tools.ix.angles"), hint: t("tools.ix.anglesHint") },
            { value: "distances", label: t("tools.ix.distances"), hint: t("tools.ix.distancesHint") },
            { value: "lines", label: t("tools.ix.lines"), hint: t("tools.ix.linesHint") },
          ]}
        />
        <div className="grid gap-x-3 sm:grid-cols-2">
          <PointField label={mode === "lines" ? t("tools.ix.l1a") : "A"} value={a} onChange={setA} points={pts} />
          <PointField label={mode === "lines" ? t("tools.ix.l1b") : "B"} value={b} onChange={setB} points={pts} />
          {mode === "lines" && <PointField label={t("tools.ix.l2a")} value={c} onChange={setC} points={pts} />}
          {mode === "lines" && <PointField label={t("tools.ix.l2b")} value={d} onChange={setD} points={pts} />}
        </div>
        {mode === "angles" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <AngleField label={t("tools.ix.angleA")} value={v1} onChange={setV1} />
            <AngleField label={t("tools.ix.angleB")} value={v2} onChange={setV2} />
          </div>
        )}
        {mode === "distances" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <NumberField label={t("tools.ix.ra")} suffix="m" value={v1} onChange={setV1} />
            <NumberField label={t("tools.ix.rb")} suffix="m" value={v2} onChange={setV2} />
          </div>
        )}
        <Button type="submit" disabled={r.busy}>
          {t("tools.compute")} <ArrowRight />
        </Button>
      </form>
      <ResultBox error={r.error}>
        {r.result &&
          (sols.length === 0 ? (
            <p className="text-sm text-muted">{r.result.message ?? t("tools.ix.none")}</p>
          ) : (
            <div className="space-y-3">
              {sols.map((s, i) => (
                <div key={i} className="flex items-center gap-3 rounded-lg border px-3 py-2">
                  <span className="text-sm font-medium">P{i + 1}</span>
                  <span className="flex-1 text-right text-sm tabular">
                    {fmtNum(s.x, 3)} · {fmtNum(s.y, 3)}
                  </span>
                  <Button size="icon-sm" variant="ghost" aria-label={t("tools.addToProject")} onClick={() => add([{ ...s, name: s.name ?? null }], "P")}>
                    <Plus />
                  </Button>
                </div>
              ))}
              {r.result.message && <p className="text-xs text-muted">{r.result.message}</p>}
            </div>
          ))}
      </ResultBox>
    </div>
  );
}

export function OffsetTool() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const pts = useProjectPoints();
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [list, setList] = useState("");
  const pa = resolvePoint(a, pts);
  const pb = resolvePoint(b, pts);
  const parsed = parsePointList(list, pts);
  const r = useRunner<OffsetResult>();
  useOverlay(
    [...ov(pa, a || "A", "input"), ...ov(pb, b || "B", "input"), ...parsed.pts.map((p) => ({ x: p.x, y: p.y, label: p.name ?? undefined, role: "input" as const }))],
    [...(pa && pb ? [[ll(pa)!, ll(pb)!]] : []), ...(r.result?.rows ?? []).map((row, i) => [ll(parsed.pts[i])!, [row.foot.x, row.foot.y] as [number, number]]).filter((l) => l[0])],
  );
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (pa && pb && parsed.pts.length) void r.run(() => cogo.offset({ a: pa, b: pb, points: parsed.pts }));
        }}
      >
        <div className="grid gap-x-3 sm:grid-cols-2">
          <PointField label={t("tools.off.start")} value={a} onChange={setA} points={pts} />
          <PointField label={t("tools.off.end")} value={b} onChange={setB} points={pts} />
        </div>
        <PointListField label={t("tools.off.points")} value={list} onChange={setList} />
        {parsed.bad.length > 0 && <p className="text-xs text-danger">{t("tools.badLines", { lines: parsed.bad.slice(0, 3).join(" · ") })}</p>}
        <Button type="submit" disabled={!pa || !pb || !parsed.pts.length || r.busy}>
          {t("tools.compute")} <ArrowRight />
        </Button>
      </form>
      <ResultBox error={r.error}>
        {r.result && (
          <div className="space-y-3">
            <div className="text-xs text-muted tabular">
              {t("tools.off.line")}: {fmtNum(r.result.line_length, 3)} m · {formatAngle(r.result.azimuth, unit)}
            </div>
            <table className="w-full text-sm tabular">
              <thead>
                <tr className="border-b text-xs text-muted">
                  <th className="py-1.5 text-left font-medium">{t("tools.point")}</th>
                  <th className="py-1.5 text-right font-medium">{t("tools.off.chainage")}</th>
                  <th className="py-1.5 text-right font-medium">{t("tools.off.offset")}</th>
                </tr>
              </thead>
              <tbody>
                {r.result.rows.map((row, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="py-1.5 font-medium">{row.name ?? `P${i + 1}`}</td>
                    <td className="py-1.5 text-right">{formatChainage(row.chainage)}</td>
                    <td className="py-1.5 text-right">
                      {fmtSigned(row.offset, 3)} <span className="text-xs text-muted">{row.offset >= 0 ? t("tools.off.right") : t("tools.off.left")}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </ResultBox>
    </div>
  );
}
