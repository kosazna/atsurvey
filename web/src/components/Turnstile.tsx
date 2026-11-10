// Cloudflare Turnstile bot check for sign-up / sign-in / password reset. Renders nothing unless
// VITE_TURNSTILE_SITE_KEY is set (the hosted Supabase project then requires the token; see
// docs/supabase.md). The script is loaded on demand from challenges.cloudflare.com (CSP).
import { useEffect, useRef } from "react";
import { env } from "@/lib/env";

interface TurnstileApi {
  render(el: HTMLElement, opts: { sitekey: string; callback: (token: string) => void; "expired-callback": () => void; language?: string }): string;
  reset(id: string): void;
  remove(id: string): void;
}
declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
let loading: Promise<TurnstileApi> | null = null;

function loadTurnstile(): Promise<TurnstileApi> {
  loading ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = SCRIPT;
    s.async = true;
    s.onload = () => (window.turnstile ? resolve(window.turnstile) : reject(new Error("turnstile")));
    s.onerror = () => reject(new Error("turnstile"));
    document.head.appendChild(s);
  });
  return loading;
}

export const captchaEnabled = Boolean(env.turnstileSiteKey);

export function Turnstile({ onToken, language }: { onToken: (token: string | null) => void; language: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!captchaEnabled || !ref.current) return;
    let id: string | null = null;
    let api: TurnstileApi | null = null;
    const el = ref.current;
    void loadTurnstile().then((t) => {
      api = t;
      id = t.render(el, {
        sitekey: env.turnstileSiteKey,
        callback: (token) => onToken(token),
        "expired-callback": () => onToken(null),
        language,
      });
    });
    return () => {
      if (api && id) api.remove(id);
    };
  }, [onToken, language]);
  if (!captchaEnabled) return null;
  return <div ref={ref} className="min-h-16" />;
}
