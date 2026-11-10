// Shared inputs for the COGO tools: point fields that accept a project point name or typed
// coordinates (or a click on the map), angle fields in the project unit, and helpers.
import { Crosshair, Plus } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tooltip } from "@/components/ui/tooltip";
import { formatAngle, parseAngle } from "@/lib/angles";
import { isNotAvailable } from "@/lib/api";
import { apiErrorMessage } from "@/lib/apiErrors";
import type { XY } from "@/lib/cogoTypes";
import { cn, fmtNum, parseNum, uid } from "@/lib/utils";
import { type PickedPoint, useWorkspace } from "../../useWorkspace";

export interface NamedPoint extends XY {
  name: string;
}

/** All points known to the project: computed result points first, then control points. */
export function useProjectPoints(): Map<string, NamedPoint> {
  const ws = useWorkspace();
  return useMemo(() => {
    const m = new Map<string, NamedPoint>();
    for (const p of ws.data.control_points) {
      if (p.name && Number.isFinite(p.x) && Number.isFinite(p.y)) m.set(p.name, { name: p.name, x: p.x, y: p.y, z: p.z ?? null });
    }
    for (const p of ws.result?.points ?? []) m.set(p.name, { name: p.name, x: p.x, y: p.y, z: p.z });
    return m;
  }, [ws.data.control_points, ws.result]);
}

/** Parse "x y [z]" (whitespace or ; separated; decimal comma allowed when unambiguous). */
export function parseCoords(text: string): XY | null {
  const t = text.trim();
  if (!t) return null;
  let parts = t.split(/[\s;]+/).filter(Boolean);
  if (parts.length === 1 && (t.match(/,/g) ?? []).length >= 1 && !t.includes(".")) {
    // "476000,4205000" → treat comma as separator
    parts = t.split(",");
  }
  const nums = parts.map((p) => parseNum(p));
  if (nums.length < 2 || nums.some((n) => n === null)) return null;
  return { x: nums[0]!, y: nums[1]!, z: nums[2] ?? null };
}

/** Resolve a field value: point name → project point, otherwise coordinates. */
export function resolvePoint(text: string, points: Map<string, NamedPoint>): XY | null {
  const t = text.trim();
  if (!t) return null;
  const p = points.get(t);
  if (p) return p;
  return parseCoords(t);
}

/**
 * Parse a multi-line list: each line is a project point name, "name x y [z]" or "x y [z]".
 * Returns the points and the lines that could not be read.
 */
export function parsePointList(text: string, points: Map<string, NamedPoint>): { pts: XY[]; bad: string[] } {
  const pts: XY[] = [];
  const bad: string[] = [];
  text.split(/\r?\n/).forEach((line, i) => {
    const l = line.trim();
    if (!l) return;
    const known = points.get(l);
    if (known) {
      pts.push(known);
      return;
    }
    const parts = l.split(/[\s;\t]+/).filter(Boolean);
    const firstNum = parseNum(parts[0] ?? "");
    if (firstNum === null && parts.length >= 3) {
      const c = parseCoords(parts.slice(1).join(" "));
      if (c) {
        pts.push({ ...c, name: parts[0] });
        return;
      }
    }
    const c = parseCoords(l);
    if (c) pts.push({ ...c, name: `P${i + 1}` });
    else bad.push(l);
  });
  return { pts, bad };
}

export function PointField({
  label,
  value,
  onChange,
  points,
  testId,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  points: Map<string, NamedPoint>;
  testId?: string;
  placeholder?: string;
}) {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const id = useId();
  const listId = `${id}-list`;
  const resolved = resolvePoint(value, points);
  const picking = ws.pick !== null && ws.pick.name === `pick-${id}`;
  const startPick = () => {
    ws.revealMap();
    const fn = Object.defineProperty(
      (p: PickedPoint) => {
        onChange(p.name ?? `${p.x.toFixed(3)} ${p.y.toFixed(3)}`);
        ws.setPick(null);
      },
      "name",
      { value: `pick-${id}` },
    ) as (p: PickedPoint) => void;
    ws.setPick(picking ? null : fn);
  };
  const names = useMemo(() => [...points.keys()].slice(0, 2000), [points]);
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex gap-1">
        <Input
          id={id}
          list={listId}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder ?? t("tools.pointPlaceholder")}
          className={cn("tabular", value.trim() && !resolved && "border-danger")}
          data-testid={testId}
          autoComplete="off"
        />
        <Tooltip content={t("tools.pickOnMap")}>
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-pressed={picking}
            className={cn(picking && "border-accent bg-accent-subtle text-accent")}
            onClick={startPick}
            aria-label={t("tools.pickOnMap")}
          >
            <Crosshair />
          </Button>
        </Tooltip>
        <datalist id={listId}>
          {names.map((n) => (
            <option key={n} value={n} />
          ))}
        </datalist>
      </div>
      <div className="h-4 truncate text-xs text-muted tabular">
        {resolved ? `X ${fmtNum(resolved.x, 3)}  Y ${fmtNum(resolved.y, 3)}${resolved.z !== null && resolved.z !== undefined ? `  Z ${fmtNum(resolved.z, 3)}` : ""}` : value.trim() ? t("tools.unresolved") : ""}
      </div>
    </div>
  );
}

export function AngleField({ label, value, onChange, testId }: { label: string; value: string; onChange: (v: string) => void; testId?: string }) {
  const ws = useWorkspace();
  const unit = ws.data.meta.angle_unit;
  const id = useId();
  const rad = parseAngle(value, unit);
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>
        {label} <span className="font-normal text-muted">({unit === "gon" ? "grad" : unit === "deg" ? "°" : "° ′ ″"})</span>
      </Label>
      <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} inputMode="decimal" className={cn("tabular", value.trim() && rad === null && "border-danger")} data-testid={testId} />
    </div>
  );
}

export function NumberField({
  label,
  value,
  onChange,
  suffix,
  testId,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  suffix?: string;
  testId?: string;
}) {
  const id = useId();
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>
        {label} {suffix && <span className="font-normal text-muted">({suffix})</span>}
      </Label>
      <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} inputMode="decimal" className={cn("tabular", value.trim() && parseNum(value) === null && "border-danger")} data-testid={testId} />
    </div>
  );
}

export function PointListField({ label, value, onChange, hint, testId }: { label: string; value: string; onChange: (v: string) => void; hint?: string; testId?: string }) {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const id = useId();
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        {ws.selected && (
          <Button type="button" variant="ghost" size="sm" onClick={() => onChange((value.trim() ? `${value.trimEnd()}\n` : "") + ws.selected)}>
            <Plus /> {ws.selected}
          </Button>
        )}
      </div>
      <Textarea id={id} rows={5} value={value} onChange={(e) => onChange(e.target.value)} className="font-mono text-xs" placeholder={hint ?? t("tools.listHint")} data-testid={testId} />
    </div>
  );
}

/** Async runner with friendly errors and an "endpoint not available yet" state. */
export function useRunner<T>() {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(
    async (fn: () => Promise<T>) => {
      setBusy(true);
      setError(null);
      try {
        const r = await fn();
        setResult(r);
        return r;
      } catch (e) {
        setResult(null);
        setError(isNotAvailable(e) ? t("tools.notAvailable") : apiErrorMessage(e, t));
        return null;
      } finally {
        setBusy(false);
      }
    },
    [t],
  );
  return { busy, result, error, run, setResult };
}

export function ResultBox({ children, error, testId }: { children?: React.ReactNode; error?: string | null; testId?: string }) {
  if (error) return <div className="rounded-lg border border-danger bg-danger-subtle px-3 py-2 text-sm text-danger" data-testid={testId ? `${testId}-error` : undefined}>{error}</div>;
  if (!children) return null;
  return (
    <div className="rounded-xl border bg-surface p-4" data-testid={testId}>
      {children}
    </div>
  );
}

export function KV({ items }: { items: { k: React.ReactNode; v: React.ReactNode; strong?: boolean }[] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm">
      {items.map((it, i) => (
        <div key={i} className="contents">
          <dt className="text-muted">{it.k}</dt>
          <dd className={cn("text-right tabular", it.strong && "font-semibold")}>{it.v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** "Add to project" — appends computed points as control points with code COGO. */
export function useAddToProject() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  return useCallback(
    (pts: XY[], fallbackPrefix = "C") => {
      const existing = new Set(ws.data.control_points.map((p) => p.name));
      let k = 1;
      const add = pts.map((p) => {
        let name = (p.name ?? "").trim();
        if (!name || existing.has(name)) {
          while (existing.has(`${fallbackPrefix}${k}`)) k++;
          name = `${fallbackPrefix}${k}`;
        }
        existing.add(name);
        return { id: uid(), name, x: p.x, y: p.y, z: p.z ?? null, code: "COGO" };
      });
      ws.update({ control_points: [...ws.data.control_points, ...add] });
      toast.success(t("tools.added", { count: add.length, names: add.map((a) => a.name).join(", ") }), {
        action: { label: t("ws.undo"), onClick: () => ws.undo() },
      });
    },
    [t, ws],
  );
}

/** Push tool geometry to the map while mounted. */
export function useOverlay(points: { x: number; y: number; label?: string; role: "input" | "result" }[], lines: [number, number][][] = [], polygons: [number, number][][] = []) {
  const ws = useWorkspace();
  const key = JSON.stringify([points, lines, polygons]);
  useEffect(() => {
    ws.setOverlay({ points, lines, polygons });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  useEffect(() => () => ws.setOverlay({ points: [], lines: [], polygons: [] }), []); // eslint-disable-line react-hooks/exhaustive-deps
}

export { formatAngle };
