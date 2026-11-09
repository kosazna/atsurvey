// Field-code line work: choose which feature codes form lines; review the resulting lines.
import { Check, Spline } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatArea } from "@/lib/geometry";
import { useLineColors } from "@/lib/linePalette";
import { detectCodes } from "@/lib/linework";
import type { LineworkSettings } from "@/lib/types";
import { cn, fmtNum } from "@/lib/utils";
import { useWorkspace } from "../useWorkspace";
import { SectionFrame, SectionHeader } from "./SectionLayout";

function TokenList({ label, value, onCommit }: { label: string; value: string[]; onCommit: (v: string[]) => void }) {
  const [text, setText] = useState(value.join(", "));
  useEffect(() => setText(value.join(", ")), [value]);
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={() =>
          onCommit(
            text
              .split(/[,\s]+/)
              .map((s) => s.trim())
              .filter(Boolean),
          )
        }
      />
    </div>
  );
}

export default function LineworkSection() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const lw = ws.data.settings.linework;
  const r = ws.result;
  const codes = useMemo(() => detectCodes(r?.points ?? [], lw.case_sensitive), [r, lw.case_sensitive]);
  const colors = useLineColors(lw.line_codes);
  const lines = r?.linework ?? [];

  const setLw = (patch: Partial<LineworkSettings>) => ws.update({ settings: { ...ws.data.settings, linework: { ...lw, ...patch } } });
  const toggle = (code: string) => {
    const on = lw.line_codes.includes(code);
    setLw({ line_codes: on ? lw.line_codes.filter((c) => c !== code) : [...lw.line_codes, code] });
  };

  const totals = useMemo(() => {
    const m = new Map<string, { n: number; length: number; area: number }>();
    for (const l of lines) {
      const cur = m.get(l.code) ?? { n: 0, length: 0, area: 0 };
      cur.n++;
      cur.length += l.length;
      cur.area += l.area ?? 0;
      m.set(l.code, cur);
    }
    return m;
  }, [lines]);

  return (
    <SectionFrame className="overflow-y-auto">
      <SectionHeader title={t("lines.title")} description={t("lines.subtitle")} actions={<Badge variant="secondary">{t("lines.count", { count: lines.length })}</Badge>} />
      <div className="grid gap-4 p-4 xl:grid-cols-[1fr_1.2fr]">
        <div className="space-y-4">
          <Card className="p-4">
            <div className="text-sm font-medium">{t("lines.codes")}</div>
            <p className="mt-0.5 text-xs text-muted">{t("lines.codesHint")}</p>
            {codes.length === 0 ? (
              <p className="mt-4 text-xs text-muted">{t("lines.noCodes")}</p>
            ) : (
              <div className="mt-3 flex flex-wrap gap-1.5" data-testid="line-codes">
                {codes.map(({ code, count }) => {
                  const on = lw.line_codes.includes(code);
                  return (
                    <button
                      key={code}
                      aria-pressed={on}
                      onClick={() => toggle(code)}
                      className={cn(
                        "flex h-7 cursor-pointer items-center gap-1.5 rounded-full border px-2.5 text-xs transition-colors",
                        on ? "border-border-strong bg-surface font-medium text-fg" : "text-muted hover:text-fg",
                      )}
                    >
                      {on ? <span className="size-2 rounded-full" style={{ background: colors[code] }} /> : <span className="size-2 rounded-full border" />}
                      {code} <span className="tabular text-subtle">{count}</span>
                      {on && <Check className="size-3" />}
                    </button>
                  );
                })}
              </div>
            )}
          </Card>
          <Card className="space-y-3 p-4">
            <div>
              <div className="text-sm font-medium">{t("lines.control")}</div>
              <p className="mt-0.5 text-xs text-muted">{t("lines.controlHint")}</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <TokenList label={t("lines.start")} value={lw.start_tokens} onCommit={(v) => setLw({ start_tokens: v })} />
              <TokenList label={t("lines.close")} value={lw.close_tokens} onCommit={(v) => setLw({ close_tokens: v })} />
              <TokenList label={t("lines.end")} value={lw.end_tokens} onCommit={(v) => setLw({ end_tokens: v })} />
            </div>
            <div className="rounded-lg bg-surface-sunken px-3 py-2 font-mono text-xs leading-relaxed text-muted">
              101 OIK ST · 102 OIK · 103 OIK · 104 OIK CL
              <br />
              201 KR · 202 KR · 203 KR · 204 KR E
            </div>
          </Card>
        </div>

        <div className="space-y-3">
          {lines.length === 0 ? (
            <Card>
              <EmptyState icon={<Spline />} title={t("lines.empty")} description={lw.line_codes.length ? t("lines.emptyHint") : t("lines.chooseHint")} />
            </Card>
          ) : (
            <>
              <div className="grid gap-2 sm:grid-cols-2">
                {[...totals.entries()].map(([code, s]) => (
                  <div key={code} className="flex items-center gap-3 rounded-xl border bg-surface p-3">
                    <span className="h-8 w-1 rounded-full" style={{ background: colors[code] }} />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold">{code}</div>
                      <div className="text-xs text-muted tabular">
                        {t("lines.summary", { n: s.n, length: fmtNum(s.length, 2) })}
                        {s.area > 0 && ` · ${formatArea(s.area, 1)}`}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <Card className="overflow-hidden" data-testid="lines-table">
                <table className="w-full text-sm tabular">
                  <thead>
                    <tr className="border-b bg-surface-sunken text-xs text-muted">
                      <th className="px-3 py-2 text-left font-medium">{t("lines.line")}</th>
                      <th className="px-3 py-2 text-left font-medium">{t("lines.points")}</th>
                      <th className="px-3 py-2 text-right font-medium">{t("lines.length")}</th>
                      <th className="px-3 py-2 text-right font-medium">{t("lines.area")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lines.map((l) => (
                      <tr key={l.name} className="cursor-pointer border-b last:border-0 hover:bg-surface-sunken" onClick={() => ws.setSelected(l.points[0] ?? null)}>
                        <td className="px-3 py-1.5">
                          <span className="flex items-center gap-2 font-medium">
                            <span className="size-2 rounded-full" style={{ background: colors[l.code] }} />
                            {l.name}
                            {l.closed && <Badge variant="secondary">{t("lines.closed")}</Badge>}
                          </span>
                        </td>
                        <td className="max-w-48 truncate px-3 py-1.5 text-xs text-muted">{l.points.join(" → ")}</td>
                        <td className="px-3 py-1.5 text-right">{fmtNum(l.length, 2)} m</td>
                        <td className="px-3 py-1.5 text-right">{l.area ? formatArea(l.area, 1) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </>
          )}
        </div>
      </div>
    </SectionFrame>
  );
}
