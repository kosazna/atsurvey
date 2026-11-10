// Road axis (οριζοντιογραφία + μηκοτομή) from the tangent polygon: inputs and orchestration.
import { ArrowRight } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type AlignmentRequest, type AlignmentResult, parseChainage, parseProfile, parseVertices, setoutApi } from "@/lib/setoutApi";
import { NumberField, type NamedPoint, ResultBox, useOverlay, useProjectPoints, useRunner } from "../shared";
import { AlignmentQueries } from "./AlignmentQueries";
import { AlignmentTables } from "./AlignmentTables";
import { IssueList, Sketch } from "./common";

/** A line starting with a project point name and at most three numbers (R, A1, A2) takes the
 *  point's coordinates: "K1 300 150" → "K1 x y 300 150". */
export function expandProjectVertices(text: string, pts: Map<string, NamedPoint>): string {
  return text
    .split(/\r?\n/)
    .map((line) => {
      const parts = line.trim().split(/[\s;\t]+/).filter(Boolean);
      const p = parts.length && parts.length <= 4 ? pts.get(parts[0]) : undefined;
      return p ? [parts[0], p.x, p.y, ...parts.slice(1)].join(" ") : line;
    })
    .join("\n");
}

export function AlignmentTool() {
  const { t } = useTranslation();
  const pts = useProjectPoints();
  const [vtext, setVtext] = useState("");
  const [ptext, setPtext] = useState("");
  const [start, setStart] = useState("0+000");
  const v = useMemo(() => parseVertices(expandProjectVertices(vtext, pts)), [vtext, pts]);
  const p = useMemo(() => parseProfile(ptext), [ptext]);
  const ch0 = parseChainage(start);
  const r = useRunner<AlignmentResult>();
  const [req, setReq] = useState<AlignmentRequest | null>(null);
  const ready = v.vertices.length >= 2 && ch0 !== null && (p.pvis.length === 0 || p.pvis.length >= 2);
  const compute = () => {
    const next: AlignmentRequest = { vertices: v.vertices, start_chainage: ch0 ?? 0, profile: p.pvis.length >= 2 ? { pvis: p.pvis } : null };
    setReq(next);
    void r.run(() => setoutApi.alignment(next));
  };
  const res = r.result;
  const ok = res !== null && res.elements.length > 0;
  useOverlay(
    (res?.main_points ?? []).map((m) => ({ x: m.x, y: m.y, label: m.code, role: "result" as const })),
    res ? [res.polyline] : [],
  );
  const bad = [...v.bad, ...p.bad];
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <div className="space-y-1.5">
          <Label htmlFor="align-vertices">{t("setout.vertices")}</Label>
          <Textarea id="align-vertices" rows={7} value={vtext} onChange={(e) => setVtext(e.target.value)} className="font-mono text-xs" placeholder={"A 476000 4205000\nK1 476000 4205500 300 150\nK2 476400 4205800 250\nB 476900 4205800"} data-testid="align-vertices" />
          <p className="text-xs text-muted">{t("setout.verticesHint")}</p>
        </div>
        <div className="space-y-3">
          <NumberField label={t("setout.startChainage")} value={start} onChange={setStart} />
          <div className="space-y-1.5">
            <Label htmlFor="align-profile">{t("setout.profile")}</Label>
            <Textarea id="align-profile" rows={4} value={ptext} onChange={(e) => setPtext(e.target.value)} className="font-mono text-xs" placeholder={"0+000 100.00\n0+400 108.00 H3000\n1+200 102.00"} />
            <p className="text-xs text-muted">{t("setout.profileHint")}</p>
          </div>
          {bad.length > 0 && <p className="text-xs text-danger">{t("tools.badLines", { lines: bad.slice(0, 3).join(" · ") })}</p>}
          <Button disabled={!ready || r.busy} onClick={compute} data-testid="align-compute">
            {t("tools.compute")} <ArrowRight />
          </Button>
        </div>
      </div>
      <ResultBox error={r.error} testId="align-result">
        {res && (
          <div className="space-y-4">
            <IssueList issues={res.issues} />
            <Sketch
              testId="align-sketch"
              height={320}
              dashed={[res.vertices.map((x) => [x.x, x.y] as [number, number])]}
              lines={ok ? [res.polyline] : []}
              points={[
                ...res.vertices.map((x) => ({ x: x.x, y: x.y, label: x.name ?? undefined, tone: "input" as const })),
                ...res.main_points.filter((m) => m.code !== "BP" && m.code !== "EP").map((m) => ({ x: m.x, y: m.y, label: m.code, tone: "result" as const })),
              ]}
            />
            {ok && <AlignmentTables res={res} />}
          </div>
        )}
      </ResultBox>
      {ok && req && <AlignmentQueries req={req} res={res} />}
    </div>
  );
}
