// Levelling network ("Δίκτυο" mode of the Levelling section): lines grid, weights, datum, and
// least-squares adjustment via /v1/leveling/network. Lines can be built from the section's
// readings (forward and return runs, split at benchmarks and section points).
import { ListRestart, Network, RefreshCw } from "lucide-react";
import { type ReactNode, Suspense, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type { LevelingData } from "@/data/store";
import { isNotAvailable } from "@/lib/api";
import { apiErrorMessage } from "@/lib/apiErrors";
import { instrumentsApi, type LevelNetDatum, type LevelNetResult, type LevelNetWeighting } from "@/lib/instrumentsApi";
import { emptyNetwork, type LevelNetData, type LevelNetRow, readingsToNetworkLines, toLevelNetRequest, validateNetwork } from "@/lib/leveling";
import { parseNum, uid } from "@/lib/utils";
import type { Col } from "../grid/DataGrid";
import { DataGrid } from "../grid/LazyDataGrid";
import { LevelNetResults } from "./LevelNetResults";

interface Props {
  lv: LevelingData;
  save: (patch: Partial<LevelingData>) => void;
  /** The section's benchmarks card (shared with the line mode) */
  benchmarks: ReactNode;
}

const numCol = (id: "dh" | "length_km" | "setups", title: string, decimals: number, width: number): Col<LevelNetRow> => ({
  id,
  title,
  width,
  kind: "number",
  get: (r) => (r[id] === null ? "" : (r[id] as number).toFixed(decimals)),
  set: (r, v) => {
    if (String(v).trim() === "") return { ...r, [id]: null };
    const n = parseNum(String(v));
    if (n === null || (id !== "dh" && n <= 0)) return null;
    return { ...r, [id]: id === "setups" ? Math.round(n) : n };
  },
});

/** Number input that keeps the typed text and commits only positive numbers. */
function PositiveInput({ id, value, onCommit }: { id: string; value: number; onCommit: (n: number) => void }) {
  const [text, setText] = useState(String(value));
  const n = parseNum(text);
  return (
    <Input
      id={id}
      className={n === null || n <= 0 ? "border-danger tabular" : "tabular"}
      inputMode="decimal"
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        const v = parseNum(e.target.value);
        if (v !== null && v > 0) onCommit(v);
      }}
    />
  );
}

export function LevelNetPanel({ lv, save, benchmarks }: Props) {
  const { t } = useTranslation();
  const net = lv.network ?? emptyNetwork();
  const setNet = (patch: Partial<LevelNetData>) => save({ network: { ...net, ...patch } });
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<LevelNetResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const problems = validateNetwork(lv, net);
  const blocking = problems.some((p) => p.key === "noLines" || (p.key === "noBenchmark" && net.datum === "fixed"));

  const cols = useMemo<Col<LevelNetRow>[]>(
    () => [
      { id: "frm", title: t("instruments.levnet.frm"), width: 90, get: (r) => r.frm, set: (r, v) => ({ ...r, frm: String(v).trim() }), invalid: (r) => !r.frm },
      { id: "to", title: t("instruments.levnet.to"), width: 90, get: (r) => r.to, set: (r, v) => ({ ...r, to: String(v).trim() }), invalid: (r) => !r.to || r.to === r.frm },
      { ...numCol("dh", t("instruments.levnet.dh"), 4, 100), invalid: (r) => r.dh === null },
      numCol("length_km", t("instruments.levnet.length"), 3, 95),
      numCol("setups", t("instruments.levnet.setups"), 0, 70),
    ],
    [t],
  );

  const fromReadings = () => {
    const lines = readingsToNetworkLines(lv);
    if (!lines.length) return toast.info(t("instruments.levnet.fromReadingsNone"));
    setNet({ lines: lines.map((l) => ({ id: uid(), ...l })) });
    toast.success(t("instruments.levnet.fromReadingsDone", { count: lines.length }));
  };

  const compute = async () => {
    setBusy(true);
    setErr(null);
    try {
      setRes(await instrumentsApi.levelNetwork(toLevelNetRequest(lv, net)));
    } catch (e) {
      setRes(null);
      setErr(isNotAvailable(e) ? t("tools.notAvailable") : apiErrorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-4 p-4 xl:grid-cols-[1fr_1.1fr]">
      <div className="space-y-4">
        {benchmarks}
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
            <span className="text-sm font-medium">{t("instruments.levnet.lines")}</span>
            <Button size="sm" variant="ghost" className="ml-auto" onClick={fromReadings} disabled={!lv.rows.length} data-testid="levnet-from-readings">
              <ListRestart /> {t("instruments.levnet.fromReadings")}
            </Button>
            <span className="w-full text-xs text-muted">{t("instruments.levnet.linesHint")}</span>
          </div>
          <div className="h-72" data-testid="grid-levnet">
            <Suspense fallback={<Skeleton className="m-3 h-60" />}>
              <DataGrid
                rows={net.lines}
                columns={cols}
                onChange={(lines) => setNet({ lines })}
                makeRow={() => ({ id: uid(), frm: net.lines.at(-1)?.to ?? "", to: "", dh: null, length_km: null, setups: null })}
                appendLabel={t("instruments.levnet.addLine")}
              />
            </Suspense>
          </div>
        </Card>
        <Card className="grid gap-3 p-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>{t("instruments.levnet.weighting")}</Label>
            <Select<LevelNetWeighting>
              value={net.weighting}
              onValueChange={(weighting) => setNet({ weighting })}
              options={(["length", "setups"] as const).map((w) => ({ value: w, label: t(`instruments.levnet.weightings.${w}`) }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="levnet-sigma">{t(net.weighting === "length" ? "instruments.levnet.sigmaKm" : "instruments.levnet.sigmaSetup")}</Label>
            <PositiveInput
              key={net.weighting}
              id="levnet-sigma"
              value={net.weighting === "length" ? net.sigma_mm_per_sqrt_km : net.sigma_mm_per_setup}
              onCommit={(n) => setNet(net.weighting === "length" ? { sigma_mm_per_sqrt_km: n } : { sigma_mm_per_setup: n })}
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t("instruments.levnet.datum")}</Label>
            <Select<LevelNetDatum>
              value={net.datum}
              onValueChange={(datum) => setNet({ datum })}
              options={(["fixed", "free"] as const).map((d) => ({ value: d, label: t(`instruments.levnet.datums.${d}`) }))}
            />
          </div>
          {net.datum === "free" && (
            <div className="space-y-1.5">
              <Label htmlFor="levnet-free">{t("instruments.levnet.freePoints")}</Label>
              <Input id="levnet-free" value={net.free_points} onChange={(e) => setNet({ free_points: e.target.value })} />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="levnet-tb">{t("lev.tolBase")}</Label>
            <Input id="levnet-tb" className="tabular" inputMode="decimal" value={lv.tolerance_base_mm} onChange={(e) => save({ tolerance_base_mm: parseNum(e.target.value) ?? 0 })} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="levnet-tk">{t("lev.tolKm")}</Label>
            <Input id="levnet-tk" className="tabular" inputMode="decimal" value={lv.tolerance_mm_per_sqrt_km} onChange={(e) => save({ tolerance_mm_per_sqrt_km: parseNum(e.target.value) ?? 12 })} />
          </div>
          {net.datum === "free" && <p className="text-xs text-muted sm:col-span-2">{t("instruments.levnet.freePointsHint")}</p>}
        </Card>
        {problems.length > 0 && net.lines.length > 0 && (
          <ul className="space-y-1 text-xs text-warning">
            {problems.slice(0, 5).map((p) => (
              <li key={`${p.key}${p.row}`}>• {t(`instruments.levnet.problems.${p.key}`, { row: p.row })}</li>
            ))}
          </ul>
        )}
        <div className="flex items-center gap-3">
          <Button onClick={() => void compute()} disabled={busy || blocking} data-testid="btn-levnet">
            {busy ? <RefreshCw className="animate-spin" /> : <Network />} {t("instruments.levnet.compute")}
          </Button>
          <span className="text-xs text-muted">{t("instruments.levnet.formula")}</span>
        </div>
      </div>
      <LevelNetResults res={res} err={err} />
    </div>
  );
}
