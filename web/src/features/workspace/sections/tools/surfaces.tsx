import { ContoursTool } from "./surfaces/ContoursTool";
import { HeightsTool } from "./surfaces/HeightsTool";
import { ProfileTool } from "./surfaces/ProfileTool";
import { VolumesTool } from "./surfaces/VolumesTool";
import type { ToolEntry } from "./registry";

/** Tool tabs of the surfaces feature ("Ανάγλυφο", composed into a page in sections/modules). */
export const SURFACES_TOOLS: ToolEntry[] = [
  { id: "surfContours", el: <ContoursTool /> },
  { id: "surfHeights", el: <HeightsTool /> },
  { id: "surfVolumes", el: <VolumesTool /> },
  { id: "surfProfile", el: <ProfileTool /> },
];
