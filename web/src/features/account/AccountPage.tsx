import { Navigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useSession } from "@/data/session";
import { supabase } from "@/lib/supabase";
import { setTheme, useTheme } from "@/lib/theme";
import { PageShell } from "./PageShell";
import { DataCard } from "./security/DataCard";
import { EmailCard } from "./security/EmailCard";
import { PasswordCard } from "./security/PasswordCard";
import { TwoFactorCard } from "./security/TwoFactorCard";

export function AccountPage() {
  const { t, i18n } = useTranslation();
  const { mode, session } = useSession();
  const theme = useTheme();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const cloud = mode === "cloud" && supabase && session;

  useEffect(() => {
    if (!cloud) return;
    void supabase!
      .from("profiles")
      .select("full_name, locale")
      .eq("id", session!.user.id)
      .maybeSingle()
      .then(({ data }) => {
        if (data?.full_name) setName(data.full_name as string);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cloud, session?.user.id]);

  if (mode === "none") return <Navigate to="/" />;
  if (mode === "loading") return null;

  const changeLocale = async (lng: "el" | "en") => {
    await i18n.changeLanguage(lng);
    if (cloud) await supabase!.from("profiles").update({ locale: lng }).eq("id", session!.user.id);
  };

  const saveProfile = async () => {
    if (!cloud) return;
    setBusy(true);
    const { error } = await supabase!.from("profiles").update({ full_name: name.trim() || null }).eq("id", session!.user.id);
    setBusy(false);
    if (error) toast.error(error.message);
    else toast.success(t("account.saved"));
  };

  return (
    <PageShell title={t("account.title")} description={t("account.subtitle")}>
      <Card>
        <CardHeader>
          <CardTitle>{t("account.profile")}</CardTitle>
          <CardDescription>{cloud ? session!.user.email : t("account.demoProfile")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="full-name">{t("account.fullName")}</Label>
            <Input id="full-name" value={name} disabled={!cloud} onChange={(e) => setName(e.target.value)} placeholder={t("account.fullNamePlaceholder")} />
          </div>
          <Button size="sm" onClick={() => void saveProfile()} disabled={!cloud || busy} data-testid="btn-save-profile">
            {t("common.save")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("account.preferences")}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>{t("common.language")}</Label>
            <Select<"el" | "en">
              value={i18n.language === "en" ? "en" : "el"}
              onValueChange={(v) => void changeLocale(v)}
              options={[
                { value: "el", label: "Ελληνικά" },
                { value: "en", label: "English" },
              ]}
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t("common.theme")}</Label>
            <Select<"light" | "dark">
              value={theme}
              onValueChange={(v) => setTheme(v)}
              options={[
                { value: "light", label: t("common.light") },
                { value: "dark", label: t("common.dark") },
              ]}
            />
          </div>
        </CardContent>
      </Card>

      {cloud ? (
        <section className="space-y-4" aria-labelledby="security-heading">
          <div>
            <h2 id="security-heading" className="text-base font-semibold">
              {t("sec.title")}
            </h2>
            <p className="text-sm text-muted">{t("sec.subtitle")}</p>
          </div>
          <TwoFactorCard />
          <PasswordCard />
          <EmailCard current={session!.user.email ?? ""} />
          <DataCard email={session!.user.email ?? ""} />
        </section>
      ) : (
        <p className="text-sm text-muted">{t("sec.cloudOnly")}</p>
      )}
    </PageShell>
  );
}
