import { AlertTriangle, FileText, Loader2, Trash2, UploadCloud, XCircle } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useStore } from "@/data/session";
import type { StoredControlPoint, StoredSetup } from "@/data/store";
import { api } from "@/lib/api";
import type { DisplayAngleUnit, ParseResult, RawFormat } from "@/lib/types";
import { cn, uid } from "@/lib/utils";
import { useWorkspace } from "../useWorkspace";

const FORMAT_LABEL: Record<RawFormat, string> = {
  leica_gsi: "Leica GSI",
  trimble_jobxml: "Trimble JobXML",
  landxml: "LandXML",
  nikon_raw: "Nikon RAW",
  rw5: "Carlson RW5",
  csv: "CSV",
};

interface Item {
  key: string;
  file: File;
  status: "parsing" | "ok" | "error";
  result?: ParseResult;
  error?: string;
}

export function ImportDialog() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const store = useStore();
  const open = ws.dialog === "import";
  const [items, setItems] = useState<Item[]>([]);
  const [unit, setUnit] = useState<"auto" | DisplayAngleUnit>("auto");
  const [importControl, setImportControl] = useState(true);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const parseFile = useCallback(
    async (file: File, key: string, u: "auto" | DisplayAngleUnit) => {
      try {
        const result = await api.parse(file, { angle_unit: u === "auto" ? null : u });
        setItems((prev) => prev.map((i) => (i.key === key ? { ...i, status: "ok", result } : i)));
      } catch (e) {
        setItems((prev) => prev.map((i) => (i.key === key ? { ...i, status: "error", error: (e as Error).message } : i)));
      }
    },
    [],
  );

  const addFiles = (files: FileList | File[]) => {
    const list = [...files].map((file) => ({ key: uid(), file, status: "parsing" as const }));
    setItems((prev) => [...prev, ...list]);
    list.forEach((i) => void parseFile(i.file, i.key, unit));
  };

  const reparseAll = (u: "auto" | DisplayAngleUnit) => {
    setUnit(u);
    setItems((prev) => prev.map((i) => ({ ...i, status: "parsing", result: undefined, error: undefined })));
    items.forEach((i) => void parseFile(i.file, i.key, u));
  };

  const close = () => {
    ws.setDialog(null);
    setItems([]);
  };

  const ok = items.filter((i) => i.status === "ok" && i.result);
  const totals = ok.reduce(
    (a, i) => ({ setups: a.setups + i.result!.stats.setups, observations: a.observations + i.result!.stats.observations, control: a.control + i.result!.control_points.length }),
    { setups: 0, observations: 0, control: 0 },
  );

  const doImport = async () => {
    setBusy(true);
    try {
      const newSetups: StoredSetup[] = [];
      let control = [...ws.data.control_points];
      for (const it of ok) {
        const r = it.result!;
        let rawId: string | null = null;
        try {
          rawId = await store.uploadRawFile(ws.projectId, it.file, r);
        } catch (e) {
          toast.warning(`${it.file.name}: ${(e as Error).message}`);
        }
        for (const s of r.setups) {
          newSetups.push({
            ...s,
            id: uid(),
            raw_file_id: rawId,
            observations: s.observations.map((o) => ({ ...o, id: uid(), excluded: o.excluded ?? false })),
          });
        }
        if (importControl && r.control_points.length) {
          const byName = new Map(control.map((c) => [c.name, c]));
          for (const cp of r.control_points) {
            if (!byName.has(cp.name)) byName.set(cp.name, { ...cp, id: uid() } as StoredControlPoint);
          }
          control = [...byName.values()];
        }
      }
      ws.update({ setups: [...ws.data.setups, ...newSetups], ...(importControl ? { control_points: control } : {}) });
      toast.success(t("imp.imported", { setups: totals.setups, observations: totals.observations }));
      close();
      ws.goTo("observations");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent wide>
        <DialogHeader>
          <DialogTitle>{t("imp.title")}</DialogTitle>
          <DialogDescription>{t("imp.description")}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div
            role="button"
            tabIndex={0}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
            }}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors",
              drag ? "border-primary bg-primary/5" : "hover:border-foreground/20 hover:bg-accent/40",
            )}
            data-testid="dropzone"
          >
            <UploadCloud className="size-7 text-muted-foreground" />
            <div className="text-sm font-medium">{t("imp.drop")}</div>
            <div className="text-xs text-muted-foreground">{t("imp.formats")}</div>
            <input
              ref={inputRef}
              type="file"
              multiple
              className="hidden"
              accept=".gsi,.jxl,.xml,.raw,.rw5,.csv,.txt"
              onChange={(e) => {
                if (e.target.files?.length) addFiles(e.target.files);
                e.target.value = "";
              }}
              data-testid="file-input"
            />
          </div>
          <p className="flex items-start gap-2 rounded-lg bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> {t("imp.exportFirst")}
          </p>
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Label>{t("imp.angleUnit")}</Label>
              <Select<"auto" | DisplayAngleUnit>
                className="w-44"
                value={unit}
                onValueChange={reparseAll}
                options={[
                  { value: "auto", label: t("imp.auto") },
                  { value: "gon", label: t("units.gon") },
                  { value: "deg", label: t("units.deg") },
                  { value: "dms", label: t("units.dms") },
                ]}
              />
            </div>
            {totals.control > 0 && (
              <label className="flex items-center gap-2 text-sm">
                <Checkbox checked={importControl} onCheckedChange={(c) => setImportControl(c === true)} />
                {t("imp.importControl")}
              </label>
            )}
          </div>

          {items.length > 0 && (
            <ul className="divide-y rounded-xl border">
              {items.map((i) => (
                <li key={i.key} className="flex items-start gap-3 px-3 py-2.5">
                  <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-medium">{i.file.name}</span>
                      {i.result && <Badge>{FORMAT_LABEL[i.result.format] ?? i.result.format}</Badge>}
                      {i.result?.angle_unit && <Badge variant="secondary">{t(`units.${i.result.angle_unit}`)}</Badge>}
                    </div>
                    {i.status === "parsing" && (
                      <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Loader2 className="size-3 animate-spin" /> {t("imp.parsing")}
                      </div>
                    )}
                    {i.status === "error" && (
                      <div className="mt-0.5 flex items-center gap-1.5 text-xs text-destructive">
                        <XCircle className="size-3" /> {t("imp.failed")}: {i.error}
                      </div>
                    )}
                    {i.result && (
                      <div className="mt-0.5 text-xs text-muted-foreground tabular">
                        {t("imp.stats", i.result.stats)}
                        {i.result.control_points.length > 0 && ` · ${t("imp.controlFound", { count: i.result.control_points.length })}`}
                      </div>
                    )}
                    {i.result && i.result.warnings.length > 0 && (
                      <details className="mt-1 text-xs">
                        <summary className="cursor-pointer text-warning">
                          {t("imp.warnings")} ({i.result.warnings.length})
                        </summary>
                        <ul className="mt-1 max-h-28 list-disc space-y-0.5 overflow-y-auto pl-5 text-muted-foreground">
                          {i.result.warnings.map((w, k) => (
                            <li key={k}>{w}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </div>
                  <Button variant="ghost" size="icon-sm" onClick={() => setItems((p) => p.filter((x) => x.key !== i.key))} aria-label={t("imp.remove")}>
                    <Trash2 />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </DialogBody>
        <DialogFooter>
          {ok.length > 0 && <span className="mr-auto text-xs text-muted-foreground tabular">{t("imp.stats", totals)}</span>}
          <Button variant="ghost" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button onClick={doImport} disabled={busy || ok.length === 0 || items.some((i) => i.status === "parsing")} data-testid="btn-do-import">
            {busy && <Loader2 className="animate-spin" />} {t("imp.import")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
