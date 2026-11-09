// Map of control / traverse / detail points. MapLibre renders points and lines;
// labels are drawn on a 2D canvas overlay (Inter font, Greek-safe, no glyph server).
// An adaptive EGSA87 grid replaces a basemap by default.
import "maplibre-gl/dist/maplibre-gl.css";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, Map as MLMap, StyleSpecification } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { Crosshair, Layers, Maximize2, Ruler, Tag, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Tooltip } from "@/components/ui/tooltip";
import { formatAngle, gridAzimuth } from "@/lib/angles";
import { egsaToLngLat, lngLatToEgsa } from "@/lib/proj";
import { useTheme } from "@/lib/theme";
import type { PointKind } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useWorkspace } from "../useWorkspace";

maplibregl.setWorkerUrl(workerUrl);

type Basemap = "none" | "osm" | "sat";

interface MapPoint {
  name: string;
  x: number;
  y: number;
  z: number | null;
  kind: PointKind;
  code?: string | null;
}

const COLORS = {
  light: { bg: "#f6f7f9", grid: "#e3e6ec", gridText: "#9aa1ae", control: "#dc3b2f", traverse: "#2563eb", detail: "#16a34a", line: "#2563eb", label: "#1f2430", halo: "#ffffff", sel: "#f59e0b" },
  dark: { bg: "#16191f", grid: "#252a33", gridText: "#5f6878", control: "#ff6b5e", traverse: "#60a5fa", detail: "#4ade80", line: "#60a5fa", label: "#e7eaf0", halo: "#16191f", sel: "#fbbf24" },
};

function baseStyle(theme: "light" | "dark"): StyleSpecification {
  const c = COLORS[theme];
  return {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        maxzoom: 19,
        attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>',
      },
      sat: {
        type: "raster",
        tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
        tileSize: 256,
        maxzoom: 19,
        attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
      },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": c.bg } },
      { id: "osm", type: "raster", source: "osm", layout: { visibility: "none" } },
      { id: "sat", type: "raster", source: "sat", layout: { visibility: "none" } },
    ],
  };
}

function niceStep(span: number): number {
  const raw = span / 6;
  const p = 10 ** Math.floor(Math.log10(raw));
  const f = raw / p;
  return (f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * p;
}

function triangleImage(color: string, halo: string): ImageData {
  const s = 26;
  const cv = document.createElement("canvas");
  cv.width = s;
  cv.height = s;
  const ctx = cv.getContext("2d")!;
  ctx.beginPath();
  ctx.moveTo(s / 2, 3);
  ctx.lineTo(s - 3, s - 4);
  ctx.lineTo(3, s - 4);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.strokeStyle = halo;
  ctx.lineWidth = 2.5;
  ctx.stroke();
  ctx.fill();
  ctx.beginPath();
  ctx.arc(s / 2, s / 2 + 2.5, 2.2, 0, Math.PI * 2);
  ctx.fillStyle = halo;
  ctx.fill();
  return ctx.getImageData(0, 0, s, s);
}

export default function MapPanel() {
  const { t } = useTranslation();
  const theme = useTheme();
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const container = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [basemap, setBasemap] = useState<Basemap>("none");
  const [labels, setLabels] = useState(true);
  const [heights, setHeights] = useState(false);
  const [cursor, setCursor] = useState<[number, number] | null>(null);
  const [hover, setHover] = useState<{ p: MapPoint; x: number; y: number } | null>(null);
  const [measure, setMeasure] = useState(false);
  const [measurePts, setMeasurePts] = useState<MapPoint[]>([]);
  const fitted = useRef(false);

  // ------------------------------------------------------------ data
  const points: MapPoint[] = useMemo(() => {
    if (ws.result) return ws.result.points.map((p) => ({ name: p.name, x: p.x, y: p.y, z: p.z, kind: p.kind, code: p.code }));
    return ws.data.control_points
      .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y) && p.name)
      .map((p) => ({ name: p.name, x: p.x, y: p.y, z: p.z ?? null, kind: "control" as const, code: p.code }));
  }, [ws.result, ws.data.control_points]);

  const byName = useMemo(() => new Map(points.map((p) => [p.name, p])), [points]);

  const lines = useMemo(() => {
    const out: [number, number][][] = [];
    for (const tr of ws.result?.traverses ?? []) {
      const coords = tr.route.map((n) => byName.get(n)).filter(Boolean) as MapPoint[];
      if (coords.length >= 2) out.push(coords.map((p) => egsaToLngLat(p.x, p.y)));
    }
    return out;
  }, [ws.result, byName]);

  const pointsGeo = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: points.map((p) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: egsaToLngLat(p.x, p.y) },
        properties: { name: p.name, kind: p.kind, selected: p.name === ws.selected ? 1 : 0 },
      })),
    }),
    [points, ws.selected],
  );

  // ------------------------------------------------------------ init
  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: baseStyle(theme),
      center: [23.73, 37.98],
      zoom: 12,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
      maxZoom: 22,
    });
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    mapRef.current = map;
    map.on("load", () => setLoaded(true));
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(container.current);
    return () => {
      ro.disconnect();
      map.remove();
      mapRef.current = null;
      setLoaded(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // layers (re)created on load and on theme change
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const c = COLORS[theme];
    map.setPaintProperty("bg", "background-color", c.bg);
    if (map.hasImage("tri")) map.removeImage("tri");
    map.addImage("tri", triangleImage(c.control, c.halo), { pixelRatio: 2 });
    if (map.hasImage("tri-sel")) map.removeImage("tri-sel");
    map.addImage("tri-sel", triangleImage(c.sel, c.halo), { pixelRatio: 1.6 });

    const ensureSource = (id: string) => {
      if (!map.getSource(id)) map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    };
    ["grid", "lines", "points", "measure"].forEach(ensureSource);
    for (const id of ["grid-l", "lines-l", "measure-l", "pts-detail", "pts-trav", "pts-sel", "pts-control"]) {
      if (map.getLayer(id)) map.removeLayer(id);
    }
    map.addLayer({ id: "grid-l", type: "line", source: "grid", paint: { "line-color": c.grid, "line-width": 1 } });
    map.addLayer({ id: "lines-l", type: "line", source: "lines", paint: { "line-color": c.line, "line-width": 1.6, "line-opacity": 0.85 } });
    map.addLayer({ id: "measure-l", type: "line", source: "measure", paint: { "line-color": c.sel, "line-width": 2, "line-dasharray": [2, 1.5] } });
    map.addLayer({
      id: "pts-sel",
      type: "circle",
      source: "points",
      filter: ["==", ["get", "selected"], 1],
      paint: { "circle-radius": 11, "circle-color": c.sel, "circle-opacity": 0.25, "circle-stroke-color": c.sel, "circle-stroke-width": 1.5 },
    });
    map.addLayer({
      id: "pts-detail",
      type: "circle",
      source: "points",
      filter: ["==", ["get", "kind"], "detail"],
      paint: { "circle-radius": 3.5, "circle-color": c.detail, "circle-stroke-color": c.halo, "circle-stroke-width": 1 },
    });
    map.addLayer({
      id: "pts-trav",
      type: "circle",
      source: "points",
      filter: ["==", ["get", "kind"], "traverse"],
      paint: { "circle-radius": 5, "circle-color": c.traverse, "circle-stroke-color": c.halo, "circle-stroke-width": 1.5 },
    });
    map.addLayer({
      id: "pts-control",
      type: "symbol",
      source: "points",
      filter: ["==", ["get", "kind"], "control"],
      layout: { "icon-image": "tri", "icon-allow-overlap": true, "icon-ignore-placement": true },
    });
    map.triggerRepaint();
  }, [loaded, theme]);

  // basemap
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    map.setLayoutProperty("osm", "visibility", basemap === "osm" ? "visible" : "none");
    map.setLayoutProperty("sat", "visibility", basemap === "sat" ? "visible" : "none");
    map.setLayoutProperty("grid-l", "visibility", basemap === "none" ? "visible" : "none");
  }, [basemap, loaded, theme]);

  // data
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    (map.getSource("points") as GeoJSONSource | undefined)?.setData(pointsGeo);
    (map.getSource("lines") as GeoJSONSource | undefined)?.setData({
      type: "FeatureCollection",
      features: lines.map((l) => ({ type: "Feature", geometry: { type: "LineString", coordinates: l }, properties: {} })),
    });
    map.triggerRepaint();
  }, [pointsGeo, lines, loaded, theme]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const coords = measurePts.map((p) => egsaToLngLat(p.x, p.y));
    (map.getSource("measure") as GeoJSONSource | undefined)?.setData({
      type: "FeatureCollection",
      features: coords.length === 2 ? [{ type: "Feature", geometry: { type: "LineString", coordinates: coords }, properties: {} }] : [],
    });
  }, [measurePts, loaded, theme]);

  // fit once when points first appear
  const fit = () => {
    const map = mapRef.current;
    if (!map || points.length === 0) return;
    const ll = points.map((p) => egsaToLngLat(p.x, p.y));
    const lons = ll.map((p) => p[0]);
    const lats = ll.map((p) => p[1]);
    const b: [[number, number], [number, number]] = [
      [Math.min(...lons), Math.min(...lats)],
      [Math.max(...lons), Math.max(...lats)],
    ];
    if (points.length === 1) map.jumpTo({ center: ll[0], zoom: 18 });
    else map.fitBounds(b, { padding: 48, duration: 0, maxZoom: 19 });
  };
  useEffect(() => {
    if (!loaded || fitted.current || points.length === 0) return;
    fitted.current = true;
    fit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, points.length]);

  // center on selected point if out of view
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded || !ws.selected) return;
    const p = byName.get(ws.selected);
    if (!p) return;
    const ll = egsaToLngLat(p.x, p.y);
    if (!map.getBounds().contains(ll)) map.easeTo({ center: ll, duration: 300 });
  }, [ws.selected, byName, loaded]);

  // interactions
  const stateRef = useRef({ measure, measurePts, byName, setSelected: ws.setSelected });
  stateRef.current = { measure, measurePts, byName, setSelected: ws.setSelected };
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const layers = ["pts-control", "pts-trav", "pts-detail"];
    const pick = (e: maplibregl.MapMouseEvent) => {
      const bbox: [maplibregl.PointLike, maplibregl.PointLike] = [
        [e.point.x - 6, e.point.y - 6],
        [e.point.x + 6, e.point.y + 6],
      ];
      const f = map.queryRenderedFeatures(bbox, { layers });
      return f.length ? stateRef.current.byName.get(String(f[0].properties?.name)) : undefined;
    };
    const onMove = (e: maplibregl.MapMouseEvent) => {
      const [x, y] = lngLatToEgsa(e.lngLat.lng, e.lngLat.lat);
      setCursor([x, y]);
      const p = pick(e);
      map.getCanvas().style.cursor = p ? "pointer" : stateRef.current.measure ? "crosshair" : "";
      setHover(p ? { p, x: e.point.x, y: e.point.y } : null);
    };
    const onClick = (e: maplibregl.MapMouseEvent) => {
      const p = pick(e);
      const st = stateRef.current;
      if (st.measure) {
        if (!p) return;
        setMeasurePts((prev) => (prev.length >= 2 ? [p] : [...prev, p]));
        return;
      }
      st.setSelected(p ? p.name : null);
    };
    const onLeave = () => {
      setCursor(null);
      setHover(null);
    };
    map.on("mousemove", onMove);
    map.on("click", onClick);
    map.on("mouseout", onLeave);
    return () => {
      map.off("mousemove", onMove);
      map.off("click", onClick);
      map.off("mouseout", onLeave);
    };
  }, [loaded]);

  // grid + labels overlay, redrawn on every render frame
  const drawRef = useRef<() => void>(() => {});
  drawRef.current = () => {
    const map = mapRef.current;
    const cv = canvasRef.current;
    if (!map || !cv) return;
    const c = COLORS[theme];
    const w = map.getContainer().clientWidth;
    const h = map.getContainer().clientHeight;
    const dpr = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
      cv.style.width = `${w}px`;
      cv.style.height = `${h}px`;
    }
    const ctx = cv.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    // EGSA87 grid lines (data for the line layer) + edge labels
    if (basemap === "none") {
      const b = map.getBounds();
      const corners = [b.getSouthWest(), b.getNorthEast(), b.getNorthWest(), b.getSouthEast()].map((ll) => lngLatToEgsa(ll.lng, ll.lat));
      const xs = corners.map((p) => p[0]);
      const ys = corners.map((p) => p[1]);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const step = niceStep(Math.max(maxX - minX, 1));
      const feats: { type: "Feature"; properties: Record<string, never>; geometry: { type: "LineString"; coordinates: [number, number][] } }[] = [];
      ctx.font = "500 10px Inter Variable, sans-serif";
      ctx.fillStyle = c.gridText;
      for (let x = Math.ceil(minX / step) * step; x <= maxX; x += step) {
        feats.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [egsaToLngLat(x, minY), egsaToLngLat(x, maxY)] } });
        const px = map.project(egsaToLngLat(x, (minY + maxY) / 2));
        ctx.textAlign = "center";
        ctx.fillText(Math.round(x).toString(), px.x, h - 42);
      }
      for (let y = Math.ceil(minY / step) * step; y <= maxY; y += step) {
        feats.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [egsaToLngLat(minX, y), egsaToLngLat(maxX, y)] } });
        const py = map.project(egsaToLngLat((minX + maxX) / 2, y));
        ctx.textAlign = "left";
        ctx.fillText(Math.round(y).toString(), 6, py.y - 3);
      }
      const key = `${step}|${Math.round(minX / step)}|${Math.round(maxX / step)}|${Math.round(minY / step)}|${Math.round(maxY / step)}`;
      const src = map.getSource("grid") as (GeoJSONSource & { _atsKey?: string }) | undefined;
      if (src && src._atsKey !== key) {
        src._atsKey = key;
        src.setData({ type: "FeatureCollection", features: feats });
      }
    }

    if (!labels) return;
    const occupied = new Set<string>();
    const cell = 14;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.lineJoin = "round";
    const order: PointKind[] = ["control", "traverse", "detail"];
    const sorted = [...points].sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind));
    let drawn = 0;
    for (const p of sorted) {
      if (drawn > 1500) break;
      const px = map.project(egsaToLngLat(p.x, p.y));
      if (px.x < -20 || px.y < -20 || px.x > w + 20 || px.y > h + 20) continue;
      const text = heights && p.z !== null ? `${p.name}  ${p.z.toFixed(2)}` : p.name;
      const bold = p.kind !== "detail";
      ctx.font = `${bold ? 600 : 500} ${bold ? 12 : 11}px Inter Variable, sans-serif`;
      const tw = ctx.measureText(text).width;
      const lx = px.x + 8;
      const ly = px.y - 9;
      const keys: string[] = [];
      for (let gx = Math.floor(lx / cell); gx <= Math.floor((lx + tw) / cell); gx++) keys.push(`${gx}:${Math.floor(ly / cell)}`);
      if (p.kind === "detail" && keys.some((k) => occupied.has(k))) continue;
      keys.forEach((k) => occupied.add(k));
      ctx.strokeStyle = c.halo;
      ctx.lineWidth = 3;
      ctx.strokeText(text, lx, ly);
      ctx.fillStyle = p.name === ws.selected ? c.sel : p.kind === "detail" ? c.gridText : c.label;
      if (p.kind === "detail" && theme === "light") ctx.fillStyle = p.name === ws.selected ? c.sel : "#5b6474";
      ctx.fillText(text, lx, ly);
      drawn++;
    }
  };
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const draw = () => drawRef.current();
    map.on("render", draw);
    draw();
    return () => {
      map.off("render", draw);
    };
  }, [loaded]);
  useEffect(() => {
    mapRef.current?.triggerRepaint();
  }, [labels, heights, basemap, points, ws.selected, theme]);

  const m = measurePts.length === 2 ? measurePts : null;
  const mDist = m ? Math.hypot(m[1].x - m[0].x, m[1].y - m[0].y) : null;
  const mAz = m ? gridAzimuth(m[0].x, m[0].y, m[1].x, m[1].y) : null;

  return (
    <div className="relative h-full w-full overflow-hidden bg-[var(--map-bg)]" data-testid="map">
      <div ref={container} style={{ position: "absolute", inset: 0 }} />
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0" />

      <div className="absolute left-2 top-2 z-10 flex gap-1">
        <div className="flex items-center gap-0.5 rounded-lg border bg-card/95 p-0.5 shadow-sm backdrop-blur">
          <Tooltip content={t("map.fit")}>
            <Button variant="ghost" size="icon-sm" onClick={fit} aria-label={t("map.fit")}>
              <Maximize2 />
            </Button>
          </Tooltip>
          <Tooltip content={t("map.measure")}>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-pressed={measure}
              className={cn(measure && "bg-primary/15 text-primary")}
              onClick={() => {
                setMeasure(!measure);
                setMeasurePts([]);
              }}
              aria-label={t("map.measure")}
            >
              <Ruler />
            </Button>
          </Tooltip>
          <Tooltip content={t("map.labels")}>
            <Button variant="ghost" size="icon-sm" aria-pressed={labels} className={cn(labels && "text-primary")} onClick={() => setLabels(!labels)} aria-label={t("map.labels")}>
              <Tag />
            </Button>
          </Tooltip>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label={t("map.basemap")}>
                <Layers />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuLabel>{t("map.basemap")}</DropdownMenuLabel>
              {(["none", "osm", "sat"] as Basemap[]).map((b) => (
                <DropdownMenuItem key={b} onSelect={() => setBasemap(b)}>
                  <span className={cn("size-2 rounded-full", basemap === b ? "bg-primary" : "bg-border")} />
                  {t(`map.base.${b}`)}
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setHeights(!heights)}>
                <span className={cn("size-2 rounded-full", heights ? "bg-primary" : "bg-border")} />
                {t("map.heights")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {measure && (
        <div className="absolute left-2 top-12 z-10 min-w-52 rounded-lg border bg-card/95 p-2.5 text-xs shadow-md backdrop-blur">
          <div className="mb-1 flex items-center justify-between font-medium">
            <span className="flex items-center gap-1.5">
              <Ruler className="size-3.5" /> {t("map.measure")}
            </span>
            <button className="text-muted-foreground hover:text-foreground" onClick={() => setMeasure(false)} aria-label={t("common.close")}>
              <X className="size-3.5" />
            </button>
          </div>
          {m ? (
            <div className="space-y-0.5 tabular">
              <div className="text-muted-foreground">
                {m[0].name} → {m[1].name}
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-muted-foreground">{t("map.distance")}</span>
                <span className="font-medium">{mDist!.toFixed(3)} m</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-muted-foreground">{t("map.azimuth")}</span>
                <span className="font-medium">{formatAngle(mAz, unit)}</span>
              </div>
            </div>
          ) : (
            <div className="text-muted-foreground">
              {t("map.measureHint")} {measurePts.length === 1 && `(${measurePts[0].name} → …)`}
            </div>
          )}
        </div>
      )}

      {hover && !measure && (
        <div
          className="pointer-events-none absolute z-20 rounded-md border bg-popover px-2 py-1.5 text-xs shadow-lg"
          style={{ left: Math.min(hover.x + 12, (container.current?.clientWidth ?? 400) - 180), top: hover.y + 12 }}
        >
          <div className="font-semibold">
            {hover.p.name} <span className="font-normal text-muted-foreground">· {t(`kind.${hover.p.kind}`)}</span>
          </div>
          <div className="mt-0.5 grid grid-cols-[auto_1fr] gap-x-2 tabular text-muted-foreground">
            <span>X</span>
            <span className="text-right text-foreground">{hover.p.x.toFixed(3)}</span>
            <span>Y</span>
            <span className="text-right text-foreground">{hover.p.y.toFixed(3)}</span>
            {hover.p.z !== null && (
              <>
                <span>Z</span>
                <span className="text-right text-foreground">{hover.p.z.toFixed(3)}</span>
              </>
            )}
            {hover.p.code && (
              <>
                <span>Code</span>
                <span className="text-right text-foreground">{hover.p.code}</span>
              </>
            )}
          </div>
        </div>
      )}

      <div className="pointer-events-none absolute bottom-2 left-2 z-10">
        <div className="flex items-center gap-1.5 rounded-md border bg-card/90 px-2 py-1 text-[11px] tabular text-muted-foreground shadow-xs backdrop-blur">
          <Crosshair className="size-3" />
          {cursor ? `X ${cursor[0].toFixed(2)}  Y ${cursor[1].toFixed(2)}` : "ΕΓΣΑ87"}
        </div>
      </div>
      <div className="pointer-events-none absolute right-2 top-[84px] z-10">
        <div className="hidden flex-col items-start gap-1 rounded-md border bg-card/90 px-2 py-1.5 text-[11px] text-muted-foreground shadow-xs backdrop-blur sm:flex">
          <span className="flex items-center gap-1">
            <svg viewBox="0 0 10 10" className="size-2.5">
              <path d="M5 1 9 9H1z" fill="var(--pt-control)" />
            </svg>
            {t("kind.control")}
          </span>
          <span className="flex items-center gap-1">
            <span className="size-2 rounded-full bg-pt-traverse" />
            {t("kind.traverse")}
          </span>
          <span className="flex items-center gap-1">
            <span className="size-1.5 rounded-full bg-pt-detail" />
            {t("kind.detail")}
          </span>
        </div>
      </div>

      {points.length === 0 && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span className="rounded-md border bg-card/90 px-3 py-1.5 text-xs text-muted-foreground shadow-xs">{t("map.empty")}</span>
        </div>
      )}
    </div>
  );
}
