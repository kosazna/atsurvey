import { describe, expect, it } from "vitest";
import { MODULE_TOOLS, type ModuleId } from "../../sections";
import { MODULE_LOADERS, orderTools } from "./index";

describe("module pages load exactly the tabs MODULE_TOOLS lists, in that order", () => {
  it.each(Object.keys(MODULE_TOOLS) as ModuleId[])("%s", async (id) => {
    const tools = orderTools(id, await MODULE_LOADERS[id]());
    expect(tools.map((x) => x.id)).toEqual([...MODULE_TOOLS[id]]);
  });

  it("refuses a page whose tabs drifted from the catalogue", () => {
    expect(() => orderTools("cogo", [{ id: "inverse", el: null }])).toThrow(/missing: polar/);
    expect(() => orderTools("preanalysis", [{ id: "preanalysis", el: null }, { id: "ghost", el: null }])).toThrow(/unlisted: ghost/);
  });
});
