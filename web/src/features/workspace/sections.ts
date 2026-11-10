// Workspace navigation model: every page of a project, its sidebar group, whether the map is
// shown there by default, and (for module pages) the ordered tool tabs it contains.
// Pure data (no JSX) so the router and tests can import it cheaply.

export const SECTIONS = [
  "overview",
  // data: what was measured
  "control",
  "observations",
  "traverses",
  "leveling",
  // computations and their checks
  "results",
  "adjustment",
  "linework",
  "reports",
  "issues",
  "runs",
  // applications: studies built on the project's points
  "parcels",
  "cadastre",
  "terrain",
  "setout",
  // utilities: calculators and checks
  "cogo",
  "coords",
  "preanalysis",
  "instruments",
] as const;
export type Section = (typeof SECTIONS)[number];

export type NavGroup = "data" | "compute" | "apps" | "utils";

export const SECTION_GROUP: Record<Section, NavGroup | null> = {
  overview: null,
  control: "data",
  observations: "data",
  traverses: "data",
  leveling: "data",
  results: "compute",
  adjustment: "compute",
  linework: "compute",
  reports: "compute",
  issues: "compute",
  runs: "compute",
  parcels: "apps",
  cadastre: "apps",
  terrain: "apps",
  setout: "apps",
  cogo: "utils",
  coords: "utils",
  preanalysis: "utils",
  instruments: "utils",
};

/**
 * Map shown by default on this page. Pages about the project's geometry show it; applications
 * and utilities keep the full width and open the map only when a tool needs it (picking a point,
 * showing contours or ellipses) or when the user asks. The user's toggle is remembered per page.
 */
export const MAP_DEFAULT: Record<Section, boolean> = {
  overview: true,
  control: true,
  observations: true,
  traverses: true,
  leveling: false,
  results: true,
  adjustment: true,
  linework: true,
  reports: false,
  issues: true,
  runs: false,
  parcels: false,
  cadastre: false,
  terrain: false,
  setout: false,
  cogo: false,
  coords: false,
  preanalysis: false,
  instruments: false,
};

/** Pages made of tool tabs, with their tabs in display order (ids key tools.tabs.<id>). */
export const MODULE_TOOLS = {
  parcels: ["parcelArea", "parcelSubdivide", "parcelMerge", "area"],
  cadastre: ["dgmBuild", "dgmValidate"],
  terrain: ["surfContours", "surfHeights", "surfVolumes", "surfProfile"],
  setout: ["setoutPoints", "stakeout", "setoutCheck", "setoutAlignment"],
  cogo: ["inverse", "polar", "intersection", "resection", "offset"],
  coords: ["coordsConvert", "coordsInfo", "transform"],
  preanalysis: ["preanalysis"],
  instruments: ["twoFace", "twoPeg", "edmConstant"],
} as const satisfies Partial<Record<Section, readonly string[]>>;
export type ModuleId = keyof typeof MODULE_TOOLS;

export function isModule(s: Section): s is ModuleId {
  return Object.hasOwn(MODULE_TOOLS, s);
}

/** Old page ids that may still be in bookmarks or links. */
const SECTION_ALIASES: Record<string, Section> = { tools: "cogo" };

export function parseSection(value: unknown): Section | undefined {
  if (typeof value !== "string") return undefined;
  if ((SECTIONS as readonly string[]).includes(value)) return value as Section;
  return Object.hasOwn(SECTION_ALIASES, value) ? SECTION_ALIASES[value] : undefined;
}

const TOOL_ID = /^[A-Za-z][A-Za-z0-9]{0,63}$/;

export function parseTool(value: unknown): string | undefined {
  return typeof value === "string" && TOOL_ID.test(value) ? value : undefined;
}

/** The tab to show on a module page: the requested one if it exists there, else the first. */
export function activeTool(module: ModuleId, requested: string | undefined): string {
  const tools: readonly string[] = MODULE_TOOLS[module];
  return requested && tools.includes(requested) ? requested : tools[0];
}

/** Which module page holds a tool tab (for links such as "?tool=parcelSubdivide"). */
export function moduleOfTool(tool: string): ModuleId | undefined {
  return (Object.keys(MODULE_TOOLS) as ModuleId[]).find((m) => (MODULE_TOOLS[m] as readonly string[]).includes(tool));
}

export type MapPrefs = Partial<Record<Section, boolean>>;

/** Parse the remembered per-page map choices; anything malformed is ignored. */
export function parseMapPrefs(raw: string | null): MapPrefs {
  if (!raw) return {};
  try {
    const obj: unknown = JSON.parse(raw);
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) return {};
    const out: MapPrefs = {};
    for (const [k, v] of Object.entries(obj)) {
      const s = parseSection(k);
      if (s && typeof v === "boolean" && s === k) out[s] = v;
    }
    return out;
  } catch {
    return {};
  }
}

/** Is the map visible on a page: forced open by a tool, else the user's choice, else the default. */
export function mapVisibleFor(section: Section, prefs: MapPrefs, forced: boolean): boolean {
  return forced || (prefs[section] ?? MAP_DEFAULT[section]);
}
