import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MIN_PASSWORD_LENGTH } from "@/features/account/security/PasswordCard";
import { useSession } from "@/data/session";
import { supabase } from "@/lib/supabase";

/**
 * Target of the "forgot password" e-mail. The link signs the user in (recovery session,
 * detectSessionInUrl); here they choose the new password.
 */
export function ResetPasswordPage() {
  const { t } = useTranslation();
  const { mode } = useSession();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setBusy(true);
    const { error } = await supabase.auth.updateUser({ password });
    setBusy(false);
    if (error) {
      toast.error(error.message);
      return;
    }
    toast.success(t("sec.password.changed"));
    void navigate({ to: "/projects" });
  }

  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-6 px-4">
      <Logo />
      <div className="w-full max-w-sm rounded-xl border bg-surface p-5">
        <h1 className="text-base font-semibold">{t("sec.resetTitle")}</h1>
        {mode === "loading" ? null : mode !== "cloud" ? (
          <p className="mt-2 text-sm text-muted">{t("sec.resetInvalid")}</p>
        ) : (
          <form onSubmit={save} className="mt-3 space-y-3">
            <p className="text-sm text-muted">{t("sec.resetText")}</p>
            <div className="space-y-1.5">
              <Label htmlFor="reset-password">{t("sec.password.new")}</Label>
              <Input
                id="reset-password"
                type="password"
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <p className="text-xs text-muted">{t("sec.password.hint")}</p>
            </div>
            <Button type="submit" className="w-full" disabled={busy}>
              {t("sec.resetSave")}
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}
