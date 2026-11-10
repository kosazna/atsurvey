// Result tables of the road axis: vertex data, main points, elements and vertical curves.
import { useTranslation } from "react-i18next";
import { type AlignmentResult, formatChainage } from "@/lib/setoutApi";
import { fmtNum } from "@/lib/utils";
import { useWorkspace } from "../../../useWorkspace";
import { formatAngle, KV } from "../shared";

const TH = "py-1.5 text-right font-medium";
const TD = "py-1.5 text-right";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-medium">{title}</h3>
      <div className="scroll-x-visible">{children}</div>
    </section>
  );
}

export function AlignmentTables({ res }: { res: AlignmentResult }) {
  const { t } = useTranslation();
  const unit = useWorkspace().data.meta.angle_unit;
  const curves = res.vertices.filter((v) => v.radius !== null);
  return (
    <div className="space-y-5">
      <KV
        items={[
          { k: t("setout.length"), v: `${fmtNum(res.length, 3)} m`, strong: true },
          { k: t("setout.chainage"), v: `${formatChainage(res.start_chainage)} – ${formatChainage(res.end_chainage)}` },
        ]}
      />
      {curves.length > 0 && (
        <Section title={t("setout.vertexTable")}>
          <table className="w-full min-w-[720px] text-xs tabular" data-testid="align-vertex-table">
            <thead>
              <tr className="border-b text-muted">
                <th className="py-1.5 text-left font-medium">{t("setout.vertex")}</th>
                <th className={TH}>{t("setout.deflection")}</th>
                <th className={TH}>R</th>
                <th className={TH}>A₁ / A₂</th>
                <th className={TH}>L₁ / L₂</th>
                <th className={TH}>{t("setout.shift")}</th>
                <th className={TH}>{t("setout.tangent")}</th>
                <th className={TH}>{t("setout.arc")}</th>
                <th className={TH}>{t("setout.external")}</th>
              </tr>
            </thead>
            <tbody>
              {curves.map((v) => (
                <tr key={v.name} className="border-b last:border-0">
                  <td className="py-1.5 font-medium">{v.name}</td>
                  <td className={TD}>
                    {formatAngle(Math.abs(v.deflection ?? 0), unit)} {t(`setout.turn.${(v.deflection ?? 0) > 0 ? "right" : "left"}`)}
                  </td>
                  <td className={TD}>{fmtNum(v.radius, 2)}</td>
                  <td className={TD}>{`${fmtNum(v.a_in, 2)} / ${fmtNum(v.a_out, 2)}`}</td>
                  <td className={TD}>{`${fmtNum(v.l_in, 3)} / ${fmtNum(v.l_out, 3)}`}</td>
                  <td className={TD}>{`${fmtNum(v.shift_in, 3)} / ${fmtNum(v.shift_out, 3)}`}</td>
                  <td className={TD}>{`${fmtNum(v.t_in, 3)} / ${fmtNum(v.t_out, 3)}`}</td>
                  <td className={TD}>{fmtNum(v.arc_length, 3)}</td>
                  <td className={TD}>{fmtNum(v.external, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}
      <Section title={t("setout.mainPoints")}>
        <table className="w-full min-w-[640px] text-xs tabular" data-testid="align-main-points">
          <thead>
            <tr className="border-b text-muted">
              <th className="py-1.5 text-left font-medium">{t("setout.code")}</th>
              <th className="py-1.5 text-left font-medium">{t("setout.vertex")}</th>
              <th className={TH}>{t("setout.chainage")}</th>
              <th className={TH}>X</th>
              <th className={TH}>Y</th>
              <th className={TH}>{t("setout.azimuth")}</th>
              {res.profile && <th className={TH}>{t("setout.designZ")}</th>}
            </tr>
          </thead>
          <tbody>
            {res.main_points.map((m, i) => (
              <tr key={i} className="border-b last:border-0">
                <td className="py-1.5 font-medium" title={t(`setout.codes.${m.code}`)}>
                  {m.code} <span className="font-normal text-muted">{t(`setout.codes.${m.code}`)}</span>
                </td>
                <td className="py-1.5">{m.vertex}</td>
                <td className={TD}>{formatChainage(m.chainage, 3)}</td>
                <td className={TD}>{fmtNum(m.x, 3)}</td>
                <td className={TD}>{fmtNum(m.y, 3)}</td>
                <td className={TD}>{formatAngle(m.azimuth, unit)}</td>
                {res.profile && <td className={TD}>{fmtNum(m.z, 3)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
      <Section title={t("setout.elementTable")}>
        <table className="w-full min-w-[640px] text-xs tabular">
          <thead>
            <tr className="border-b text-muted">
              <th className="py-1.5 text-left font-medium">{t("setout.kind")}</th>
              <th className={TH}>{t("setout.chainage")}</th>
              <th className={TH}>L</th>
              <th className={TH}>R / A</th>
              <th className={TH}>{t("setout.azimuth")}</th>
            </tr>
          </thead>
          <tbody>
            {res.elements.map((e, i) => (
              <tr key={i} className="border-b last:border-0">
                <td className="py-1.5">
                  {t(`setout.kinds.${e.kind}`)}
                  {e.turn && <span className="text-muted"> · {t(`setout.turn.${e.turn}`)}</span>}
                </td>
                <td className={TD}>{`${formatChainage(e.start_chainage, 3)} – ${formatChainage(e.end_chainage, 3)}`}</td>
                <td className={TD}>{fmtNum(e.length, 3)}</td>
                <td className={TD}>{e.kind === "arc" ? `R ${fmtNum(e.radius, 2)}` : e.kind === "clothoid" ? `A ${fmtNum(e.a, 2)}` : "—"}</td>
                <td className={TD}>{`${formatAngle(e.start_azimuth, unit)} → ${formatAngle(e.end_azimuth, unit)}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
      {res.profile && res.profile.curves.length > 0 && (
        <Section title={t("setout.verticalCurves")}>
          <table className="w-full min-w-[560px] text-xs tabular">
            <thead>
              <tr className="border-b text-muted">
                <th className="py-1.5 text-left font-medium">{t("setout.vertex")}</th>
                <th className={TH}>{t("setout.chainage")}</th>
                <th className={TH}>{t("setout.grade")} %</th>
                <th className={TH}>L</th>
                <th className={TH}>H</th>
                <th className={TH}>PVC – PVT</th>
              </tr>
            </thead>
            <tbody>
              {res.profile.curves.map((c, i) => (
                <tr key={i} className="border-b last:border-0">
                  <td className="py-1.5">
                    {c.name} <span className="text-muted">{c.kind === "crest" ? t("setout.crest") : c.kind === "sag" ? t("setout.sag") : ""}</span>
                  </td>
                  <td className={TD}>{`${formatChainage(c.chainage)} · ${fmtNum(c.elevation, 3)}`}</td>
                  <td className={TD}>{`${fmtNum(res.profile!.grades[i].grade * 100, 3)} → ${fmtNum(res.profile!.grades[i + 1].grade * 100, 3)}`}</td>
                  <td className={TD}>{fmtNum(c.length, 2)}</td>
                  <td className={TD}>{fmtNum(c.radius, 0)}</td>
                  <td className={TD}>{`${formatChainage(c.pvc_chainage)} – ${formatChainage(c.pvt_chainage)}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}
    </div>
  );
}
