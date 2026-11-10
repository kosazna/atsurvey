import { ConvertTool } from "./coords/ConvertTool";
import { PointInfoTool } from "./coords/PointInfoTool";
import type { ToolEntry } from "./registry";

/** Tool tabs of the coords feature, group "Συστήματα" (composed into a page in sections/modules). */
export const COORDS_TOOLS: ToolEntry[] = [
  { id: "coordsConvert", el: <ConvertTool /> },
  { id: "coordsInfo", el: <PointInfoTool /> },
];
