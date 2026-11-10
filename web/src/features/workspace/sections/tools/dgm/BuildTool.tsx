// "Σύνταξη ΔΓΜ": choose the kind (deed: subdivision / merge, or correction), load the cadastral
// parcels, define the partition line or the final polygons, preview, check and export the DXF.
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import type { DgmMode, DgmRequest, DgmResult } from "@/lib/dgmApi";
import { dgmApi } from "@/lib/dgmApi";
import { ResultBox, useProjectPoints, useRunner } from "../shared";
import { Disclaimer } from "./common";
import { SurveyFields, TitleFields } from "./ExtraFields";
import { type DgmForm, INITIAL_FORM, toRequest } from "./form";
import { ModeFields } from "./ModeFields";
import { ParcelsEditor } from "./ParcelsEditor";
import { ResultView } from "./ResultView";

const MODES: DgmMode[] = ["subdivision", "merge", "correction"];

export function BuildTool() {
  const { t } = useTranslation();
  const pts = useProjectPoints();
  const [form, setForm] = useState<DgmForm>(INITIAL_FORM);
  const [sent, setSent] = useState<DgmRequest | null>(null);
  const r = useRunner<DgmResult>();
  const patch = (p: Partial<DgmForm>) => setForm((cur) => ({ ...cur, ...p }));
  const built = toRequest(form, pts);
  const run = () => {
    if (!built.req) return;
    const req = built.req;
    setSent(req);
    void r.run(() => dgmApi.build(req));
  };
  return (
    <div className="space-y-6">
      <Disclaimer />
      <div className="w-80 space-y-1.5">
        <Label>{t("dgm.build.mode")}</Label>
        <Select<DgmMode> value={form.mode} onValueChange={(mode) => patch({ mode })} options={MODES.map((m) => ({ value: m, label: t(`dgm.modes.${m}`) }))} />
        <p className="text-xs text-muted">{t(`dgm.modeHints.${form.mode}`)}</p>
      </div>
      <ParcelsEditor items={form.parcels} onChange={(parcels) => patch({ parcels })} />
      <ModeFields form={form} patch={patch} />
      <SurveyFields form={form} patch={patch} />
      <TitleFields form={form} patch={patch} />
      {built.bad.length > 0 && <p className="text-xs text-danger">{t("tools.badLines", { lines: built.bad.slice(0, 3).join(" · ") })}</p>}
      <Button size="sm" disabled={!built.req || r.busy} onClick={run} data-testid="dgm-build-run">
        {t("dgm.build.run")} <ArrowRight />
      </Button>
      <ResultBox error={r.error} testId="dgm-build-result">
        {r.result && sent && <ResultView res={r.result} req={sent} />}
      </ResultBox>
    </div>
  );
}
