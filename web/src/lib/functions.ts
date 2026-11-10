// Calls a Supabase Edge Function with the user's session and turns its JSON error body
// ({"error": "<code>", ...}) into a typed exception the UI can switch on.
import { FunctionsHttpError } from "@supabase/supabase-js";
import { supabase } from "./supabase";

export class FunctionError extends Error {
  constructor(
    readonly code: string,
    readonly status: number,
    readonly body: Record<string, unknown>,
  ) {
    super(code);
  }
}

export async function invokeFunction<T>(name: string, body: Record<string, unknown>): Promise<T> {
  if (!supabase) throw new FunctionError("not_configured", 0, {});
  const { data, error } = await supabase.functions.invoke<T>(name, { body });
  if (!error) return data as T;
  if (error instanceof FunctionsHttpError) {
    const res = error.context as Response;
    let payload: Record<string, unknown> = {};
    try {
      payload = (await res.json()) as Record<string, unknown>;
    } catch {
      /* not JSON */
    }
    throw new FunctionError(String(payload.error ?? "request_failed"), res.status, payload);
  }
  throw new FunctionError("network_error", 0, {});
}
