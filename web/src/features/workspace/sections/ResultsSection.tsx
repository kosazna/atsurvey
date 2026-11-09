import { ListOrdered } from "lucide-react";
import { Suspense, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatAngle } from "@/lib/angles";
import type { DetailShot, PointKind, ResultPoint } from "@/lib/types";
import { cn, fmtNum } from "@/lib/utils";
import type { Col } from "../grid/DataGrid";
import { DataGrid } from "../grid/LazyDataGrid";
import { useWorkspace } from "../useWorkspace";
import { SectionFrame, SectionHeader } from "./SectionLayout";


const KIND_DOT: Record<PointKind, string> = {
  control: "bg-point-control",
  traverse: "bg-point-traverse",
  detail: "bg-point-detail",
};

export function ResultsSection() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const [kinds, setKinds] = useState<Set<PointKind>>(new Set(["control", "traverse", "detail"]));
  const r = ws.result;

  const points = useMemo(() => (r?.points ?? []).filter((p) => kinds.has(p.kind)), [r, kinds]);
  const counts = useMemo(() => {
    const c: Record<PointKind, number> = { control: 0, traverse: 0, detail: 0 };
    (r?.points ?? []).forEach((p) => (c[p.kind] += 1));
    return c;
  }, [r]);

  const pointCols = useMemo<Col<ResultPoint>[]>(
    () => [
      { id: "name", title: t("results.cols.name"), width: 100, get: (p) => p.name },
      { id: "kind", title: t("results.cols.kind"), width: 120, get: (p) => t(`kind.${p.kind}`) },
      { id: "x", title: t("results.cols.x"), width: 120, kind: "number", get: (p) => fmtNum(p.x, 3) },
      { id: "y", title: t("results.cols.y"), width: 125, kind: "number", get: (p) => fmtNum(p.y, 3) },
      { id: "z", title: t("results.cols.z"), width: 90, kind: "number", get: (p) => fmtNum(p.z, 3) },
      { id: "code", title: t("results.cols.code"), width: 80, get: (p) => p.code ?? "" },
      { id: "source", title: t("results.cols.source"), width: 150, get: (p) => p.source ?? "" },
      { id: "n", title: t("results.cols.n"), width: 44, kind: "number", get: (p) => String(p.n) },
    ],
    [t],
  );

  const detailCols = useMemo<Col<DetailShot>[]>(
    () => [
      { id: "station", title: t("results.detailCols.station"), width: 80, get: (d) => d.station },
      { id: "target", title: t("results.detailCols.target"), width: 80, get: (d) => d.target },
      { id: "az", title: t("results.detailCols.azimuth"), width: 115, kind: "number", get: (d) => formatAngle(d.azimuth, unit) },
      { id: "hd", title: t("results.detailCols.hd"), width: 105, kind: "number", get: (d) => fmtNum(d.hd, 3) },
      { id: "grid", title: t("results.detailCols.grid"), width: 110, kind: "number", get: (d) => fmtNum(d.distance_grid, 3) },
      { id: "x", title: "X", width: 115, kind: "number", get: (d) => fmtNum(d.x, 3) },
      { id: "y", title: "Y", width: 120, kind: "number", get: (d) => fmtNum(d.y, 3) },
      { id: "z", title: "Z", width: 85, kind: "number", get: (d) => fmtNum(d.z, 3) },
      { id: "code", title: t("results.cols.code"), width: 70, get: (d) => d.code ?? "" },
      {
        id: "check",
        title: t("results.detailCols.residual"),
        width: 90,
        kind: "number",
        get: (d) => (d.check ? fmtNum(d.residual, 3) : ""),
        invalid: (d) => d.check && d.residual !== null && d.residual > ws.data.settings.tolerances.check_shot_m,
      },
    ],
    [t, unit, ws.data.settings.tolerances.check_shot_m],
  );

  if (!r || r.points.length === 0) {
    return (
      <SectionFrame>
        <SectionHeader title={t("results.title")} />
        <EmptyState icon={<ListOrdered />} title={t("results.empty")} description={t("results.emptyHint")} action={<Button size="sm" onClick={ws.compute}>{t("ws.compute")}</Button>} />
      </SectionFrame>
    );
  }

  const selectedIndex = ws.selected ? points.findIndex((p) => p.name === ws.selected) : -1;

  return (
    <SectionFrame>
      <Tabs defaultValue="points" className="flex min-h-0 flex-1 flex-col">
        <SectionHeader
          title={t("results.title")}
          actions={
            <TabsList>
              <TabsTrigger value="points">
                {t("results.points")} <span className="tabular text-muted">{r.points.length}</span>
              </TabsTrigger>
              <TabsTrigger value="detail">
                {t("results.detail")} <span className="tabular text-muted">{r.detail.length}</span>
              </TabsTrigger>
            </TabsList>
          }
        />
        <TabsContent value="points" className="flex min-h-0 flex-1 flex-col data-[state=inactive]:hidden">
          <div className="flex flex-wrap gap-1.5 border-b px-4 py-2">
            {(["control", "traverse", "detail"] as PointKind[]).map((k) => {
              const on = kinds.has(k);
              return (
                <button
                  key={k}
                  aria-pressed={on}
                  onClick={() => {
                    const next = new Set(kinds);
                    if (on) next.delete(k);
                    else next.add(k);
                    setKinds(next);
                  }}
                  className={cn(
                    "flex h-7 cursor-pointer items-center gap-1.5 rounded-full border px-2.5 text-xs transition-colors",
                    on ? "bg-surface text-fg" : "text-muted opacity-60",
                  )}
                >
                  <span className={cn("size-2 rounded-full", KIND_DOT[k])} />
                  {t(`kind.${k}`)} <span className="tabular text-muted">{counts[k]}</span>
                </button>
              );
            })}
          </div>
          <div className="min-h-0 flex-1">
            <Suspense fallback={<Skeleton className="m-4 h-64" />}>
              <DataGrid
                testId="grid-results"
                rows={points}
                columns={pointCols}
                readonly
                selectedRow={selectedIndex >= 0 ? selectedIndex : null}
                onSelectRow={(i) => i !== null && points[i] && ws.setSelected(points[i].name)}
              />
            </Suspense>
          </div>
        </TabsContent>
        <TabsContent value="detail" className="min-h-0 flex-1 data-[state=inactive]:hidden">
          <Suspense fallback={<Skeleton className="m-4 h-64" />}>
            <DataGrid rows={r.detail} columns={detailCols} readonly onSelectRow={(i) => i !== null && r.detail[i] && ws.setSelected(r.detail[i].target)} />
          </Suspense>
        </TabsContent>
      </Tabs>
    </SectionFrame>
  );
}
