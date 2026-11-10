// "Υψόμετρα σημείων": ground height at given points (e.g. building corners) from the TIN.
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { type HeightsRequest, type HeightsResult, surfacesApi } from "@/lib/surfacesApi";
import { cn, fmtNum } from "@/lib/utils";
import { parsePointList, PointListField, ResultBox, useOverlay, useProjectPoints, useRunner } from "../shared";
import { boundaryPolygons, DownloadButtons, IssueList, SurfaceSourcePanel, useSurfaceExport, useSurfaceSource } from "./common";

export function HeightsTool() {
  const { t } = useTranslation();
  const src = useSurfaceSource();
  const named = useProjectPoints();
  const [text, setText] = useState("");
  const r = useRunner<HeightsResult>();
  const [used, setUsed] = useState<HeightsRequest | null>(null);
  const exp = useSurfaceExport();
  const { pts, bad } = parsePointList(text, named);
  useOverlay(
    pts.map((p) => ({ x: p.x, y: p.y, label: p.name ?? undefined, role: "input" as const })),
    [],
    boundaryPolygons(src),
  );
  const ready = src.problem === null && pts.length > 0 && bad.length === 0;

  return (
    <div className="space-y-4">
      <SurfaceSourcePanel src={src} />
      <div className="grid gap-6 xl:grid-cols-[1fr_1.2fr]">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!ready) return;
            const req: HeightsRequest = { surface: src.spec, points: pts.map((p) => ({ name: p.name ?? null, x: p.x, y: p.y })) };
            setUsed(req);
            void r.run(() => surfacesApi.heights(req));
          }}
        >
          <PointListField label={t("surfaces.heightsPoints")} value={text} onChange={setText} hint={t("surfaces.heightsHint")} testId="surf-heights-points" />
          {bad.length > 0 && <p className="text-xs text-danger">{t("surfaces.badLines", { lines: bad.slice(0, 5).join(", ") })}</p>}
          {src.problem && <p className="text-xs text-danger">{src.problem}</p>}
          <Button type="submit" disabled={!ready || r.busy} data-testid="surf-heights-run">
            {t("tools.compute")} <ArrowRight />
          </Button>
        </form>
        <ResultBox error={r.error} testId="surf-heights-result">
          {r.result && used && (
            <div className="space-y-3">
              <table className="w-full text-xs tabular">
                <thead>
                  <tr className="border-b text-muted">
                    <th className="py-1 text-left font-medium">{t("tools.point")}</th>
                    <th className="py-1 text-right font-medium">X</th>
                    <th className="py-1 text-right font-medium">Y</th>
                    <th className="py-1 text-right font-medium">{t("surfaces.zGround")}</th>
                  </tr>
                </thead>
                <tbody>
                  {r.result.rows.map((row, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-1">{row.name ?? i + 1}</td>
                      <td className="py-1 text-right">{fmtNum(row.x, 3)}</td>
                      <td className="py-1 text-right">{fmtNum(row.y, 3)}</td>
                      <td className={cn("py-1 text-right", row.inside ? "font-semibold" : "text-warning")}>{row.inside ? fmtNum(row.z, 3) : t("surfaces.outside")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <IssueList issues={[...r.result.surface.issues, ...r.result.issues]} />
              <DownloadButtons
                busy={exp.busy}
                onDxf={() => void exp.download({ format: "dxf", content: "heights", heights: used })}
                onCsv={() => void exp.download({ format: "csv", content: "heights", heights: used })}
              />
            </div>
          )}
        </ResultBox>
      </div>
    </div>
  );
}
