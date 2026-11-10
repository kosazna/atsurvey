// Level two-peg (collimation) test: Förstner by default; Kukkamäki and middle-and-end layouts.
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { instrumentsApi, PEG_LAYOUTS, type PegMethod, type TwoPegResult } from "@/lib/instrumentsApi";
import { emptyMeta, type Report, type ReportMeta } from "@/lib/instrumentsReport";
import { fmtNum, fmtSigned, parseNum } from "@/lib/utils";
import { KV, NumberField, ResultBox, useRunner } from "../shared";
import { PassBadge, ReportButtons, ReportMetaFields, useMetaLabels } from "./common";

const METHODS: PegMethod[] = ["forstner", "kukkamaki", "middle_end", "custom"];
type Field = "a1" | "b1" | "a2" | "b2" | "sa1" | "sb1" | "sa2" | "sb2";

function layout(m: PegMethod): Partial<Record<Field, string>> {
  if (m === "custom") return {};
  const [sa1, sb1, sa2, sb2] = PEG_LAYOUTS[m].map(String);
  return { sa1, sb1, sa2, sb2 };
}

export function TwoPegTool() {
  const { t } = useTranslation();
  const [method, setMethod] = useState<PegMethod>("forstner");
  const [v, setV] = useState<Record<Field, string>>({ a1: "", b1: "", a2: "", b2: "", sa1: "", sb1: "", sa2: "", sb2: "", ...layout("forstner") });
  const [tol, setTol] = useState("3");
  const [meta, setMeta] = useState<ReportMeta>(() => emptyMeta());
  const labels = useMetaLabels();
  const r = useRunner<TwoPegResult>();
  const n = (f: Field) => parseNum(v[f]);
  const set = (f: Field) => (s: string) => setV((cur) => ({ ...cur, [f]: s }));
  const ready = (Object.keys(v) as Field[]).every((f) => n(f) !== null) && (parseNum(tol) ?? 0) > 0;

  const [input, setInput] = useState(v);
  const go = () => {
    if (!ready) return;
    setInput(v);
    void r.run(() =>
      instrumentsApi.twoPeg({
        method,
        setup1: { a: n("a1")!, b: n("b1")!, dist_a: n("sa1")!, dist_b: n("sb1")! },
        setup2: { a: n("a2")!, b: n("b2")!, dist_a: n("sa2")!, dist_b: n("sb2")! },
        tolerance_mm_per_30m: parseNum(tol)!,
      }),
    );
  };

  const res = r.result;
  // the staff with the longer sight at setup 2 is the one to adjust on
  const far = res && (parseNum(input.sa2) ?? 0) >= (parseNum(input.sb2) ?? 0) ? { staff: "A", reading: res.corrected_a2 } : res ? { staff: "B", reading: res.corrected_b2 } : null;
  const report: Report | null = res && {
    title: t("instruments.twoPeg.title"),
    metaLabels: labels,
    meta,
    summary: [
      [t("instruments.twoPeg.method"), t(`instruments.twoPeg.methods.${method}`)],
      [t("instruments.twoPeg.error30"), `${fmtSigned(res.error_mm_per_30m, 2)} mm / 30 m`],
      [t("instruments.twoPeg.angle"), `${fmtSigned(res.error_arcsec, 1)}″ · ${fmtSigned(res.error_cc, 0)} cc`],
      [t("instruments.twoPeg.tolerance"), `±${fmtNum(res.tolerance_mm_per_30m, 1)} mm / 30 m — ${res.within_tolerance ? t("instruments.pass") : t("instruments.fail")}`],
      [t("instruments.twoPeg.dhTrue"), `${fmtSigned(res.dh_true, 4)} m`],
      [t("instruments.twoPeg.correctedA"), `${fmtNum(res.corrected_a2, 4)} m`],
      [t("instruments.twoPeg.correctedB"), `${fmtNum(res.corrected_b2, 4)} m`],
    ],
    tables: [
      {
        title: t("instruments.twoPeg.method"),
        headers: ["", t("instruments.twoPeg.readingA"), t("instruments.twoPeg.readingB"), t("instruments.twoPeg.distA"), t("instruments.twoPeg.distB"), "ΔH"],
        rows: [
          [t("instruments.twoPeg.setup", { n: 1 }), input.a1, input.b1, input.sa1, input.sb1, fmtSigned(res.dh_setup1, 4)],
          [t("instruments.twoPeg.setup", { n: 2 }), input.a2, input.b2, input.sa2, input.sb2, fmtSigned(res.dh_setup2, 4)],
        ],
      },
    ],
    notes: [t("instruments.twoPeg.formula")],
  };

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          go();
        }}
      >
        <ReportMetaFields meta={meta} onChange={setMeta} />
        <div className="space-y-1.5">
          <Label>{t("instruments.twoPeg.method")}</Label>
          <Select<PegMethod>
            value={method}
            onValueChange={(m) => {
              setMethod(m);
              setV((cur) => ({ ...cur, ...layout(m) }));
            }}
            options={METHODS.map((m) => ({ value: m, label: t(`instruments.twoPeg.methods.${m}`) }))}
          />
        </div>
        {([1, 2] as const).map((s) => (
          <fieldset key={s} className="grid gap-3 rounded-xl border p-3 sm:grid-cols-2">
            <legend className="px-1 text-xs font-medium text-muted">{t("instruments.twoPeg.setup", { n: s })}</legend>
            <NumberField label={t("instruments.twoPeg.readingA")} suffix="m" value={v[`a${s}`]} onChange={set(`a${s}`)} testId={`peg-a${s}`} />
            <NumberField label={t("instruments.twoPeg.readingB")} suffix="m" value={v[`b${s}`]} onChange={set(`b${s}`)} testId={`peg-b${s}`} />
            <NumberField label={t("instruments.twoPeg.distA")} suffix="m" value={v[`sa${s}`]} onChange={set(`sa${s}`)} />
            <NumberField label={t("instruments.twoPeg.distB")} suffix="m" value={v[`sb${s}`]} onChange={set(`sb${s}`)} />
          </fieldset>
        ))}
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-48">
            <NumberField label={t("instruments.twoPeg.tolerance")} suffix="mm / 30 m" value={tol} onChange={setTol} />
          </div>
          <Button type="submit" disabled={!ready || r.busy} data-testid="btn-two-peg">
            {t("tools.compute")} <ArrowRight />
          </Button>
        </div>
        <p className="text-xs text-muted">{t("instruments.twoPeg.formula")}</p>
      </form>
      <ResultBox error={r.error} testId="two-peg-result">
        {res && report && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <PassBadge ok={res.within_tolerance} testId="peg-status" />
              <span className="text-xs text-muted">{res.epsilon >= 0 ? t("instruments.twoPeg.up") : t("instruments.twoPeg.down")}</span>
            </div>
            <KV
              items={[
                { k: t("instruments.twoPeg.error30"), v: `${fmtSigned(res.error_mm_per_30m, 2)} mm / 30 m`, strong: true },
                { k: t("instruments.twoPeg.angle"), v: `${fmtSigned(res.error_arcsec, 1)}″ · ${fmtSigned(res.error_cc, 0)} cc` },
                { k: t("instruments.twoPeg.dhTrue"), v: `${fmtSigned(res.dh_true, 4)} m` },
                { k: t("instruments.twoPeg.dh1"), v: `${fmtSigned(res.dh_setup1, 4)} m` },
                { k: t("instruments.twoPeg.dh2"), v: `${fmtSigned(res.dh_setup2, 4)} m` },
                { k: t("instruments.twoPeg.correctedA"), v: `${fmtNum(res.corrected_a2, 4)} m` },
                { k: t("instruments.twoPeg.correctedB"), v: `${fmtNum(res.corrected_b2, 4)} m` },
              ]}
            />
            {!res.within_tolerance && far && <p className="text-sm">{t("instruments.twoPeg.adjustHint", { staff: far.staff, reading: fmtNum(far.reading, 4) })}</p>}
            <ReportButtons report={report} filename={`two-peg-${meta.date}`} />
          </div>
        )}
      </ResultBox>
    </div>
  );
}
