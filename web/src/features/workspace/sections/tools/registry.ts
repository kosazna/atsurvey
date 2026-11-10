import type { ReactNode } from "react";

/** One tab in the Tools section. `id` keys the i18n strings tools.tabs.<id> and tools.desc.<id>. */
export interface ToolEntry {
  id: string;
  el: ReactNode;
}

/** A group of tool tabs (tools.groups.<id>); empty groups are hidden. */
export interface ToolGroup {
  id: string;
  tools: ToolEntry[];
}
