// "Κατάτμηση": cut a parcel into parts of given areas or ratios with lines parallel or
// perpendicular to a side, or through a fixed point; then check that the parts cover the
// original exactly (as the Cadastre requires).
import { ArrowRight, CheckCircle2, Plus, XCircle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { type CoverageResult, type ParcelVertex, parcelsApi, parseParts, partsCsv, pointsCsv, stremmata, type SubdivideMethod, type SubdivideRequest, type SubdivisionResult } from "@/lib/parcelsApi";
import { cn, fmtNum, parseNum } from "@/lib/utils";
import { NumberField, PointField, ResultBox, resolvePoint, useAddToProject, useOverlay, useProjectPoints, useRunner } from "../shared";
import { AreaText, CsvButton, IssueList, ParcelSketch, ParcelTables, useVertexList, VertexInput } from "./common";

interface Output {
  sub: SubdivisionResult;
  cov: CoverageResult | null;
}

export function SubdivideTool() {
  const { t } = useTranslation();
  const pts = useProjectPoints();
  const list = useVertexList("parcel-sub-pick");
  const [method, setMethod] = useState<SubdivideMethod>("parallel");
  const [side, setSide] = useState("0");
  const [fromEnd, setFromEnd] = useState<"start" | "end">("start");
  const [pivotMode, setPivotMode] = useState<"vertex" | "point">("vertex");
  const [pivot, setPivot] = useState("");
  const [pivotPoint, setPivotPoint] = useState("");
  const [towards, setTowards] = useState("");
  const [mode, setMode] = useState<"areas" | "ratios">("ratios");
  const [partsText, setPartsText] = useState("1 1");
  const [prefix, setPrefix] = useState("Ν");
  const [frontSide, setFrontSide] = useState("none");
  const [minFront, setMinFront] = useState("");
  const r = useRunner<Output>();
  const vs = list.vertices;
  const n = vs.length;
  const parts = parseParts(partsText);
  const pivotXY = pivotMode === "point" ? resolvePoint(pivotPoint, pts) : null;
  const pivotName = pivotMode === "vertex" ? pivot || vs[0]?.name || "" : "";
  const ready = n >= 3 && parts !== null && (method !== "pivot" || pivotMode === "vertex" || pivotXY !== null);
  useOverlay(
    vs.map((v) => ({ x: v.x, y: v.y, label: v.name, role: "input" as const })),
    (r.result?.sub.cut_lines ?? []).map((c) => [[c.a.x, c.a.y], [c.b.x, c.b.y]] as [number, number][]),
    n >= 3 ? [vs.map((v) => [v.x, v.y] as [number, number])] : [],
  );
  const sideOptions = vs.map((v, i) => ({ value: String(i), label: `${v.name}–${vs[(i + 1) % n].name}` }));
  const pivotIdx = vs.findIndex((v) => v.name === pivotName);
  const neighbours = pivotIdx >= 0 ? [vs[(pivotIdx + 1) % n]?.name, vs[(pivotIdx - 1 + n) % n]?.name] : [];

  async function run(): Promise<Output> {
    const parcel = { vertices: vs };
    const req: SubdivideRequest = {
      parcel,
      method,
      mode,
      parts: parts ?? [],
      side: method === "pivot" ? null : Number(side),
      from_end: fromEnd,
      pivot: method === "pivot" && pivotMode === "vertex" ? pivotName : null,
      pivot_point: method === "pivot" && pivotXY ? { x: pivotXY.x, y: pivotXY.y } : null,
      towards: method === "pivot" && pivotMode === "vertex" && towards ? towards : null,
      new_point_prefix: prefix,
      frontage_side: frontSide === "none" ? null : Number(frontSide),
      min_frontage: frontSide === "none" ? null : parseNum(minFront),
    };
    const sub = await parcelsApi.subdivide(req);
    if (sub.parts.length === 0) return { sub, cov: null };
    const cov = await parcelsApi.coverage({ outline: parcel, parts: sub.parts.map((p) => ({ label: p.geometry.label, vertices: p.geometry.vertices })) });
    return { sub, cov };
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-3">
          <VertexInput state={list} testId="parcel-sub-list" />
          <p className="text-xs text-muted">{t("parcels.sub.arcsNote")}</p>
        </div>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) void r.run(run);
          }}
        >
          <Field label={t("parcels.sub.method")}>
            <Select<SubdivideMethod>
              value={method}
              onValueChange={setMethod}
              options={(["parallel", "perpendicular", "pivot"] as const).map((m) => ({ value: m, label: t(`parcels.sub.${m}`) }))}
            />
          </Field>
          {method !== "pivot" && n >= 3 && (
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("parcels.sub.side")}>
                <Select<string> value={side} onValueChange={setSide} options={sideOptions} />
              </Field>
              {method === "perpendicular" && (
                <Field label={t("parcels.sub.fromEnd")}>
                  <Select<"start" | "end">
                    value={fromEnd}
                    onValueChange={setFromEnd}
                    options={[
                      { value: "start", label: vs[Number(side) % n]?.name ?? "—" },
                      { value: "end", label: vs[(Number(side) + 1) % n]?.name ?? "—" },
                    ]}
                  />
                </Field>
              )}
            </div>
          )}
          {method === "pivot" && n >= 3 && (
            <PivotFields
              mode={pivotMode}
              onMode={setPivotMode}
              vertexNames={vs.map((v) => v.name)}
              pivot={pivotName}
              onPivot={setPivot}
              neighbours={neighbours.filter((x): x is string => !!x)}
              towards={towards}
              onTowards={setTowards}
              pointText={pivotPoint}
              onPointText={setPivotPoint}
            />
          )}
          <div className="grid grid-cols-[auto_1fr] gap-3">
            <Field label={t("parcels.sub.mode")}>
              <Select<"areas" | "ratios">
                value={mode}
                onValueChange={setMode}
                options={[
                  { value: "ratios", label: t("parcels.sub.ratios") },
                  { value: "areas", label: t("parcels.sub.areas") },
                ]}
              />
            </Field>
            <Field label={t("parcels.sub.parts")}>
              <Input value={partsText} onChange={(e) => setPartsText(e.target.value)} className={cn("tabular", parts === null && "border-danger")} data-testid="parcel-sub-parts" />
            </Field>
          </div>
          <p className="text-xs text-muted">{t("parcels.sub.partsHint")}</p>
          <div className="grid grid-cols-3 gap-3">
            <Field label={t("parcels.sub.prefix")}>
              <Input value={prefix} onChange={(e) => setPrefix(e.target.value)} maxLength={16} />
            </Field>
            <Field label={t("parcels.sub.frontageSide")}>
              <Select<string> value={frontSide} onValueChange={setFrontSide} options={[{ value: "none", label: t("parcels.sub.noFrontage") }, ...sideOptions]} />
            </Field>
            {frontSide !== "none" && <NumberField label={t("parcels.sub.minFrontage")} value={minFront} onChange={setMinFront} />}
          </div>
          <Button type="submit" size="sm" disabled={!ready || r.busy} data-testid="parcel-sub-run">
            {t("parcels.sub.run")} <ArrowRight />
          </Button>
        </form>
      </div>
      <ResultBox error={r.error} testId="parcel-sub-result">
        {r.result && <SubdivisionView out={r.result} />}
      </ResultBox>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}

function PivotFields(props: {
  mode: "vertex" | "point";
  onMode: (m: "vertex" | "point") => void;
  vertexNames: string[];
  pivot: string;
  onPivot: (v: string) => void;
  neighbours: string[];
  towards: string;
  onTowards: (v: string) => void;
  pointText: string;
  onPointText: (v: string) => void;
}) {
  const { t } = useTranslation();
  const pts = useProjectPoints();
  return (
    <div className="space-y-3">
      <Select<"vertex" | "point">
        value={props.mode}
        onValueChange={props.onMode}
        options={[
          { value: "vertex", label: t("parcels.sub.pivotVertex") },
          { value: "point", label: t("parcels.sub.pivotOnSide") },
        ]}
      />
      {props.mode === "vertex" ? (
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("parcels.sub.pivotVertex")}>
            <Select<string> value={props.pivot} onValueChange={props.onPivot} options={props.vertexNames.map((v) => ({ value: v, label: v }))} />
          </Field>
          <Field label={t("parcels.sub.towards")}>
            <Select<string>
              value={props.neighbours.includes(props.towards) ? props.towards : (props.neighbours[0] ?? "")}
              onValueChange={props.onTowards}
              options={props.neighbours.map((v) => ({ value: v, label: v }))}
            />
          </Field>
        </div>
      ) : (
        <PointField label={t("parcels.sub.pivotCoords")} value={props.pointText} onChange={props.onPointText} points={pts} />
      )}
    </div>
  );
}

function SubdivisionView({ out }: { out: Output }) {
  const { t } = useTranslation();
  const add = useAddToProject();
  const { sub, cov } = out;
  if (sub.parts.length === 0) return <IssueList issues={sub.issues} />;
  const allPoints: ParcelVertex[] = sub.new_points;
  return (
    <div className="space-y-5">
      <IssueList issues={sub.issues} />
      {cov && <CoverageLine cov={cov} />}
      <div className="grid gap-6 lg:grid-cols-[1fr_auto]">
        <PartsTable sub={sub} />
        <ParcelSketch parcels={sub.parts.map((p) => ({ vertices: p.geometry.vertices, label: p.geometry.label }))} cuts={sub.cut_lines} />
      </div>
      {allPoints.length > 0 && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-medium">{t("parcels.sub.newPoints")}</span>
            <div className="flex gap-2">
              <CsvButton csv={pointsCsv(allPoints)} filename="new-points.csv" />
              <Button size="sm" variant="outline" onClick={() => add(allPoints, "Ν")}>
                <Plus /> {t("parcels.sub.addPoints")}
              </Button>
            </div>
          </div>
          <p className="text-sm tabular">{allPoints.map((p) => `${p.name} (${fmtNum(p.x, 3)}, ${fmtNum(p.y, 3)})`).join(" · ")}</p>
        </div>
      )}
      {sub.parts.map((p, i) => (
        <details key={i} className="rounded-lg border px-3 py-2">
          <summary className="cursor-pointer text-sm">
            {t("parcels.sub.part")} {p.geometry.label} · <AreaText m2={p.geometry.area} />
          </summary>
          <div className="mt-3">
            <ParcelTables geo={p.geometry} name={`part-${i + 1}`} />
          </div>
        </details>
      ))}
    </div>
  );
}

function CoverageLine({ cov }: { cov: CoverageResult }) {
  const { t } = useTranslation();
  return (
    <div className={cn("flex items-start gap-2 text-sm", cov.ok ? "text-success" : "text-danger")} data-testid="parcel-coverage">
      {cov.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> : <XCircle className="mt-0.5 size-4 shrink-0" />}
      <div>
        {cov.ok ? t("parcels.sub.coverageOk", { sum: fmtNum(cov.parts_area, 2) }) : t("parcels.sub.coverageFail")}
        {!cov.ok && <IssueList issues={cov.issues} />}
      </div>
    </div>
  );
}

function PartsTable({ sub }: { sub: SubdivisionResult }) {
  const { t } = useTranslation();
  const hasFront = sub.parts.some((p) => p.frontage !== null);
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">{t("parcels.sub.partsTable")}</span>
        <CsvButton csv={partsCsv(sub)} filename="parts.csv" />
      </div>
      <div className="scroll-x-visible">
        <table className="w-full min-w-[480px] text-sm tabular" data-testid="parcel-parts">
          <thead>
            <tr className="border-b text-xs text-muted">
              <th className="py-1 text-left font-medium">{t("parcels.sub.part")}</th>
              <th className="py-1 text-right font-medium">{t("parcels.sub.requested")}</th>
              <th className="py-1 text-right font-medium">{t("parcels.area")} (m²)</th>
              <th className="py-1 text-right font-medium">{t("parcels.stremmata")}</th>
              <th className="py-1 text-right font-medium">{t("parcels.sub.error")}</th>
              {hasFront && <th className="py-1 text-right font-medium">{t("parcels.sub.frontage")}</th>}
            </tr>
          </thead>
          <tbody>
            {sub.parts.map((p, i) => (
              <tr key={i} className="border-b last:border-0">
                <td className="py-1">{p.geometry.label}</td>
                <td className="py-1 text-right">{p.requested_area === null ? <span className="text-muted">{t("parcels.sub.remainder")}</span> : fmtNum(p.requested_area, 2)}</td>
                <td className="py-1 text-right font-medium">{fmtNum(p.geometry.area, 2)}</td>
                <td className="py-1 text-right">{p.geometry.area === null ? "—" : stremmata(p.geometry.area).toFixed(3)}</td>
                <td className="py-1 text-right text-muted">{p.area_error === null ? "" : p.area_error.toExponential(1)}</td>
                {hasFront && <td className="py-1 text-right">{fmtNum(p.frontage, 2)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
