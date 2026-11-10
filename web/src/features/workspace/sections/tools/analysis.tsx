import { PreanalysisTool } from "./analysis/PreanalysisTool";
import type { ToolEntry } from "./registry";

/** Tool tabs of the analysis feature, group "Σχεδιασμός δικτύου" (composed into a page in sections/modules). */
export const ANALYSIS_TOOLS: ToolEntry[] = [{ id: "preanalysis", el: <PreanalysisTool /> }];
