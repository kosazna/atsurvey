import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { supabase } from "@/lib/supabase";

/** E-mail change: confirmed from both the old and the new address (double_confirm_changes). */
export function EmailCard({ current }: { current: string }) {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setBusy(true);
    const { error } = await supabase.auth.updateUser(
      { email: email.trim() },
      { emailRedirectTo: `${window.location.origin}/account` },
    );
    setBusy(false);
    if (error) {
      toast.error(error.message);
      return;
    }
    setEmail("");
    toast.success(t("sec.email.sent"));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("sec.email.title")}</CardTitle>
        <CardDescription>{current}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
          <div className="min-w-56 flex-1 space-y-1.5">
            <Label htmlFor="new-email">{t("sec.email.new")}</Label>
            <Input id="new-email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <Button type="submit" size="sm" variant="secondary" disabled={busy || email.trim() === current}>
            {t("sec.email.change")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
