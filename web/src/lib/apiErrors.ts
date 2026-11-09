import type { TFunction } from "i18next";
import { ApiError } from "./api";

/** Human message for an API failure (rate limits, size limits, offline, validation). */
export function apiErrorMessage(e: unknown, t: TFunction): string {
  if (e instanceof ApiError) {
    if (e.status === 429) return e.retryAfter ? t("errors.rateLimitedIn", { seconds: e.retryAfter }) : t("errors.rateLimited");
    if (e.status === 413) return t("errors.tooLarge");
    if (e.status === 503) return t("errors.busy");
    if (e.status === 0) return t("errors.offline");
    if (e.status === 404 || e.status === 405 || e.status === 501) return t("errors.notAvailable");
    return e.message;
  }
  return (e as Error)?.message ?? String(e);
}
