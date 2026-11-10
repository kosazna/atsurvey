// Pre-analysis (network design): plan observations from the project or by hand, set the
// instrument specification and compute the precision and reliability of the planned network.
import { ArrowRight, FolderInput } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  analysis,
  buildRequest,
  derivePlan,
  type DirectionUnit,
  fromCc,
  type InstrumentSpec,
  type PlannedPoint,
  type PlannedRow,
  type PreanalysisRequest,
  PREANALYSIS_LIMITS,
  type PreanalysisResult,
  toCc,
} from "@/lib/analysisApi";
import { cn, parseNum, uid } from "@/lib/utils";
import { useWorkspace } from "../../../useWorkspace";
import { NumberField, ResultBox, useProjectPoints, useRunner } from "../shared";
import { EllipsePlot, type PlotLine } from "./EllipsePlot";
import { PlanTable } from "./PlanTable";
import { PreanalysisResults } from "./PreanalysisResults";

type SpecText = Record<keyof InstrumentSpec, string>;

const SPEC_FIELDS: { k: keyof InstrumentSpec; label: string; unit?: string }[] = [
  { k: "sigma_direction_cc", label: "analysis.sDir" },
  { k: "sigma_distance_mm", label: "analysis.sDistA", unit: "mm" },
  { k: "sigma_distance_ppm", label: "analysis.sDistB", unit: "ppm" },
  { k: "sigma_centering_instrument_mm", label: "analysis.sCi", unit: "mm" },
  { k: "sigma_centering_target_mm", label: "analysis.sCt", unit: "mm" },
  { k: "sigma_height_mm", label: "analysis.sH", unit: "mm/√km" },
];

interface Snapshot {
  req: PreanalysisRequest;
  points: PlannedPoint[];
}

export function PreanalysisTool() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const projectPoints = useProjectPoints();
  const adj = ws.data.settings.adjustment;
  const [includeHeights, setIncludeHeights] = useState(false);
  const [unit, setUnit] = useState<DirectionUnit>("cc");
  const derive = (heights: boolean) =>
    derivePlan({ control_points: ws.data.control_points, setups: ws.data.setups, resultPoints: ws.result?.points ?? [] }, heights, uid);
  const [plan, setPlan] = useState(() => derive(false));
  const projectSpec = (): SpecText => ({
    sigma_direction_cc: String(fromCc(adj.sigma_direction_cc, unit)),
    sigma_distance_mm: String(adj.sigma_distance_mm),
    sigma_distance_ppm: String(adj.sigma_distance_ppm),
    sigma_centering_instrument_mm: String(adj.sigma_centering_mm),
    sigma_centering_target_mm: String(adj.sigma_centering_mm),
    sigma_height_mm: String(adj.sigma_height_mm),
  });
  const [spec, setSpec] = useState<SpecText>(projectSpec);
  const r = useRunner<PreanalysisResult>();
  const [shown, setShown] = useState<Snapshot | null>(null);

  const parsedSpec = useMemo((): InstrumentSpec | null => {
    const out: Partial<InstrumentSpec> = {};
    for (const { k } of SPEC_FIELDS) {
      const v = parseNum(spec[k]);
      if (v === null || v < 0) return null;
      out[k] = k === "sigma_direction_cc" ? toCc(v, unit) : v;
    }
    return out as InstrumentSpec;
  }, [spec, unit]);

  const setRows = (rows: PlannedRow[]) => setPlan((p) => ({ ...p, rows }));
  const ensurePoint = (name: string): boolean => {
    if (plan.points.some((p) => p.name === name)) return true;
    const p = projectPoints.get(name);
    if (!p) return false;
    const fixed = ws.data.control_points.some((c) => c.name === name);
    setPlan((cur) => ({ ...cur, points: [...cur.points, { name, x: p.x, y: p.y, fixed }] }));
    return true;
  };

  const req = parsedSpec ? buildRequest(plan.points, plan.rows, parsedSpec) : null;
  const tooLarge = !!req && (req.points.length > PREANALYSIS_LIMITS.points || req.observations.length > PREANALYSIS_LIMITS.observations);
  const run = () => {
    if (!req || tooLarge) return;
    const snapshot = { req, points: req.points };
    void r.run(() => analysis.preanalysis(req)).then((res) => setShown(res ? snapshot : null));
  };

  const result = shown ? r.result : null;
  const plotPoints = result && shown ? shown.points : (req?.points ?? []);
  const lines: PlotLine[] = result && shown
    ? shown.req.observations.map((o, i) => ({ a: o.station, b: o.target, status: result.observations[i]?.status }))
    : (req?.observations ?? []).map((o) => ({ a: o.station, b: o.target }));

  return (
    <div className="space-y-4">
      <div className="grid gap-6 xl:grid-cols-[1.1fr_1fr]">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <Button type="button" variant="outline" size="sm" onClick={() => setPlan(derive(includeHeights))} title={t("analysis.fromProjectHint")} data-testid="plan-from-project">
              <FolderInput /> {t("analysis.fromProject")}
            </Button>
            <label className="flex items-center gap-1.5 text-xs">
              <Checkbox checked={includeHeights} onCheckedChange={(v) => setIncludeHeights(v === true)} />
              {t("analysis.includeHeights")}
            </label>
          </div>
          {plan.rows.length === 0 && <p className="text-xs text-muted">{t("analysis.emptyPlan")}</p>}
          <PlanTable rows={plan.rows} onChange={setRows} pointNames={[...new Set([...plan.points.map((p) => p.name), ...projectPoints.keys()])]} ensurePoint={ensurePoint} />
        </div>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            run();
          }}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-medium">{t("analysis.instrument")}</div>
            <Button type="button" variant="ghost" size="sm" onClick={() => setSpec(projectSpec())}>
              {t("analysis.useProjectSigma")}
            </Button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="spec-dir">{t("analysis.sDir")}</Label>
              <div className="flex gap-1">
                <Input
                  id="spec-dir"
                  value={spec.sigma_direction_cc}
                  onChange={(e) => setSpec({ ...spec, sigma_direction_cc: e.target.value })}
                  inputMode="decimal"
                  className={cn("tabular", parseNum(spec.sigma_direction_cc) === null && "border-danger")}
                  data-testid="spec-dir"
                />
                <Select<DirectionUnit>
                  className="w-24"
                  aria-label={t("analysis.sDir")}
                  value={unit}
                  onValueChange={(u) => {
                    const v = parseNum(spec.sigma_direction_cc);
                    if (v !== null) setSpec({ ...spec, sigma_direction_cc: String(+fromCc(toCc(v, unit), u).toFixed(4)) });
                    setUnit(u);
                  }}
                  options={[
                    { value: "cc", label: "cc" },
                    { value: "mgon", label: "mgon" },
                  ]}
                />
              </div>
            </div>
            {SPEC_FIELDS.slice(1).map((f) => (
              <NumberField key={f.k} label={t(f.label)} suffix={f.unit} value={spec[f.k]} onChange={(v) => setSpec({ ...spec, [f.k]: v })} />
            ))}
          </div>
          <Button type="submit" disabled={!req || !req.observations.length || tooLarge || r.busy} data-testid="btn-preanalysis">
            {t("analysis.compute")} <ArrowRight />
          </Button>
          {tooLarge && <p className="text-xs text-danger">{t("analysis.tooLarge", { points: PREANALYSIS_LIMITS.points, obs: PREANALYSIS_LIMITS.observations })}</p>}
        </form>
      </div>
      <EllipsePlot points={plotPoints} lines={lines} precision={result?.points ?? []} />
      <ResultBox error={r.error}>{result && <PreanalysisResults result={result} unit={unit} />}</ResultBox>
    </div>
  );
}
