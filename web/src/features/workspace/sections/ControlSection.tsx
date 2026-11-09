import { FileUp, Plus, Trash2, Triangle } from "lucide-react";
import { Suspense, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import type { StoredControlPoint } from "@/data/store";
import { parseNum, uid } from "@/lib/utils";
import type { Col } from "../grid/DataGrid";
import { DataGrid } from "../grid/LazyDataGrid";
import { useWorkspace } from "../useWorkspace";
import { SectionFrame, SectionHeader } from "./SectionLayout";


export function parseControlCsv(text: string): StoredControlPoint[] {
  const out: StoredControlPoint[] = [];
  for (const line of text.split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith("#")) continue;
    const parts = t.includes(";") ? t.split(";") : t.includes("\t") ? t.split("\t") : t.split(/[,\s]+/);
    if (parts.length < 3) continue;
    const [name, xs, ys, zs, code] = parts.map((p) => p.trim().replace(/^"|"$/g, ""));
    const x = parseNum(xs);
    const y = parseNum(ys);
    if (!name || x === null || y === null) continue;
    const z = zs !== undefined ? parseNum(zs) : null;
    out.push({ id: uid(), name, x, y, z, code: code || null });
  }
  return out;
}

export function ControlSection() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const rows = ws.data.control_points;
  const [selRows, setSelRows] = useState<number[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const dupNames = useMemo(() => {
    const seen = new Map<string, number>();
    rows.forEach((r) => seen.set(r.name, (seen.get(r.name) ?? 0) + 1));
    return new Set([...seen].filter(([n, c]) => n && c > 1).map(([n]) => n));
  }, [rows]);

  const numCol = (id: "x" | "y" | "z", title: string, required: boolean): Col<StoredControlPoint> => ({
    id,
    title,
    width: id === "z" ? 100 : 130,
    kind: "number",
    get: (r) => (r[id] === null || r[id] === undefined || Number.isNaN(r[id]) ? "" : String(r[id])),
    display: (r) => (r[id] === null || r[id] === undefined || Number.isNaN(r[id]) ? "" : (r[id] as number).toFixed(3)),
    set: (r, v) => {
      const n = parseNum(String(v));
      if (n === null && String(v).trim() !== "") return null;
      return { ...r, [id]: n === null ? (required ? Number.NaN : null) : n };
    },
    invalid: (r) => required && !Number.isFinite(r[id] as number) && r.name !== "",
  });

  const columns: Col<StoredControlPoint>[] = [
    {
      id: "name",
      title: t("control.cols.name"),
      width: 120,
      get: (r) => r.name,
      set: (r, v) => ({ ...r, name: String(v).trim() }),
      invalid: (r) => dupNames.has(r.name),
    },
    numCol("x", t("control.cols.x"), true),
    numCol("y", t("control.cols.y"), true),
    numCol("z", t("control.cols.z"), false),
    { id: "code", title: t("control.cols.code"), width: 110, get: (r) => r.code ?? "", set: (r, v) => ({ ...r, code: String(v) || null }) },
  ];

  const makeRow = (): StoredControlPoint => ({ id: uid(), name: "", x: Number.NaN, y: Number.NaN, z: null, code: null });
  const selectedIndex = ws.selected ? rows.findIndex((r) => r.name === ws.selected) : -1;

  return (
    <SectionFrame>
      <SectionHeader
        title={t("control.title")}
        description={t("control.hint")}
        actions={
          <>
            {selRows.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  const del = new Set(selRows);
                  ws.update({ control_points: rows.filter((_, i) => !del.has(i)) });
                  setSelRows([]);
                }}
              >
                <Trash2 /> {t("control.deleteSelected")} ({selRows.length})
              </Button>
            )}
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.txt,.xyz"
              className="hidden"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (!f) return;
                const pts = parseControlCsv(await f.text());
                if (!pts.length) return void toast.error(t("control.csvFailed"));
                const byName = new Map(rows.map((r) => [r.name, r]));
                pts.forEach((p) => byName.set(p.name, { ...p, id: byName.get(p.name)?.id ?? p.id }));
                ws.update({ control_points: [...byName.values()] });
                toast.success(t("control.csvImported", { count: pts.length }));
              }}
            />
            <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()}>
              <FileUp /> {t("control.importCsv")}
            </Button>
            <Button size="sm" onClick={() => ws.update({ control_points: [...rows, makeRow()] })}>
              <Plus /> {t("control.addRow")}
            </Button>
          </>
        }
      />
      {rows.length === 0 ? (
        <EmptyState
          icon={<Triangle />}
          title={t("control.empty")}
          description={t("control.emptyHint")}
          action={
            <Button size="sm" onClick={() => ws.update({ control_points: [makeRow()] })}>
              <Plus /> {t("control.addRow")}
            </Button>
          }
        />
      ) : (
        <div className="min-h-0 flex-1">
          <Suspense fallback={<Skeleton className="m-4 h-64" />}>
            <DataGrid
              testId="grid-control"
              rows={rows}
              columns={columns}
              makeRow={makeRow}
              onChange={(next) => ws.update({ control_points: next })}
              selectedRow={selectedIndex >= 0 ? selectedIndex : null}
              onSelectRow={(i) => i !== null && rows[i]?.name && ws.setSelected(rows[i].name)}
              onSelectionRows={setSelRows}
              appendLabel={t("control.addRow")}
            />
          </Suspense>
        </div>
      )}
    </SectionFrame>
  );
}
