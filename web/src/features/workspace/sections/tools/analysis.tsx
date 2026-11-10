import { PreanalysisTool } from "./analysis/PreanalysisTool";
import type { ToolEntry } from "./registry";

/** Tool tabs of the analysis feature, group "Σχεδιασμός δικτύου" (registered in ToolsSection). */
export const ANALYSIS_TOOLS: ToolEntry[] = [{ id: "preanalysis", el: <PreanalysisTool /> }];
