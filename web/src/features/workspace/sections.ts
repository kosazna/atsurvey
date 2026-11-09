export const SECTIONS = ["overview", "control", "observations", "traverses", "results", "reports", "issues"] as const;
export type Section = (typeof SECTIONS)[number];
