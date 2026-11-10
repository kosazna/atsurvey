import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import { MODULE_TOOLS, type ModuleId } from "../../sections";
import type { ToolEntry } from "../tools/registry";
import { ModuleSection } from "./ModuleSection";

/** Put the loaded tabs in MODULE_TOOLS order; a tab missing from either side is a wiring bug. */
export function orderTools(id: ModuleId, tools: ToolEntry[]): ToolEntry[] {
  const order: readonly string[] = MODULE_TOOLS[id];
  const byId = new Map(tools.map((x) => [x.id, x]));
  const missing = order.filter((x) => !byId.has(x));
  const extra = tools.filter((x) => !order.includes(x.id)).map((x) => x.id);
  if (missing.length || extra.length) {
    throw new Error(`Module "${id}": tabs out of sync with MODULE_TOOLS (missing: ${missing.join(", ") || "-"}; unlisted: ${extra.join(", ") || "-"})`);
  }
  return order.map((x) => byId.get(x) as ToolEntry);
}

function modulePage(id: ModuleId): LazyExoticComponent<ComponentType> {
  return lazy(async () => {
    const tools = orderTools(id, await MODULE_LOADERS[id]());
    function ModulePage() {
      return <ModuleSection id={id} tools={tools} />;
    }
    return { default: ModulePage };
  });
}

/** Where each module page gets its tabs (dynamic imports: one chunk per feature). */
export const MODULE_LOADERS: Record<ModuleId, () => Promise<ToolEntry[]>> = {
  parcels: async () => {
    const [m, cogo] = await Promise.all([import("../tools/parcels"), import("../tools/cogo")]);
    return [...m.PARCELS_TOOLS, cogo.QUICK_AREA_TOOL];
  },
  cadastre: async () => (await import("../tools/dgm")).DGM_TOOLS,
  terrain: async () => (await import("../tools/surfaces")).SURFACES_TOOLS,
  setout: async () => {
    const [m, cogo] = await Promise.all([import("../tools/setout"), import("../tools/cogo")]);
    return [...m.SETOUT_TOOLS, cogo.SINGLE_STAKEOUT_TOOL];
  },
  cogo: async () => (await import("../tools/cogo")).COGO_TOOLS,
  coords: async () => {
    const [m, cogo] = await Promise.all([import("../tools/coords"), import("../tools/cogo")]);
    return [...m.COORDS_TOOLS, cogo.COMMON_POINTS_TOOL];
  },
  preanalysis: async () => (await import("../tools/analysis")).ANALYSIS_TOOLS,
  instruments: async () => (await import("../tools/instruments")).INSTRUMENTS_TOOLS,
};

/** One lazily loaded page per module, so each feature ships in its own chunk. */
export const MODULE_PAGES = Object.fromEntries(
  (Object.keys(MODULE_LOADERS) as ModuleId[]).map((id) => [id, modulePage(id)]),
) as Record<ModuleId, LazyExoticComponent<ComponentType>>;
