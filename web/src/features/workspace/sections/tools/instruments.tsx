import { EdmTool } from "./instruments/EdmTool";
import { TwoFaceTool } from "./instruments/TwoFaceTool";
import { TwoPegTool } from "./instruments/TwoPegTool";
import type { ToolEntry } from "./registry";

/** Tool tabs of the instruments feature (registered in ToolsSection). The levelling network
 *  adjustment lives in the Levelling section ("Δίκτυο" mode), next to its readings. */
export const INSTRUMENTS_TOOLS: ToolEntry[] = [
  { id: "twoFace", el: <TwoFaceTool /> },
  { id: "twoPeg", el: <TwoPegTool /> },
  { id: "edmConstant", el: <EdmTool /> },
];
