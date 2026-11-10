// Map of control / traverse / detail points. MapLibre renders points and lines;
// labels are drawn on a 2D canvas overlay (token font, Greek-safe, no glyph server).
// Colours come from design tokens resolved at runtime (MapLibre cannot read CSS vars).
// An adaptive EGSA87 grid replaces a basemap by default.
import "maplibre-gl/dist/maplibre-gl.css";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, Map as MLMap, StyleSpecification } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { Crosshair, Expand, ImageDown, Layers, Maximize2, MousePointerClick, PenTool, Ruler, Search, Tag, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Tooltip } from "@/components/ui/tooltip";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { formatAngle, gridAzimuth } from "@/lib/angles";
import { ellipsePolygon, formatArea, polygonArea } from "@/lib/geometry";
import { useLineColors } from "@/lib/linePalette";
import { egsaToLngLat, lngLatToEgsa } from "@/lib/proj";
import { useTheme } from "@/lib/theme";
import { type ResolvedTokens, useTokens } from "@/lib/tokens";
import type { PointKind } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useWorkspace } from "../useWorkspace";
import { setContourVisible, useContourOverlay } from "./contoursOverlay";

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

interface MapColors {
  bg: string;
  grid: string;
  gridText: string;
  control: string;
  traverse: string;
  detail: string;
  line: string;
  label: string;
  labelMuted: string;
  halo: string;
  sel: string;
  accent: string;
  accentSubtle: string;
  ellipse: string;
  contour: string;
  contourIndex: string;
}

function mapColors(t: ResolvedTokens): MapColors {
  return {
    bg: t.mapBg,
    grid: t.mapGrid,
    gridText: t.textSubtle,
    control: t.pointControl,
    traverse: t.pointTraverse,
    detail: t.pointDetail,
    line: t.traverseLine,
    label: t.text,
    labelMuted: t.textMuted,
    halo: t.mapBg,
    sel: t.warning,
    accent: t.accent,
    accentSubtle: t.accentSubtle,
    ellipse: t.danger,
    contour: t.textSubtle,
    contourIndex: t.textMuted,
  };
}

function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return Boolean(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

function baseStyle(c: MapColors): StyleSpecification {
  return {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        maxzoom: 19,
        attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>',
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

/** Height labels on index contours (one per line, at its middle vertex, kept upright). */
function drawContourLabels(
  ctx: CanvasRenderingContext2D,
  map: MLMap,
  lines: { z: number; index: boolean; points: [number, number][] }[],
  c: MapColors,
  tokens: ResolvedTokens,
  w: number,
  h: number,
) {
  const labelled = lines.filter((l) => l.index && l.points.length >= 2);
  if (labelled.length === 0 || labelled.length > 600) return;
  ctx.font = `${tokens.weightMedium} ${tokens.textXs - 1}px ${tokens.fontSans}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.lineJoin = "round";
  for (const l of labelled) {
    const i = Math.floor((l.points.length - 1) / 2);
    const a = map.project(egsaToLngLat(...l.points[i]));
    const b = map.project(egsaToLngLat(...l.points[i + 1]));
    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;
    if (mx < 0 || my < 0 || mx > w || my > h || Math.hypot(b.x - a.x, b.y - a.y) < 0.5) continue;
    let ang = Math.atan2(b.y - a.y, b.x - a.x);
    if (ang > Math.PI / 2) ang -= Math.PI;
    else if (ang < -Math.PI / 2) ang += Math.PI;
    const text = Number.isInteger(l.z) ? l.z.toFixed(0) : l.z.toFixed(2);
    ctx.save();
    ctx.translate(mx, my);
    ctx.rotate(ang);
    ctx.strokeStyle = c.halo;
    ctx.lineWidth = 3;
    ctx.strokeText(text, 0, 0);
    ctx.fillStyle = c.labelMuted;
    ctx.fillText(text, 0, 0);
    ctx.restore();
  }
}

export default function MapPanel() {
  const { t } = useTranslation();
  const theme = useTheme();
  const tokens = useTokens();
  const colors = useMemo(() => mapColors(tokens), [tokens]);
  const [glError, setGlError] = useState<string | null>(() => (webglAvailable() ? null : "webgl"));
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const container = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [basemap, setBasemap] = useState<Basemap>("none");
  const [labels, setLabels] = useState(true);
  const [heights, setHeights] = useState(false);
  const [codes, setCodes] = useState(false);
  const [areaMode, setAreaMode] = useState(false);
  const [areaPts, setAreaPts] = useState<[number, number][]>([]);
  const [search, setSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
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

  const lineCodes = useMemo(() => [...new Set((ws.result?.linework ?? []).map((l) => l.code))], [ws.result]);
  const lineColors = useLineColors(lineCodes);
  const lineworkGeo = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: (ws.result?.linework ?? [])
        .map((l) => {
          const coords = l.points.map((n) => byName.get(n)).filter(Boolean) as MapPoint[];
          if (coords.length < 2) return null;
          const ring = coords.map((p) => egsaToLngLat(p.x, p.y));
          if (l.closed) ring.push(ring[0]);
          return { type: "Feature" as const, geometry: { type: "LineString" as const, coordinates: ring }, properties: { color: lineColors[l.code] ?? colors.line, code: l.code } };
        })
        .filter(Boolean) as { type: "Feature"; geometry: { type: "LineString"; coordinates: [number, number][] }; properties: { color: string; code: string } }[],
    }),
    [ws.result, byName, lineColors, colors.line],
  );

  const ellipsesGeo = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: (ws.result?.adjustment ? ws.result.points : [])
        .filter((p) => p.ellipse)
        .map((p) => {
          const e = p.ellipse!;
          const ring = ellipsePolygon(p.x, p.y, e.a * e.k95, e.b * e.k95, e.theta, ws.ellipseScale).map(([x, y]) => egsaToLngLat(x, y));
          return { type: "Feature" as const, geometry: { type: "Polygon" as const, coordinates: [ring] }, properties: { name: p.name } };
        }),
    }),
    [ws.result, ws.ellipseScale],
  );

  // terrain contours from the surface tools (own store: they persist across tool tabs)
  const contourState = useContourOverlay();
  const contourLines = contourState.projectId === ws.projectId ? contourState.lines : [];
  const showContours = contourState.visible && contourLines.length > 0;
  const contoursGeo = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: (showContours ? contourLines : []).map((l) => ({
        type: "Feature" as const,
        geometry: { type: "LineString" as const, coordinates: l.points.map(([x, y]) => egsaToLngLat(x, y)) },
        properties: { index: l.index ? 1 : 0 },
      })),
    }),
    [contourLines, showContours],
  );

  const overlayGeo = useMemo(() => {
    const o = ws.overlay;
    type Feat = { type: "Feature"; geometry: { type: "Point"; coordinates: [number, number] } | { type: "LineString"; coordinates: [number, number][] } | { type: "Polygon"; coordinates: [number, number][][] }; properties: { t: string } };
    const feats: Feat[] = [
      ...o.polygons.filter((r) => r.length >= 3).map((r) => ({ type: "Feature" as const, geometry: { type: "Polygon" as const, coordinates: [[...r, r[0]].map(([x, y]) => egsaToLngLat(x, y))] }, properties: { t: "poly" } })),
      ...o.lines.filter((l) => l.length >= 2).map((l) => ({ type: "Feature" as const, geometry: { type: "LineString" as const, coordinates: l.map(([x, y]) => egsaToLngLat(x, y)) }, properties: { t: "line" } })),
      ...o.points.map((p) => ({ type: "Feature" as const, geometry: { type: "Point" as const, coordinates: egsaToLngLat(p.x, p.y) }, properties: { t: p.role } })),
    ];
    if (areaPts.length) {
      const ring = areaPts.map(([x, y]) => egsaToLngLat(x, y));
      if (areaPts.length >= 3) feats.push({ type: "Feature", geometry: { type: "Polygon", coordinates: [[...ring, ring[0]]] }, properties: { t: "poly" } });
      else if (areaPts.length === 2) feats.push({ type: "Feature", geometry: { type: "LineString", coordinates: ring }, properties: { t: "line" } });
      areaPts.forEach(([x, y]) => feats.push({ type: "Feature", geometry: { type: "Point", coordinates: egsaToLngLat(x, y) }, properties: { t: "input" } }));
    }
    return { type: "FeatureCollection" as const, features: feats };
  }, [ws.overlay, areaPts]);

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
    if (!container.current || glError) return;
    let map: MLMap;
    try {
      map = new maplibregl.Map({
      container: container.current,
      style: baseStyle(colors),
      center: [23.73, 37.98],
      zoom: 12,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
      maxZoom: 22,
    });
    } catch (e) {
      setGlError((e as Error).message || "webgl");
      return;
    }
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
    const c = colors;
    map.setPaintProperty("bg", "background-color", c.bg);
    if (map.hasImage("tri")) map.removeImage("tri");
    map.addImage("tri", triangleImage(c.control, c.halo), { pixelRatio: 2 });
    if (map.hasImage("tri-sel")) map.removeImage("tri-sel");
    map.addImage("tri-sel", triangleImage(c.sel, c.halo), { pixelRatio: 1.6 });

    const ensureSource = (id: string) => {
      if (!map.getSource(id)) map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    };
    ["grid", "contours", "lines", "points", "measure", "linework", "ellipses", "overlay"].forEach(ensureSource);
    for (const id of ["grid-l", "contours-l", "contours-idx", "lines-l", "linework-l", "ellipses-f", "ellipses-l", "overlay-f", "overlay-l", "overlay-p", "measure-l", "pts-detail", "pts-trav", "pts-sel", "pts-control"]) {
      if (map.getLayer(id)) map.removeLayer(id);
    }
    map.addLayer({ id: "grid-l", type: "line", source: "grid", paint: { "line-color": c.grid, "line-width": 1 } });
    map.addLayer({ id: "contours-l", type: "line", source: "contours", filter: ["==", ["get", "index"], 0], paint: { "line-color": c.contour, "line-width": 0.8 } });
    map.addLayer({ id: "contours-idx", type: "line", source: "contours", filter: ["==", ["get", "index"], 1], paint: { "line-color": c.contourIndex, "line-width": 1.6 } });
    map.addLayer({ id: "linework-l", type: "line", source: "linework", paint: { "line-color": ["get", "color"], "line-width": 1.8 }, layout: { "line-join": "round", "line-cap": "round" } });
    map.addLayer({ id: "lines-l", type: "line", source: "lines", paint: { "line-color": c.line, "line-width": 1.6, "line-opacity": 0.85 } });
    map.addLayer({ id: "ellipses-f", type: "fill", source: "ellipses", paint: { "fill-color": c.ellipse, "fill-opacity": 0.08 } });
    map.addLayer({ id: "ellipses-l", type: "line", source: "ellipses", paint: { "line-color": c.ellipse, "line-width": 1.2 } });
    map.addLayer({ id: "overlay-f", type: "fill", source: "overlay", filter: ["==", ["get", "t"], "poly"], paint: { "fill-color": c.accent, "fill-opacity": 0.12 } });
    map.addLayer({
      id: "overlay-l",
      type: "line",
      source: "overlay",
      filter: ["in", ["get", "t"], ["literal", ["line", "poly"]]],
      paint: { "line-color": c.accent, "line-width": 1.6, "line-dasharray": [3, 2] },
    });
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
    map.addLayer({
      id: "overlay-p",
      type: "circle",
      source: "overlay",
      filter: ["in", ["get", "t"], ["literal", ["input", "result"]]],
      paint: {
        "circle-radius": ["case", ["==", ["get", "t"], "result"], 6, 5],
        "circle-color": ["case", ["==", ["get", "t"], "result"], c.accent, c.halo],
        "circle-stroke-color": c.accent,
        "circle-stroke-width": 2,
      },
    });
    map.triggerRepaint();
  }, [loaded, colors]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    (map.getSource("linework") as GeoJSONSource | undefined)?.setData(lineworkGeo);
    (map.getSource("ellipses") as GeoJSONSource | undefined)?.setData(ellipsesGeo);
    (map.getSource("overlay") as GeoJSONSource | undefined)?.setData(overlayGeo);
    (map.getSource("contours") as GeoJSONSource | undefined)?.setData(contoursGeo);
    map.triggerRepaint();
  }, [lineworkGeo, ellipsesGeo, overlayGeo, contoursGeo, loaded, colors]);

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

  // frame tool geometry (COGO inputs/results) when it is off-screen or too small to read
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const o = ws.overlay;
    const xy: [number, number][] = [...o.points.map((p) => [p.x, p.y] as [number, number]), ...o.lines.flat(), ...o.polygons.flat()];
    if (xy.length === 0) return;
    const ll = xy.map(([x, y]) => egsaToLngLat(x, y));
    const lons = ll.map((p) => p[0]);
    const lats = ll.map((p) => p[1]);
    const b = map.getBounds();
    const sw = map.project([Math.min(...lons), Math.min(...lats)]);
    const ne = map.project([Math.max(...lons), Math.max(...lats)]);
    const spanPx = Math.max(Math.abs(ne.x - sw.x), Math.abs(ne.y - sw.y));
    const inside = ll.every((p) => b.contains(p));
    if (inside && (xy.length === 1 || spanPx > 120)) return;
    if (xy.length === 1) map.easeTo({ center: ll[0], zoom: Math.max(map.getZoom(), 17), duration: 350 });
    else
      map.fitBounds(
        [
          [Math.min(...lons), Math.min(...lats)],
          [Math.max(...lons), Math.max(...lats)],
        ],
        { padding: 80, duration: 350, maxZoom: 20 },
      );
  }, [ws.overlay, loaded]);

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
  const stateRef = useRef({ measure, measurePts, byName, setSelected: ws.setSelected, pick: ws.pick, areaMode });
  stateRef.current = { measure, measurePts, byName, setSelected: ws.setSelected, pick: ws.pick, areaMode };
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
      const st = stateRef.current;
      map.getCanvas().style.cursor = st.pick || st.areaMode ? "crosshair" : p ? "pointer" : st.measure ? "crosshair" : "";
      setHover(p ? { p, x: e.point.x, y: e.point.y } : null);
    };
    const onClick = (e: maplibregl.MapMouseEvent) => {
      const p = pick(e);
      const st = stateRef.current;
      if (st.pick) {
        if (p) st.pick({ name: p.name, x: p.x, y: p.y, z: p.z });
        else {
          const [x, y] = lngLatToEgsa(e.lngLat.lng, e.lngLat.lat);
          st.pick({ x, y });
        }
        return;
      }
      if (st.areaMode) {
        const xy: [number, number] = p ? [p.x, p.y] : lngLatToEgsa(e.lngLat.lng, e.lngLat.lat);
        setAreaPts((prev) => [...prev, xy]);
        return;
      }
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
    const c = colors;
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
      ctx.font = `${tokens.weightRegular} ${tokens.textXs - 1}px ${tokens.fontSans}`;
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

    if (showContours) drawContourLabels(ctx, map, contourLines, c, tokens, w, h);

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
      let text = p.name;
      if (heights && p.z !== null) text += `  ${p.z.toFixed(2)}`;
      if (codes && p.code) text += `  ${p.code}`;
      const bold = p.kind !== "detail";
      ctx.font = `${bold ? tokens.weightSemibold : tokens.weightRegular} ${bold ? tokens.textXs : tokens.textXs - 1}px ${tokens.fontSans}`;
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
      ctx.fillStyle = p.name === ws.selected ? c.sel : p.kind === "detail" ? c.labelMuted : c.label;
      ctx.fillText(text, lx, ly);
      drawn++;
    }
    // tool overlay labels (only coordinates typed by hand need a label; project points have one)
    ctx.font = `${tokens.weightMedium} ${tokens.textXs}px ${tokens.fontSans}`;
    for (const op of ws.overlay.points) {
      if (!op.label || byName.has(op.label)) continue;
      const px = map.project(egsaToLngLat(op.x, op.y));
      ctx.strokeStyle = c.halo;
      ctx.lineWidth = 3;
      ctx.strokeText(op.label, px.x + 9, px.y - 9);
      ctx.fillStyle = c.accent;
      ctx.fillText(op.label, px.x + 9, px.y - 9);
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
  }, [labels, heights, codes, basemap, points, ws.selected, colors, ws.overlay, contoursGeo]);

  // ------------------------------------------------------------ actions
  const flyTo = (name: string) => {
    const p = byName.get(name.trim());
    const map = mapRef.current;
    if (!p || !map) return false;
    ws.setSelected(p.name);
    map.easeTo({ center: egsaToLngLat(p.x, p.y), zoom: Math.max(map.getZoom(), 18), duration: 400 });
    return true;
  };

  const exportPng = () => {
    const map = mapRef.current;
    const overlayCanvas = canvasRef.current;
    if (!map || !overlayCanvas) return;
    map.once("render", () => {
      const gl = map.getCanvas();
      const out = document.createElement("canvas");
      out.width = gl.width;
      out.height = gl.height;
      const ctx = out.getContext("2d")!;
      ctx.fillStyle = colors.bg;
      ctx.fillRect(0, 0, out.width, out.height);
      ctx.drawImage(gl, 0, 0);
      ctx.drawImage(overlayCanvas, 0, 0, out.width, out.height);
      out.toBlob((blob) => {
        if (!blob) return;
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `${ws.data.meta.name.replace(/[^\p{L}\p{N}_-]+/gu, "_")}-map.png`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      }, "image/png");
    });
    map.triggerRepaint();
  };

  const rootRef = useRef<HTMLDivElement>(null);
  const toggleFullscreen = () => {
    const el = rootRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen?.();
  };

  const area = areaPts.length >= 3 ? polygonArea(areaPts.map(([x, y]) => ({ x, y }))) : null;

  const m = measurePts.length === 2 ? measurePts : null;
  const mDist = m ? Math.hypot(m[1].x - m[0].x, m[1].y - m[0].y) : null;
  const mAz = m ? gridAzimuth(m[0].x, m[0].y, m[1].x, m[1].y) : null;

  return (
    <div ref={rootRef} className="relative h-full w-full overflow-hidden bg-map-bg" data-testid="map">
      <div ref={container} style={{ position: "absolute", inset: 0 }} />
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0" />

      <div className="absolute left-2 top-2 z-10 flex gap-1">
        <div className="flex items-center gap-0.5 rounded-lg border bg-surface p-0.5">
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
              className={cn(measure && "bg-accent-subtle text-accent")}
              onClick={() => {
                setMeasure(!measure);
                setMeasurePts([]);
                setAreaMode(false);
              }}
              aria-label={t("map.measure")}
            >
              <Ruler />
            </Button>
          </Tooltip>
          <Tooltip content={t("map.areaMeasure")}>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-pressed={areaMode}
              className={cn(areaMode && "bg-accent-subtle text-accent")}
              onClick={() => {
                setAreaMode(!areaMode);
                setAreaPts([]);
                setMeasure(false);
              }}
              aria-label={t("map.areaMeasure")}
              data-testid="map-area"
            >
              <PenTool />
            </Button>
          </Tooltip>
          <Popover open={searchOpen} onOpenChange={setSearchOpen}>
            <Tooltip content={t("map.search")}>
              <PopoverTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label={t("map.search")} data-testid="map-search">
                  <Search />
                </Button>
              </PopoverTrigger>
            </Tooltip>
            <PopoverContent className="w-60 p-2">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (flyTo(search)) setSearchOpen(false);
                }}
              >
                <Input autoFocus list="map-search-pts" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("map.searchPlaceholder")} data-testid="map-search-input" />
                <datalist id="map-search-pts">
                  {points.slice(0, 3000).map((p) => (
                    <option key={p.name} value={p.name} />
                  ))}
                </datalist>
                {search && !byName.has(search.trim()) && <p className="mt-1.5 text-xs text-muted">{t("map.notFound")}</p>}
              </form>
            </PopoverContent>
          </Popover>
          <DropdownMenu>
            <Tooltip content={t("map.labels")}>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" className={cn(labels && "text-accent")} aria-label={t("map.labels")}>
                  <Tag />
                </Button>
              </DropdownMenuTrigger>
            </Tooltip>
            <DropdownMenuContent>
              <DropdownMenuLabel>{t("map.labels")}</DropdownMenuLabel>
              {[
                { on: labels, set: setLabels, k: "map.labelName" },
                { on: heights, set: setHeights, k: "map.heights" },
                { on: codes, set: setCodes, k: "map.labelCode" },
              ].map((o) => (
                <DropdownMenuItem
                  key={o.k}
                  onSelect={(e) => {
                    e.preventDefault();
                    o.set(!o.on);
                    if (!o.on && o.k !== "map.labelName") setLabels(true);
                  }}
                >
                  <span className={cn("size-2 rounded-full", o.on ? "bg-accent" : "bg-border")} />
                  {t(o.k)}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
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
                  <span className={cn("size-2 rounded-full", basemap === b ? "bg-accent" : "bg-border")} />
                  {t(`map.base.${b}`)}
                </DropdownMenuItem>
              ))}
              {contourLines.length > 0 && (
                <DropdownMenuItem
                  onSelect={(e) => {
                    e.preventDefault();
                    setContourVisible(!contourState.visible);
                  }}
                  data-testid="map-contours"
                >
                  <span className={cn("size-2 rounded-full", contourState.visible ? "bg-accent" : "bg-border")} />
                  {t("map.contours")}
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={exportPng}>
                <ImageDown /> {t("map.exportPng")}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={toggleFullscreen}>
                <Expand /> {t("map.fullscreen")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {ws.pick && (
        <div className="absolute left-1/2 top-2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-full border border-accent bg-surface px-3 py-1.5 text-xs shadow-md" data-testid="pick-banner">
          <MousePointerClick className="size-3.5 text-accent" />
          {t("map.pickHint")}
          <button className="text-muted hover:text-fg" onClick={() => ws.setPick(null)} aria-label={t("common.cancel")}>
            <X className="size-3.5" />
          </button>
        </div>
      )}

      {areaMode && (
        <div className="absolute left-2 top-12 z-10 min-w-56 rounded-lg border bg-surface p-2.5 text-xs" data-testid="area-panel">
          <div className="mb-1 flex items-center justify-between font-medium">
            <span className="flex items-center gap-1.5">
              <PenTool className="size-3.5" /> {t("map.areaMeasure")}
            </span>
            <button className="text-muted hover:text-fg" onClick={() => setAreaMode(false)} aria-label={t("common.close")}>
              <X className="size-3.5" />
            </button>
          </div>
          {area ? (
            <div className="space-y-0.5 tabular">
              <div className="flex justify-between gap-4">
                <span className="text-muted">{t("map.area")}</span>
                <span className="font-medium">{formatArea(area.area)}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-muted">{t("map.perimeter")}</span>
                <span className="font-medium">{area.perimeter.toFixed(3)} m</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-muted">{t("map.vertices")}</span>
                <span>{areaPts.length}</span>
              </div>
            </div>
          ) : (
            <div className="text-muted">{t("map.areaHint")}</div>
          )}
          {areaPts.length > 0 && (
            <div className="mt-2 flex gap-1">
              <Button size="sm" variant="ghost" onClick={() => setAreaPts((p) => p.slice(0, -1))}>
                {t("map.undoVertex")}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setAreaPts([])}>
                {t("map.clear")}
              </Button>
            </div>
          )}
        </div>
      )}

      {measure && (
        <div className="absolute left-2 top-12 z-10 min-w-52 rounded-lg border bg-surface p-2.5 text-xs">
          <div className="mb-1 flex items-center justify-between font-medium">
            <span className="flex items-center gap-1.5">
              <Ruler className="size-3.5" /> {t("map.measure")}
            </span>
            <button className="text-muted hover:text-fg" onClick={() => setMeasure(false)} aria-label={t("common.close")}>
              <X className="size-3.5" />
            </button>
          </div>
          {m ? (
            <div className="space-y-0.5 tabular">
              <div className="text-muted">
                {m[0].name} → {m[1].name}
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-muted">{t("map.distance")}</span>
                <span className="font-medium">{mDist!.toFixed(3)} m</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-muted">{t("map.azimuth")}</span>
                <span className="font-medium">{formatAngle(mAz, unit)}</span>
              </div>
            </div>
          ) : (
            <div className="text-muted">
              {t("map.measureHint")} {measurePts.length === 1 && `(${measurePts[0].name} → …)`}
            </div>
          )}
        </div>
      )}

      {hover && !measure && (
        <div
          className="pointer-events-none absolute z-20 rounded-md border bg-surface-raised px-2 py-1.5 text-xs shadow-lg"
          style={{ left: Math.min(hover.x + 12, (container.current?.clientWidth ?? 400) - 180), top: hover.y + 12 }}
        >
          <div className="font-semibold">
            {hover.p.name} <span className="font-normal text-muted">· {t(`kind.${hover.p.kind}`)}</span>
          </div>
          <div className="mt-0.5 grid grid-cols-[auto_1fr] gap-x-2 tabular text-muted">
            <span>X</span>
            <span className="text-right text-fg">{hover.p.x.toFixed(3)}</span>
            <span>Y</span>
            <span className="text-right text-fg">{hover.p.y.toFixed(3)}</span>
            {hover.p.z !== null && (
              <>
                <span>Z</span>
                <span className="text-right text-fg">{hover.p.z.toFixed(3)}</span>
              </>
            )}
            {hover.p.code && (
              <>
                <span>Code</span>
                <span className="text-right text-fg">{hover.p.code}</span>
              </>
            )}
          </div>
        </div>
      )}

      <div className="pointer-events-none absolute bottom-2 left-2 z-10">
        <div className="flex items-center gap-1.5 rounded-md border bg-surface px-2 py-1 text-xs tabular text-muted backdrop-blur">
          <Crosshair className="size-3" />
          {cursor ? `X ${cursor[0].toFixed(2)}  Y ${cursor[1].toFixed(2)}` : "ΕΓΣΑ87"}
        </div>
      </div>
      <div className="pointer-events-none absolute right-2 top-[84px] z-10">
        <div className="hidden flex-col items-start gap-1 rounded-md border bg-surface px-2 py-1.5 text-xs text-muted backdrop-blur sm:flex">
          <span className="flex items-center gap-1">
            <svg viewBox="0 0 10 10" className="size-2.5">
              <path d="M5 1 9 9H1z" fill="var(--color-point-control)" />
            </svg>
            {t("kind.control")}
          </span>
          <span className="flex items-center gap-1">
            <span className="size-2 rounded-full bg-point-traverse" />
            {t("kind.traverse")}
          </span>
          <span className="flex items-center gap-1">
            <span className="size-1.5 rounded-full bg-point-detail" />
            {t("kind.detail")}
          </span>
        </div>
      </div>

      {glError && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-map-bg p-6">
          <div className="max-w-xs rounded-lg border bg-surface p-4 text-center text-sm text-muted">
            <div className="mb-1 font-medium text-fg">{t("map.noWebglTitle")}</div>
            {t("map.noWebgl")}
          </div>
        </div>
      )}

      {!glError && points.length === 0 && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span className="rounded-md border bg-surface px-3 py-1.5 text-xs text-muted">{t("map.empty")}</span>
        </div>
      )}
    </div>
  );
}
