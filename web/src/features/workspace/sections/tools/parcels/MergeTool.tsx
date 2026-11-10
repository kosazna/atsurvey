// "Συνένωση": merge two or more adjacent parcels into one.
import { ArrowRight, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type MergeResult, parcelsApi, toVertices } from "@/lib/parcelsApi";
import { fmtNum, parseNum, uid } from "@/lib/utils";
import { KV, NumberField, parsePointList, PointListField, ResultBox, useOverlay, useProjectPoints, useRunner } from "../shared";
import { AreaText, IssueList, ParcelSketch, ParcelTables } from "./common";

const MAX_PARCELS = 20;

interface Item {
  id: string;
  text: string;
}

export function MergeTool() {
  const { t } = useTranslation();
  const pts = useProjectPoints();
  const [items, setItems] = useState<Item[]>(() => [{ id: uid(), text: "" }, { id: uid(), text: "" }]);
  const [snapMm, setSnapMm] = useState("1");
  const [label, setLabel] = useState("");
  const r = useRunner<MergeResult>();
  const parsed = items.map((it) => parsePointList(it.text, pts));
  const parcels = parsed.map((p, i) => ({ label: String(i + 1), vertices: toVertices(p.pts) }));
  const snap = parseNum(snapMm);
  const ready = parcels.length >= 2 && parcels.every((p) => p.vertices.length >= 3) && snap !== null && snap > 0 && snap <= 1000;
  useOverlay(
    parcels.flatMap((p) => p.vertices.map((v) => ({ x: v.x, y: v.y, label: v.name, role: "input" as const }))),
    [],
    parcels.filter((p) => p.vertices.length >= 3).map((p) => p.vertices.map((v) => [v.x, v.y] as [number, number])),
  );
  const update = (id: string, text: string) => setItems((cur) => cur.map((it) => (it.id === id ? { ...it, text } : it)));

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2">
        {items.map((it, i) => (
          <div key={it.id} className="space-y-1">
            <PointListField label={t("parcels.merge.parcel", { n: i + 1 })} value={it.text} onChange={(v) => update(it.id, v)} hint={t("parcels.verticesHint")} testId={`parcel-merge-${i}`} />
            {parsed[i].bad.length > 0 && <p className="text-xs text-danger">{t("tools.badLines", { lines: parsed[i].bad.slice(0, 3).join(" · ") })}</p>}
            {items.length > 2 && (
              <Button type="button" size="sm" variant="ghost" onClick={() => setItems((cur) => cur.filter((x) => x.id !== it.id))}>
                <Trash2 /> {t("parcels.merge.remove")}
              </Button>
            )}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <Button type="button" size="sm" variant="outline" disabled={items.length >= MAX_PARCELS} onClick={() => setItems((cur) => [...cur, { id: uid(), text: "" }])}>
          <Plus /> {t("parcels.merge.add")}
        </Button>
        <div className="w-40">
          <NumberField label={t("parcels.merge.snap")} value={snapMm} onChange={setSnapMm} />
        </div>
        <div className="w-56 space-y-1.5">
          <Label>{t("parcels.merge.label")}</Label>
          <Input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={100} />
        </div>
        <Button
          size="sm"
          disabled={!ready || r.busy}
          data-testid="parcel-merge-run"
          onClick={() => void r.run(() => parcelsApi.merge({ parcels, snap_tolerance: (snap ?? 1) / 1000, label }))}
        >
          {t("parcels.merge.run")} <ArrowRight />
        </Button>
      </div>
      <ResultBox error={r.error} testId="parcel-merge-result">
        {r.result && <MergeView res={r.result} />}
      </ResultBox>
    </div>
  );
}

function MergeView({ res }: { res: MergeResult }) {
  const { t } = useTranslation();
  const g = res.merged;
  return (
    <div className="space-y-5">
      <IssueList issues={res.issues} />
      {g && g.valid && (
        <>
          <div className="grid gap-6 lg:grid-cols-[1fr_auto]">
            <KV
              items={[
                { k: t("parcels.merge.merged"), v: <AreaText m2={g.area} />, strong: true },
                { k: t("parcels.merge.sum"), v: <AreaText m2={res.area_sum} /> },
                { k: t("parcels.perimeter"), v: `${fmtNum(g.perimeter, 3)} m` },
                { k: t("parcels.merge.maxSnap"), v: `${fmtNum(res.max_snap * 1000, 1)} mm` },
                ...(res.inserted.length ? [{ k: t("parcels.merge.inserted"), v: res.inserted.join(", ") }] : []),
              ]}
            />
            <ParcelSketch parcels={[g]} />
          </div>
          <ParcelTables geo={g} name="merged" />
        </>
      )}
    </div>
  );
}
