import type { Factor } from "@supabase/supabase-js";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSession } from "@/data/session";
import { supabase } from "@/lib/supabase";

interface Enrolment {
  factorId: string;
  qr: string;
  secret: string;
}

/** TOTP enrolment / removal. Removing needs an aal2 session (Supabase enforces it). */
export function TwoFactorCard() {
  const { t } = useTranslation();
  const { refreshMfa } = useSession();
  const [factors, setFactors] = useState<Factor[]>([]);
  const [enrolment, setEnrolment] = useState<Enrolment | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!supabase) return;
    const { data } = await supabase.auth.mfa.listFactors();
    setFactors(data?.totp ?? []);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const verified = factors.filter((f) => f.status === "verified");

  async function start() {
    if (!supabase) return;
    setBusy(true);
    // drop abandoned, unverified enrolments first (they count towards the factor limit)
    for (const f of factors.filter((x) => x.status !== "verified")) await supabase.auth.mfa.unenroll({ factorId: f.id });
    const { data, error } = await supabase.auth.mfa.enroll({ factorType: "totp", friendlyName: `ATSurvey ${new Date().toISOString().slice(0, 10)}` });
    setBusy(false);
    if (error || !data) {
      toast.error(error?.message ?? "enroll failed");
      return;
    }
    setEnrolment({ factorId: data.id, qr: data.totp.qr_code, secret: data.totp.secret });
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    if (!supabase || !enrolment) return;
    setBusy(true);
    const { error } = await supabase.auth.mfa.challengeAndVerify({ factorId: enrolment.factorId, code: code.trim() });
    setBusy(false);
    if (error) {
      toast.error(t("sec.mfa.wrongCode"));
      return;
    }
    setEnrolment(null);
    setCode("");
    toast.success(t("sec.mfa.enabled"));
    await load();
    await refreshMfa();
  }

  async function disable(factorId: string) {
    if (!supabase) return;
    setBusy(true);
    const { error } = await supabase.auth.mfa.unenroll({ factorId });
    setBusy(false);
    if (error) {
      toast.error(error.code === "insufficient_aal" ? t("sec.mfa.needAal2") : error.message);
      return;
    }
    toast.success(t("sec.mfa.disabled"));
    await load();
    await refreshMfa();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {t("sec.mfa.title")}
          <Badge variant={verified.length ? "success" : "secondary"}>{verified.length ? t("sec.mfa.on") : t("sec.mfa.off")}</Badge>
        </CardTitle>
        <CardDescription>{t("sec.mfa.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {verified.map((f) => (
          <div key={f.id} className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
            <span>{f.friendly_name ?? "TOTP"}</span>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => void disable(f.id)}>
              {t("sec.mfa.disable")}
            </Button>
          </div>
        ))}
        {!verified.length && !enrolment && (
          <Button size="sm" disabled={busy} onClick={() => void start()} data-testid="btn-mfa-enable">
            {t("sec.mfa.enable")}
          </Button>
        )}
        {enrolment && (
          <form onSubmit={verify} className="space-y-3">
            <p className="text-sm text-muted">{t("sec.mfa.scan")}</p>
            <div className="flex flex-wrap items-center gap-4">
              <img src={enrolment.qr} alt="QR" className="size-40 rounded-lg border bg-white p-2" />
              <code className="break-all rounded bg-surface-sunken px-2 py-1 text-xs" data-testid="mfa-secret">
                {enrolment.secret}
              </code>
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="mfa-code">{t("sec.mfa.code")}</Label>
                <Input id="mfa-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" required value={code} onChange={(e) => setCode(e.target.value)} />
              </div>
              <Button type="submit" size="sm" disabled={busy} data-testid="btn-mfa-verify">
                {t("sec.mfa.verify")}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
