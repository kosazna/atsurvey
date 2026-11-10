// Inputs that depend on the kind of ΔΓΜ: partition line (subdivision), parcels to merge, or
// corrected parcels and final polygons (correction / ΤΔΓΜ).
import { Copy, Plus, Trash2, Wand2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { apiErrorMessage } from "@/lib/apiErrors";
import { normalizeKaek } from "@/lib/dgmApi";
import { parcelsApi, parseParts } from "@/lib/parcelsApi";
import { PointListField, useProjectPoints } from "../shared";
import { type DgmForm, kaeksOf, newItem, vertices } from "./form";

interface Props {
  form: DgmForm;
  patch: (p: Partial<DgmForm>) => void;
}

function KaekChecks({ kaeks, selected, onChange, testId }: { kaeks: string[]; selected: string[]; onChange: (v: string[]) => void; testId?: string }) {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-2" data-testid={testId}>
      {kaeks.map((k) => (
        <label key={k} className="inline-flex items-center gap-2 text-sm tabular">
          <Checkbox checked={selected.includes(k)} onCheckedChange={(c) => onChange(c ? [...selected, k] : selected.filter((x) => x !== k))} />
          {k}
        </label>
      ))}
    </div>
  );
}

export function ModeFields({ form, patch }: Props) {
  if (form.mode === "subdivision") return <SubdivisionFields form={form} patch={patch} />;
  if (form.mode === "merge") return <MergeFields form={form} patch={patch} />;
  return <CorrectionFields form={form} patch={patch} />;
}

function SubdivisionFields({ form, patch }: Props) {
  const { t } = useTranslation();
  const kaeks = kaeksOf(form);
  const subject = form.subject && kaeks.includes(form.subject) ? form.subject : (kaeks[0] ?? "");
  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold">{t("dgm.build.partition")}</h3>
      {kaeks.length > 1 && (
        <div className="w-64 space-y-1.5">
          <Label>{t("dgm.build.subject")}</Label>
          <Select value={subject} onValueChange={(v) => patch({ subject: v })} options={kaeks.map((k) => ({ value: k, label: k }))} />
        </div>
      )}
      <PointListField label={t("dgm.build.lines")} value={form.lines} onChange={(v) => patch({ lines: v })} hint={t("dgm.build.linesHint")} testId="dgm-lines" />
      <label className="inline-flex items-center gap-2 text-sm">
        <Checkbox checked={form.extend} onCheckedChange={(c) => patch({ extend: c === true })} />
        {t("dgm.build.extend")}
      </label>
      <ProposeLine form={form} subject={subject} onLines={(lines) => patch({ lines })} />
    </section>
  );
}

/** Propose the partition line from areas with the parcels subdivision (parallel/perpendicular). */
function ProposeLine({ form, subject, onLines }: { form: DgmForm; subject: string; onLines: (text: string) => void }) {
  const { t } = useTranslation();
  const pts = useProjectPoints();
  const [method, setMethod] = useState<"parallel" | "perpendicular">("parallel");
  const [side, setSide] = useState("1");
  const [parts, setParts] = useState("");
  const [busy, setBusy] = useState(false);
  const item = form.parcels.find((p) => normalizeKaek(p.kaek) === subject) ?? form.parcels[0];
  const propose = async () => {
    const areas = parseParts(parts);
    const sideNo = Number(side);
    if (!item || !areas || !Number.isInteger(sideNo) || sideNo < 1) return;
    setBusy(true);
    try {
      const res = await parcelsApi.subdivide({ parcel: { vertices: vertices(item.text, pts) }, method, mode: "areas", parts: areas, side: sideNo - 1 });
      if (res.cut_lines.length === 0) {
        toast.warning(t("dgm.build.noProposal"));
        return;
      }
      onLines(res.cut_lines.map((c) => [c.a, c.b].map((v) => `${v.name} ${v.x.toFixed(3)} ${v.y.toFixed(3)}`).join("\n")).join("\n\n"));
    } catch (e) {
      toast.error(apiErrorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };
  return (
    <details className="rounded-lg border px-3 py-2 text-sm">
      <summary className="cursor-pointer text-muted">{t("dgm.build.propose")}</summary>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div className="w-44 space-y-1.5">
          <Label>{t("dgm.build.method")}</Label>
          <Select
            value={method}
            onValueChange={setMethod}
            options={[
              { value: "parallel", label: t("dgm.build.parallel") },
              { value: "perpendicular", label: t("dgm.build.perpendicular") },
            ]}
          />
        </div>
        <div className="w-24 space-y-1.5">
          <Label>{t("dgm.build.side")}</Label>
          <Input value={side} onChange={(e) => setSide(e.target.value)} inputMode="numeric" />
        </div>
        <div className="w-56 space-y-1.5">
          <Label>{t("dgm.build.areas")}</Label>
          <Input value={parts} onChange={(e) => setParts(e.target.value)} placeholder="600" />
        </div>
        <Button size="sm" variant="outline" disabled={busy || !parseParts(parts)} onClick={() => void propose()}>
          <Wand2 /> {t("dgm.build.proposeRun")}
        </Button>
      </div>
      <p className="mt-2 text-xs text-muted">{t("dgm.build.proposeHint")}</p>
    </details>
  );
}

function MergeFields({ form, patch }: Props) {
  const { t } = useTranslation();
  const kaeks = kaeksOf(form);
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">{t("dgm.build.mergeWhich")}</h3>
      <KaekChecks kaeks={kaeks} selected={form.merge ?? kaeks} onChange={(v) => patch({ merge: v })} testId="dgm-merge" />
    </section>
  );
}

function CorrectionFields({ form, patch }: Props) {
  const { t } = useTranslation();
  const kaeks = kaeksOf(form);
  const update = (id: string, p: { kaek?: string; text?: string }) => patch({ finals: form.finals.map((f) => (f.id === id ? { ...f, ...p } : f)) });
  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold">{t("dgm.build.subjects")}</h3>
      <KaekChecks kaeks={kaeks} selected={form.subjects} onChange={(v) => patch({ subjects: v })} testId="dgm-subjects" />
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="mr-auto text-sm font-semibold">{t("dgm.build.finals")}</h3>
        <Button type="button" size="sm" variant="outline" onClick={() => patch({ finals: form.parcels.map((p) => newItem(normalizeKaek(p.kaek), p.text)) })}>
          <Copy /> {t("dgm.build.copyFinals")}
        </Button>
      </div>
      <p className="text-xs text-muted">{t("dgm.build.finalsHint")}</p>
      <div className="grid gap-4 md:grid-cols-2">
        {form.finals.map((f, i) => (
          <div key={f.id} className="space-y-1.5 rounded-lg border p-3">
            <div className="flex items-center gap-2">
              <Select
                value={f.kaek || "__new"}
                onValueChange={(v) => update(f.id, { kaek: v === "__new" ? "" : v })}
                options={[...kaeks.map((k) => ({ value: k, label: k })), { value: "__new", label: t("dgm.build.newParcel") }]}
                aria-label={t("dgm.kaek")}
              />
              <Button type="button" size="sm" variant="ghost" aria-label={t("dgm.remove")} onClick={() => patch({ finals: form.finals.filter((x) => x.id !== f.id) })}>
                <Trash2 />
              </Button>
            </div>
            <PointListField label={t("dgm.build.vertices")} value={f.text} onChange={(v) => update(f.id, { text: v })} testId={`dgm-final-${i}`} />
          </div>
        ))}
      </div>
      <Button type="button" size="sm" variant="outline" onClick={() => patch({ finals: [...form.finals, newItem()] })}>
        <Plus /> {t("dgm.build.addFinal")}
      </Button>
    </section>
  );
}
