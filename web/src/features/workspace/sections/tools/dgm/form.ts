// State of the "Σύνταξη ΔΓΜ" form and its conversion to a /v1/dgm request.
import { type DgmMode, type DgmRequest, EMPTY_TITLE, type FinalPolygon, normalizeKaek, parseVertices, splitBlocks, type TitleBlock } from "@/lib/dgmApi";
import { AREA_TOLERANCE_PRESETS, type Parcel, type ParcelVertex } from "@/lib/parcelsApi";
import { uid } from "@/lib/utils";
import type { NamedPoint } from "../shared";

export interface PolyItem {
  id: string;
  /** KAEK; for a final polygon "" means a new parcel («ΝΕΟ») */
  kaek: string;
  text: string;
}

export interface DgmForm {
  mode: DgmMode;
  parcels: PolyItem[];
  subject: string;
  lines: string;
  extend: boolean;
  merge: string[] | null;
  subjects: string[];
  finals: PolyItem[];
  topo: string;
  topoNew: string;
  buildings: string;
  boundary: "implemented" | "unimplemented";
  toleranceId: string;
  title: TitleBlock;
}

export const newItem = (kaek = "", text = ""): PolyItem => ({ id: uid(), kaek, text });

export const INITIAL_FORM: DgmForm = {
  mode: "subdivision",
  parcels: [newItem()],
  subject: "",
  lines: "",
  extend: true,
  merge: null,
  subjects: [],
  finals: [],
  topo: "",
  topoNew: "",
  buildings: "",
  boundary: "unimplemented",
  toleranceId: "cadastre_urban",
  title: EMPTY_TITLE,
};

export interface Built {
  req: DgmRequest | null;
  /** lines that could not be read, per field */
  bad: string[];
}

type Points = Map<string, NamedPoint>;

export function vertices(text: string, pts: Points, bad: string[] = [], field = ""): ParcelVertex[] {
  const parsed = parseVertices(text, (name) => pts.get(name));
  bad.push(...parsed.bad.slice(0, 3).map((l) => (field ? `${field}: ${l}` : l)));
  return parsed.vertices;
}

function polygons(text: string, pts: Points, bad: string[], field: string, label: string): Parcel[] {
  return splitBlocks(text)
    .map((block, i) => ({ label: `${label}${i + 1}`, vertices: vertices(block, pts, bad, field) }))
    .filter((p) => p.vertices.length >= 3);
}

export function kaeksOf(form: DgmForm): string[] {
  return form.parcels.map((p) => normalizeKaek(p.kaek)).filter(Boolean);
}

/** The request for the current form, or null while required parts are missing. */
export function toRequest(form: DgmForm, pts: Points): Built {
  const bad: string[] = [];
  const parcels: Parcel[] = form.parcels
    .map((p) => ({ kaek: normalizeKaek(p.kaek) || null, vertices: vertices(p.text, pts, bad, p.kaek || "ΚΑΕΚ") }))
    .filter((p) => p.vertices.length >= 3);
  if (parcels.length === 0) return { req: null, bad };
  const preset = AREA_TOLERANCE_PRESETS.find((p) => p.id === form.toleranceId);
  const req: DgmRequest = {
    mode: form.mode,
    parcels,
    topo_prop: polygons(form.topo, pts, bad, "TOPO_PROP", ""),
    topo_prop_new: polygons(form.topoNew, pts, bad, "TOPO_PROP_NEW", ""),
    buildings: polygons(form.buildings, pts, bad, "BLD", "Κ"),
    boundary: form.boundary,
    tolerance: preset ? preset.rule : null,
    title: form.title,
  };
  if (form.mode === "subdivision") {
    const lines = splitBlocks(form.lines)
      .map((b) => ({ vertices: vertices(b, pts, bad, "LINE_XM") }))
      .filter((l) => l.vertices.length >= 2);
    if (lines.length === 0) return { req: null, bad };
    req.subject = form.subject || parcels[0].kaek;
    req.partition_lines = lines;
    req.extend_lines = form.extend;
  } else if (form.mode === "merge") {
    req.merge = form.merge ?? [];
  } else {
    const finals: FinalPolygon[] = form.finals
      .map((f) => ({ kaek: normalizeKaek(f.kaek) || null, vertices: vertices(f.text, pts, bad, f.kaek || "ΝΕΟ") }))
      .filter((f) => f.vertices.length >= 3);
    if (finals.length === 0 || form.subjects.length === 0) return { req: null, bad };
    req.subjects = form.subjects;
    req.finals = finals;
  }
  return { req, bad };
}
