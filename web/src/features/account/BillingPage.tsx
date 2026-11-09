import { useQuery } from "@tanstack/react-query";
import { Navigate } from "@tanstack/react-router";
import { Check, CreditCard, Lock } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/data/session";
import { api } from "@/lib/api";
import { apiErrorMessage } from "@/lib/apiErrors";
import { billingEnabled, env } from "@/lib/env";
import { cn } from "@/lib/utils";
import { PageShell } from "./PageShell";

interface PaddleGlobal {
  Environment: { set: (e: "sandbox" | "production") => void };
  Initialize: (o: { token: string; eventCallback?: (e: { name: string }) => void }) => void;
  Checkout: { open: (o: Record<string, unknown>) => void };
}
declare global {
  interface Window {
    Paddle?: PaddleGlobal;
  }
}

let paddleReady: Promise<PaddleGlobal> | null = null;
function loadPaddle(onEvent: (name: string) => void): Promise<PaddleGlobal> {
  paddleReady ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://cdn.paddle.com/paddle/v2/paddle.js";
    s.async = true;
    s.onload = () => {
      const P = window.Paddle;
      if (!P) return reject(new Error("Paddle.js failed to load"));
      if (env.paddleClientToken.startsWith("test_")) P.Environment.set("sandbox");
      P.Initialize({ token: env.paddleClientToken, eventCallback: (e) => onEvent(e.name) });
      resolve(P);
    };
    s.onerror = () => reject(new Error("Paddle.js failed to load"));
    document.head.appendChild(s);
  });
  return paddleReady;
}

export function BillingPage() {
  const { t } = useTranslation();
  const { mode, session, store } = useSession();
  const [interval, setInterval] = useState<"monthly" | "yearly">(env.paddlePriceMonthly ? "monthly" : "yearly");
  const me = useQuery({
    queryKey: ["me", mode],
    queryFn: async () => api.me(store ? await store.workspaceId() : null),
    enabled: mode === "cloud" || mode === "demo",
  });

  if (mode === "none") return <Navigate to="/" />;
  if (mode === "loading") return null;

  const plan = me.data?.plan ?? (mode === "demo" ? "anonymous" : "free");
  const canCheckout = billingEnabled && mode === "cloud";

  const checkout = async () => {
    try {
      const workspaceId = await store!.workspaceId();
      const priceId = interval === "monthly" ? env.paddlePriceMonthly : env.paddlePriceYearly;
      const P = await loadPaddle((name) => {
        if (name === "checkout.completed") {
          toast.success(t("billing.thanks"));
          window.setTimeout(() => void me.refetch(), 4000);
        }
      });
      P.Checkout.open({
        items: [{ priceId, quantity: 1 }],
        customData: { workspace_id: workspaceId },
        customer: session?.user.email ? { email: session.user.email } : undefined,
      });
    } catch (e) {
      toast.error(apiErrorMessage(e, t));
    }
  };

  return (
    <PageShell title={t("billing.title")} description={t("billing.subtitle")}>
      <Card>
        <CardHeader>
          <CardTitle>{t("billing.current")}</CardTitle>
          <CardDescription>{t(`billing.planDesc.${plan}`)}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          {me.isLoading ? (
            <Skeleton className="h-6 w-24" />
          ) : (
            <Badge variant={plan === "pro" ? "success" : "secondary"} className="px-2 py-1 text-sm" data-testid="current-plan">
              {t(`billing.plan.${plan}`)}
            </Badge>
          )}
          <div className="flex flex-wrap gap-1.5 text-xs text-muted">
            {(me.data?.export_formats ?? ["csv"]).map((f) => (
              <span key={f} className="rounded-md border px-1.5 py-0.5 uppercase">
                {f}
              </span>
            ))}
          </div>
        </CardContent>
      </Card>

      {plan !== "pro" && (
        <Card className="border-accent">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CreditCard className="size-4" /> {t("billing.upgradeTitle")}
            </CardTitle>
            <CardDescription>{t("billing.upgradeText")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ul className="grid gap-2 sm:grid-cols-2">
              {(t("landing.plans.pro.items", { returnObjects: true }) as string[]).map((it) => (
                <li key={it} className="flex items-start gap-2 text-sm">
                  <Check className="mt-0.5 size-4 shrink-0 text-success" /> {it}
                </li>
              ))}
            </ul>
            {canCheckout ? (
              <div className="flex flex-wrap items-center gap-2">
                {env.paddlePriceMonthly && env.paddlePriceYearly && (
                  <div className="flex rounded-md border p-0.5" role="radiogroup">
                    {(["monthly", "yearly"] as const).map((i) => (
                      <button
                        key={i}
                        role="radio"
                        aria-checked={interval === i}
                        onClick={() => setInterval(i)}
                        className={cn("h-7 cursor-pointer rounded px-3 text-xs", interval === i ? "bg-surface-sunken font-medium text-fg" : "text-muted")}
                      >
                        {t(`billing.${i}`)}
                      </button>
                    ))}
                  </div>
                )}
                <Button onClick={() => void checkout()} data-testid="btn-checkout">
                  {t("billing.upgrade")}
                </Button>
              </div>
            ) : (
              <div className="flex items-start gap-2 rounded-lg border border-dashed bg-surface-sunken p-3 text-sm text-muted" data-testid="billing-unconfigured">
                <Lock className="mt-0.5 size-4 shrink-0" />
                {mode === "demo" ? t("billing.demo") : t("billing.notConfigured")}
              </div>
            )}
          </CardContent>
        </Card>
      )}
      {me.isError && <p className="text-xs text-danger">{apiErrorMessage(me.error, t)}</p>}
    </PageShell>
  );
}
