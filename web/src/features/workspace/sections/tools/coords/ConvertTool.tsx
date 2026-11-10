// "Μετατροπή συντεταγμένων": batch conversion between ΕΓΣΑ87, φλ, UTM, TM3 and Hatt.
import { ArrowLeftRight, ArrowRight, Download, ListPlus, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  type ConvertResult,
  type DatumMethod,
  type GeoFormat,
  type HeightKind,
  MAX_POINTS,
  SYSTEM_DATUM,
  type SystemId,
  changesDatum,
  convertCsv,
  coordHeaders,
  coordsApi,
  formatPoint,
  isGeographic,
  isUnverifiedDefinition,
  parseCoordList,
} from "@/lib/coordsApi";
import { cn, downloadBlob, parseNum } from "@/lib/utils";
import { ResultBox, useAddToProject, useOverlay, useProjectPoints } from "../shared";
import { EMPTY_HATT, GeoFormatSelect, type HattDraft, HattFields, IssueList, Note, SystemSelect, hattSpec, useCoordsRunner } from "./common";

function HeightOptions({
  hin,
  hout,
  n,
  onChange,
}: {
  hin: HeightKind;
  hout: HeightKind;
  n: string;
  onChange: (patch: { hin?: HeightKind; hout?: HeightKind; n?: string }) => void;
}) {
  const { t } = useTranslation();
  const opts = [
    { value: "orthometric" as const, label: t("coords.orthometric") },
    { value: "ellipsoidal" as const, label: t("coords.ellipsoidal") },
  ];
  return (
    <fieldset className="space-y-2 rounded-lg border p-3">
      <legend className="px-1 text-xs font-medium text-muted">{t("coords.heights")}</legend>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1.5">
          <Label>{t("coords.heightIn")}</Label>
          <Select<HeightKind> value={hin} onValueChange={(v) => onChange({ hin: v })} options={opts} aria-label={t("coords.heightIn")} />
        </div>
        <div className="space-y-1.5">
          <Label>{t("coords.heightOut")}</Label>
          <Select<HeightKind> value={hout} onValueChange={(v) => onChange({ hout: v })} options={opts} aria-label={t("coords.heightOut")} />
        </div>
      </div>
      {hin !== hout && (
        <div className="space-y-1.5">
          <Label htmlFor="coords-n">
            {t("coords.geoidN")} <span className="font-normal text-muted">(m)</span>
          </Label>
          <Input id="coords-n" value={n} onChange={(e) => onChange({ n: e.target.value })} inputMode="decimal" className={cn("tabular", n.trim() && parseNum(n) === null && "border-danger")} />
          <p className="text-xs text-muted">{t("coords.geoidHint")}</p>
        </div>
      )}
    </fieldset>
  );
}

function ResultTable({ result, fmt }: { result: ConvertResult; fmt: GeoFormat }) {
  const { t } = useTranslation();
  const geo = isGeographic(result.dst);
  const [a, b] = coordHeaders(geo);
  const shown = result.points.slice(0, 500);
  return (
    <div className="scroll-x-visible">
      <table className="w-full min-w-[360px] text-sm tabular" data-testid="coords-result-table">
        <thead>
          <tr className="border-b text-xs text-muted">
            <th className="py-1.5 text-left font-medium">{t("tools.point")}</th>
            <th className="py-1.5 text-right font-medium">{a}</th>
            <th className="py-1.5 text-right font-medium">{b}</th>
            <th className="py-1.5 text-right font-medium">Z</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((p, i) => {
            const [ca, cb, cz] = formatPoint(p, geo, fmt);
            return (
              <tr key={i} className="border-b last:border-0">
                <td className="py-1.5 font-medium">{p.name ?? i + 1}</td>
                {p.x === null ? (
                  <td colSpan={3} className="py-1.5 text-right text-danger">
                    {t("coords.failed")}
                  </td>
                ) : (
                  <>
                    <td className="py-1.5 text-right font-semibold">{ca}</td>
                    <td className="py-1.5 text-right font-semibold">{cb}</td>
                    <td className="py-1.5 text-right text-muted">{cz || "—"}</td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      {result.points.length > shown.length && <p className="pt-2 text-xs text-muted">… +{result.points.length - shown.length} (CSV)</p>}
    </div>
  );
}

function AccuracyBanner({ result }: { result: ConvertResult }) {
  const { t } = useTranslation();
  if (result.approximate)
    return (
      <Note tone="warning" testId="coords-approx-banner">
        <strong className="block text-sm">{t("coords.approxTitle", { accuracy: result.accuracy_m })}</strong>
        {t("coords.approxBody")}
      </Note>
    );
  if (result.datum_shift.length > 0) return <Note tone="info">{t("coords.officialDone", { accuracy: result.accuracy_m })}</Note>;
  return <Note tone="info">{t("coords.exact")}</Note>;
}

export function ConvertTool() {
  const { t } = useTranslation();
  const projectPoints = useProjectPoints();
  const add = useAddToProject();
  const [src, setSrc] = useState<SystemId>("wgs84_geo");
  const [dst, setDst] = useState<SystemId>("egsa87");
  const [fmt, setFmt] = useState<GeoFormat>("dms");
  const [list, setList] = useState("");
  const [method, setMethod] = useState<DatumMethod>("approximate");
  const [h, setH] = useState<{ hin: HeightKind; hout: HeightKind; n: string }>({ hin: "orthometric", hout: "orthometric", n: "" });
  const [srcHatt, setSrcHatt] = useState<HattDraft>(EMPTY_HATT);
  const [dstHatt, setDstHatt] = useState<HattDraft>(EMPTY_HATT);
  const r = useCoordsRunner<ConvertResult>();

  const parsed = useMemo(() => parseCoordList(list, isGeographic(src), fmt), [list, src, fmt]);
  const srcSpec = src === "hatt" ? hattSpec(srcHatt, fmt) : null;
  const dstSpec = dst === "hatt" ? hattSpec(dstHatt, fmt) : null;
  const shifts = changesDatum(src, dst);
  const n = parseNum(h.n);
  const ready =
    parsed.pts.length > 0 &&
    parsed.pts.length <= MAX_POINTS &&
    (src !== "hatt" || srcSpec !== null) &&
    (dst !== "hatt" || dstSpec !== null) &&
    (h.hin === h.hout || n !== null);

  const result = r.result;
  const csv = useMemo(() => (result ? convertCsv(result, fmt) : ""), [result, fmt]);
  const egsaOut = result?.dst === "egsa87" ? result.points.filter((p) => p.x !== null && p.y !== null) : [];
  useOverlay(egsaOut.map((p) => ({ x: p.x!, y: p.y!, label: p.name ?? undefined, role: "result" as const })));

  const fillFromProject = () => {
    setSrc("egsa87");
    setList([...projectPoints.values()].map((p) => [p.name, p.x.toFixed(3), p.y.toFixed(3), p.z === null || p.z === undefined ? "" : p.z.toFixed(3)].join(" ").trim()).join("\n"));
  };
  const swap = () => {
    setSrc(dst);
    setDst(src);
    setSrcHatt(dstHatt);
    setDstHatt(srcHatt);
  };
  const submit = () =>
    void r.run(() =>
      coordsApi.convert({
        src,
        dst,
        points: parsed.pts,
        src_hatt: srcSpec,
        dst_hatt: dstSpec,
        datum_method: method,
        height_in: h.hin,
        height_out: h.hout,
        geoid_undulation: h.hin === h.hout ? null : n,
      }),
    );

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[1.1fr_1fr]">
        <div className="space-y-3">
          <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-2">
            <SystemSelect label={t("coords.from")} value={src} onChange={setSrc} testId="coords-src" />
            <Button type="button" variant="ghost" size="icon" onClick={swap} aria-label={t("coords.swap")}>
              <ArrowLeftRight />
            </Button>
            <SystemSelect label={t("coords.to")} value={dst} onChange={setDst} testId="coords-dst" />
          </div>
          {(isGeographic(src) || isGeographic(dst) || src === "hatt" || dst === "hatt") && <GeoFormatSelect value={fmt} onChange={setFmt} />}
          {src === "hatt" && <HattFields value={srcHatt} onChange={setSrcHatt} fmt={fmt} withCoefficients={method === "official" && SYSTEM_DATUM[dst] !== "greek"} />}
          {dst === "hatt" && <HattFields value={dstHatt} onChange={setDstHatt} fmt={fmt} withCoefficients={false} />}
          {shifts && (
            <div className="space-y-1.5">
              <Label>{t("coords.method")}</Label>
              <Select<DatumMethod>
                value={method}
                onValueChange={setMethod}
                aria-label={t("coords.method")}
                options={[
                  { value: "approximate", label: t("coords.methodApprox"), hint: t("coords.methodApproxHint") },
                  { value: "official", label: t("coords.methodOfficial"), hint: t("coords.methodOfficialHint") },
                ]}
              />
            </div>
          )}
          {shifts && method === "approximate" && <Note tone="warning" testId="coords-approx-chip">{t("coords.approxBefore")}</Note>}
          {(isUnverifiedDefinition(src) || isUnverifiedDefinition(dst)) && <Note tone="info">{t("coords.unverified")}</Note>}
          {shifts && (SYSTEM_DATUM[src] === "greek" || SYSTEM_DATUM[dst] === "greek") && <Note tone="info">{t("coords.oldDatum")}</Note>}
          <HeightOptions hin={h.hin} hout={h.hout} n={h.n} onChange={(patch) => setH((cur) => ({ ...cur, ...patch }))} />
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor="coords-list">{t("coords.points")}</Label>
            {projectPoints.size > 0 && (
              <Button type="button" variant="ghost" size="sm" onClick={fillFromProject} title={t("coords.fromProjectHint")}>
                <ListPlus /> {t("coords.fromProject")}
              </Button>
            )}
          </div>
          <Textarea
            id="coords-list"
            rows={10}
            value={list}
            onChange={(e) => setList(e.target.value)}
            className="font-mono text-xs"
            placeholder={isGeographic(src) ? t("coords.pointsHintGeo") : t("coords.pointsHintGrid")}
            data-testid="coords-list"
          />
          {parsed.bad.length > 0 && <p className="text-xs text-danger">{t("tools.badLines", { lines: parsed.bad.slice(0, 3).join(" · ") })}</p>}
          {parsed.pts.length > MAX_POINTS && <p className="text-xs text-danger">{t("coords.tooMany", { max: MAX_POINTS })}</p>}
          <Button disabled={!ready || r.busy} onClick={submit} data-testid="coords-convert">
            {t("coords.convert")} <ArrowRight />
          </Button>
        </div>
      </div>
      <ResultBox error={r.error} testId="coords-result">
        {result && (
          <div className="space-y-3">
            <AccuracyBanner result={result} />
            {result.datum_shift.length > 0 && (
              <p className="text-xs text-muted">
                {t("coords.shift")}: {result.datum_shift.join(" → ")}
              </p>
            )}
            {/* the banner above already states the approximation */}
            <IssueList issues={result.issues.filter((i) => i.code !== "COORD_APPROXIMATE")} />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium">{t("coords.result", { count: result.points.length })}</span>
              <div className="flex gap-2">
                {egsaOut.length > 0 && (
                  <Button size="sm" variant="outline" onClick={() => add(egsaOut.map((p) => ({ name: p.name ?? null, x: p.x!, y: p.y!, z: p.z ?? null })), "K")}>
                    <Plus /> {t("coords.addToProject")}
                  </Button>
                )}
                <Button size="sm" variant="outline" onClick={() => downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), `coords-${result.src}-${result.dst}.csv`)}>
                  <Download /> CSV
                </Button>
              </div>
            </div>
            <ResultTable result={result} fmt={fmt} />
          </div>
        )}
      </ResultBox>
    </div>
  );
}
