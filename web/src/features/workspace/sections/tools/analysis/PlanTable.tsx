// Planned observations: a grid with an "active" checkbox per row, an add row
// (from, to, observation types) and removal of disabled rows.
import { Plus, Trash2 } from "lucide-react";
import { Suspense, useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { PlannedKind, PlannedRow } from "@/lib/analysisApi";
import { uid } from "@/lib/utils";
import type { Col } from "../../../grid/DataGrid";
import { DataGrid } from "../../../grid/LazyDataGrid";

const KINDS: PlannedKind[] = ["direction", "distance", "height"];

export function PlanTable({
  rows,
  onChange,
  pointNames,
  ensurePoint,
}: {
  rows: PlannedRow[];
  onChange: (rows: PlannedRow[]) => void;
  pointNames: string[];
  /** Makes sure the named point is in the plan; false if it is unknown. */
  ensurePoint: (name: string) => boolean;
}) {
  const { t } = useTranslation();
  const listId = useId();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [kinds, setKinds] = useState<Record<PlannedKind, boolean>>({ direction: true, distance: true, height: false });

  const cols = useMemo<Col<PlannedRow>[]>(
    () => [
      { id: "on", title: "✓", width: 44, kind: "boolean", get: (r) => r.enabled, set: (r, v) => ({ ...r, enabled: v === true || v === "true" }) },
      { id: "kind", title: t("analysis.cols.kind"), width: 120, readonly: true, get: (r) => t(`analysis.kind.${r.kind}`) },
      { id: "from", title: t("analysis.cols.from"), width: 90, readonly: true, get: (r) => r.station },
      { id: "to", title: t("analysis.cols.to"), width: 90, readonly: true, get: (r) => r.target },
    ],
    [t],
  );

  const add = () => {
    const a = from.trim();
    const b = to.trim();
    for (const name of [a, b]) {
      if (!ensurePoint(name)) {
        toast.error(t("analysis.unknownPoint", { name: name || "—" }));
        return;
      }
    }
    const chosen = KINDS.filter((k) => kinds[k]);
    if (!chosen.length || a === b) {
      toast.error(t("analysis.nothingToAdd"));
      return;
    }
    onChange([...rows, ...chosen.map((kind) => ({ id: uid(), enabled: true, kind, station: a, target: b, setup: null }))]);
    setTo("");
  };

  const enabled = rows.filter((r) => r.enabled).length;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium">
          {t("analysis.planned")} <span className="text-xs font-normal text-muted tabular">{t("analysis.enabledOf", { n: enabled, total: rows.length })}</span>
        </div>
        <Button type="button" variant="ghost" size="sm" disabled={enabled === rows.length} onClick={() => onChange(rows.filter((r) => r.enabled))}>
          <Trash2 /> {t("analysis.removeDisabled")}
        </Button>
      </div>
      <div className="h-[280px] rounded-lg border">
        <Suspense fallback={<Skeleton className="m-4 h-56" />}>
          <DataGrid testId="grid-preanalysis-plan" rows={rows} columns={cols} onChange={onChange} />
        </Suspense>
      </div>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          add();
        }}
      >
        <Input aria-label={t("analysis.from")} placeholder={t("analysis.from")} list={listId} value={from} onChange={(e) => setFrom(e.target.value)} className="w-24" data-testid="plan-add-from" />
        <Input aria-label={t("analysis.to")} placeholder={t("analysis.to")} list={listId} value={to} onChange={(e) => setTo(e.target.value)} className="w-24" data-testid="plan-add-to" />
        {KINDS.map((k) => (
          <label key={k} className="flex h-8 items-center gap-1.5 text-xs">
            <Checkbox checked={kinds[k]} onCheckedChange={(v) => setKinds({ ...kinds, [k]: v === true })} />
            {t(`analysis.kind.${k}`)}
          </label>
        ))}
        <Button type="submit" variant="outline" size="sm" data-testid="plan-add">
          <Plus /> {t("analysis.add")}
        </Button>
        <datalist id={listId}>
          {pointNames.slice(0, 2000).map((n) => (
            <option key={n} value={n} />
          ))}
        </datalist>
      </form>
      <p className="text-xs text-muted">{t("analysis.addHint")}</p>
    </div>
  );
}
