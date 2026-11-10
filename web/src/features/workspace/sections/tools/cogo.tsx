import { ResectionTool, StakeoutTool, TransformTool, AreaTool } from "./advanced";
import { IntersectionTool, InverseTool, OffsetTool, PolarTool } from "./basic";
import type { ToolEntry } from "./registry";

/** Geometry calculators (page «Γεωμετρικοί υπολογισμοί»). */
export const COGO_TOOLS: ToolEntry[] = [
  { id: "inverse", el: <InverseTool /> },
  { id: "polar", el: <PolarTool /> },
  { id: "intersection", el: <IntersectionTool /> },
  { id: "resection", el: <ResectionTool /> },
  { id: "offset", el: <OffsetTool /> },
];

/** Quick polygon area drawn on the map (page «Ιδιοκτησίες»). */
export const QUICK_AREA_TOOL: ToolEntry = { id: "area", el: <AreaTool /> };
/** Single-point stakeout (page «Χαράξεις»). */
export const SINGLE_STAKEOUT_TOOL: ToolEntry = { id: "stakeout", el: <StakeoutTool /> };
/** Helmert / affine from common points (page «Συστήματα συντεταγμένων»). */
export const COMMON_POINTS_TOOL: ToolEntry = { id: "transform", el: <TransformTool /> };
