import type { Session } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { supabase } from "@/lib/supabase";
import { LocalStore } from "./localStore";
import type { ProjectStore } from "./store";
import { SupabaseStore } from "./supabaseStore";

export type Mode = "loading" | "none" | "demo" | "cloud";

interface SessionCtx {
  mode: Mode;
  session: Session | null;
  store: ProjectStore | null;
  enterDemo: () => void;
  signOut: () => Promise<void>;
}

const Ctx = createContext<SessionCtx | null>(null);
const DEMO_KEY = "ats-mode";
const localStore = new LocalStore();

function demoFlag(): boolean {
  try {
    return localStorage.getItem(DEMO_KEY) === "demo";
  } catch {
    return false;
  }
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(!supabase);
  const [demo, setDemo] = useState(demoFlag);

  useEffect(() => {
    if (!supabase) return;
    void supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  const cloudStore = useMemo(() => (supabase && session ? new SupabaseStore(supabase) : null), [session?.user.id]);

  const enterDemo = useCallback(() => {
    try {
      localStorage.setItem(DEMO_KEY, "demo");
    } catch {
      /* ignore */
    }
    setDemo(true);
  }, []);

  const signOut = useCallback(async () => {
    try {
      localStorage.removeItem(DEMO_KEY);
    } catch {
      /* ignore */
    }
    setDemo(false);
    if (supabase) await supabase.auth.signOut();
  }, []);

  const mode: Mode = !ready ? "loading" : session ? "cloud" : demo ? "demo" : "none";
  const store = mode === "cloud" ? cloudStore : mode === "demo" ? localStore : null;

  const value = useMemo(() => ({ mode, session, store, enterDemo, signOut }), [mode, session, store, enterDemo, signOut]);
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
