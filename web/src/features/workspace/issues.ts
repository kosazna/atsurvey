import i18n from "@/lib/i18n";
import type { Issue } from "@/lib/types";

/** Translated issue message; falls back to the engine's English message if the
 *  code is unknown or the template needs params the engine did not send. */
export function issueText(issue: Issue): string {
  const key = `issues.codes.${issue.code}`;
  const tpl = i18n.getResource(i18n.language, "translation", key) as string | undefined;
  if (!tpl) return issue.message;
  const vars = [...tpl.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]);
  const params = issue.params ?? {};
  if (vars.some((v) => params[v] === undefined || params[v] === null)) return issue.message;
  const fmt: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(params)) {
    fmt[k] = Array.isArray(v) ? v.join(", ") : typeof v === "number" ? +v.toFixed(4) : v;
  }
  return i18n.t(key, fmt);
}
