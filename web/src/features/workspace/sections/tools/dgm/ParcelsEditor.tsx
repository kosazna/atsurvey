// Cadastral parcels (PST_KAEK): load the ΚΔ DXF, use the example, or type/paste vertices.
import { FlaskConical, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiErrorMessage } from "@/lib/apiErrors";
import { dgmApi, isKaek, normalizeKaek, verticesText } from "@/lib/dgmApi";
import type { ParcelVertex } from "@/lib/parcelsApi";
import type { Issue } from "@/lib/types";
import { PointListField, useProjectPoints } from "../shared";
import { FileButton, ProblemList } from "./common";
import { newItem, type PolyItem, vertices } from "./form";

const MAX_PARCELS = 50;

interface Props {
  items: PolyItem[];
  onChange: (items: PolyItem[]) => void;
}

export function ParcelsEditor({ items, onChange }: Props) {
  const { t } = useTranslation();
  const pts = useProjectPoints();
  const [busy, setBusy] = useState(false);
  const [issues, setIssues] = useState<Issue[]>([]);
  const update = (id: string, patch: Partial<PolyItem>) => onChange(items.map((it) => (it.id === id ? { ...it, ...patch } : it)));

  const setFrom = (parcels: { kaek?: string | null; vertices: ParcelVertex[] }[]) => {
    if (parcels.length > 0) onChange(parcels.slice(0, MAX_PARCELS).map((p) => newItem(p.kaek ?? "", verticesText(p.vertices))));
  };

  const loadSample = async () => {
    setBusy(true);
    try {
      setFrom(await dgmApi.sample());
      setIssues([]);
    } catch (e) {
      toast.error(apiErrorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  const readKd = async (file: File) => {
    setBusy(true);
    try {
      const res = await dgmApi.readKd(file);
      setIssues(res.issues);
      setFrom(res.parcels);
    } catch (e) {
      toast.error(apiErrorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="mr-auto text-sm font-semibold">{t("dgm.build.parcels")}</h3>
        <FileButton label={t("dgm.build.loadKd")} busy={busy} onFile={(f) => void readKd(f)} testId="dgm-kd-file" />
        <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => void loadSample()} data-testid="dgm-sample">
          <FlaskConical /> {t("dgm.build.example")}
        </Button>
      </div>
      <p className="text-xs text-muted">{t("dgm.build.parcelsHint")}</p>
      <ProblemList issues={issues} />
      <div className="grid gap-4 md:grid-cols-2">
        {items.map((it, i) => {
          const kaek = normalizeKaek(it.kaek);
          const bad: string[] = [];
          vertices(it.text, pts, bad);
          return (
            <div key={it.id} className="space-y-1.5 rounded-lg border p-3">
              <div className="flex items-center gap-2">
                <Input value={it.kaek} onChange={(e) => update(it.id, { kaek: e.target.value })} placeholder={t("dgm.build.kaekPlaceholder")} maxLength={32} aria-label={t("dgm.kaek")} data-testid={`dgm-parcel-kaek-${i}`} />
                {items.length > 1 && (
                  <Button type="button" size="sm" variant="ghost" aria-label={t("dgm.remove")} onClick={() => onChange(items.filter((x) => x.id !== it.id))}>
                    <Trash2 />
                  </Button>
                )}
              </div>
              {kaek && !isKaek(kaek) && <p className="text-xs text-warning">{t("dgm.build.kaekFormat")}</p>}
              <PointListField label={t("dgm.build.vertices")} value={it.text} onChange={(v) => update(it.id, { text: v })} hint={t("parcels.verticesHint")} testId={`dgm-parcel-${i}`} />
              {bad.length > 0 && <p className="text-xs text-danger">{t("tools.badLines", { lines: bad.slice(0, 3).join(" · ") })}</p>}
            </div>
          );
        })}
      </div>
      <Button type="button" size="sm" variant="outline" disabled={items.length >= MAX_PARCELS} onClick={() => onChange([...items, newItem()])}>
        <Plus /> {t("dgm.build.addParcel")}
      </Button>
    </section>
  );
}
