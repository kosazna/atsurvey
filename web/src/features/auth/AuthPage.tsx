import { Navigate, useNavigate } from "@tanstack/react-router";
import { ArrowRight, Calculator, FileDown, Map as MapIcon, Sparkles } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSession } from "@/data/session";
import { toggleLanguage } from "@/lib/i18n";
import { supabase } from "@/lib/supabase";

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.1A6.6 6.6 0 0 1 5.5 12c0-.73.13-1.44.34-2.1V7.06H2.18A11 11 0 0 0 1 12c0 1.77.43 3.45 1.18 4.94l3.66-2.84z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15A10.5 10.5 0 0 0 12 1 11 11 0 0 0 2.18 7.06L5.84 9.9C6.71 7.31 9.14 5.38 12 5.38z" />
    </svg>
  );
}

export function AuthPage() {
  const { t, i18n } = useTranslation();
  const { mode, enterDemo } = useSession();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [usePassword, setUsePassword] = useState(false);
  const [signUp, setSignUp] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  if (mode === "cloud" || mode === "demo") return <Navigate to="/projects" />;

  const redirectTo = `${window.location.origin}/projects`;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setBusy(true);
    try {
      if (!usePassword) {
        const { error } = await supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: redirectTo } });
        if (error) throw error;
        setSent(true);
      } else if (signUp) {
        const { error } = await supabase.auth.signUp({ email, password, options: { emailRedirectTo: redirectTo } });
        if (error) throw error;
        toast.success(t("auth.checkEmail"));
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
      }
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function google() {
    if (!supabase) return;
    const { error } = await supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo } });
    if (error) toast.error(error.message);
  }

  function demo() {
    enterDemo();
    void navigate({ to: "/projects" });
  }

  const features = [
    { icon: <Calculator />, text: i18n.language === "el" ? "Οδεύσεις, ταχυμετρικά, αναγωγές ΕΓΣΑ87" : "Traverses, detail points, EGSA87 reductions" },
    { icon: <MapIcon />, text: i18n.language === "el" ? "Άμεση απεικόνιση σημείων στον χάρτη" : "Instant point visualisation on the map" },
    { icon: <FileDown />, text: i18n.language === "el" ? "Εξαγωγή DXF, SHP, Excel, PDF" : "Export DXF, SHP, Excel, PDF" },
  ];

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      <div className="relative hidden overflow-hidden border-r bg-sidebar lg:flex lg:flex-col lg:justify-between lg:p-10">
        <Logo />
        <div className="relative z-10 max-w-md">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight">{t("app.tagline")}</h1>
          <ul className="mt-6 space-y-3">
            {features.map((f) => (
              <li key={f.text} className="flex items-center gap-3 text-sm text-muted-foreground">
                <span className="flex size-8 items-center justify-center rounded-lg border bg-card text-foreground shadow-xs [&_svg]:size-4">{f.icon}</span>
                {f.text}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative z-10 text-xs text-muted-foreground">ΕΓΣΑ87 · EPSG:2100</p>
        <svg className="pointer-events-none absolute -bottom-10 -right-16 h-[440px] w-[440px] text-border opacity-80" viewBox="0 0 400 400" aria-hidden>
          <defs>
            <pattern id="g" width="20" height="20" patternUnits="userSpaceOnUse">
              <path d="M20 0H0V20" fill="none" stroke="currentColor" strokeWidth="0.6" />
            </pattern>
          </defs>
          <rect width="400" height="400" fill="url(#g)" opacity="0.8" />
          <polyline points="40,300 110,240 180,265 250,190 320,210 370,120" fill="none" stroke="var(--pt-traverse)" strokeWidth="2" />
          {[
            [40, 300],
            [110, 240],
            [180, 265],
            [250, 190],
            [320, 210],
            [370, 120],
          ].map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r={i === 0 || i >= 4 ? 5 : 4} fill={i === 0 || i >= 4 ? "var(--pt-control)" : "var(--pt-traverse)"} />
          ))}
          {[
            [130, 200],
            [150, 215],
            [205, 230],
            [225, 150],
            [270, 240],
            [290, 160],
          ].map(([x, y], i) => (
            <circle key={`d${i}`} cx={x} cy={y} r={2.5} fill="var(--pt-detail)" />
          ))}
        </svg>
      </div>

      <div className="flex flex-col">
        <div className="flex items-center justify-between p-4 lg:justify-end">
          <span className="lg:hidden">
            <Logo />
          </span>
          <Button variant="ghost" size="sm" onClick={toggleLanguage}>
            {i18n.language === "el" ? "English" : "Ελληνικά"}
          </Button>
        </div>
        <div className="flex flex-1 items-center justify-center px-4 pb-16">
          <div className="w-full max-w-sm">
            <h2 className="text-xl font-semibold tracking-tight">{t("auth.title")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t("auth.subtitle")}</p>

            {supabase ? (
              <div className="mt-6 space-y-4">
                <Button variant="outline" className="w-full" onClick={google}>
                  <GoogleIcon /> {t("auth.google")}
                </Button>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <div className="h-px flex-1 bg-border" />
                  {t("auth.or")}
                  <div className="h-px flex-1 bg-border" />
                </div>
                {sent ? (
                  <div className="rounded-lg border bg-muted/50 p-3 text-sm">{t("auth.magicSent", { email })}</div>
                ) : (
                  <form onSubmit={submit} className="space-y-3">
                    <div className="space-y-1.5">
                      <Label htmlFor="email">{t("auth.email")}</Label>
                      <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@example.gr" />
                    </div>
                    {usePassword && (
                      <div className="space-y-1.5">
                        <Label htmlFor="password">{t("auth.password")}</Label>
                        <Input
                          id="password"
                          type="password"
                          autoComplete={signUp ? "new-password" : "current-password"}
                          required
                          minLength={8}
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                        />
                      </div>
                    )}
                    <Button type="submit" className="w-full" disabled={busy}>
                      {!usePassword ? t("auth.magicLink") : signUp ? t("auth.signUp") : t("auth.signIn")}
                    </Button>
                    <div className="flex items-center justify-between text-xs">
                      <button type="button" className="text-muted-foreground hover:text-foreground" onClick={() => setUsePassword(!usePassword)}>
                        {usePassword ? t("auth.magicLink") : t("auth.withPassword")}
                      </button>
                      {usePassword && (
                        <button type="button" className="text-primary hover:underline" onClick={() => setSignUp(!signUp)}>
                          {signUp ? t("auth.haveAccount") : t("auth.noAccount")}
                        </button>
                      )}
                    </div>
                  </form>
                )}
              </div>
            ) : (
              <div className="mt-6 rounded-lg border border-dashed bg-muted/40 p-3 text-xs text-muted-foreground">{t("auth.demoOnly")}</div>
            )}

            <div className="mt-8 rounded-xl border bg-card p-4 shadow-xs">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Sparkles className="size-4" />
                </span>
                <div className="flex-1">
                  <div className="text-sm font-medium">{t("auth.tryDemo")}</div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{t("auth.demoHint")}</p>
                </div>
              </div>
              <Button variant="secondary" className="mt-3 w-full" onClick={demo} data-testid="try-demo">
                {t("auth.tryDemo")} <ArrowRight />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
