// Which sign-in providers the auth server has switched on (GoTrue /auth/v1/settings), so the
// sign-in page never shows a button that would fail (e.g. Google without credentials).
import { useEffect, useState } from "react";
import { env, supabaseEnabled } from "./env";

export interface AuthProviders {
  google: boolean;
}

let cached: Promise<AuthProviders> | null = null;

export function fetchAuthProviders(): Promise<AuthProviders> {
  if (!supabaseEnabled) return Promise.resolve({ google: false });
  cached ??= fetch(`${env.supabaseUrl}/auth/v1/settings`, { headers: { apikey: env.supabaseAnonKey } })
    .then((r) => (r.ok ? (r.json() as Promise<{ external?: Record<string, boolean> }>) : {}))
    .then((s) => ({ google: Boolean((s as { external?: Record<string, boolean> }).external?.google) }))
    .catch(() => ({ google: false }));
  return cached;
}

export function useAuthProviders(): AuthProviders {
  const [providers, setProviders] = useState<AuthProviders>({ google: false });
  useEffect(() => {
    let live = true;
    void fetchAuthProviders().then((p) => live && setProviders(p));
    return () => {
      live = false;
    };
  }, []);
  return providers;
}
