// Public landing page for signed-out visitors. The hero "screenshot" is composed from real
// UI primitives and an SVG plan, so it follows tokens, theme and language.
import { Link, Navigate, useNavigate } from "@tanstack/react-router";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Crosshair,
  FileDown,
  FileSpreadsheet,
  Layers,
  Map as MapIcon,
  Ruler,
  ShieldCheck,
  Sigma,
  Telescope,
  Upload,
  Waypoints,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Logo } from "@/components/Logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useSession } from "@/data/session";
import { toggleLanguage } from "@/lib/i18n";
import { toggleTheme, useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const INSTRUMENTS = ["Leica GSI-8 / GSI-16", "Leica LandXML", "Trimble JobXML", "Nikon RAW", "Carlson RW5", "CSV / Excel"];

function HeroComposition() {
  const { t } = useTranslation();
  // plan coordinates (SVG units) for a small link traverse with detail points and a building
  const trav: [number, number][] = [
    [40, 210],
    [110, 160],
    [190, 190],
    [270, 130],
    [350, 150],
    [420, 70],
  ];
  const detail: [number, number][] = [
    [140, 120],
    [160, 135],
    [215, 150],
    [235, 95],
    [300, 185],
    [320, 105],
    [380, 120],
  ];
  return (
    <div className="relative overflow-hidden rounded-xl border bg-surface shadow-lg" aria-hidden>
      {/* window chrome */}
      <div className="flex h-9 items-center gap-2 border-b bg-surface px-3">
        <span className="size-2.5 rounded-full bg-border-strong" />
        <span className="size-2.5 rounded-full bg-border-strong" />
        <span className="size-2.5 rounded-full bg-border-strong" />
        <span className="ml-3 truncate text-xs text-muted">{t("landing.mock.title")}</span>
        <Badge variant="success" className="ml-auto">
          <Check /> {t("landing.mock.within")}
        </Badge>
      </div>
      <div className="grid sm:grid-cols-[1fr_1.15fr]">
        <div className="space-y-3 border-b p-3 sm:border-b-0 sm:border-r">
          <div className="grid grid-cols-2 gap-2">
            {[
              { k: t("landing.mock.angular"), v: "−5 cc" },
              { k: t("landing.mock.linear"), v: "0.2 cm" },
              { k: t("landing.mock.relative"), v: "1:368 377" },
              { k: "σ₀", v: "0.94" },
            ].map((s) => (
              <div key={s.k} className="rounded-lg border px-2.5 py-2">
                <div className="text-xs text-muted">{s.k}</div>
                <div className="text-sm font-semibold tabular">{s.v}</div>
              </div>
            ))}
          </div>
          <table className="w-full text-xs tabular">
            <thead>
              <tr className="text-muted">
                <th className="py-1 text-left font-medium">{t("landing.mock.point")}</th>
                <th className="py-1 text-right font-medium">X</th>
                <th className="py-1 text-right font-medium">Y</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["S1", "476458.316", "4205121.644"],
                ["S2", "476641.902", "4205183.207"],
                ["S3", "476802.455", "4205262.981"],
                ["14", "476796.155", "4205296.680"],
              ].map((r) => (
                <tr key={r[0]} className="border-t">
                  <td className="py-1 font-medium">{r[0]}</td>
                  <td className="py-1 text-right">{r[1]}</td>
                  <td className="py-1 text-right">{r[2]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="relative h-56 bg-map-bg sm:h-auto">
          <svg viewBox="0 0 460 260" className="h-full w-full" preserveAspectRatio="xMidYMid meet">
            <defs>
              <pattern id="lg" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M40 0H0V40" fill="none" stroke="var(--color-map-grid)" strokeWidth="1" />
              </pattern>
            </defs>
            <rect width="460" height="260" fill="url(#lg)" />
            <polygon points="140,120 160,135 215,150 235,95" fill="var(--color-accent-subtle)" stroke="var(--color-accent)" strokeWidth="1.2" />
            <polyline points="300,185 320,105 380,120" fill="none" stroke="var(--color-success)" strokeWidth="1.4" strokeDasharray="4 3" />
            <polyline points={trav.map((p) => p.join(",")).join(" ")} fill="none" stroke="var(--color-traverse-line)" strokeWidth="1.8" />
            {trav.map(([x, y], i) => {
              const known = i < 2 || i > 3;
              return known ? (
                <path key={i} d={`M${x} ${y - 7} L${x + 6.5} ${y + 5} L${x - 6.5} ${y + 5}Z`} fill="var(--color-point-control)" stroke="var(--color-map-bg)" strokeWidth="1.5" />
              ) : (
                <g key={i}>
                  <ellipse cx={x} cy={y} rx="14" ry="6" transform={`rotate(${i * 25} ${x} ${y})`} fill="none" stroke="var(--color-warning)" strokeWidth="1" />
                  <circle cx={x} cy={y} r="4.5" fill="var(--color-point-traverse)" stroke="var(--color-map-bg)" strokeWidth="1.5" />
                </g>
              );
            })}
            {detail.map(([x, y], i) => (
              <circle key={i} cx={x} cy={y} r="2.6" fill="var(--color-point-detail)" />
            ))}
          </svg>
          <div className="absolute bottom-2 left-2 rounded-md border bg-surface px-2 py-1 text-xs tabular text-muted">ΕΓΣΑ87 · X 476 641.90 Y 4 205 183.21</div>
        </div>
      </div>
    </div>
  );
}

export function LandingPage() {
  const { t, i18n } = useTranslation();
  const { mode, enterDemo } = useSession();
  const navigate = useNavigate();
  const theme = useTheme();
  if (mode === "cloud" || mode === "demo") return <Navigate to="/projects" />;

  const demo = () => {
    enterDemo();
    void navigate({ to: "/projects" });
  };

  const features = [
    { icon: <Upload />, k: "import" },
    { icon: <Ruler />, k: "reductions" },
    { icon: <Waypoints />, k: "traverses" },
    { icon: <Sigma />, k: "lsa" },
    { icon: <Crosshair />, k: "cogo" },
    { icon: <Layers />, k: "linework" },
    { icon: <MapIcon />, k: "map" },
    { icon: <FileDown />, k: "exports" },
    { icon: <ShieldCheck />, k: "checks" },
  ];
  const steps = ["1", "2", "3", "4"];
  const faqs = ["1", "2", "3", "4", "5"];

  return (
    <div className="h-full overflow-y-auto bg-bg" data-testid="landing">
      <header className="sticky top-0 z-(--z-dropdown) border-b bg-bg/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
          <Logo />
          <nav className="hidden items-center gap-5 text-sm text-muted md:flex">
            <a href="#features" className="hover:text-fg">
              {t("landing.nav.features")}
            </a>
            <a href="#how" className="hover:text-fg">
              {t("landing.nav.how")}
            </a>
            <a href="#pricing" className="hover:text-fg">
              {t("landing.nav.pricing")}
            </a>
            <a href="#faq" className="hover:text-fg">
              FAQ
            </a>
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={toggleLanguage}>
              {i18n.language === "el" ? "EN" : "ΕΛ"}
            </Button>
            <Button variant="ghost" size="sm" onClick={toggleTheme} aria-label={t("common.theme")}>
              {theme === "dark" ? t("common.light") : t("common.dark")}
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to="/login">{t("landing.signIn")}</Link>
            </Button>
          </div>
        </div>
      </header>

      {/* hero */}
      <section className="mx-auto grid max-w-6xl items-center gap-10 px-4 pb-16 pt-14 lg:grid-cols-[1fr_1.15fr] lg:pt-20">
        <div>
          <Badge variant="secondary" className="mb-5">
            {t("landing.eyebrow")}
          </Badge>
          <h1 className="text-3xl font-semibold leading-tight tracking-tight">{t("landing.title")}</h1>
          <p className="mt-4 max-w-xl text-lg text-muted">{t("landing.subtitle")}</p>
          <div className="mt-8 flex flex-wrap gap-2">
            <Button size="lg" onClick={demo} data-testid="try-demo">
              {t("landing.ctaDemo")} <ArrowRight />
            </Button>
            <Button size="lg" variant="outline" asChild>
              <Link to="/login">{t("landing.ctaSignIn")}</Link>
            </Button>
          </div>
          <p className="mt-3 text-xs text-muted">{t("landing.ctaHint")}</p>
        </div>
        <HeroComposition />
      </section>

      {/* instruments */}
      <section className="border-y bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-5">
          <span className="text-xs font-medium text-muted">{t("landing.instruments")}</span>
          {INSTRUMENTS.map((i) => (
            <span key={i} className="flex items-center gap-1.5 text-sm text-muted">
              <Telescope className="size-3.5" /> {i}
            </span>
          ))}
        </div>
      </section>

      {/* features */}
      <section id="features" className="mx-auto max-w-6xl scroll-mt-16 px-4 py-20">
        <h2 className="text-2xl font-semibold tracking-tight">{t("landing.featuresTitle")}</h2>
        <p className="mt-2 max-w-2xl text-muted">{t("landing.featuresSubtitle")}</p>
        <div className="mt-10 grid gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <div key={f.k} className="bg-surface p-5">
              <span className="flex size-8 items-center justify-center rounded-lg bg-accent-subtle text-accent [&_svg]:size-4">{f.icon}</span>
              <h3 className="mt-4 text-sm font-semibold">{t(`landing.features.${f.k}.title`)}</h3>
              <p className="mt-1 text-sm leading-relaxed text-muted">{t(`landing.features.${f.k}.text`)}</p>
            </div>
          ))}
        </div>
      </section>

      {/* how it works */}
      <section id="how" className="scroll-mt-16 border-y bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-20">
          <h2 className="text-2xl font-semibold tracking-tight">{t("landing.howTitle")}</h2>
          <ol className="mt-10 grid gap-6 md:grid-cols-4">
            {steps.map((s, i) => (
              <li key={s} className="relative">
                <span className="flex size-8 items-center justify-center rounded-full border bg-bg text-sm font-semibold tabular">{i + 1}</span>
                <h3 className="mt-4 text-sm font-semibold">{t(`landing.how.${s}.title`)}</h3>
                <p className="mt-1 text-sm leading-relaxed text-muted">{t(`landing.how.${s}.text`)}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* pricing */}
      <section id="pricing" className="mx-auto max-w-6xl scroll-mt-16 px-4 py-20">
        <h2 className="text-2xl font-semibold tracking-tight">{t("landing.pricingTitle")}</h2>
        <p className="mt-2 text-muted">{t("landing.pricingSubtitle")}</p>
        <div className="mt-10 grid gap-4 md:grid-cols-2">
          {(["free", "pro"] as const).map((plan) => {
            const items = t(`landing.plans.${plan}.items`, { returnObjects: true }) as string[];
            return (
              <div key={plan} className={cn("flex flex-col rounded-xl border bg-surface p-6", plan === "pro" && "border-accent")}>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold">{t(`landing.plans.${plan}.name`)}</h3>
                  {plan === "pro" && <Badge>{t("landing.plans.recommended")}</Badge>}
                </div>
                <div className="mt-3 text-3xl font-semibold tracking-tight tabular">{t(`landing.plans.${plan}.price`)}</div>
                <p className="mt-1 text-sm text-muted">{t(`landing.plans.${plan}.note`)}</p>
                <ul className="mt-6 flex-1 space-y-2">
                  {items.map((it) => (
                    <li key={it} className="flex items-start gap-2 text-sm">
                      <Check className="mt-0.5 size-4 shrink-0 text-success" /> {it}
                    </li>
                  ))}
                </ul>
                <Button className="mt-6" variant={plan === "pro" ? "default" : "outline"} onClick={plan === "free" ? demo : undefined} asChild={plan === "pro"}>
                  {plan === "pro" ? <Link to="/login">{t("landing.plans.pro.cta")}</Link> : <span>{t("landing.plans.free.cta")}</span>}
                </Button>
              </div>
            );
          })}
        </div>
      </section>

      {/* faq */}
      <section id="faq" className="scroll-mt-16 border-t bg-surface">
        <div className="mx-auto max-w-3xl px-4 py-20">
          <h2 className="text-2xl font-semibold tracking-tight">{t("landing.faqTitle")}</h2>
          <div className="mt-8 divide-y rounded-xl border bg-bg">
            {faqs.map((f) => (
              <details key={f} className="group px-5 py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-medium">
                  {t(`landing.faq.${f}.q`)}
                  <ChevronDown className="size-4 shrink-0 text-muted transition-transform group-open:rotate-180" />
                </summary>
                <p className="mt-2 text-sm leading-relaxed text-muted">{t(`landing.faq.${f}.a`)}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* closing CTA */}
      <section className="mx-auto max-w-6xl px-4 py-20 text-center">
        <h2 className="text-2xl font-semibold tracking-tight">{t("landing.closingTitle")}</h2>
        <p className="mx-auto mt-2 max-w-xl text-muted">{t("landing.closingText")}</p>
        <div className="mt-6 flex justify-center gap-2">
          <Button size="lg" onClick={demo}>
            {t("landing.ctaDemo")} <ArrowRight />
          </Button>
        </div>
      </section>

      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-6 text-xs text-muted">
          <Logo className="text-fg" />
          <span>© {new Date().getFullYear()} ATSurvey</span>
          <span className="flex items-center gap-1">
            <FileSpreadsheet className="size-3.5" /> ΕΓΣΑ87 · EPSG:2100
          </span>
          <nav className="ml-auto flex gap-4">
            <a href="#" className="hover:text-fg">
              {t("landing.footer.terms")}
            </a>
            <a href="#" className="hover:text-fg">
              {t("landing.footer.privacy")}
            </a>
            <a href="#" className="hover:text-fg">
              {t("landing.footer.contact")}
            </a>
          </nav>
        </div>
      </footer>
    </div>
  );
}
