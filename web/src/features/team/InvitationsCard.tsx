import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { type MyWorkspace, type Role, rolesInvitableBy, teams } from "@/data/teams";
import { teamErrorMessage } from "@/data/useTeams";
import { supabase } from "@/lib/supabase";
import { relativeTime } from "@/lib/utils";

/** Invite by e-mail (consent: the invitee accepts in the app), list and revoke pending ones. */
export function InvitationsCard({ ws }: { ws: MyWorkspace }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const roles = rolesInvitableBy(ws.role);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [busy, setBusy] = useState(false);
  const pending = useQuery({ queryKey: ["invitations", ws.id], queryFn: () => teams.invitations(supabase!, ws.id) });

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await teams.invite(supabase!, ws.id, email, role);
      toast.success(t("team.invite.sent", { email: email.trim().toLowerCase() }));
      setEmail("");
    } catch (err) {
      toast.error(teamErrorMessage(t, err));
    } finally {
      setBusy(false);
      await qc.invalidateQueries({ queryKey: ["invitations", ws.id] });
    }
  }

  async function revoke(id: string) {
    try {
      await teams.revoke(supabase!, id);
    } catch (err) {
      toast.error(teamErrorMessage(t, err));
    } finally {
      await qc.invalidateQueries({ queryKey: ["invitations", ws.id] });
    }
  }

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/login`);
      toast.success(t("team.invite.copied"));
    } catch {
      /* clipboard blocked: the link is the app address */
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("team.invite.title")}</CardTitle>
        <CardDescription>{t("team.invite.text")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={invite} className="flex flex-wrap items-end gap-2">
          <div className="min-w-56 flex-1 space-y-1.5">
            <Label htmlFor="invite-email">{t("team.invite.email")}</Label>
            <Input id="invite-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="w-40 space-y-1.5">
            <Label>{t("team.invite.role")}</Label>
            <Select<Role> value={role} onValueChange={setRole} options={roles.map((r) => ({ value: r, label: t(`team.roles.${r}`) }))} />
          </div>
          <Button type="submit" disabled={busy} data-testid="btn-invite">
            {t("team.invite.send")}
          </Button>
          <Button type="button" variant="ghost" onClick={() => void copyLink()}>
            <Copy /> {t("team.invite.copyLink")}
          </Button>
        </form>
        <p className="text-xs text-muted">{t(`team.roleHelp.${role}`)}</p>
        <div className="divide-y">
          {(pending.data ?? []).length === 0 && <p className="text-sm text-muted">{t("team.invite.none")}</p>}
          {(pending.data ?? []).map((inv) => (
            <div key={inv.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
              <span className="min-w-0 flex-1 truncate">{inv.email}</span>
              <Badge variant="secondary">{t(`team.roles.${inv.role}`)}</Badge>
              <span className="text-xs text-muted">{t("team.invite.expires", { when: relativeTime(inv.expires_at, i18n.language) })}</span>
              <Button size="sm" variant="ghost" onClick={() => void revoke(inv.id)}>
                {t("team.invite.revoke")}
              </Button>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
