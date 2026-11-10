import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { useSession } from "@/data/session";
import { type MyWorkspace, type Role, type RosterEntry, teams } from "@/data/teams";
import { teamErrorMessage } from "@/data/useTeams";
import { supabase } from "@/lib/supabase";

/** Roster with role changes, removal and ownership transfer (rules enforced by the database). */
export function MembersCard({ ws }: { ws: MyWorkspace }) {
  const { t } = useTranslation();
  const { session } = useSession();
  const qc = useQueryClient();
  const me = session?.user.id;
  const roster = useQuery({ queryKey: ["roster", ws.id], queryFn: () => teams.roster(supabase!, ws.id) });
  const isOwner = ws.role === "owner";
  const manage = isOwner || ws.role === "admin";

  async function run(fn: () => Promise<void>, success?: string) {
    try {
      await fn();
      if (success) toast.success(success);
    } catch (e) {
      toast.error(teamErrorMessage(t, e));
    } finally {
      await qc.invalidateQueries({ queryKey: ["roster", ws.id] });
      await qc.invalidateQueries({ queryKey: ["my-workspaces"] });
    }
  }

  const roleOptions = (m: RosterEntry) =>
    (isOwner ? (["owner", "admin", "member", "viewer"] as Role[]) : (["admin", "member", "viewer"] as Role[]))
      .filter((r) => r !== "owner" || m.role === "owner")
      .map((r) => ({ value: r, label: t(`team.roles.${r}`) }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("team.members")}</CardTitle>
      </CardHeader>
      <CardContent className="divide-y">
        {(roster.data ?? []).map((m) => {
          const self = m.user_id === me;
          const editable = manage && !self && m.role !== "owner";
          return (
            <div key={m.user_id} className="flex flex-wrap items-center gap-3 py-2.5" data-testid="roster-row">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">
                  {m.full_name ?? m.email} {self && <span className="text-xs font-normal text-muted">({t("team.you")})</span>}
                </div>
                <div className="truncate text-xs text-muted">{m.email}</div>
              </div>
              {m.has_mfa && (
                <Badge variant="success" title={t("sec.mfa.title")}>
                  <ShieldCheck /> {t("team.mfaOn")}
                </Badge>
              )}
              {editable ? (
                <div className="w-36">
                  <Select<Role>
                    value={m.role}
                    onValueChange={(r) => void run(() => teams.setRole(supabase!, ws.id, m.user_id, r))}
                    options={roleOptions(m)}
                  />
                </div>
              ) : (
                <Badge variant="secondary">{t(`team.roles.${m.role}`)}</Badge>
              )}
              {editable && (
                <Button size="sm" variant="ghost" onClick={() => void run(() => teams.removeMember(supabase!, ws.id, m.user_id))}>
                  {t("team.remove")}
                </Button>
              )}
              {isOwner && !self && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    toast(t("team.transferConfirm", { name: m.full_name ?? m.email }), {
                      action: {
                        label: t("team.transfer"),
                        onClick: () => void run(() => teams.transferOwnership(supabase!, ws.id, m.user_id), t("team.transferred")),
                      },
                    })
                  }
                >
                  {t("team.transfer")}
                </Button>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
