// Surface settings shared by the four "Ανάγλυφο" tabs (tabs unmount when hidden, so the
// settings live outside React), kept per project for the session.
import { useCallback, useSyncExternalStore } from "react";
import type { PointKind } from "@/lib/types";

export interface SurfaceSettings {
  kinds: PointKind[];
  onlyCodes: string;
  excludeCodes: string;
  /** line-work codes whose polylines become breaklines */
  breaklineCodes: string[];
  /** one vertex per line: project point name or "x y" */
  boundary: string;
  /** maximum border edge length (m), empty = no trimming */
  maxEdge: string;
}

export const DEFAULT_SETTINGS: SurfaceSettings = {
  kinds: ["control", "traverse", "detail"],
  onlyCodes: "",
  excludeCodes: "",
  breaklineCodes: [],
  boundary: "",
  maxEdge: "",
};

const byProject = new Map<string, SurfaceSettings>();
const listeners = new Set<() => void>();

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useSurfaceSettings(projectId: string): [SurfaceSettings, (patch: Partial<SurfaceSettings>) => void] {
  const settings = useSyncExternalStore(
    subscribe,
    () => byProject.get(projectId) ?? DEFAULT_SETTINGS,
    () => DEFAULT_SETTINGS,
  );
  const update = useCallback(
    (patch: Partial<SurfaceSettings>) => {
      byProject.set(projectId, { ...(byProject.get(projectId) ?? DEFAULT_SETTINGS), ...patch });
      listeners.forEach((l) => l());
    },
    [projectId],
  );
  return [settings, update];
}
