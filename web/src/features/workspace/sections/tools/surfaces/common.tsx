// Shared parts of the "Ανάγλυφο" tools: the surface source (which project points, breaklines,
// boundary, trimming), the surface statistics, issue lists and DXF/CSV downloads.
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown, Download, Info } from "lucide-react";
import { useCallback, useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSession, useStore } from "@/data/session";
import { ApiError } from "@/lib/api";
import { apiErrorMessage } from "@/lib/apiErrors";
import { formatArea } from "@/lib/geometry";
import {
  breaklinesFrom,
  filterPoints,
  MAX_SURFACE_POINTS,
  type PlanXY,
  type SourcePoint,
  type SurfaceExportRequest,
  type SurfaceResult,
  type SurfaceSpec,
  surfacesApi,
  toSurfacePoints,
} from "@/lib/surfacesApi";
import type { Issue, PointKind } from "@/lib/types";
import { cn, downloadBlob, fmtNum, parseNum } from "@/lib/utils";
import { issueText } from "../../../issues";
import { useWorkspace } from "../../../useWorkspace";
import { KV, NumberField, parsePointList, PointListField, useProjectPoints } from "../shared";
import { type SurfaceSettings, useSurfaceSettings } from "./store";

const KINDS: PointKind[] = ["control", "traverse", "detail"];

/** Project points with kind and code: computed points first, control points otherwise. */
export function useSourcePoints(): SourcePoint[] {
  const ws = useWorkspace();
  return useMemo(() => {
    const m = new Map<string, SourcePoint>();
    for (const p of ws.data.control_points) {
      if (p.name && Number.isFinite(p.x) && Number.isFinite(p.y))
        m.set(p.name, { name: p.name, x: p.x, y: p.y, z: p.z ?? null, kind: "control", code: p.code ?? null });
    }
    for (const p of ws.result?.points ?? []) m.set(p.name, { name: p.name, x: p.x, y: p.y, z: p.z, kind: p.kind, code: p.code ?? null });
    return [...m.values()];
  }, [ws.data.control_points, ws.result]);
}

export interface SurfaceSource {
  spec: SurfaceSpec;
  settings: SurfaceSettings;
  update: (patch: Partial<SurfaceSettings>) => void;
  selected: SourcePoint[];
  withZ: number;
  lineCodes: string[];
  boundary: PlanXY[] | null;
  /** why the surface cannot be computed yet (null = ready) */
  problem: string | null;
}

export function useSurfaceSource(): SurfaceSource {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const [settings, update] = useSurfaceSettings(ws.projectId);
  const source = useSourcePoints();
  const named = useProjectPoints();
  return useMemo(() => {
    const selected = filterPoints(source, settings);
    const withZ = selected.filter((p) => p.z !== null && Number.isFinite(p.z)).length;
    const linework = ws.result?.linework ?? [];
    const lineCodes = [...new Set(linework.map((l) => l.code))].sort();
    const b = parsePointList(settings.boundary, named);
    const boundary = b.pts.length ? b.pts.map((p) => ({ x: p.x, y: p.y })) : null;
    const maxEdge = parseNum(settings.maxEdge);
    let problem: string | null = null;
    if (withZ < 3) problem = t("surfaces.needPoints");
    else if (selected.length > MAX_SURFACE_POINTS) problem = t("surfaces.tooMany", { max: MAX_SURFACE_POINTS });
    else if (b.bad.length) problem = t("surfaces.boundaryBad", { lines: b.bad.slice(0, 5).join(", ") });
    else if (boundary && boundary.length < 3) problem = t("surfaces.boundaryShort");
    const spec: SurfaceSpec = {
      points: toSurfacePoints(selected),
      breaklines: breaklinesFrom(linework, settings.breaklineCodes),
      boundary: boundary && boundary.length >= 3 ? boundary : null,
      max_edge: maxEdge !== null && maxEdge > 0 ? maxEdge : null,
    };
    return { spec, settings, update, selected, withZ, lineCodes, boundary, problem };
  }, [source, settings, update, named, ws.result, t]);
}

/** Collapsible panel with the surface settings shared by every tab. */
export function SurfaceSourcePanel({ src }: { src: SurfaceSource }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const { settings, update } = src;
  const id = useId();
  const toggleKind = (k: PointKind) =>
    update({ kinds: settings.kinds.includes(k) ? settings.kinds.filter((x) => x !== k) : [...settings.kinds, k] });
  const toggleLine = (c: string) =>
    update({ breaklineCodes: settings.breaklineCodes.includes(c) ? settings.breaklineCodes.filter((x) => x !== c) : [...settings.breaklineCodes, c] });
  return (
    <div className="rounded-xl border bg-surface">
      <button type="button" className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left" aria-expanded={open} onClick={() => setOpen(!open)} data-testid="surf-source-toggle">
        <span>
          <span className="block text-sm font-medium">{t("surfaces.source")}</span>
          <span className="block text-xs text-muted tabular">
            {t("surfaces.sourceSummary", { used: src.withZ, total: src.selected.length })} ·{" "}
            {t("surfaces.sourceExtras", { breaklines: src.spec.breaklines?.length ?? 0, boundary: src.spec.boundary ? t("surfaces.yes") : t("surfaces.no") })}
          </span>
        </span>
        <ChevronDown className={cn("size-4 shrink-0 text-muted transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="grid gap-4 border-t px-4 py-4 lg:grid-cols-2">
          <div className="space-y-3">
            <div className="space-y-1.5">
              <span className="text-sm font-medium">{t("surfaces.kinds")}</span>
              <div className="flex flex-wrap gap-4">
                {KINDS.map((k) => (
                  <label key={k} className="flex items-center gap-2 text-sm">
                    <Checkbox checked={settings.kinds.includes(k)} onCheckedChange={() => toggleKind(k)} />
                    {t(`surfaces.kind.${k}`)}
                  </label>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor={`${id}-only`}>{t("surfaces.onlyCodes")}</Label>
                <Input id={`${id}-only`} value={settings.onlyCodes} onChange={(e) => update({ onlyCodes: e.target.value })} placeholder={t("surfaces.codesHint")} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`${id}-excl`}>{t("surfaces.excludeCodes")}</Label>
                <Input id={`${id}-excl`} value={settings.excludeCodes} onChange={(e) => update({ excludeCodes: e.target.value })} placeholder={t("surfaces.codesHint")} />
              </div>
            </div>
            <div className="space-y-1.5">
              <span className="text-sm font-medium">{t("surfaces.breaklines")}</span>
              {src.lineCodes.length === 0 ? (
                <p className="text-xs text-muted">{t("surfaces.noLinework")}</p>
              ) : (
                <div className="flex flex-wrap gap-3">
                  {src.lineCodes.map((c) => (
                    <label key={c} className="flex items-center gap-2 text-sm">
                      <Checkbox checked={settings.breaklineCodes.includes(c)} onCheckedChange={() => toggleLine(c)} />
                      {c}
                    </label>
                  ))}
                </div>
              )}
            </div>
            <div>
              <NumberField label={t("surfaces.maxEdge")} suffix="m" value={settings.maxEdge} onChange={(v) => update({ maxEdge: v })} />
              <p className="mt-1 text-xs text-muted">{t("surfaces.maxEdgeHint")}</p>
            </div>
          </div>
          <PointListField label={t("surfaces.boundary")} value={settings.boundary} onChange={(v) => update({ boundary: v })} hint={t("surfaces.boundaryHint")} />
        </div>
      )}
    </div>
  );
}

export function IssueList({ issues }: { issues: Issue[] }) {
  if (!issues.length) return null;
  return (
    <ul className="space-y-1.5" data-testid="surf-issues">
      {issues.map((i, k) => (
        <li key={k} className={cn("flex items-start gap-2 rounded-lg px-3 py-2 text-xs", i.severity === "info" ? "bg-surface-sunken text-muted" : "bg-warning-subtle text-warning")}>
          {i.severity === "info" ? <Info className="mt-0.5 size-3.5 shrink-0" /> : <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />}
          <span>{issueText(i)}</span>
        </li>
      ))}
    </ul>
  );
}

export function SurfaceStatsView({ s }: { s: SurfaceResult }) {
  const { t } = useTranslation();
  const st = s.stats;
  return (
    <div className="space-y-3">
      <KV
        items={[
          { k: t("surfaces.stats.points"), v: st.vertices, strong: true },
          { k: t("surfaces.stats.triangles"), v: st.triangles },
          { k: t("surfaces.stats.zRange"), v: `${fmtNum(st.z_min, 3)} – ${fmtNum(st.z_max, 3)} m` },
          { k: t("surfaces.stats.area2d"), v: formatArea(st.area_2d) },
          { k: t("surfaces.stats.area3d"), v: formatArea(st.area_3d) },
          ...(st.points_without_z ? [{ k: t("surfaces.stats.withoutZ"), v: st.points_without_z }] : []),
          ...(st.duplicates_merged ? [{ k: t("surfaces.stats.merged"), v: st.duplicates_merged }] : []),
          ...(st.breakline_segments ? [{ k: t("surfaces.stats.breaklines"), v: st.breakline_segments }] : []),
          ...(st.trimmed_triangles ? [{ k: t("surfaces.stats.trimmed"), v: st.trimmed_triangles }] : []),
        ]}
      />
      <IssueList issues={s.issues} />
    </div>
  );
}

/** DXF/CSV download through /v1/surfaces/export with the plan gating of the export dialog. */
export function useSurfaceExport() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const store = useStore();
  const { mode } = useSession();
  const wsId = useQuery({ queryKey: ["workspace-id", mode], queryFn: () => store.workspaceId(), staleTime: Infinity });
  const [busy, setBusy] = useState<string | null>(null);
  const download = useCallback(
    async (req: Omit<SurfaceExportRequest, "workspace_id" | "project_id" | "project_name">) => {
      setBusy(req.format);
      try {
        const { blob, filename } = await surfacesApi.exportFile({
          ...req,
          project_name: ws.data.meta.name || "surface",
          workspace_id: wsId.data ?? null,
          project_id: store.kind === "supabase" ? ws.projectId : null,
        });
        downloadBlob(blob, filename);
        toast.success(t("exp.done", { file: filename }));
      } catch (e) {
        if (e instanceof ApiError && (e.status === 402 || e.code === "plan_required")) toast.warning(t("exp.upgrade"));
        else toast.error(t("errors.api", { message: apiErrorMessage(e, t) }));
      } finally {
        setBusy(null);
      }
    },
    [t, ws.data.meta.name, ws.projectId, wsId.data, store.kind],
  );
  return { busy, download };
}

export function DownloadButtons({ onDxf, onCsv, busy }: { onDxf?: () => void; onCsv?: () => void; busy: string | null }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap gap-2">
      {onDxf && (
        <Button size="sm" variant="outline" onClick={onDxf} disabled={busy !== null} data-testid="surf-dxf">
          <Download /> {t("surfaces.downloadDxf")}
        </Button>
      )}
      {onCsv && (
        <Button size="sm" variant="outline" onClick={onCsv} disabled={busy !== null} data-testid="surf-csv">
          <Download /> {t("surfaces.downloadCsv")}
        </Button>
      )}
    </div>
  );
}

/** Boundary ring for the map overlay. */
export function boundaryPolygons(src: SurfaceSource): [number, number][][] {
  return src.spec.boundary ? [src.spec.boundary.map((p) => [p.x, p.y] as [number, number])] : [];
}
