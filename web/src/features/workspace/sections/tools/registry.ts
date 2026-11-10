import type { ReactNode } from "react";

/**
 * One tab of a module page (Ιδιοκτησίες, Ανάγλυφο, …). `id` keys the i18n strings
 * tools.tabs.<id> and tools.desc.<id>, and must be listed in MODULE_TOOLS (sections.ts).
 */
export interface ToolEntry {
  id: string;
  el: ReactNode;
}
