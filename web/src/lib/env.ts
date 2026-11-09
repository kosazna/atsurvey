export const env = {
  apiUrl: (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "http://localhost:8000",
  supabaseUrl: (import.meta.env.VITE_SUPABASE_URL as string | undefined) || "",
  supabaseAnonKey: (import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined) || "",
  paddleClientToken: (import.meta.env.VITE_PADDLE_CLIENT_TOKEN as string | undefined) || "",
  paddlePriceMonthly: (import.meta.env.VITE_PADDLE_PRICE_MONTHLY as string | undefined) || "",
  paddlePriceYearly: (import.meta.env.VITE_PADDLE_PRICE_YEARLY as string | undefined) || "",
};

export const billingEnabled = Boolean(env.paddleClientToken && (env.paddlePriceMonthly || env.paddlePriceYearly));

export const supabaseEnabled = Boolean(env.supabaseUrl && env.supabaseAnonKey);
