// "Στοιχεία σημείου": φ λ, scale factor k, meridian convergence γ, elevation/combined factor, zones.
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { type GeoFormat, type HeightKind, type PointInfoResult, type SystemId, coordsApi, formatGeo, isGeographic, isUnverifiedDefinition, parseCoordLine } from "@/lib/coordsApi";
import { cn, fmtNum, parseNum } from "@/lib/utils";
import { useWorkspace } from "../../../useWorkspace";
import { KV, ResultBox, formatAngle, resolvePoint, useProjectPoints } from "../shared";
import { EMPTY_HATT, GeoFormatSelect, type HattDraft, HattFields, IssueList, Note, SystemSelect, hattSpec, useCoordsRunner } from "./common";

const PPM = 1e6;

function ppm(f: number | null): string {
  return f === null ? "—" : `${f.toFixed(8)}  (${((f - 1) * PPM).toFixed(1)} ppm)`;
}

function InfoResult({ r, fmt }: { r: PointInfoResult; fmt: GeoFormat }) {
  const { t } = useTranslation();
  const unit = useWorkspace().data.meta.angle_unit;
  const conformal = r.scale_factor !== null;
  return (
    <div className="space-y-3">
      <KV
        items={[
          { k: t("coords.info.lat"), v: formatGeo(r.lat, fmt), strong: true },
          { k: t("coords.info.lon"), v: formatGeo(r.lon, fmt), strong: true },
          ...(r.lon_athens !== null ? [{ k: t("coords.info.lonAthens"), v: formatGeo(r.lon_athens, fmt) }] : []),
          ...(r.x !== null && r.y !== null ? [{ k: "E · N", v: `${fmtNum(r.x, 3)} · ${fmtNum(r.y, 3)}` }] : []),
          ...(conformal ? [{ k: t("coords.info.scale"), v: ppm(r.scale_factor), strong: true }] : []),
          ...(!conformal && r.scale_min !== null ? [{ k: t("coords.info.scaleRange"), v: `${r.scale_min.toFixed(8)} – ${(r.scale_max ?? 0).toFixed(8)}` }] : []),
          ...(r.convergence !== null ? [{ k: t("coords.info.convergence"), v: `${formatAngle(r.convergence, unit)}  (${formatAngle(r.convergence, "dms", 2)})` }] : []),
          ...(r.elevation_factor !== null ? [{ k: t("coords.info.elevation"), v: ppm(r.elevation_factor) }] : []),
          ...(r.combined_factor !== null ? [{ k: t("coords.info.combined"), v: ppm(r.combined_factor), strong: true }] : []),
          { k: t("coords.info.utmZone"), v: `${r.utm_zone}N` },
          ...(r.tm3_zone ? [{ k: t("coords.info.tm3Zone"), v: t(`coords.systems.${r.tm3_zone}`) }] : []),
          { k: t("coords.info.inside"), v: r.inside_zone ? t("common.yes") : t("common.no") },
        ]}
      />
      <IssueList issues={r.issues} />
    </div>
  );
}

export function PointInfoTool() {
  const { t } = useTranslation();
  const points = useProjectPoints();
  const [system, setSystem] = useState<SystemId>("egsa87");
  const [fmt, setFmt] = useState<GeoFormat>("dms");
  const [text, setText] = useState("");
  const [height, setHeight] = useState("");
  const [kind, setKind] = useState<HeightKind>("orthometric");
  const [n, setN] = useState("");
  const [hatt, setHatt] = useState<HattDraft>(EMPTY_HATT);
  const r = useCoordsRunner<PointInfoResult>();
  const geo = isGeographic(system);
  // a project point name resolves to its ΕΓΣΑ87 coordinates
  const projectPoint = system === "egsa87" ? resolvePoint(text, points) : null;
  const point = projectPoint ? { x: projectPoint.x, y: projectPoint.y } : parseCoordLine(text, geo, fmt);
  const spec = system === "hatt" ? hattSpec(hatt, fmt) : null;
  const z = height.trim() ? parseNum(height) : (projectPoint?.z ?? null);
  const ready = point !== null && (system !== "hatt" || spec !== null);
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready) void r.run(() => coordsApi.pointInfo({ system, point: { x: point.x, y: point.y, z }, hatt: spec, height_kind: kind, geoid_undulation: parseNum(n) }));
        }}
      >
        <SystemSelect label={t("coords.info.system")} value={system} onChange={setSystem} />
        {(geo || system === "hatt") && <GeoFormatSelect value={fmt} onChange={setFmt} />}
        {system === "hatt" && <HattFields value={hatt} onChange={setHatt} fmt={fmt} withCoefficients={false} />}
        {isUnverifiedDefinition(system) && <Note tone="info">{t("coords.unverified")}</Note>}
        <div className="space-y-1.5">
          <Label htmlFor="coords-info-point">{t("coords.info.point")}</Label>
          <Input id="coords-info-point" list={system === "egsa87" ? "coords-info-pts" : undefined} value={text} onChange={(e) => setText(e.target.value)} className={cn("tabular", text.trim() && !point && "border-danger")} placeholder={geo ? "37°58'45.6\" 23°43'39.0\"" : "476000.000 4205000.000"} data-testid="coords-info-point" />
          <datalist id="coords-info-pts">
            {[...points.keys()].slice(0, 2000).map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="space-y-1.5">
            <Label htmlFor="coords-info-h">{t("coords.info.height")}</Label>
            <Input id="coords-info-h" value={height} onChange={(e) => setHeight(e.target.value)} inputMode="decimal" className="tabular" placeholder={projectPoint?.z !== null && projectPoint?.z !== undefined ? projectPoint.z.toFixed(3) : "—"} />
          </div>
          <div className="space-y-1.5">
            <Label>{t("coords.heights")}</Label>
            <Select<HeightKind>
              value={kind}
              onValueChange={setKind}
              aria-label={t("coords.heights")}
              options={[
                { value: "orthometric", label: t("coords.orthometric") },
                { value: "ellipsoidal", label: t("coords.ellipsoidal") },
              ]}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="coords-info-n">N (m)</Label>
            <Input id="coords-info-n" value={n} onChange={(e) => setN(e.target.value)} inputMode="decimal" className="tabular" disabled={kind === "ellipsoidal"} />
          </div>
        </div>
        <Button type="submit" disabled={!ready || r.busy} data-testid="coords-info-compute">
          {t("coords.info.compute")} <ArrowRight />
        </Button>
      </form>
      <ResultBox error={r.error} testId="coords-info-result">
        {r.result && <InfoResult r={r.result} fmt={fmt} />}
      </ResultBox>
    </div>
  );
}
