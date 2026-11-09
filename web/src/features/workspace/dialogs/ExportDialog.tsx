import { Link } from "@tanstack/react-router";
import { apiErrorMessage } from "@/lib/apiErrors";
import { useQuery } from "@tanstack/react-query";
import { Braces, Check, Download, FileCode2, FileSpreadsheet, FileText, Globe2, Loader2, Lock, MapPinned, Network, Table } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useSession, useStore } from "@/data/session";
import { api, ApiError } from "@/lib/api";
import { ALL_EXPORT_FORMATS, type ExportFormat, type PointKind } from "@/lib/types";
import { cn, downloadBlob } from "@/lib/utils";
import { useWorkspace } from "../useWorkspace";

const ICONS: Record<ExportFormat, React.ReactNode> = {
  csv: <Table />,
  xlsx: <FileSpreadsheet />,
  shp: <MapPinned />,
  dxf: <FileCode2 />,
  pdf: <FileText />,
  landxml: <Network />,
  kml: <Globe2 />,
  geojson: <Braces />,
};

export function ExportDialog() {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const { mode } = useSession();
  const store = useStore();
  const open = ws.dialog === "export";
  const wsId = useQuery({ queryKey: ["workspace-id", mode], queryFn: () => store.workspaceId(), enabled: open, staleTime: Infinity });
  const me = useQuery({
    queryKey: ["me", mode, wsId.data ?? null],
    queryFn: () => api.me(wsId.data),
    enabled: open && !wsId.isLoading,
    retry: 0,
    staleTime: 60_000,
  });
  const allowed = new Set<ExportFormat>(me.data?.export_formats ?? ALL_EXPORT_FORMATS);
  const [formats, setFormats] = useState<Set<ExportFormat>>(new Set(["xlsx", "dxf", "csv"]));
  const [include, setInclude] = useState<Set<PointKind>>(new Set(["control", "traverse", "detail"]));
  const [decimals, setDecimals] = useState(3);
  const [delimiter, setDelimiter] = useState<"," | ";" | "\t" | " ">(",");
  const [header, setHeader] = useState(true);
  const [textHeight, setTextHeight] = useState(0.5);
  const [ellipseScale, setEllipseScale] = useState(1000);
  const lsa = Boolean(ws.result?.adjustment);
  const [busy, setBusy] = useState(false);

  const chosen = [...formats].filter((f) => allowed.has(f));

  const run = async () => {
    setBusy(true);
    try {
      for (const format of ALL_EXPORT_FORMATS.filter((f) => chosen.includes(f))) {
        const { blob, filename } = await api.exportFile({
          format,
          project_name: ws.data.meta.name,
          input: ws.input,
          options: {
            angle_unit: ws.data.meta.angle_unit,
            decimals,
            csv_delimiter: delimiter,
            csv_header: header,
            include: [...include],
            dxf_text_height: textHeight,
            dxf_ellipse_scale: lsa ? ellipseScale : 0,
            language: i18n.language === "en" ? "en" : "el",
          },
          workspace_id: wsId.data ?? null,
        });
        downloadBlob(blob, filename);
        toast.success(t("exp.done", { file: filename }));
      }
      ws.setDialog(null);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 402 || e.code === "plan_required"))
        toast.warning(me.data?.plan === "anonymous" ? t("exp.signupHint") : t("exp.upgrade"));
      else toast.error(t("errors.api", { message: apiErrorMessage(e, t) }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && ws.setDialog(null)}>
      <DialogContent wide>
        <DialogHeader>
          <DialogTitle>{t("exp.title")}</DialogTitle>
          <DialogDescription>{t("exp.description")}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-5">
          <div>
            <Label className="mb-2 block">{t("exp.formats")}</Label>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {ALL_EXPORT_FORMATS.map((f) => {
                const locked = !allowed.has(f);
                const on = formats.has(f) && !locked;
                return (
                  <button
                    key={f}
                    type="button"
                    disabled={locked}
                    aria-pressed={on}
                    data-testid={`fmt-${f}`}
                    onClick={() => {
                      const next = new Set(formats);
                      if (next.has(f)) next.delete(f);
                      else next.add(f);
                      setFormats(next);
                    }}
                    className={cn(
                      "relative flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors [&>svg]:size-4",
                      on ? "border-accent bg-accent-subtle ring-1 ring-accent" : "hover:bg-surface-sunken",
                      locked && "cursor-not-allowed opacity-55",
                    )}
                  >
                    <span className={cn("flex size-8 items-center justify-center rounded-md border bg-surface [&_svg]:size-4", on && "text-accent")}>{ICONS[f]}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium uppercase">{f}</span>
                      <span className="block truncate text-xs text-muted">{t(`exp.fmt.${f}`)}</span>
                    </span>
                    {locked ? <Lock className="text-muted" /> : on ? <Check className="text-accent" /> : null}
                  </button>
                );
              })}
            </div>
            {ALL_EXPORT_FORMATS.some((f) => !allowed.has(f)) && (
              <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                <Lock className="size-3" /> {me.data?.plan === "anonymous" ? t("exp.signupHint") : t("exp.upgrade")}
                {me.data?.plan === "free" && (
                  <Link to="/billing" className="font-medium text-accent hover:underline" onClick={() => ws.setDialog(null)}>
                    {t("billing.upgrade")} →
                  </Link>
                )}
              </p>
            )}
          </div>

          <div>
            <Label className="mb-2 block">{t("exp.include")}</Label>
            <div className="flex flex-wrap gap-4">
              {(["control", "traverse", "detail"] as PointKind[]).map((k) => (
                <label key={k} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={include.has(k)}
                    onCheckedChange={(c) => {
                      const next = new Set(include);
                      if (c === true) next.add(k);
                      else next.delete(k);
                      setInclude(next);
                    }}
                  />
                  {t(`kind.${k}`)}
                </label>
              ))}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="ex-dec">{t("exp.decimals")}</Label>
              <Input id="ex-dec" type="number" min={0} max={6} value={decimals} onChange={(e) => setDecimals(Math.max(0, Math.min(6, Number(e.target.value) || 0)))} />
            </div>
            {formats.has("csv") && (
              <div className="space-y-1.5">
                <Label>{t("exp.delimiter")}</Label>
                <Select<"," | ";" | "\t" | " ">
                  value={delimiter}
                  onValueChange={setDelimiter}
                  options={[
                    { value: ",", label: t("exp.comma") },
                    { value: ";", label: t("exp.semicolon") },
                    { value: "\t", label: t("exp.tab") },
                    { value: " ", label: t("exp.space") },
                  ]}
                />
              </div>
            )}
            {formats.has("dxf") && (
              <div className="space-y-1.5">
                <Label htmlFor="ex-th">{t("exp.textHeight")}</Label>
                <Input id="ex-th" type="number" step={0.1} min={0.05} value={textHeight} onChange={(e) => setTextHeight(Number(e.target.value) || 0.5)} />
              </div>
            )}
            {formats.has("dxf") && lsa && (
              <div className="space-y-1.5">
                <Label htmlFor="ex-es">{t("exp.ellipseScale")}</Label>
                <Input
                  id="ex-es"
                  type="number"
                  step={100}
                  min={0}
                  max={100000}
                  value={ellipseScale}
                  onChange={(e) => setEllipseScale(Math.max(0, Math.min(100000, Number(e.target.value) || 0)))}
                />
              </div>
            )}
          </div>
          {formats.has("csv") && (
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={header} onCheckedChange={setHeader} /> {t("exp.header")}
            </label>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => ws.setDialog(null)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={run} disabled={busy || chosen.length === 0 || include.size === 0} data-testid="btn-download">
            {busy ? <Loader2 className="animate-spin" /> : <Download />} {busy ? t("exp.downloading") : t("exp.download")}
            {chosen.length > 1 && ` (${chosen.length})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
