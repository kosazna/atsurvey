// Shared inputs for the coordinate-system tools: system / φλ-format selectors, Hatt sheet
// centre, issue list, a runner that turns coded engine failures into Greek messages.
import { AlertTriangle, Info } from "lucide-react";
import { useCallback, useId } from "react";
import { useTranslation } from "react-i18next";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { parseAngle } from "@/lib/angles";
import { type GeoFormat, type HattSpec, SYSTEM_IDS, type SystemId, coordsErrorCode, issueParams } from "@/lib/coordsApi";
import type { Issue } from "@/lib/types";
import { cn, parseNum } from "@/lib/utils";
import { useRunner } from "../shared";

export function SystemSelect({ label, value, onChange, testId }: { label: string; value: SystemId; onChange: (v: SystemId) => void; testId?: string }) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <div className="space-y-1.5" data-testid={testId}>
      <Label htmlFor={id}>{label}</Label>
      <Select<SystemId> id={id} value={value} onValueChange={onChange} options={SYSTEM_IDS.map((s) => ({ value: s, label: t(`coords.systems.${s}`) }))} />
    </div>
  );
}

export function GeoFormatSelect({ value, onChange }: { value: GeoFormat; onChange: (v: GeoFormat) => void }) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{t("coords.geoFormat")}</Label>
      <Select<GeoFormat>
        id={id}
        value={value}
        onValueChange={onChange}
        options={[
          { value: "dms", label: t("coords.dms") },
          { value: "deg", label: t("coords.deg") },
        ]}
      />
    </div>
  );
}

export interface HattDraft {
  lat0: string;
  lon0: string;
  meridian: "athens" | "greenwich";
  coefficients: string;
}

export const EMPTY_HATT: HattDraft = { lat0: "", lon0: "", meridian: "athens", coefficients: "" };

function parseCoefficients(text: string): number[] | null {
  const nums = text.split(/[\s;\t]+/).filter(Boolean).map(parseNum);
  return nums.length === 12 && nums.every((n) => n !== null) ? (nums as number[]) : null;
}

/** HattSpec from the draft, or null while incomplete/invalid. */
export function hattSpec(d: HattDraft, fmt: GeoFormat): HattSpec | null {
  const lat0 = parseAngle(d.lat0, fmt);
  const lon0 = parseAngle(d.lon0, fmt);
  if (lat0 === null || lon0 === null) return null;
  const coefficients = d.coefficients.trim() ? parseCoefficients(d.coefficients) : null;
  if (d.coefficients.trim() && !coefficients) return null;
  return { lat0, lon0, meridian: d.meridian, coefficients };
}

export function HattFields({ value, onChange, fmt, withCoefficients }: { value: HattDraft; onChange: (d: HattDraft) => void; fmt: GeoFormat; withCoefficients: boolean }) {
  const { t } = useTranslation();
  const id = useId();
  const set = (patch: Partial<HattDraft>) => onChange({ ...value, ...patch });
  const bad = (s: string) => s.trim() !== "" && parseAngle(s, fmt) === null;
  const coeffBad = value.coefficients.trim() !== "" && parseCoefficients(value.coefficients) === null;
  return (
    <fieldset className="space-y-2 rounded-lg border p-3">
      <legend className="px-1 text-xs font-medium text-muted">{t("coords.hatt.title")}</legend>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-lat`}>{t("coords.hatt.lat0")}</Label>
          <Input id={`${id}-lat`} value={value.lat0} onChange={(e) => set({ lat0: e.target.value })} className={cn("tabular", bad(value.lat0) && "border-danger")} placeholder={fmt === "dms" ? "38°15'" : "38.25"} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-lon`}>{t("coords.hatt.lon0")}</Label>
          <Input id={`${id}-lon`} value={value.lon0} onChange={(e) => set({ lon0: e.target.value })} className={cn("tabular", bad(value.lon0) && "border-danger")} placeholder={fmt === "dms" ? "0°15'" : "0.25"} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-mer`}>{t("coords.hatt.meridian")}</Label>
        <Select<"athens" | "greenwich">
          id={`${id}-mer`}
          value={value.meridian}
          onValueChange={(meridian) => set({ meridian })}
          options={[
            { value: "athens", label: t("coords.hatt.athens") },
            { value: "greenwich", label: t("coords.hatt.greenwich") },
          ]}
        />
      </div>
      {withCoefficients && (
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-coef`}>{t("coords.hatt.coefficients")}</Label>
          <Textarea id={`${id}-coef`} rows={2} value={value.coefficients} onChange={(e) => set({ coefficients: e.target.value })} className={cn("font-mono text-xs", coeffBad && "border-danger")} placeholder={t("coords.hatt.coefficientsHint")} />
          {coeffBad && <p className="text-xs text-danger">{t("coords.hatt.coefficientsBad")}</p>}
        </div>
      )}
    </fieldset>
  );
}

export function Note({ tone, children, testId }: { tone: "warning" | "info"; children: React.ReactNode; testId?: string }) {
  const Icon = tone === "warning" ? AlertTriangle : Info;
  return (
    <div className={cn("flex items-start gap-2 rounded-lg px-3 py-2 text-xs", tone === "warning" ? "bg-warning-subtle text-warning" : "bg-accent-subtle text-muted")} data-testid={testId}>
      <Icon className="mt-0.5 size-3.5 shrink-0" />
      <div>{children}</div>
    </div>
  );
}

export function IssueList({ issues }: { issues: Issue[] }) {
  const { t } = useTranslation();
  if (!issues.length) return null;
  return (
    <ul className="space-y-1 text-xs">
      {issues.map((i, k) => (
        <li key={k} className={cn(i.severity === "error" ? "text-danger" : i.severity === "warning" ? "text-warning" : "text-muted")}>
          {t(`issues.codes.${i.code}`, { ...issueParams(i.params), defaultValue: i.message })}
        </li>
      ))}
    </ul>
  );
}

/** useRunner whose errors show the Greek text of coded engine failures (COORD_*). */
export function useCoordsRunner<T>() {
  const { t } = useTranslation();
  const r = useRunner<T>();
  const { run: baseRun } = r;
  const run = useCallback(
    (fn: () => Promise<T>) =>
      baseRun(async () => {
        try {
          return await fn();
        } catch (e) {
          const coded = coordsErrorCode(e);
          if (coded) throw new Error(t(`issues.codes.${coded.code}`, { ...issueParams(coded.params), defaultValue: coded.code }));
          throw e;
        }
      }),
    [baseRun, t],
  );
  return { ...r, run };
}
