import { describe, expect, it } from "vitest";
import { elBundle, enBundle, type Tree } from "@/lib/i18nResources";
import {
  activeTool,
  isModule,
  MAP_DEFAULT,
  mapVisibleFor,
  MODULE_TOOLS,
  moduleOfTool,
  parseMapPrefs,
  parseSection,
  parseTool,
  SECTION_GROUP,
  SECTIONS,
  type ModuleId,
} from "./sections";

const MODULES = Object.keys(MODULE_TOOLS) as ModuleId[];
const ALL_TOOLS = MODULES.flatMap((m) => [...MODULE_TOOLS[m]]);

function lookup(tree: Tree, key: string): unknown {
  return key.split(".").reduce<unknown>((node, k) => (node && typeof node === "object" ? (node as Tree)[k] : undefined), tree);
}

describe("page ids in the URL", () => {
  it("accepts every page and maps the old Tools page to the geometry calculators", () => {
    for (const s of SECTIONS) expect(parseSection(s)).toBe(s);
    expect(parseSection("tools")).toBe("cogo");
  });

  it("ignores unknown or non-string pages", () => {
    expect(parseSection("admin")).toBeUndefined();
    expect(parseSection(3)).toBeUndefined();
    expect(parseSection(undefined)).toBeUndefined();
    expect(parseSection("__proto__")).toBeUndefined();
  });

  it("accepts tool ids and rejects anything else", () => {
    expect(parseTool("parcelSubdivide")).toBe("parcelSubdivide");
    expect(parseTool("<script>")).toBeUndefined();
    expect(parseTool("a".repeat(65))).toBeUndefined();
    expect(parseTool(["inverse"])).toBeUndefined();
  });
});

describe("module pages", () => {
  it("lists every tab exactly once across all pages", () => {
    expect(new Set(ALL_TOOLS).size).toBe(ALL_TOOLS.length);
    for (const m of MODULES) expect(MODULE_TOOLS[m].length).toBeGreaterThan(0);
  });

  it("are pages of the Applications or Tools group, with the map closed by default", () => {
    for (const m of MODULES) {
      expect(SECTIONS).toContain(m);
      expect(isModule(m)).toBe(true);
      expect(["apps", "utils"]).toContain(SECTION_GROUP[m]);
      expect(MAP_DEFAULT[m]).toBe(false);
    }
    expect(isModule("results")).toBe(false);
  });

  it("open the requested tab only if it belongs to the page", () => {
    expect(activeTool("parcels", undefined)).toBe("parcelArea");
    expect(activeTool("parcels", "parcelMerge")).toBe("parcelMerge");
    expect(activeTool("parcels", "inverse")).toBe("parcelArea");
    expect(activeTool("cogo", "polar")).toBe("polar");
  });

  it("find the page of a tab", () => {
    expect(moduleOfTool("dgmBuild")).toBe("cadastre");
    expect(moduleOfTool("transform")).toBe("coords");
    expect(moduleOfTool("stakeout")).toBe("setout");
    expect(moduleOfTool("nothing")).toBeUndefined();
  });
});

describe("map visibility", () => {
  it("follows the page default, then the user's choice, then a tool's need", () => {
    expect(mapVisibleFor("results", {}, false)).toBe(true);
    expect(mapVisibleFor("cogo", {}, false)).toBe(false);
    expect(mapVisibleFor("cogo", { cogo: true }, false)).toBe(true);
    expect(mapVisibleFor("results", { results: false }, false)).toBe(false);
    expect(mapVisibleFor("cogo", { cogo: false }, true)).toBe(true);
  });

  it("reads remembered choices defensively", () => {
    expect(parseMapPrefs('{"cogo":true,"results":false,"x":true,"tools":true,"terrain":"yes"}')).toEqual({ cogo: true, results: false });
    expect(parseMapPrefs("not json")).toEqual({});
    expect(parseMapPrefs("[true]")).toEqual({});
    expect(parseMapPrefs("null")).toEqual({});
    expect(parseMapPrefs(null)).toEqual({});
  });

  it("has a default for every page", () => {
    for (const s of SECTIONS) expect(typeof MAP_DEFAULT[s]).toBe("boolean");
  });
});

describe.each([
  ["el", elBundle],
  ["en", enBundle],
])("navigation strings (%s)", (_lang, bundle) => {
  const keys = [
    ...SECTIONS.map((s) => `ws.sections.${s}`),
    ...(["data", "compute", "apps", "utils"] as const).map((g) => `ws.groups.${g}`),
    ...MODULES.map((m) => `ws.sectionHints.${m}`),
    ...SECTIONS.filter((s) => SECTION_GROUP[s] === "apps" || SECTION_GROUP[s] === "utils").map((s) => `overview.moreHints.${s}`),
    ...ALL_TOOLS.flatMap((tool) => [`tools.tabs.${tool}`, `tools.desc.${tool}`]),
    "cmd.tools",
    "cmd.navigation",
    "tools.pickingHint",
    "ws.map",
    "ws.showMap",
    "ws.hideMap",
    "ws.mapHasGeometry",
  ];
  it.each(keys)("%s", (key) => {
    const v = lookup(bundle, key);
    expect(typeof v).toBe("string");
    expect((v as string).length).toBeGreaterThan(0);
  });
});
