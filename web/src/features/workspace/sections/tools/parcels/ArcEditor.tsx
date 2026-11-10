// Optional circular arcs: one row per side (vertex i → i+1) with radius, bulge side and
// major-arc flag. Convention as in the engine: the arc belongs to the side that starts at the
// vertex and bulges left/right looking from that vertex towards the next.
import { useTranslation } from "react-i18next";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { ArcSpec, ParcelVertex } from "@/lib/parcelsApi";
import { parseNum } from "@/lib/utils";

interface Props {
  vertices: ParcelVertex[];
  arcs: Record<string, ArcSpec>;
  onChange: (arcs: Record<string, ArcSpec>) => void;
}

export function ArcEditor({ vertices, arcs, onChange }: Props) {
  const { t } = useTranslation();
  if (vertices.length < 3) return null;
  const set = (name: string, arc: ArcSpec | null) => {
    const { [name]: _drop, ...rest } = arcs;
    onChange(arc ? { ...rest, [name]: arc } : rest);
  };
  const count = vertices.filter((v) => arcs[v.name]).length;
  return (
    <details className="rounded-lg border px-3 py-2">
      <summary className="cursor-pointer text-sm">
        {t("parcels.arcs.title")} {count > 0 && <span className="text-muted">({count})</span>}
      </summary>
      <p className="mt-2 text-xs text-muted">{t("parcels.arcs.hint")}</p>
      <div className="mt-2 space-y-1.5">
        {vertices.map((v, i) => {
          const next = vertices[(i + 1) % vertices.length];
          const arc = arcs[v.name];
          return (
            <div key={`${v.name}-${i}`} className="grid grid-cols-[5rem_6rem_1fr] items-center gap-2 text-sm">
              <span className="tabular">
                {v.name}–{next.name}
              </span>
              <Input
                aria-label={`${t("parcels.radius")} ${v.name}–${next.name}`}
                inputMode="decimal"
                placeholder="R"
                defaultValue={arc ? String(arc.radius) : ""}
                onChange={(e) => {
                  const r = parseNum(e.target.value);
                  set(v.name, r !== null && r > 0 ? { radius: r, side: arc?.side ?? "right", large: arc?.large ?? false } : null);
                }}
              />
              {arc ? (
                <div className="flex items-center gap-3">
                  <Select<"left" | "right">
                    value={arc.side}
                    onValueChange={(side) => set(v.name, { ...arc, side })}
                    options={[
                      { value: "left", label: t("parcels.arcs.left") },
                      { value: "right", label: t("parcels.arcs.right") },
                    ]}
                    aria-label={t("parcels.arcs.bulge")}
                  />
                  <label className="flex items-center gap-1.5 text-xs">
                    <Checkbox checked={!!arc.large} onCheckedChange={(c) => set(v.name, { ...arc, large: c === true })} />
                    {t("parcels.arcs.large")}
                  </label>
                </div>
              ) : (
                <span />
              )}
            </div>
          );
        })}
      </div>
    </details>
  );
}
