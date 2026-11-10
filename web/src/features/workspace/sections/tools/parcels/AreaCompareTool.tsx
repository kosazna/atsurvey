// "Εμβαδόν & σύγκριση": parcel geometry (with optional arcs) and comparison of the surveyed area
// with the deed and the cadastral diagram against a tolerance rule the user chooses.
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { type AreaCompareResult, type AreaToleranceRule, AREA_TOLERANCE_PRESETS, type ArcSpec, CADASTRE_CAP_PERCENT, describeRule, type ParcelGeometry, parcelsApi, type ToleranceKind } from "@/lib/parcelsApi";
import { cn, fmtNum, fmtSigned, parseNum } from "@/lib/utils";
import { KV, NumberField, ResultBox, useOverlay, useRunner } from "../shared";
import { ArcEditor } from "./ArcEditor";
import { AreaText, IssueList, ParcelSketch, ParcelTables, useVertexList, VertexInput } from "./common";

interface Output {
  geo: ParcelGeometry;
  cmp: AreaCompareResult | null;
}

type RuleChoice = "none" | "custom" | string; // or a preset id

export function AreaCompareTool() {
  const { t } = useTranslation();
  const list = useVertexList("parcel-area-pick");
  const [label, setLabel] = useState("");
  const [kaek, setKaek] = useState("");
  const [arcs, setArcs] = useState<Record<string, ArcSpec>>({});
  const [deed, setDeed] = useState("");
  const [cadastre, setCadastre] = useState("");
  const [choice, setChoice] = useState<RuleChoice>("none");
  const [rule, setRule] = useState<AreaToleranceRule>({ kind: "percent", value: null, source: "" });
  const [cap, setCap] = useState(false);
  const r = useRunner<Output>();
  const vertices = list.vertices.map((v) => ({ ...v, arc: arcs[v.name] ?? null }));
  useOverlay(
    vertices.map((v) => ({ x: v.x, y: v.y, label: v.name, role: "input" as const })),
    [],
    vertices.length >= 3 ? [vertices.map((v) => [v.x, v.y] as [number, number])] : [],
  );

  const preset = AREA_TOLERANCE_PRESETS.find((p) => p.id === choice);
  const activeRule: AreaToleranceRule | null =
    choice === "none" ? null : { ...(preset ? preset.rule : rule), cap_percent: cap ? CADASTRE_CAP_PERCENT : null };

  async function compute(): Promise<Output> {
    const parcel = { label, kaek: kaek.trim() || null, vertices };
    const geo = await parcelsApi.compute(parcel);
    const deedArea = parseNum(deed);
    const cadArea = parseNum(cadastre);
    if (!geo.valid || (deedArea === null && cadArea === null)) return { geo, cmp: null };
    const cmp = await parcelsApi.compare({ parcel, deed_area: deedArea, cadastre_area: cadArea, tolerance: activeRule });
    return { geo, cmp };
  }

  const out = r.result;
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (vertices.length >= 3) void r.run(compute);
          }}
        >
          <div className="grid grid-cols-2 gap-3">
            <TextField label={t("parcels.label")} value={label} onChange={setLabel} />
            <TextField label={t("parcels.kaek")} value={kaek} onChange={setKaek} />
          </div>
          <VertexInput state={list} testId="parcel-area-list" />
          <ArcEditor vertices={list.vertices} arcs={arcs} onChange={setArcs} />
          <Button type="submit" size="sm" disabled={vertices.length < 3 || r.busy} data-testid="parcel-area-run">
            {t("parcels.compute")} <ArrowRight />
          </Button>
        </form>
        <div className="space-y-3">
          <p className="text-sm font-medium">{t("parcels.compare.title")}</p>
          <div className="grid grid-cols-2 gap-3">
            <NumberField label={t("parcels.compare.deed")} value={deed} onChange={setDeed} />
            <NumberField label={t("parcels.compare.cadastre")} value={cadastre} onChange={setCadastre} />
          </div>
          <p className="text-xs text-muted">{t("parcels.compare.cadastreHint")}</p>
          <RuleEditor choice={choice} onChoice={setChoice} rule={rule} onRule={setRule} cap={cap} onCap={setCap} />
        </div>
      </div>
      <ResultBox error={r.error} testId="parcel-area-result">
        {out && <AreaResultView out={out} />}
      </ResultBox>
    </div>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input value={value} onChange={(e) => onChange(e.target.value)} maxLength={100} />
    </div>
  );
}

function RuleEditor(props: { choice: RuleChoice; onChoice: (c: RuleChoice) => void; rule: AreaToleranceRule; onRule: (r: AreaToleranceRule) => void; cap: boolean; onCap: (v: boolean) => void }) {
  const { t } = useTranslation();
  const { choice, rule, onRule } = props;
  const num = (v: string) => parseNum(v);
  const field = (key: "value" | "a" | "b" | "u0", lbl: string) => (
    <NumberField label={lbl} value={rule[key] === null || rule[key] === undefined ? "" : String(rule[key])} onChange={(v) => onRule({ ...rule, [key]: num(v) })} />
  );
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label>{t("parcels.compare.rule")}</Label>
        <Select<string>
          value={choice}
          onValueChange={props.onChoice}
          options={[
            { value: "none", label: t("parcels.compare.none") },
            ...AREA_TOLERANCE_PRESETS.map((p) => ({ value: p.id, label: p.label, hint: p.to_be_confirmed ? t("parcels.compare.toConfirm") : undefined })),
            { value: "custom", label: t("parcels.compare.custom") },
          ]}
        />
      </div>
      {choice !== "none" && choice !== "custom" && <p className="text-xs text-warning">{t("parcels.compare.presetNote")}</p>}
      {choice === "custom" && (
        <>
          <Select<ToleranceKind>
            value={rule.kind}
            onValueChange={(kind) => onRule({ ...rule, kind })}
            options={(["fixed", "percent", "formula", "cadastre"] as const).map((k) => ({ value: k, label: t(`parcels.compare.${k === "cadastre" ? "cadastreRule" : k}`) }))}
          />
          <div className="grid grid-cols-2 gap-3">
            {(rule.kind === "fixed" || rule.kind === "percent") && field("value", t("parcels.compare.value"))}
            {rule.kind === "formula" && field("a", t("parcels.compare.a"))}
            {rule.kind === "formula" && field("b", t("parcels.compare.b"))}
            {rule.kind === "cadastre" && field("u0", t("parcels.compare.u0"))}
          </div>
          <div className="space-y-1.5">
            <Label>{t("parcels.compare.source")}</Label>
            <Input value={rule.source} onChange={(e) => onRule({ ...rule, source: e.target.value })} placeholder={t("parcels.compare.sourceHint")} maxLength={300} />
          </div>
        </>
      )}
      {choice !== "none" && (
        <label className="flex items-center gap-2 text-sm">
          <Checkbox checked={props.cap} onCheckedChange={(v) => props.onCap(v === true)} />
          {t("parcels.compare.cap")}
        </label>
      )}
    </div>
  );
}

function AreaResultView({ out }: { out: Output }) {
  const { t } = useTranslation();
  const { geo, cmp } = out;
  return (
    <div className="space-y-5">
      <IssueList issues={geo.issues} />
      {!geo.valid ? (
        <p className="text-sm text-danger">{t("parcels.invalid")}</p>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1fr_auto]">
          <KV
            items={[
              { k: t("parcels.area"), v: <AreaText m2={geo.area} />, strong: true },
              { k: t("parcels.perimeter"), v: `${fmtNum(geo.perimeter, 3)} m` },
              { k: t("parcels.orientation"), v: geo.orientation ? t(`parcels.${geo.orientation}`) : "—" },
              { k: t("parcels.centroid"), v: geo.centroid ? `${fmtNum(geo.centroid.x, 3)} · ${fmtNum(geo.centroid.y, 3)}` : "—" },
            ]}
          />
          <ParcelSketch parcels={[geo]} />
        </div>
      )}
      {cmp && <CompareTable cmp={cmp} />}
      {geo.valid && <ParcelTables geo={geo} />}
    </div>
  );
}

function CompareTable({ cmp }: { cmp: AreaCompareResult }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2" data-testid="parcel-compare">
      <p className="text-sm font-medium">{t("parcels.compare.title")}</p>
      <div className="scroll-x-visible">
        <table className="w-full min-w-[520px] text-sm tabular">
          <thead>
            <tr className="border-b text-xs text-muted">
              <th className="py-1 text-left font-medium" />
              <th className="py-1 text-right font-medium">{t("parcels.compare.reference")}</th>
              <th className="py-1 text-right font-medium">{t("parcels.compare.difference")}</th>
              <th className="py-1 text-right font-medium">{t("parcels.compare.percentCol")}</th>
              <th className="py-1 text-right font-medium">{t("parcels.compare.tolerance")}</th>
              <th className="py-1 text-right font-medium">{t("parcels.compare.verdict")}</th>
            </tr>
          </thead>
          <tbody>
            {cmp.rows.map((row) => (
              <tr key={row.kind} className="border-b last:border-0">
                <td className="py-1">{t(`parcels.compare.kind.${row.kind}`)}</td>
                <td className="py-1 text-right">{fmtNum(row.reference_area, 2)}</td>
                <td className="py-1 text-right">{fmtSigned(row.difference, 2)}</td>
                <td className="py-1 text-right">{row.difference_percent === null ? "—" : `${fmtSigned(row.difference_percent, 2)} %`}</td>
                <td className="py-1 text-right">{row.tolerance === null ? "—" : fmtNum(row.tolerance, 2)}</td>
                <td className={cn("py-1 text-right font-medium", row.within === true && "text-success", row.within === false && "text-danger")}>
                  {row.within === null ? t("parcels.compare.noRule") : row.within ? t("parcels.compare.within") : t("parcels.compare.outside")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {cmp.tolerance && (
        <div className="space-y-0.5 text-xs text-muted">
          <p data-testid="parcel-rule">{t("parcels.compare.ruleShown", { rule: describeRule(cmp.tolerance), source: cmp.tolerance.source || t("parcels.compare.noSource") })}</p>
          {cmp.tolerance.kind === "cadastre" && cmp.perimeter !== null && <p>{t("parcels.compare.perimeterUsed", { perimeter: fmtNum(cmp.perimeter, 2) })}</p>}
          <p>{t("parcels.compare.disclaimer")}</p>
        </div>
      )}
    </div>
  );
}
