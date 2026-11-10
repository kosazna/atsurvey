import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { supabase } from "@/lib/supabase";

export const MIN_PASSWORD_LENGTH = 10;

/**
 * Password change. With secure_password_change on, Supabase asks for a re-authentication code
 * (sent by e-mail) when the last sign-in is not recent; the form then asks for it.
 */
export function PasswordCard() {
  const { t } = useTranslation();
  const [password, setPassword] = useState("");
  const [nonce, setNonce] = useState("");
  const [needsNonce, setNeedsNonce] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setBusy(true);
    try {
      const { error } = await supabase.auth.updateUser(needsNonce ? { password, nonce: nonce.trim() } : { password });
      if (error?.code === "reauthentication_needed" || error?.code === "reauth_nonce_missing") {
        const re = await supabase.auth.reauthenticate();
        if (re.error) throw re.error;
        setNeedsNonce(true);
        toast.info(t("sec.password.nonceSent"));
        return;
      }
      if (error) throw error;
      setPassword("");
      setNonce("");
      setNeedsNonce(false);
      toast.success(t("sec.password.changed"));
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("sec.password.title")}</CardTitle>
        <CardDescription>{t("sec.password.hint")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="new-password">{t("sec.password.new")}</Label>
            <Input
              id="new-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {needsNonce && (
            <div className="space-y-1.5">
              <Label htmlFor="reauth-nonce">{t("sec.password.nonce")}</Label>
              <Input id="reauth-nonce" inputMode="numeric" autoComplete="one-time-code" required value={nonce} onChange={(e) => setNonce(e.target.value)} />
            </div>
          )}
          <Button type="submit" size="sm" disabled={busy} data-testid="btn-change-password">
            {needsNonce ? t("sec.password.confirm") : t("sec.password.change")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
