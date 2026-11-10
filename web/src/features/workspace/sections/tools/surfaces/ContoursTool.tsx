// "Επιφάνεια & ισοϋψείς": build the TIN and its contours, show them on the map, DXF/CSV.
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { type ContoursRequest, type ContoursResult, surfacesApi } from "@/lib/surfacesApi";
import { parseNum } from "@/lib/utils";
import { setContourOverlay, setContourVisible, useContourOverlay } from "../../../map/contoursOverlay";
import { useWorkspace } from "../../../useWorkspace";
import { KV, NumberField, ResultBox, useOverlay, useRunner } from "../shared";
import { boundaryPolygons, DownloadButtons, IssueList, SurfaceSourcePanel, SurfaceStatsView, useSurfaceExport, useSurfaceSource } from "./common";

export function ContoursTool() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const src = useSurfaceSource();
  const [step, setStep] = useState("1");
  const [base, setBase] = useState("0");
  const [indexEvery, setIndexEvery] = useState("5");
  const [withTin, setWithTin] = useState(false);
  const r = useRunner<ContoursResult>();
  const [used, setUsed] = useState<ContoursRequest | null>(null);
  const overlay = useContourOverlay();
  const exp = useSurfaceExport();
  useOverlay([], [], boundaryPolygons(src));

  const interval = parseNum(step);
  const baseZ = parseNum(base) ?? 0;
  const every = parseNum(indexEvery);
  const valid = src.problem === null && interval !== null && interval > 0 && every !== null && every >= 0 && Number.isInteger(every);
  const request = (): ContoursRequest => ({ surface: src.spec, interval: interval!, base: baseZ, index_every: every! });
  const onMap = overlay.projectId === ws.projectId && overlay.lines.length > 0;

  return (
    <div className="space-y-4">
      <SurfaceSourcePanel src={src} />
      <div className="grid gap-6 xl:grid-cols-[1fr_1.2fr]">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!valid) return;
            const req = request();
            setUsed(req);
            void r.run(() => surfacesApi.contours(req)).then((res) => {
              if (!res) return;
              setContourOverlay(ws.projectId, res.lines.map((l) => ({ z: l.z, index: l.index, points: l.points })));
              if (res.lines.length > 0) ws.revealMap(); // contours are only visible on the map
            });
          }}
        >
          <div className="grid grid-cols-3 gap-3">
            <NumberField label={t("surfaces.interval")} suffix="m" value={step} onChange={setStep} testId="surf-interval" />
            <NumberField label={t("surfaces.base")} suffix="m" value={base} onChange={setBase} />
            <NumberField label={t("surfaces.indexEvery")} value={indexEvery} onChange={setIndexEvery} />
          </div>
          <p className="text-xs text-muted">{t("surfaces.indexHint")} · {t("surfaces.noSmoothing")}</p>
          {src.problem && <p className="text-xs text-danger">{src.problem}</p>}
          <Button type="submit" disabled={!valid || r.busy} data-testid="surf-contours-run">
            {t("tools.compute")} <ArrowRight />
          </Button>
        </form>
        <ResultBox error={r.error} testId="surf-contours-result">
          {r.result && used && (
            <div className="space-y-4">
              <SurfaceStatsView s={r.result.surface} />
              <KV
                items={[
                  { k: t("surfaces.levels"), v: r.result.levels.length },
                  { k: t("surfaces.lines"), v: r.result.lines.length, strong: true },
                  { k: t("surfaces.indexLines"), v: r.result.lines.filter((l) => l.index).length },
                ]}
              />
              <IssueList issues={r.result.issues} />
              {onMap && (
                <label className="flex items-center gap-2 text-sm">
                  <Switch checked={overlay.visible} onCheckedChange={(v) => {
                      setContourVisible(v);
                      if (v) ws.revealMap();
                    }} data-testid="surf-contours-map" />
                  {t("surfaces.showOnMap")}
                </label>
              )}
              <label className="flex items-center gap-2 text-sm">
                <Checkbox checked={withTin} onCheckedChange={(v) => setWithTin(v === true)} />
                {t("surfaces.includeTin")}
              </label>
              <DownloadButtons
                busy={exp.busy}
                onDxf={() => void exp.download({ format: "dxf", content: "contours", contours: used, include_tin: withTin })}
                onCsv={() => void exp.download({ format: "csv", content: "contours", contours: used })}
              />
            </div>
          )}
        </ResultBox>
      </div>
    </div>
  );
}
