// Contours drawn on the map by the surface tools. A tiny external store (not tool overlay
// state) so the lines stay on the map while the user switches tools, with a visibility
// toggle in the map's layer menu. Lines belong to one project and are hidden elsewhere.
import { useSyncExternalStore } from "react";

export interface ContourOverlayLine {
  z: number;
  index: boolean;
  /** EGSA87 metres (x = Easting, y = Northing) */
  points: [number, number][];
}

export interface ContourOverlayState {
  projectId: string | null;
  lines: ContourOverlayLine[];
  visible: boolean;
}

let state: ContourOverlayState = { projectId: null, lines: [], visible: true };
const listeners = new Set<() => void>();

function emit(next: ContourOverlayState) {
  state = next;
  listeners.forEach((l) => l());
}

export function setContourOverlay(projectId: string, lines: ContourOverlayLine[]): void {
  emit({ projectId, lines, visible: true });
}

export function setContourVisible(visible: boolean): void {
  emit({ ...state, visible });
}

export function clearContourOverlay(): void {
  emit({ projectId: null, lines: [], visible: true });
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useContourOverlay(): ContourOverlayState {
  return useSyncExternalStore(
    subscribe,
    () => state,
    () => state,
  );
}
