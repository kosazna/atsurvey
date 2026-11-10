import { AreaCompareTool } from "./parcels/AreaCompareTool";
import { MergeTool } from "./parcels/MergeTool";
import { SubdivideTool } from "./parcels/SubdivideTool";
import type { ToolEntry } from "./registry";

/** Tool tabs of the parcels feature (page «Ιδιοκτησίες», see sections/modules). */
export const PARCELS_TOOLS: ToolEntry[] = [
  { id: "parcelArea", el: <AreaCompareTool /> },
  { id: "parcelSubdivide", el: <SubdivideTool /> },
  { id: "parcelMerge", el: <MergeTool /> },
];
