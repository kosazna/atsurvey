import { RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { defaultSettings, type AdjustmentMethod, type AdjustmentSettings, type ComputeSettings, type DisplayAngleUnit, type ElevationMode, type ScaleMode, type TolerancePreset, type Tolerances } from "@/lib/types";
import { api } from "@/lib/api";
import { parseNum } from "@/lib/utils";
import { useWorkspace } from "../useWorkspace";

function NumField({ id, label, value, onChange, step = "any" }: { id: string; label: string; value: number; onChange: (v: number) => void; step?: string }) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        inputMode="decimal"
        step={step}
        className="tabular"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          const n = parseNum(text);
          if (n === null) setText(String(value));
          else onChange(n);
        }}
      />
    </div>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div>
        <div className="text-sm">{label}</div>
        {hint && <div className="text-xs text-muted">{hint}</div>}
      </div>
      {children}
    </div>
  );
}

export function SettingsDialog() {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const open = ws.dialog === "settings";
  const [s, setS] = useState<ComputeSettings>(ws.data.settings);
  const [unit, setUnit] = useState<DisplayAngleUnit>(ws.data.meta.angle_unit);

  useEffect(() => {
    if (open) {
      setS(ws.data.settings);
      setUnit(ws.data.meta.angle_unit);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const red = s.reduction;
  const setRed = (patch: Partial<ComputeSettings["reduction"]>) => setS({ ...s, reduction: { ...red, ...patch } });
  const setTol = (k: keyof Tolerances, v: number) =>
    setS({ ...s, tolerances: { ...s.tolerances, [k]: v, preset: null } });
  const [presets, setPresets] = useState<TolerancePreset[]>([]);
  useEffect(() => {
    let alive = true;
    api
      .tolerancePresets()
      .then((p) => alive && setPresets(p))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  const applyPreset = (id: string) => {
    const preset = presets.find((p) => p.id === id);
    if (!preset) {
      setS({ ...s, tolerances: { ...s.tolerances, preset: null } });
      return;
    }
    const p = preset.tolerances;
    setS({
      ...s,
      tolerances: {
        ...s.tolerances,
        angular_base_cc: p.angular_base_cc,
        angular_per_sqrt_n_cc: p.angular_per_sqrt_n_cc,
        linear_base_m: p.linear_base_m,
        linear_per_sqrt_km_m: p.linear_per_sqrt_km_m,
        linear_per_sqrt_m_m: p.linear_per_sqrt_m_m,
        min_relative_precision: p.min_relative_precision,
        preset: preset.id,
      },
    });
  };
  const numericTolKeys = (Object.keys(s.tolerances) as (keyof Tolerances)[]).filter(
    (k) => typeof s.tolerances[k] === "number",
  );
  const scaleModes: ScaleMode[] = ["leg_simpson", "leg_mean", "traverse_mean", "none", "fixed"];
  const adj = s.adjustment;
  const setAdj = (patch: Partial<AdjustmentSettings>) => setS({ ...s, adjustment: { ...adj, ...patch } });
  const sigmaFields: { k: keyof AdjustmentSettings; unit: string }[] = [
    { k: "sigma_direction_cc", unit: "cc" },
    { k: "sigma_distance_mm", unit: "mm" },
    { k: "sigma_distance_ppm", unit: "ppm" },
    { k: "sigma_centering_mm", unit: "mm" },
    { k: "sigma_height_mm", unit: "mm/√km" },
    { k: "alpha_global", unit: "α" },
    { k: "alpha_w", unit: "α" },
    { k: "max_iterations", unit: "" },
  ];

  return (
    <Dialog open={open} onOpenChange={(o) => !o && ws.setDialog(null)}>
      <DialogContent wide>
        <DialogHeader>
          <DialogTitle>{t("set.title")}</DialogTitle>
        </DialogHeader>
        <Tabs defaultValue="general" className="flex min-h-0 flex-1 flex-col">
          <div className="px-5 pt-3">
            <TabsList>
              <TabsTrigger value="general">{t("set.general")}</TabsTrigger>
              <TabsTrigger value="reductions">{t("set.reductions")}</TabsTrigger>
              <TabsTrigger value="tolerances">{t("set.tolerances")}</TabsTrigger>
              <TabsTrigger value="adjustment" data-testid="tab-adjustment">{t("set.adjustment")}</TabsTrigger>
            </TabsList>
          </div>
          <DialogBody>
            <TabsContent value="general" className="space-y-1 divide-y">
              <Row label={t("projects.angleUnit")}>
                <Select<DisplayAngleUnit>
                  className="w-48"
                  value={unit}
                  onValueChange={setUnit}
                  options={[
                    { value: "gon", label: t("units.gon") },
                    { value: "deg", label: t("units.deg") },
                    { value: "dms", label: t("units.dms") },
                  ]}
                />
              </Row>
              <Row label={t("set.computeDetail")}>
                <Switch checked={s.compute_detail} onCheckedChange={(v) => setS({ ...s, compute_detail: v })} />
              </Row>
            </TabsContent>
            <TabsContent value="reductions" className="space-y-4">
              <div className="space-y-1.5">
                <Label>{t("set.scaleMode")}</Label>
                <Select<ScaleMode>
                  value={red.scale_mode}
                  onValueChange={(v) => setRed({ scale_mode: v })}
                  options={scaleModes.map((m) => ({ value: m, label: t(`set.scale.${m}`), hint: t(`set.scale.${m}Hint`) }))}
                />
              </div>
              {red.scale_mode === "fixed" && <NumField id="fixed-k" label={t("set.fixedScale")} value={red.fixed_scale} onChange={(v) => setRed({ fixed_scale: v })} />}
              <div className="divide-y rounded-lg border px-3">
                <Row label={t("set.elevationReduction")}>
                  <Switch checked={red.elevation_reduction} onCheckedChange={(v) => setRed({ elevation_reduction: v })} />
                </Row>
                {red.elevation_reduction && (
                  <div className="grid gap-3 py-3 sm:grid-cols-3">
                    <div className="space-y-1.5">
                      <Label>{t("set.elevationMode")}</Label>
                      <Select<ElevationMode>
                        value={red.elevation_mode}
                        onValueChange={(v) => setRed({ elevation_mode: v })}
                        options={[
                          { value: "leg", label: t("set.elevLeg") },
                          { value: "traverse", label: t("set.elevTraverse") },
                        ]}
                      />
                    </div>
                    <NumField id="geoid" label={t("set.geoid")} value={red.geoid_undulation} onChange={(v) => setRed({ geoid_undulation: v })} />
                    <NumField id="defh" label={t("set.defaultElevation")} value={red.default_elevation} onChange={(v) => setRed({ default_elevation: v })} />
                  </div>
                )}
                <Row label={t("set.curvature")}>
                  <Switch checked={red.curvature_refraction} onCheckedChange={(v) => setRed({ curvature_refraction: v })} />
                </Row>
                {red.curvature_refraction && (
                  <div className="grid gap-3 py-3 sm:grid-cols-3">
                    <NumField id="kappa" label={t("set.refraction")} value={red.refraction_coefficient} onChange={(v) => setRed({ refraction_coefficient: v })} />
                  </div>
                )}
              </div>
            </TabsContent>
            <TabsContent value="adjustment" className="space-y-4">
              <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label={t("set.adjMethod")}>
                {(["bowditch", "least_squares"] as AdjustmentMethod[]).map((m) => (
                  <button
                    key={m}
                    type="button"
                    role="radio"
                    aria-checked={adj.method === m}
                    data-testid={`method-${m}`}
                    onClick={() => setAdj({ method: m })}
                    className={
                      adj.method === m
                        ? "cursor-pointer rounded-lg border border-accent bg-accent-subtle p-3 text-left ring-1 ring-accent"
                        : "cursor-pointer rounded-lg border p-3 text-left hover:bg-surface-sunken"
                    }
                  >
                    <div className="text-sm font-medium">{t(`set.method.${m}`)}</div>
                    <div className="mt-0.5 text-xs text-muted">{t(`set.method.${m}Hint`)}</div>
                  </button>
                ))}
              </div>
              {adj.method === "least_squares" && (
                <>
                  <p className="text-xs text-muted">{t("set.sigmaHint")}</p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {sigmaFields.map(({ k, unit: u }) => (
                      <NumField key={k} id={`adj-${k}`} label={`${t(`set.adj.${k}`)}${u ? ` (${u})` : ""}`} value={adj[k] as number} onChange={(v) => setAdj({ [k]: v } as Partial<AdjustmentSettings>)} />
                    ))}
                  </div>
                </>
              )}
            </TabsContent>
            <TabsContent value="tolerances" className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="tol-preset">{t("set.tolPreset")}</Label>
                <Select<string>
                  value={s.tolerances.preset ?? "custom"}
                  onValueChange={applyPreset}
                  options={[
                    { value: "custom", label: t("set.tolCustom") },
                    ...presets.map((p) => ({ value: p.id, label: i18n.language === "en" ? p.label_en : p.label_el })),
                  ]}
                />
              </div>
              {!s.tolerances.preset && (
                <p className="rounded-lg bg-warning-subtle px-3 py-2 text-xs text-warning">{t("set.tolHint")}</p>
              )}
              <div className="grid gap-3 sm:grid-cols-2">
                {numericTolKeys.map((k) => (
                  <NumField key={k} id={`tol-${k}`} label={t(`set.tol.${k}`)} value={s.tolerances[k] as number} onChange={(v) => setTol(k, v)} />
                ))}
              </div>
            </TabsContent>
          </DialogBody>
        </Tabs>
        <DialogFooter>
          <Button
            variant="ghost"
            className="mr-auto"
            onClick={() => {
              setS(defaultSettings());
            }}
          >
            <RotateCcw /> {t("set.reset")}
          </Button>
          <Button variant="ghost" onClick={() => ws.setDialog(null)}>
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => {
              ws.update({ settings: s, meta: { angle_unit: unit } });
              ws.setDialog(null);
            }}
            data-testid="btn-save-settings"
          >
            {t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
