import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { env, supabaseEnabled } from "./env";

export const supabase: SupabaseClient | null = supabaseEnabled
  ? createClient(env.supabaseUrl, env.supabaseAnonKey, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    })
  : null;

export async function getAccessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
