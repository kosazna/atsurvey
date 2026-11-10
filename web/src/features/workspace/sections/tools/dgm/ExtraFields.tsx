// Survey layers (TOPO_PROP, TOPO_PROP_NEW, BLD), the area tolerance and the title block.
import { useTranslation } from "react-i18next";
import { Checkbox } from "@/components/ui/checkbox";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import type { TitleBlock } from "@/lib/dgmApi";
import { AREA_TOLERANCE_PRESETS } from "@/lib/parcelsApi";
import { PointListField } from "../shared";
import type { DgmForm } from "./form";

interface Props {
  form: DgmForm;
  patch: (p: Partial<DgmForm>) => void;
}

export function SurveyFields({ form, patch }: Props) {
  const { t } = useTranslation();
  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold">{t("dgm.build.survey")}</h3>
      <p className="text-xs text-muted">{t(form.mode === "correction" ? "dgm.build.surveyHintCorrection" : "dgm.build.surveyHintDeed")}</p>
      <div className="grid gap-4 md:grid-cols-2">
        <PointListField label={t("dgm.build.topo")} value={form.topo} onChange={(v) => patch({ topo: v })} hint={t("dgm.build.blocksHint")} testId="dgm-topo" />
        {form.mode !== "correction" && <PointListField label={t("dgm.build.topoNew")} value={form.topoNew} onChange={(v) => patch({ topoNew: v })} hint={t("dgm.build.blocksHint")} />}
        <PointListField label={t("dgm.build.buildings")} value={form.buildings} onChange={(v) => patch({ buildings: v })} hint={t("dgm.build.blocksHint")} />
      </div>
      <div className="flex flex-wrap gap-4">
        <div className="w-64 space-y-1.5">
          <Label>{t("dgm.build.boundary")}</Label>
          <Select
            value={form.boundary}
            onValueChange={(v) => patch({ boundary: v })}
            options={[
              { value: "unimplemented", label: t("dgm.build.unimplemented") },
              { value: "implemented", label: t("dgm.build.implemented") },
            ]}
          />
        </div>
        <div className="w-96 space-y-1.5">
          <Label>{t("dgm.build.tolerance")}</Label>
          <Select
            value={form.toleranceId || "__none"}
            onValueChange={(v) => patch({ toleranceId: v === "__none" ? "" : v })}
            options={[{ value: "__none", label: t("dgm.build.noTolerance") }, ...AREA_TOLERANCE_PRESETS.map((p) => ({ value: p.id, label: p.to_be_confirmed ? `${p.label} *` : p.label }))]}
          />
        </div>
      </div>
    </section>
  );
}

const TEXT_FIELDS: (keyof TitleBlock)[] = ["title", "location", "municipality", "client", "author", "author_details", "date"];

export function TitleFields({ form, patch }: Props) {
  const { t } = useTranslation();
  const title = form.title;
  const set = (p: Partial<TitleBlock>) => patch({ title: { ...title, ...p } });
  return (
    <details className="rounded-lg border px-3 py-2">
      <summary className="cursor-pointer text-sm font-semibold">{t("dgm.title.heading")}</summary>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {TEXT_FIELDS.map((k) => (
          <div key={k} className="space-y-1.5">
            <Label>{t(`dgm.title.${k}`)}</Label>
            <Input value={String(title[k])} onChange={(e) => set({ [k]: e.target.value })} maxLength={k === "date" ? 40 : 200} />
          </div>
        ))}
        <div className="space-y-1.5">
          <Label>{t("dgm.title.scale")}</Label>
          <Input value={String(title.scale)} inputMode="numeric" onChange={(e) => set({ scale: Math.min(100000, Math.max(1, Number(e.target.value) || 500)) })} />
        </div>
        <div className="space-y-1.5">
          <Label>{t("dgm.title.method")}</Label>
          <Select
            value={title.method}
            onValueChange={(v) => set({ method: v })}
            options={[
              { value: "hepos", label: "HEPOS" },
              { value: "other", label: t("dgm.title.methodOther") },
            ]}
          />
        </div>
        {title.method === "other" && (
          <div className="space-y-1.5">
            <Label>{t("dgm.title.methodOther")}</Label>
            <Input value={title.method_other} onChange={(e) => set({ method_other: e.target.value })} maxLength={200} />
          </div>
        )}
        <div className="space-y-1.5 md:col-span-2">
          <Label>{t("dgm.title.notes")}</Label>
          <Textarea value={title.notes} onChange={(e) => set({ notes: e.target.value })} maxLength={4000} rows={3} />
        </div>
        {form.mode === "correction" && (
          <label className="inline-flex items-center gap-2 text-sm md:col-span-2">
            <Checkbox checked={title.tdgm} onCheckedChange={(c) => set({ tdgm: c === true })} />
            {t("dgm.title.tdgm")}
          </label>
        )}
      </div>
    </details>
  );
}
