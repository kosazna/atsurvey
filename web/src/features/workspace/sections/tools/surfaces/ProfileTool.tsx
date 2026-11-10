// "Μηκοτομή & διατομές": long profile along an alignment and cross-sections at an interval.
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { type ProfileRequest, type ProfileResult, surfacesApi } from "@/lib/surfacesApi";
import { fmtNum, parseNum } from "@/lib/utils";
import { KV, NumberField, parsePointList, PointListField, ResultBox, useOverlay, useProjectPoints, useRunner } from "../shared";
import { boundaryPolygons, DownloadButtons, IssueList, SurfaceSourcePanel, useSurfaceExport, useSurfaceSource } from "./common";
import { ProfileChart } from "./ProfileChart";

/** Plan segments of the cross-sections (for the map), from their azimuth and half width. */
function sectionLines(res: ProfileResult, halfWidth: number): [number, number][][] {
  return res.sections.map((cs) => {
    const rx = Math.cos(cs.azimuth);
    const ry = -Math.sin(cs.azimuth);
    return [
      [cs.x - halfWidth * rx, cs.y - halfWidth * ry],
      [cs.x + halfWidth * rx, cs.y + halfWidth * ry],
    ];
  });
}

export function ProfileTool() {
  const { t } = useTranslation();
  const src = useSurfaceSource();
  const named = useProjectPoints();
  const [text, setText] = useState("");
  const [intervalText, setIntervalText] = useState("");
  const [halfWidth, setHalfWidth] = useState("10");
  const [sectionIdx, setSectionIdx] = useState("0");
  const r = useRunner<ProfileResult>();
  const [used, setUsed] = useState<ProfileRequest | null>(null);
  const exp = useSurfaceExport();
  const { pts, bad } = parsePointList(text, named);
  const line = pts.map((p) => [p.x, p.y] as [number, number]);
  const hw = parseNum(halfWidth);
  const every = parseNum(intervalText);
  useOverlay(
    pts.map((p) => ({ x: p.x, y: p.y, label: p.name ?? undefined, role: "input" as const })),
    [...(line.length >= 2 ? [line] : []), ...(r.result && used ? sectionLines(r.result, used.half_width ?? 10) : [])],
    boundaryPolygons(src),
  );
  const ready = src.problem === null && pts.length >= 2 && bad.length === 0 && hw !== null && hw > 0 && (every === null || every > 0);

  const res = r.result;
  const zs = res?.stations.map((s) => s.z) ?? [];
  const section = res?.sections[Number(sectionIdx)] ?? null;

  return (
    <div className="space-y-4">
      <SurfaceSourcePanel src={src} />
      <div className="grid gap-6 xl:grid-cols-[1fr_1.4fr]">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!ready) return;
            const req: ProfileRequest = { surface: src.spec, alignment: pts.map((p) => ({ x: p.x, y: p.y })), section_interval: every, half_width: hw! };
            setUsed(req);
            setSectionIdx("0");
            void r.run(() => surfacesApi.profile(req));
          }}
        >
          <PointListField label={t("surfaces.alignment")} value={text} onChange={setText} hint={t("surfaces.alignmentHint")} testId="surf-alignment" />
          {bad.length > 0 && <p className="text-xs text-danger">{t("surfaces.badLines", { lines: bad.slice(0, 5).join(", ") })}</p>}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <NumberField label={t("surfaces.sectionInterval")} suffix="m" value={intervalText} onChange={setIntervalText} />
              <p className="mt-1 text-xs text-muted">{t("surfaces.sectionHint")}</p>
            </div>
            <NumberField label={t("surfaces.halfWidth")} suffix="m" value={halfWidth} onChange={setHalfWidth} />
          </div>
          {src.problem && <p className="text-xs text-danger">{src.problem}</p>}
          <Button type="submit" disabled={!ready || r.busy} data-testid="surf-profile-run">
            {t("tools.compute")} <ArrowRight />
          </Button>
        </form>
        <ResultBox error={r.error} testId="surf-profile-result">
          {res && used && (
            <div className="space-y-4">
              <KV
                items={[
                  { k: t("surfaces.length"), v: `${fmtNum(res.length, 3)} m`, strong: true },
                  { k: t("surfaces.stations"), v: res.stations.length },
                  ...(zs.length ? [{ k: t("surfaces.zRange"), v: `${fmtNum(Math.min(...zs), 3)} – ${fmtNum(Math.max(...zs), 3)} m` }] : []),
                ]}
              />
              {res.stations.length >= 2 ? (
                <ProfileChart stations={res.stations} x0={0} x1={res.length} title={`${t("surfaces.longProfile")} (${t("surfaces.chainage")} m)`} testId="surf-profile-chart" />
              ) : (
                <p className="text-sm text-warning">{t("surfaces.noProfile")}</p>
              )}
              {res.sections.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Label className="shrink-0">{t("surfaces.section")}</Label>
                    <Select
                      value={sectionIdx}
                      onValueChange={setSectionIdx}
                      aria-label={t("surfaces.section")}
                      options={res.sections.map((cs, i) => ({ value: String(i), label: `${t("surfaces.chainage")} ${fmtNum(cs.chainage, 2)}` }))}
                    />
                  </div>
                  {section && section.stations.length >= 2 && (
                    <ProfileChart
                      stations={section.stations}
                      x0={-(used.half_width ?? 10)}
                      x1={used.half_width ?? 10}
                      centre
                      title={`${t("surfaces.section")} ${t("surfaces.chainage")} ${fmtNum(section.chainage, 2)} · Z ${fmtNum(section.z, 3)} (${t("surfaces.offset")} m)`}
                    />
                  )}
                </div>
              )}
              <IssueList issues={[...res.surface.issues, ...res.issues]} />
              <DownloadButtons
                busy={exp.busy}
                onDxf={() => void exp.download({ format: "dxf", content: "profile", profile: used })}
                onCsv={() => void exp.download({ format: "csv", content: "profile", profile: used })}
              />
            </div>
          )}
        </ResultBox>
      </div>
    </div>
  );
}
