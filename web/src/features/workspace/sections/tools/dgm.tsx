import { BuildTool } from "./dgm/BuildTool";
import { ValidateTool } from "./dgm/ValidateTool";
import type { ToolEntry } from "./registry";

/** Tool tabs of the ΔΓΜ feature ("ΔΓΜ Κτηματολογίου", registered in ToolsSection). */
export const DGM_TOOLS: ToolEntry[] = [
  { id: "dgmBuild", el: <BuildTool /> },
  { id: "dgmValidate", el: <ValidateTool /> },
];
