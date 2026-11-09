export const SECTIONS = [
  "overview",
  "control",
  "observations",
  "traverses",
  "results",
  "adjustment",
  "reports",
  "linework",
  "tools",
  "leveling",
  "runs",
  "issues",
] as const;
export type Section = (typeof SECTIONS)[number];
