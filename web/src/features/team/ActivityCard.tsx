import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { type AuditEvent, type MyWorkspace, teams } from "@/data/teams";
import { supabase } from "@/lib/supabase";
import { relativeTime } from "@/lib/utils";

/** One-line summary of an event's details (names, roles, formats, e-mails). */
export function describeDetails(d: Record<string, unknown>): string {
  const s = (k: string) => (typeof d[k] === "string" ? (d[k] as string) : null);
  if (s("from") && s("to")) return `${s("from")} → ${s("to")}`;
  return [s("name"), s("filename"), s("email"), s("role"), s("format")].filter(Boolean).join(" · ");
}

/** The workspace's append-only audit log (owners and admins; RLS hides it from others). */
export function ActivityCard({ ws, names }: { ws: MyWorkspace; names: Map<string, string> }) {
  const { t, i18n } = useTranslation();
  const events = useQuery({ queryKey: ["activity", ws.id], queryFn: () => teams.activity(supabase!, ws.id) });
  const who = (e: AuditEvent) => (e.actor ? (names.get(e.actor) ?? e.actor.slice(0, 8)) : t("team.activity.system"));
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("team.activity.title")}</CardTitle>
        <CardDescription>{t("team.activity.text")}</CardDescription>
      </CardHeader>
      <CardContent>
        {(events.data ?? []).length === 0 && <p className="text-sm text-muted">{t("team.activity.empty")}</p>}
        <ol className="divide-y text-sm" data-testid="activity-list">
          {(events.data ?? []).map((e) => (
            <li key={e.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-2">
              <span className="w-28 shrink-0 text-xs text-muted tabular">{relativeTime(e.created_at, i18n.language)}</span>
              <span className="font-medium">{who(e)}</span>
              <code className="rounded bg-surface-sunken px-1.5 text-xs">{e.action}</code>
              <span className="min-w-0 truncate text-muted">{describeDetails(e.details)}</span>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
