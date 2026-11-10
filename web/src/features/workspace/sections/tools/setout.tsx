import { AlignmentTool } from "./setout/AlignmentTool";
import { CheckTool } from "./setout/CheckTool";
import { PointsTool } from "./setout/PointsTool";
import type { ToolEntry } from "./registry";

/** Tool tabs of the setout feature (composed into a page in sections/modules): group «Χαράξεις». */
export const SETOUT_TOOLS: ToolEntry[] = [
  { id: "setoutPoints", el: <PointsTool /> },
  { id: "setoutCheck", el: <CheckTool /> },
  { id: "setoutAlignment", el: <AlignmentTool /> },
];
