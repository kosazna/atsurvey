export const env = {
  apiUrl: (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "http://localhost:8000",
  supabaseUrl: (import.meta.env.VITE_SUPABASE_URL as string | undefined) || "",
  supabaseAnonKey: (import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined) || "",
};

export const supabaseEnabled = Boolean(env.supabaseUrl && env.supabaseAnonKey);
