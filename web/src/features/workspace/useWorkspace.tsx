import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { useStore } from "@/data/session";
import { toProjectInput, type ProjectData, type StoredRun } from "@/data/store";
import { api, ApiError } from "@/lib/api";
import type { ProjectInput, ProjectResult } from "@/lib/types";
import type { Section } from "./sections";

export type ComputeStatus = "idle" | "computing" | "ok" | "error" | "offline";
type Dialog = "import" | "export" | "settings" | null;
type SaveKey = "control_points" | "setups" | "traverses" | "settings";
export type WorkspacePatch = Partial<Omit<ProjectData, "meta">> & { meta?: Partial<ProjectData["meta"]> };

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
      }
      setSaveState(pending.current.size ? "dirty" : "saved");
      void qc.invalidateQueries({ queryKey: ["projects"] });
    } catch (e) {
      keys.forEach((k) => pending.current.add(k));
      setSaveState("dirty");
      toast.error(`${t("errors.generic")}: ${(e as Error).message}`);
    }
  }, [projectId, qc, store, t]);

  const update = useCallback(
    (patch: WorkspacePatch) => {
      setData((d) => ({ ...d, ...patch, meta: { ...d.meta, ...(patch.meta ?? {}) } }));
      (Object.keys(patch) as (keyof typeof patch)[]).forEach((k) => {
        if (k === "meta") pending.current.add("settings");
        else pending.current.add(k as SaveKey);
      });
      setSaveState("dirty");
      window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(() => void flush(), 700);
    },
    [flush],
  );

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
      setError(err.message);
      setStatus(err.status === 0 ? "offline" : "error");
    }
  }, []);

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

  const value: Workspace = {
    projectId,
    data,
    input,
    update,
    saveState,
    result,
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
