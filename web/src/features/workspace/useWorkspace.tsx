import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { useStore } from "@/data/session";
import { toProjectInput, type ProjectData, type StoredRun } from "@/data/store";
import { api, ApiError } from "@/lib/api";
import { apiErrorMessage } from "@/lib/apiErrors";
import type { ProjectInput, ProjectResult } from "@/lib/types";
import type { Section } from "./sections";

export type ComputeStatus = "idle" | "computing" | "ok" | "error" | "offline";
type Dialog = "import" | "export" | "settings" | null;
type SaveKey = "control_points" | "setups" | "traverses" | "settings" | "extras";
export type WorkspacePatch = Partial<Omit<ProjectData, "meta">> & { meta?: Partial<ProjectData["meta"]> };

/** Geometry drawn on the map by tools (COGO inputs/results, levelling, etc.). EGSA87 metres. */
export interface MapOverlay {
  points: { x: number; y: number; label?: string; role: "input" | "result" }[];
  lines: [number, number][][];
  polygons: [number, number][][];
}
export const EMPTY_OVERLAY: MapOverlay = { points: [], lines: [], polygons: [] };

/** A point picked on the map: a project point (with name) or a free coordinate. */
export interface PickedPoint {
  name?: string;
  x: number;
  y: number;
  z?: number | null;
}

type Snapshot = Pick<ProjectData, "settings" | "control_points" | "setups" | "traverses" | "extras"> & {
  angle_unit: ProjectData["meta"]["angle_unit"];
};
const HISTORY_LIMIT = 100;

function readLS(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

export interface Workspace {
  projectId: string;
  data: ProjectData;
  input: ProjectInput;
  update: (patch: WorkspacePatch) => void;
  saveState: "saved" | "saving" | "dirty";
  result: ProjectResult | null;
  status: ComputeStatus;
  error: string | null;
  compute: () => void;
  autoCompute: boolean;
  setAutoCompute: (v: boolean) => void;
  saveRun: () => Promise<void>;
  lastRun: StoredRun | null;
  selected: string | null;
  setSelected: (name: string | null) => void;
  mapVisible: boolean;
  setMapVisible: (v: boolean) => void;
  dialog: Dialog;
  setDialog: (d: Dialog) => void;
  section: Section;
  goTo: (s: Section, opts?: { setup?: string | null; traverse?: string | null }) => void;
  focus: { setup?: string | null; traverse?: string | null };
  /** live result, even while an older run is being viewed */
  liveResult: ProjectResult | null;
  viewing: StoredRun | null;
  setViewing: (r: StoredRun | null) => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  overlay: MapOverlay;
  setOverlay: (o: MapOverlay) => void;
  /** when set, a map click calls this instead of selecting */
  pick: ((p: PickedPoint) => void) | null;
  setPick: (fn: ((p: PickedPoint) => void) | null) => void;
  ellipseScale: number;
  setEllipseScale: (v: number) => void;
  runsVersion: number;
}

const Ctx = createContext<Workspace | null>(null);

export function useWorkspace(): Workspace {
  const c = useContext(Ctx);
  if (!c) throw new Error("WorkspaceProvider missing");
  return c;
}

export function useProjectQuery(projectId: string) {
  const store = useStore();
  return useQuery({
    queryKey: ["project", store.kind, projectId],
    queryFn: async () => {
      const [data, run] = await Promise.all([store.getProject(projectId), store.latestRun(projectId)]);
      return { data, run };
    },
    staleTime: Infinity,
    gcTime: 0,
  });
}

export function WorkspaceProvider({
  initial,
  initialRun,
  section,
  onSection,
  children,
}: {
  initial: ProjectData;
  initialRun: StoredRun | null;
  section: Section;
  onSection: (s: Section) => void;
  children: React.ReactNode;
}) {
  const store = useStore();
  const qc = useQueryClient();
  const { t } = useTranslation();
  const projectId = initial.meta.id;
  const [data, setData] = useState<ProjectData>(initial);
  const [saveState, setSaveState] = useState<"saved" | "saving" | "dirty">("saved");
  const [result, setResult] = useState<ProjectResult | null>(initialRun?.result ?? null);
  const [lastRun, setLastRun] = useState<StoredRun | null>(initialRun);
  const [status, setStatus] = useState<ComputeStatus>(initialRun ? "ok" : "idle");
  const [error, setError] = useState<string | null>(null);
  const [autoCompute, setAutoComputeState] = useState(() => readLS("ats-autocompute", "1") === "1");
  const [selected, setSelected] = useState<string | null>(null);
  const [mapVisible, setMapVisibleState] = useState(() => readLS("ats-map", "1") === "1");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [focus, setFocus] = useState<{ setup?: string | null; traverse?: string | null }>({});
  const [viewing, setViewing] = useState<StoredRun | null>(null);
  const [overlay, setOverlay] = useState<MapOverlay>(EMPTY_OVERLAY);
  const [pick, setPickState] = useState<((p: PickedPoint) => void) | null>(null);
  const setPick = useCallback((fn: ((p: PickedPoint) => void) | null) => setPickState(() => fn), []);
  const [ellipseScale, setEllipseScaleState] = useState(() => Number(readLS("ats-ellipse-scale", "100")) || 100);
  const setEllipseScale = useCallback((v: number) => {
    setEllipseScaleState(v);
    try {
      localStorage.setItem("ats-ellipse-scale", String(v));
    } catch {
      /* ignore */
    }
  }, []);
  const [runsVersion, setRunsVersion] = useState(0);
  const past = useRef<Snapshot[]>([]);
  const future = useRef<Snapshot[]>([]);
  const lastPush = useRef(0);
  const [historyTick, setHistoryTick] = useState(0);

  // ------------------------------------------------------------ persistence
  const pending = useRef(new Set<SaveKey>());
  const dataRef = useRef(data);
  dataRef.current = data;
  const saveTimer = useRef<number | undefined>(undefined);

  const flush = useCallback(async () => {
    const keys = [...pending.current];
    pending.current.clear();
    if (!keys.length) return;
    setSaveState("saving");
    const d = dataRef.current;
    try {
      for (const k of keys) {
        if (k === "control_points") await store.saveControlPoints(projectId, d.control_points);
        if (k === "setups") await store.saveSetups(projectId, d.setups);
        if (k === "traverses") await store.saveTraverses(projectId, d.traverses);
        if (k === "settings") await store.saveSettings(projectId, d.settings, d.meta.angle_unit);
        if (k === "extras") await store.saveExtras(projectId, d.extras);
      }
      setSaveState(pending.current.size ? "dirty" : "saved");
      void qc.invalidateQueries({ queryKey: ["projects"] });
    } catch (e) {
      keys.forEach((k) => pending.current.add(k));
      setSaveState("dirty");
      toast.error(`${t("errors.generic")}: ${(e as Error).message}`);
    }
  }, [projectId, qc, store, t]);

  const scheduleSave = useCallback(
    (keys: SaveKey[]) => {
      keys.forEach((k) => pending.current.add(k));
      setSaveState("dirty");
      window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(() => void flush(), 700);
    },
    [flush],
  );

  const snapshot = (d: ProjectData): Snapshot => ({
    settings: d.settings,
    control_points: d.control_points,
    setups: d.setups,
    traverses: d.traverses,
    extras: d.extras,
    angle_unit: d.meta.angle_unit,
  });

  const update = useCallback(
    (patch: WorkspacePatch) => {
      // undo history: coalesce rapid edits (typing, drag-fill) into one step
      const now = Date.now();
      if (now - lastPush.current > 600 || past.current.length === 0) {
        past.current.push(snapshot(dataRef.current));
        if (past.current.length > HISTORY_LIMIT) past.current.shift();
      }
      lastPush.current = now;
      future.current = [];
      setHistoryTick((n) => n + 1);
      setData((d) => ({ ...d, ...patch, meta: { ...d.meta, ...(patch.meta ?? {}) } }));
      scheduleSave(
        (Object.keys(patch) as (keyof typeof patch)[]).map((k) => (k === "meta" ? "settings" : (k as SaveKey))),
      );
    },
    [scheduleSave],
  );

  const restore = useCallback(
    (snap: Snapshot) => {
      setData((d) => ({ ...d, ...snap, meta: { ...d.meta, angle_unit: snap.angle_unit } }));
      scheduleSave(["settings", "control_points", "setups", "traverses", "extras"]);
      setHistoryTick((n) => n + 1);
    },
    [scheduleSave],
  );

  const undo = useCallback(() => {
    const prev = past.current.pop();
    if (!prev) return;
    future.current.push(snapshot(dataRef.current));
    lastPush.current = 0;
    restore(prev);
  }, [restore]);

  const redo = useCallback(() => {
    const next = future.current.pop();
    if (!next) return;
    past.current.push(snapshot(dataRef.current));
    lastPush.current = 0;
    restore(next);
  }, [restore]);

  useEffect(() => {
    const onUnload = () => void flush();
    window.addEventListener("beforeunload", onUnload);
    return () => {
      window.removeEventListener("beforeunload", onUnload);
      window.clearTimeout(saveTimer.current);
      void flush();
    };
  }, [flush]);

  // ------------------------------------------------------------ compute
  const input = useMemo(() => toProjectInput(data), [data]);
  const inputKey = useMemo(() => JSON.stringify(input), [input]);
  const abortRef = useRef<AbortController | null>(null);
  const lastComputedKey = useRef<string | null>(null);

  const runCompute = useCallback(async (inp: ProjectInput, key: string) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStatus("computing");
    try {
      const r = await api.compute(inp, ctrl.signal);
      if (ctrl.signal.aborted) return;
      lastComputedKey.current = key;
      setResult(r);
      setError(null);
      setStatus(r.summary.n_errors > 0 ? "error" : "ok");
    } catch (e) {
      if ((e as Error).name === "AbortError" || ctrl.signal.aborted) return;
      const err = e as ApiError;
      const msg = apiErrorMessage(err, t);
      setError(msg);
      setStatus(err.status === 0 ? "offline" : "error");
      if (err.status === 429 || err.status === 413 || err.status === 503) toast.warning(msg, { id: "compute-limit" });
    }
  }, [t]);

  const compute = useCallback(() => void runCompute(input, inputKey), [input, inputKey, runCompute]);

  useEffect(() => {
    if (!autoCompute) return;
    if (lastComputedKey.current === inputKey) return;
    if (input.control_points.length === 0 && input.setups.length === 0) return;
    const h = window.setTimeout(() => void runCompute(input, inputKey), 400);
    return () => window.clearTimeout(h);
  }, [autoCompute, input, inputKey, runCompute]);

  const saveRun = useCallback(async () => {
    if (!result) return;
    try {
      const run = await store.saveRun(projectId, result, data.settings);
      setLastRun(run);
      setRunsVersion((n) => n + 1);
      toast.success(t("ws.runSaved"));
    } catch (e) {
      toast.error((e as Error).message);
    }
  }, [data.settings, projectId, result, store, t]);

  const setAutoCompute = useCallback((v: boolean) => {
    setAutoComputeState(v);
    try {
      localStorage.setItem("ats-autocompute", v ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, []);

  const setMapVisible = useCallback((v: boolean) => {
    setMapVisibleState(v);
    try {
      localStorage.setItem("ats-map", v ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, []);

  const goTo = useCallback(
    (s: Section, opts?: { setup?: string | null; traverse?: string | null }) => {
      setFocus(opts ?? {});
      onSection(s);
    },
    [onSection],
  );

  void historyTick;
  const value: Workspace = {
    projectId,
    data,
    input,
    update,
    saveState,
    result: viewing?.result ?? result,
    liveResult: result,
    viewing,
    setViewing,
    undo,
    redo,
    canUndo: past.current.length > 0,
    canRedo: future.current.length > 0,
    overlay,
    setOverlay,
    pick,
    setPick,
    ellipseScale,
    setEllipseScale,
    runsVersion,
    status,
    error,
    compute,
    autoCompute,
    setAutoCompute,
    saveRun,
    lastRun,
    selected,
    setSelected,
    mapVisible,
    setMapVisible,
    dialog,
    setDialog,
    section,
    goTo,
    focus,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
