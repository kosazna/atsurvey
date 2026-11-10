import { BuildTool } from "./dgm/BuildTool";
import { ValidateTool } from "./dgm/ValidateTool";
import type { ToolEntry } from "./registry";

/** Tool tabs of the ΔΓΜ feature ("ΔΓΜ Κτηματολογίου", composed into a page in sections/modules). */
export const DGM_TOOLS: ToolEntry[] = [
  { id: "dgmBuild", el: <BuildTool /> },
  { id: "dgmValidate", el: <ValidateTool /> },
];
