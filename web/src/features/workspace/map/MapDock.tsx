import { Map as MapIcon, PanelRightClose } from "lucide-react";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useWorkspace } from "../useWorkspace";

const MapPanel = lazy(() => import("./MapPanel"));

const MIN_WIDTH = 280;
const MIN_CONTENT = 480;
const DEFAULT_WIDTH = 460;

function useMapWidth() {
  const [width, setWidth] = useState(() => {
    try {
      return Number(localStorage.getItem("ats-map-width")) || DEFAULT_WIDTH;
    } catch {
      return DEFAULT_WIDTH;
    }
  });
  const dragging = useRef(false);
  const start = (e: React.PointerEvent) => {
    dragging.current = true;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const move = (e: React.PointerEvent) => {
    if (!dragging.current) return;
    setWidth(Math.max(MIN_WIDTH, Math.min(window.innerWidth - MIN_CONTENT, window.innerWidth - e.clientX)));
  };
  const end = () => {
    dragging.current = false;
    try {
      localStorage.setItem("ats-map-width", String(Math.round(width)));
    } catch {
      /* ignore */
    }
  };
  return { width, handlers: { onPointerDown: start, onPointerMove: move, onPointerUp: end, onPointerCancel: end } };
}

/**
 * The map beside (wide screens) or below (narrow) the page. Closed, it leaves a slim rail to
 * reopen it; once opened it stays mounted while hidden, so zoom and position survive page changes.
 */
export function MapDock() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const { width, handlers } = useMapWidth();
  const [mounted, setMounted] = useState(ws.mapVisible);
  useEffect(() => {
    if (ws.mapVisible) setMounted(true);
  }, [ws.mapVisible]);
  const o = ws.overlay;
  const hasOverlay = o.points.length + o.lines.length + o.polygons.length > 0;

  return (
    <>
      {!ws.mapVisible && (
        <Tooltip content={hasOverlay ? t("ws.mapHasGeometry") : t("ws.showMap")}>
          <button
            type="button"
            onClick={() => ws.setMapVisible(true)}
            aria-label={t("ws.showMap")}
            data-testid="map-rail"
            className="hidden w-9 shrink-0 cursor-pointer flex-col items-center gap-2 border-l bg-bg py-3 text-xs font-medium text-muted transition-colors hover:bg-surface-sunken hover:text-fg lg:flex"
          >
            <MapIcon className="size-4" />
            <span className="[writing-mode:vertical-rl]">{t("ws.map")}</span>
            {hasOverlay && <span className="size-2 rounded-full bg-accent" data-testid="map-rail-dot" />}
          </button>
        </Tooltip>
      )}
      {mounted && (
        <>
          <div className={cn("relative hidden w-px shrink-0 cursor-col-resize bg-border", ws.mapVisible && "lg:block")} {...handlers}>
            <div className="absolute inset-y-0 -left-1.5 -right-1.5 hover:bg-accent-subtle" />
          </div>
          <aside
            className={cn("h-80 shrink-0 flex-col border-t lg:h-auto lg:border-t-0 lg:[width:var(--map-w)]", ws.mapVisible ? "flex" : "hidden")}
            style={{ "--map-w": `${width}px` } as React.CSSProperties}
            aria-label={t("ws.map")}
            aria-hidden={!ws.mapVisible}
          >
            <div className="flex h-9 shrink-0 items-center gap-2 border-b bg-surface pl-3 pr-1 text-xs font-medium text-muted">
              <MapIcon className="size-3.5" />
              {t("ws.map")}
              <Tooltip content={t("ws.hideMap")}>
                <Button variant="ghost" size="icon-sm" className="ml-auto" onClick={() => ws.setMapVisible(false)} aria-label={t("ws.hideMap")} data-testid="map-close">
                  <PanelRightClose />
                </Button>
              </Tooltip>
            </div>
            <div className="relative min-h-0 flex-1">
              <div className="absolute inset-0">
                <Suspense fallback={<Skeleton className="h-full rounded-none" />}>
                  <MapPanel />
                </Suspense>
              </div>
            </div>
          </aside>
        </>
      )}
    </>
  );
}
