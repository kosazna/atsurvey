// "Όγκοι": cut/fill of the surface against a level or a second surface (exact prisms).
import { ArrowRight } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { formatArea } from "@/lib/geometry";
import {
  type LevelVolumeRequest,
  parseCodes,
  type SurfacePoint,
  type SurfaceVolumeRequest,
  surfacesApi,
  type VolumeResult,
} from "@/lib/surfacesApi";
import { parseNum } from "@/lib/utils";
import { KV, NumberField, parsePointList, ResultBox, useOverlay, useProjectPoints, useRunner } from "../shared";
import { boundaryPolygons, DownloadButtons, IssueList, SurfaceSourcePanel, useSourcePoints, useSurfaceExport, useSurfaceSource } from "./common";

type Mode = "level" | "surface";
type Used = { level: LevelVolumeRequest } | { surfaces: SurfaceVolumeRequest };

function fmtVolume(v: number): string {
  if (!Number.isFinite(v)) return "—";
  const [int, frac] = Math.abs(v).toFixed(2).split(".");
  return `${v < 0 ? "−" : ""}${int.replace(/\B(?=(\d{3})+(?!\d))/g, " ")}.${frac} m³`;
}

export function VolumesTool() {
  const { t } = useTranslation();
  const src = useSurfaceSource();
  const all = useSourcePoints();
  const named = useProjectPoints();
  const [mode, setMode] = useState<Mode>("level");
  const [level, setLevel] = useState("");
  const [designCodes, setDesignCodes] = useState("");
  const [designText, setDesignText] = useState("");
  const r = useRunner<VolumeResult>();
  const [used, setUsed] = useState<Used | null>(null);
  const exp = useSurfaceExport();
  useOverlay([], [], boundaryPolygons(src));

  // second surface: project points with the given codes + pasted points (with a height)
  const design = useMemo(() => {
    const codes = new Set(parseCodes(designCodes));
    const coded = codes.size ? all.filter((p) => codes.has((p.code ?? "").toUpperCase())) : [];
    const list = parsePointList(designText, named);
    const points: SurfacePoint[] = [
      ...coded.map((p) => ({ name: p.name, x: p.x, y: p.y, z: p.z })),
      ...list.pts.map((p) => ({ name: p.name ?? null, x: p.x, y: p.y, z: p.z ?? null })),
    ];
    const codedNames = new Set(coded.map((p) => p.name));
    return { points, codedNames, bad: list.bad, withZ: points.filter((p) => p.z !== null && p.z !== undefined).length };
  }, [all, named, designCodes, designText]);

  const levelZ = parseNum(level);
  let problem = src.problem;
  if (!problem && mode === "surface" && design.withZ < 3) problem = t("surfaces.designNeed");
  if (!problem && mode === "surface" && design.bad.length) problem = t("surfaces.badLines", { lines: design.bad.slice(0, 5).join(", ") });
  const ready = problem === null && (mode === "surface" || levelZ !== null);

  const run = () => {
    if (mode === "level") {
      const req: LevelVolumeRequest = { surface: src.spec, level: levelZ! };
      setUsed({ level: req });
      void r.run(() => surfacesApi.volumeLevel(req));
      return;
    }
    const existingPoints = src.spec.points.filter((p) => !design.codedNames.has(p.name ?? ""));
    const req: SurfaceVolumeRequest = {
      existing: { ...src.spec, points: existingPoints, boundary: null },
      design: { points: design.points },
      boundary: src.spec.boundary ?? null,
    };
    setUsed({ surfaces: req });
    void r.run(() => surfacesApi.volumeSurfaces(req));
  };

  return (
    <div className="space-y-4">
      <SurfaceSourcePanel src={src} />
      <div className="grid gap-6 xl:grid-cols-[1fr_1.2fr]">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) run();
          }}
        >
          <div className="space-y-1.5">
            <Label>{t("surfaces.mode")}</Label>
            <Select<Mode>
              value={mode}
              onValueChange={setMode}
              aria-label={t("surfaces.mode")}
              options={[
                { value: "level", label: t("surfaces.modeLevel") },
                { value: "surface", label: t("surfaces.modeSurface") },
              ]}
            />
          </div>
          {mode === "level" ? (
            <NumberField label={t("surfaces.level")} suffix="m" value={level} onChange={setLevel} testId="surf-level" />
          ) : (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="surf-design-codes">{t("surfaces.designCodes")}</Label>
                <Input id="surf-design-codes" value={designCodes} onChange={(e) => setDesignCodes(e.target.value)} placeholder={t("surfaces.codesHint")} />
                <p className="text-xs text-muted">{t("surfaces.designCodesHint")}</p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="surf-design-list">{t("surfaces.designList")}</Label>
                <Textarea id="surf-design-list" rows={4} className="font-mono text-xs" value={designText} onChange={(e) => setDesignText(e.target.value)} placeholder={t("surfaces.designListHint")} />
              </div>
            </>
          )}
          <p className="text-xs text-muted">{t("surfaces.volumeSign")}</p>
          {problem && <p className="text-xs text-danger">{problem}</p>}
          <Button type="submit" disabled={!ready || r.busy} data-testid="surf-volume-run">
            {t("tools.compute")} <ArrowRight />
          </Button>
        </form>
        <ResultBox error={r.error} testId="surf-volume-result">
          {r.result && used && (
            <div className="space-y-3">
              <KV
                items={[
                  { k: t("surfaces.cut"), v: fmtVolume(r.result.cut), strong: true },
                  { k: t("surfaces.fill"), v: fmtVolume(r.result.fill), strong: true },
                  { k: t("surfaces.net"), v: fmtVolume(r.result.net) },
                  { k: t("surfaces.cutArea"), v: formatArea(r.result.cut_area) },
                  { k: t("surfaces.fillArea"), v: formatArea(r.result.fill_area) },
                  { k: t("surfaces.area"), v: formatArea(r.result.area) },
                  { k: t("surfaces.method"), v: t("surfaces.methodPrism") },
                ]}
              />
              <IssueList issues={[...r.result.surfaces.flatMap((s) => s.issues), ...r.result.issues]} />
              <DownloadButtons
                busy={exp.busy}
                onCsv={() =>
                  void exp.download(
                    "level" in used
                      ? { format: "csv", content: "volume", volume_level: used.level }
                      : { format: "csv", content: "volume", volume_surfaces: used.surfaces },
                  )
                }
              />
            </div>
          )}
        </ResultBox>
      </div>
    </div>
  );
}
