import type { Session } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { supabase } from "@/lib/supabase";
import { LocalStore } from "./localStore";
import type { ProjectStore } from "./store";
import { SupabaseStore } from "./supabaseStore";

/**
 * "mfa": signed in with a password (or link) but the account has two-factor authentication on,
 * so the session must be verified with an authenticator code first. The database refuses
 * every workspace to such a session anyway (migration 20261111000005); the app shows the
 * challenge instead of empty pages.
 */
export type Mode = "loading" | "none" | "demo" | "mfa" | "cloud";

interface SessionCtx {
  mode: Mode;
  session: Session | null;
  store: ProjectStore | null;
  enterDemo: () => void;
  signOut: (scope?: "local" | "global") => Promise<void>;
  clearDemoData: () => void;
  /** Re-check the assurance level after verifying or removing an authenticator. */
  refreshMfa: () => Promise<void>;
  /** Selected workspace (signed in): its projects are listed and new ones created in it. */
  workspaceId: string | null;
  setWorkspaceId: (id: string | null) => void;
}

const Ctx = createContext<SessionCtx | null>(null);
const DEMO_KEY = "ats-mode";
const WORKSPACE_KEY = "ats-workspace";

function storedWorkspace(): string | null {
  try {
    return localStorage.getItem(WORKSPACE_KEY);
  } catch {
    return null;
  }
}
const localStore = new LocalStore();

type MfaState = "unknown" | "ok" | "needed";

function demoFlag(): boolean {
  try {
    return localStorage.getItem(DEMO_KEY) === "demo";
  } catch {
    return false;
  }
}

/** Assurance level claim ("aal1" / "aal2") of an access token; display logic only. */
export function tokenAal(token: string | undefined): string {
  try {
    const part = (token ?? "").split(".")[1] ?? "";
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(part.length / 4) * 4, "="));
    const aal = (JSON.parse(json) as { aal?: unknown }).aal;
    return typeof aal === "string" ? aal : "aal1";
  } catch {
    return "aal1";
  }
}

async function mfaStateFor(session: Session | null): Promise<MfaState> {
  if (!supabase || !session) return "ok";
  const { data, error } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
  if (error || !data) return "ok"; // the database still enforces it
  return data.nextLevel === "aal2" && data.currentLevel !== "aal2" ? "needed" : "ok";
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(!supabase);
  const [demo, setDemo] = useState(demoFlag);
  const [mfa, setMfa] = useState<MfaState>("unknown");

  useEffect(() => {
    if (!supabase) return;
    void supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  // Re-check only when the user or the session's assurance level changes, not on every token
  // refresh (that would unmount open pages every 15 minutes).
  const aal = tokenAal(session?.access_token);
  useEffect(() => {
    let live = true;
    setMfa("unknown");
    void mfaStateFor(session).then((s) => live && setMfa(s));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.user.id, aal]);

  const [workspaceId, setWorkspaceState] = useState<string | null>(storedWorkspace);
  const cloudStore = useMemo(() => {
    if (!supabase || !session) return null;
    const s = new SupabaseStore(supabase);
    s.setWorkspace(storedWorkspace());
    return s;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.user.id]);

  const setWorkspaceId = useCallback(
    (id: string | null) => {
      try {
        if (id) localStorage.setItem(WORKSPACE_KEY, id);
        else localStorage.removeItem(WORKSPACE_KEY);
      } catch {
        /* per-browser convenience only */
      }
      cloudStore?.setWorkspace(id);
      setWorkspaceState(id);
    },
    [cloudStore],
  );

  const enterDemo = useCallback(() => {
    try {
      localStorage.setItem(DEMO_KEY, "demo");
    } catch {
      /* ignore */
    }
    setDemo(true);
  }, []);

  const signOut = useCallback(async (scope: "local" | "global" = "local") => {
    try {
      localStorage.removeItem(DEMO_KEY);
    } catch {
      /* ignore */
    }
    setDemo(false);
    try {
      localStorage.removeItem(WORKSPACE_KEY);
    } catch {
      /* ignore */
    }
    setWorkspaceState(null);
    if (supabase) await supabase.auth.signOut({ scope });
  }, []);

  const clearDemoData = useCallback(() => localStore.clearAll(), []);

  const refreshMfa = useCallback(async () => {
    if (!supabase) return;
    const { data } = await supabase.auth.refreshSession();
    setMfa(await mfaStateFor(data.session));
  }, []);

  const mode: Mode = !ready
    ? "loading"
    : session
      ? mfa === "unknown"
        ? "loading"
        : mfa === "needed"
          ? "mfa"
          : "cloud"
      : demo
        ? "demo"
        : "none";
  const store = mode === "cloud" ? cloudStore : mode === "demo" ? localStore : null;

  const value = useMemo(
    () => ({ mode, session, store, enterDemo, signOut, clearDemoData, refreshMfa, workspaceId, setWorkspaceId }),
    [mode, session, store, enterDemo, signOut, clearDemoData, refreshMfa, workspaceId, setWorkspaceId],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession() {
  const c = useContext(Ctx);
  if (!c) throw new Error("SessionProvider missing");
  return c;
}

export function useStore(): ProjectStore {
  const { store } = useSession();
  if (!store) throw new Error("No store (not signed in)");
  return store;
}
