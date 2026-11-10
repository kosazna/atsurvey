import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSession } from "@/data/session";
import { supabase } from "@/lib/supabase";

/** Shown instead of every page while a two-factor account is signed in with aal1 only. */
export function MfaChallenge() {
  const { t } = useTranslation();
  const { refreshMfa, signOut } = useSession();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setBusy(true);
    try {
      const { data, error } = await supabase.auth.mfa.listFactors();
      const factor = data?.totp.find((f) => f.status === "verified");
      if (error || !factor) throw error ?? new Error("no factor");
      const res = await supabase.auth.mfa.challengeAndVerify({ factorId: factor.id, code: code.trim() });
      if (res.error) throw res.error;
      await refreshMfa();
    } catch {
      setCode("");
      toast.error(t("sec.mfa.wrongCode"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-6 px-4">
      <Logo />
      <form onSubmit={verify} className="w-full max-w-xs space-y-4 rounded-xl border bg-surface p-5">
        <div className="flex items-center gap-2">
          <ShieldCheck className="size-5 text-accent" />
          <h1 className="text-base font-semibold">{t("sec.mfa.challengeTitle")}</h1>
        </div>
        <p className="text-sm text-muted">{t("sec.mfa.challengeText")}</p>
        <div className="space-y-1.5">
          <Label htmlFor="mfa-challenge">{t("sec.mfa.code")}</Label>
          <Input
            id="mfa-challenge"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            autoFocus
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </div>
        <Button type="submit" className="w-full" disabled={busy} data-testid="btn-mfa-challenge">
          {t("sec.mfa.verify")}
        </Button>
        <Button type="button" variant="ghost" className="w-full" onClick={() => void signOut("local")}>
          {t("common.signOut")}
        </Button>
      </form>
    </div>
  );
}
