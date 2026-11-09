// Maps a Paddle Billing subscription event to a row of public.subscriptions.

export const HANDLED_EVENTS = new Set([
  "subscription.created",
  "subscription.updated",
  "subscription.activated",
  "subscription.trialing",
  "subscription.past_due",
  "subscription.paused",
  "subscription.resumed",
  "subscription.canceled",
]);

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export interface PaddleEvent {
  event_id?: string;
  event_type?: string;
  occurred_at?: string;
  data?: {
    id?: string;
    status?: string;
    customer_id?: string;
    custom_data?: Record<string, unknown> | null;
    current_billing_period?: { starts_at?: string; ends_at?: string } | null;
  };
}

export interface SubscriptionRow {
  workspace_id: string | null; // null => resolve via subscription_id
  provider: "paddle";
  customer_id: string | null;
  subscription_id: string;
  plan: "free" | "pro";
  status: string;
  current_period_end: string | null;
}

export function planForStatus(status: string): "free" | "pro" {
  return status === "active" || status === "trialing" ? "pro" : "free";
}

export function toSubscriptionRow(event: PaddleEvent): SubscriptionRow | null {
  const data = event.data;
  if (!data?.id || !data.status) return null;
  const ws = data.custom_data?.["workspace_id"];
  const workspaceId = typeof ws === "string" && UUID_RE.test(ws) ? ws : null;
  return {
    workspace_id: workspaceId,
    provider: "paddle",
    customer_id: data.customer_id ?? null,
    subscription_id: data.id,
    plan: planForStatus(data.status),
    status: data.status,
    current_period_end: data.current_billing_period?.ends_at ?? null,
  };
}

/** Timestamp of the event (used to drop stale or replayed deliveries). */
export function occurredAt(event: PaddleEvent): string | null {
  const t = event.occurred_at ? Date.parse(event.occurred_at) : NaN;
  return Number.isFinite(t) ? new Date(t).toISOString() : null;
}

export interface ExistingSubscription {
  subscription_id: string | null;
  plan: string;
  last_event_at: string | null;
}

export type Decision = { apply: true } | { apply: false; reason: "stale" | "foreign_downgrade" };

/**
 * Whether an event may overwrite the stored row for its workspace.
 *
 * - stale: events for the same subscription that are not newer than the last applied one
 *   (Paddle retries out of order; a replay within the signature window is a no-op).
 * - foreign_downgrade: `custom_data.workspace_id` is set by the buyer at checkout, so a
 *   second subscription aimed at someone else's workspace must never downgrade the
 *   workspace's own active subscription (e.g. buy-then-cancel griefing).
 */
export function decide(
  existing: ExistingSubscription | null,
  row: SubscriptionRow,
  eventAt: string | null,
): Decision {
  if (!existing) return { apply: true };
  const same = existing.subscription_id === row.subscription_id;
  if (same && eventAt && existing.last_event_at && Date.parse(eventAt) <= Date.parse(existing.last_event_at)) {
    return { apply: false, reason: "stale" };
  }
  if (!same && existing.subscription_id && existing.plan === "pro" && row.plan !== "pro") {
    return { apply: false, reason: "foreign_downgrade" };
  }
  return { apply: true };
}
