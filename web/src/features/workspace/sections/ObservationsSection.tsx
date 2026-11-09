import { Plus, Telescope, Trash2, Upload } from "lucide-react";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import type { StoredObservation, StoredSetup } from "@/data/store";
import { angleToInput, formatAngle, parseAngle, unitLabel } from "@/lib/angles";
import { cn, parseNum, uid } from "@/lib/utils";
import type { Col } from "../grid/DataGrid";
import { DataGrid } from "../grid/LazyDataGrid";
import { useWorkspace } from "../useWorkspace";
import { SectionFrame, SectionHeader } from "./SectionLayout";


export function ObservationsSection() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const setups = ws.data.setups;
  const [selectedId, setSelectedId] = useState<string | null>(ws.focus.setup ?? setups[0]?.id ?? null);
  const [selRows, setSelRows] = useState<number[]>([]);

  useEffect(() => {
    if (ws.focus.setup) {
      const s = setups.find((x) => x.id === ws.focus.setup || x.station === ws.focus.setup);
      if (s) setSelectedId(s.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ws.focus.setup]);

  const setup = setups.find((s) => s.id === selectedId) ?? setups[0] ?? null;
  const updateSetup = (patch: Partial<StoredSetup>) => {
    if (!setup) return;
    ws.update({ setups: setups.map((s) => (s.id === setup.id ? { ...s, ...patch } : s)) });
  };

  const angleCol = (id: "hz" | "v", title: string): Col<StoredObservation> => ({
    id,
    title: `${title} (${unitLabel(unit)})`,
    width: 130,
    kind: "number",
    get: (r) => angleToInput(r[id], unit),
    display: (r) => (r[id] === null || r[id] === undefined ? "" : formatAngle(r[id], unit)),
    set: (r, v) => {
      const s = String(v).trim();
      if (s === "") return id === "v" ? { ...r, v: null, edited: true } : null;
      const a = parseAngle(s, unit);
      return a === null ? null : { ...r, [id]: a, edited: true };
    },
    muted: (r) => Boolean(r.excluded),
  });

  const columns = useMemo<Col<StoredObservation>[]>(
    () => [
      { id: "target", title: t("obs.cols.target"), width: 100, get: (r) => r.target, set: (r, v) => ({ ...r, target: String(v).trim(), edited: true }), muted: (r) => Boolean(r.excluded) },
      angleCol("hz", t("obs.cols.hz")),
      angleCol("v", t("obs.cols.v")),
      {
        id: "face",
        title: t("obs.cols.face"),
        width: 56,
        readonly: true,
        get: (r) => (r.v !== null && r.v !== undefined ? (r.v > Math.PI ? "II" : "I") : ""),
        muted: () => true,
      },
      {
        id: "sd",
        title: `${t("obs.cols.sd")} (m)`,
        width: 120,
        kind: "number",
        get: (r) => (r.sd === null || r.sd === undefined ? "" : String(r.sd)),
        display: (r) => (r.sd === null || r.sd === undefined ? "" : r.sd.toFixed(4)),
        set: (r, v) => {
          const s = String(v).trim();
          if (s === "") return { ...r, sd: null, edited: true };
          const n = parseNum(s);
          return n === null || n < 0 ? null : { ...r, sd: n, edited: true };
        },
        muted: (r) => Boolean(r.excluded),
      },
      {
        id: "ht",
        title: `${t("obs.cols.ht")} (m)`,
        width: 110,
        kind: "number",
        get: (r) => String(r.target_height ?? 0),
        display: (r) => (r.target_height ?? 0).toFixed(3),
        set: (r, v) => {
          const n = parseNum(String(v));
          return n === null ? null : { ...r, target_height: n, edited: true };
        },
        muted: (r) => Boolean(r.excluded),
      },
      { id: "code", title: t("obs.cols.code"), width: 90, get: (r) => r.code ?? "", set: (r, v) => ({ ...r, code: String(v) || null }), muted: (r) => Boolean(r.excluded) },
      { id: "excluded", title: t("obs.cols.excluded"), width: 80, kind: "boolean", get: (r) => Boolean(r.excluded), set: (r, v) => ({ ...r, excluded: Boolean(v) }) },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t, unit],
  );

  const makeObs = (): StoredObservation => ({ id: uid(), target: "", hz: Number.NaN, v: null, sd: null, target_height: setup?.observations.at(-1)?.target_height ?? 0, code: null, excluded: false });

  const addSetup = () => {
    const s: StoredSetup = { id: uid(), station: `S${setups.length + 1}`, instrument_height: 0, observations: [] };
    ws.update({ setups: [...setups, s] });
    setSelectedId(s.id);
  };

  if (setups.length === 0) {
    return (
      <SectionFrame>
        <SectionHeader title={t("obs.title")} />
        <EmptyState
          icon={<Telescope />}
          title={t("obs.empty")}
          description={t("obs.emptyHint")}
          action={
            <div className="flex gap-2">
              <Button size="sm" onClick={() => ws.setDialog("import")}>
                <Upload /> {t("imp.title")}
              </Button>
              <Button size="sm" variant="outline" onClick={addSetup}>
                <Plus /> {t("obs.addSetup")}
              </Button>
            </div>
          }
        />
      </SectionFrame>
    );
  }

  return (
    <SectionFrame>
      <SectionHeader
        title={t("obs.title")}
        description={t("obs.unitHint", { unit: t(`units.${unit}`) })}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => ws.setDialog("import")}>
              <Upload /> {t("common.import")}
            </Button>
            <Button size="sm" onClick={addSetup}>
              <Plus /> {t("obs.addSetup")}
            </Button>
          </>
        }
      />
      <div className="flex min-h-0 flex-1 flex-col sm:flex-row">
        <div className="flex max-h-40 shrink-0 gap-1 overflow-auto border-b p-2 sm:max-h-none sm:w-48 sm:flex-col sm:border-b-0 sm:border-r" role="listbox" aria-label={t("obs.setups")}>
          <div className="hidden px-1.5 pb-1 text-xs font-medium  text-muted sm:block">{t("obs.setups")}</div>
          {setups.map((s, i) => {
            const active = s.id === setup?.id;
            return (
              <button
                key={s.id}
                role="option"
                aria-selected={active}
                onClick={() => setSelectedId(s.id)}
                className={cn(
                  "flex shrink-0 cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-sunken",
                  active && "bg-surface-sunken font-medium",
                )}
              >
                <span className="w-5 text-xs tabular text-muted">{i + 1}</span>
                <span className="truncate">{s.station}</span>
                <span className="ml-auto text-xs tabular text-muted">{s.observations.length}</span>
              </button>
            );
          })}
        </div>
        {setup && (
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            <div className="flex flex-wrap items-end gap-3 border-b px-3 py-2">
              <div className="space-y-1">
                <Label htmlFor="st-name">{t("obs.station")}</Label>
                <Input id="st-name" className="h-7 w-28" value={setup.station} onChange={(e) => updateSetup({ station: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="st-hi">{t("obs.hi")} (m)</Label>
                <Input
                  id="st-hi"
                  className="h-7 w-24 tabular"
                  defaultValue={setup.instrument_height ?? 0}
                  key={setup.id}
                  onBlur={(e) => {
                    const n = parseNum(e.target.value);
                    if (n !== null) updateSetup({ instrument_height: n });
                  }}
                />
              </div>
              <span className="pb-1.5 text-xs text-muted">{t("obs.nobs", { count: setup.observations.length })}</span>
              <div className="ml-auto flex gap-1.5">
                {selRows.length > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const del = new Set(selRows);
                      updateSetup({ observations: setup.observations.filter((_, i) => !del.has(i)) });
                      setSelRows([]);
                    }}
                  >
                    <Trash2 /> ({selRows.length})
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-danger hover:text-danger"
                  onClick={() => {
                    const next = setups.filter((s) => s.id !== setup.id);
                    ws.update({ setups: next });
                    setSelectedId(next[0]?.id ?? null);
                  }}
                >
                  <Trash2 /> {t("obs.deleteSetup")}
                </Button>
              </div>
            </div>
            <div className="min-h-0 flex-1">
              <Suspense fallback={<Skeleton className="m-4 h-64" />}>
                <DataGrid
                  key={setup.id}
                  testId="grid-observations"
                  rows={setup.observations}
                  columns={columns}
                  makeRow={makeObs}
                  onChange={(obs) => updateSetup({ observations: obs })}
                  onSelectionRows={setSelRows}
                  appendLabel={t("obs.addRow")}
                />
              </Suspense>
            </div>
          </div>
        )}
      </div>
    </SectionFrame>
  );
}
