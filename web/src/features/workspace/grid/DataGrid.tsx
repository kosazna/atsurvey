// Spreadsheet-like grid (Glide Data Grid, canvas based). Supports in-place editing,
// multi-cell paste from Excel (rows are appended as needed), row selection and
// highlighting of the selected point coming from the map.
import "@glideapps/glide-data-grid/dist/index.css";
import {
  CompactSelection,
  DataEditor,
  GridCellKind,
  type DataEditorRef,
  type EditableGridCell,
  type GridCell,
  type GridColumn,
  type GridSelection,
  type Item,
  type Theme,
} from "@glideapps/glide-data-grid";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "@/lib/theme";

export interface Col<T> {
  id: string;
  title: string;
  width?: number;
  kind?: "text" | "number" | "boolean";
  readonly?: boolean;
  /** raw value for editing / copy */
  get: (row: T) => string | boolean;
  /** formatted display value */
  display?: (row: T) => string;
  /** apply an edited value. Return null to reject. */
  set?: (row: T, value: string | boolean) => T | null;
  invalid?: (row: T) => boolean;
  muted?: (row: T) => boolean;
}

export interface DataGridProps<T> {
  rows: T[];
  columns: Col<T>[];
  onChange?: (rows: T[]) => void;
  makeRow?: () => T;
  readonly?: boolean;
  selectedRow?: number | null;
  onSelectRow?: (index: number | null) => void;
  onSelectionRows?: (rows: number[]) => void;
  rowMarkers?: boolean;
  appendLabel?: string;
  testId?: string;
}

const LIGHT: Partial<Theme> = {
  accentColor: "#2563eb",
  accentLight: "rgba(37, 99, 235, 0.10)",
  textDark: "#1f2430",
  textMedium: "#5b6474",
  textLight: "#8a93a3",
  textBubble: "#1f2430",
  bgIconHeader: "#5b6474",
  fgIconHeader: "#ffffff",
  textHeader: "#5b6474",
  textHeaderSelected: "#ffffff",
  bgCell: "#ffffff",
  bgCellMedium: "#f7f8fa",
  bgHeader: "#f7f8fa",
  bgHeaderHasFocus: "#eef0f4",
  bgHeaderHovered: "#eef0f4",
  bgBubble: "#eef0f4",
  bgBubbleSelected: "#ffffff",
  bgSearchResult: "#fff6c2",
  borderColor: "#e6e8ee",
  horizontalBorderColor: "#eef0f4",
  drilldownBorder: "rgba(0,0,0,0)",
  linkColor: "#2563eb",
  headerFontStyle: "600 12px",
  baseFontStyle: "13px",
  fontFamily: "Inter Variable, ui-sans-serif, system-ui, sans-serif",
  editorFontSize: "13px",
  cellHorizontalPadding: 8,
  cellVerticalPadding: 3,
};

const DARK: Partial<Theme> = {
  ...LIGHT,
  accentColor: "#60a5fa",
  accentLight: "rgba(96, 165, 250, 0.16)",
  textDark: "#e7eaf0",
  textMedium: "#a3abba",
  textLight: "#7a8394",
  textBubble: "#e7eaf0",
  bgIconHeader: "#a3abba",
  fgIconHeader: "#14171d",
  textHeader: "#a3abba",
  textHeaderSelected: "#14171d",
  bgCell: "#1a1d24",
  bgCellMedium: "#1f232b",
  bgHeader: "#1f232b",
  bgHeaderHasFocus: "#272b34",
  bgHeaderHovered: "#272b34",
  bgBubble: "#272b34",
  bgBubbleSelected: "#1a1d24",
  bgSearchResult: "#4a4320",
  borderColor: "#2b303a",
  horizontalBorderColor: "#252931",
};

const EMPTY_SEL: GridSelection = { columns: CompactSelection.empty(), rows: CompactSelection.empty() };

export default function DataGrid<T>({
  rows,
  columns,
  onChange,
  makeRow,
  readonly,
  selectedRow,
  onSelectRow,
  onSelectionRows,
  rowMarkers = true,
  appendLabel,
  testId,
}: DataGridProps<T>) {
  const theme = useTheme();
  const ref = useRef<DataEditorRef>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const [selection, setSelection] = useState<GridSelection>(EMPTY_SEL);
  const [widths, setWidths] = useState<Record<string, number>>({});
  const editable = !readonly && Boolean(onChange);

  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (selectedRow !== null && selectedRow !== undefined && selectedRow >= 0 && selectedRow < rows.length) {
      ref.current?.scrollTo(0, selectedRow, "vertical", 0, 0, { vAlign: "center" });
    }
  }, [selectedRow, rows.length]);

  const gridColumns = useMemo<GridColumn[]>(
    () => columns.map((c) => ({ id: c.id, title: c.title, width: widths[c.id] ?? c.width ?? 120 })),
    [columns, widths],
  );

  const getCellContent = useCallback(
    ([col, row]: Item): GridCell => {
      const c = columns[col];
      const r = rows[row];
      if (!c || r === undefined) return { kind: GridCellKind.Text, data: "", displayData: "", allowOverlay: false };
      const ro = !editable || c.readonly || !c.set;
      const invalid = c.invalid?.(r);
      const muted = c.muted?.(r);
      const themeOverride = invalid
        ? { bgCell: theme === "dark" ? "#3a1f22" : "#fdecec", textDark: theme === "dark" ? "#ff9b9b" : "#b42318" }
        : muted
          ? { textDark: theme === "dark" ? "#6b7383" : "#9aa1ae" }
          : undefined;
      if (c.kind === "boolean") {
        return { kind: GridCellKind.Boolean, data: Boolean(c.get(r)), allowOverlay: false, readonly: ro, themeOverride };
      }
      const raw = String(c.get(r) ?? "");
      return {
        kind: GridCellKind.Text,
        data: raw,
        displayData: c.display ? c.display(r) : raw,
        allowOverlay: !ro,
        readonly: ro,
        contentAlign: c.kind === "number" ? "right" : "left",
        themeOverride,
      };
    },
    [columns, rows, editable, theme],
  );

  const applyEdits = useCallback(
    (edits: { location: Item; value: string | boolean }[]) => {
      if (!onChange) return;
      const next = [...rows];
      let changed = false;
      for (const { location, value } of edits) {
        const [col, row] = location;
        const c = columns[col];
        if (!c?.set || c.readonly) continue;
        while (row >= next.length) {
          if (!makeRow) break;
          next.push(makeRow());
        }
        if (row >= next.length) continue;
        const updated = c.set(next[row], value);
        if (updated) {
          next[row] = updated;
          changed = true;
        }
      }
      if (changed) onChange(next);
    },
    [columns, makeRow, onChange, rows],
  );

  const onCellsEdited = useCallback(
    (items: readonly { location: Item; value: EditableGridCell }[]) => {
      applyEdits(
        items.map(({ location, value }) => ({
          location,
          value: value.kind === GridCellKind.Boolean ? Boolean(value.data) : String(value.data ?? ""),
        })),
      );
      return true;
    },
    [applyEdits],
  );

  const onPaste = useCallback(
    (target: Item, values: readonly (readonly string[])[]) => {
      const edits: { location: Item; value: string | boolean }[] = [];
      values.forEach((line, i) =>
        line.forEach((v, j) => {
          const col = target[0] + j;
          if (col >= columns.length) return;
          const c = columns[col];
          const val = c.kind === "boolean" ? ["1", "true", "x", "ναι", "yes"].includes(v.trim().toLowerCase()) : v;
          edits.push({ location: [col, target[1] + i], value: val });
        }),
      );
      applyEdits(edits);
      return false;
    },
    [applyEdits, columns],
  );

  const getRowThemeOverride = useCallback(
    (row: number) =>
      row === selectedRow ? { bgCell: theme === "dark" ? "#1e2a40" : "#eaf1ff", bgCellMedium: theme === "dark" ? "#1e2a40" : "#eaf1ff" } : undefined,
    [selectedRow, theme],
  );

  return (
    <div ref={boxRef} className="relative h-full min-h-0 w-full overflow-hidden" data-testid={testId}>
      {size.w > 0 && size.h > 0 && (
        <DataEditor
          ref={ref}
          width={size.w}
          height={size.h}
          theme={theme === "dark" ? DARK : LIGHT}
          columns={gridColumns}
          rows={rows.length}
          getCellContent={getCellContent}
          getCellsForSelection
          onCellsEdited={editable ? onCellsEdited : undefined}
          onPaste={editable ? onPaste : false}
          rowMarkers={rowMarkers ? (editable ? "both" : "number") : "none"}
          smoothScrollX
          smoothScrollY
          rowHeight={30}
          headerHeight={32}
          gridSelection={selection}
          onGridSelectionChange={(s) => {
            setSelection(s);
            const rowsSel = s.rows.toArray();
            onSelectionRows?.(rowsSel);
            if (s.current) onSelectRow?.(s.current.cell[1]);
            else if (rowsSel.length === 1) onSelectRow?.(rowsSel[0]);
          }}
          getRowThemeOverride={getRowThemeOverride}
          onColumnResize={(c, w) => setWidths((prev) => ({ ...prev, [c.id ?? c.title]: w }))}
          trailingRowOptions={editable && makeRow ? { hint: appendLabel ?? "+", sticky: true, tint: true } : undefined}
          onRowAppended={
            editable && makeRow
              ? async () => {
                  onChange?.([...rows, makeRow()]);
                  return "bottom" as const;
                }
              : undefined
          }
          keybindings={{ search: true, selectAll: true, copy: true, paste: true, downFill: true, rightFill: true }}
          fillHandle={editable}
        />
      )}
    </div>
  );
}
