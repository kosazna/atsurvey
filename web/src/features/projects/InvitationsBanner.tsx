import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MailOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useSession } from "@/data/session";
import { type MyInvitation, teams } from "@/data/teams";
import { teamErrorMessage } from "@/data/useTeams";
import { supabase } from "@/lib/supabase";

/** Invitations addressed to the signed-in user's confirmed e-mail: accept or decline. */
export function InvitationsBanner() {
  const { t } = useTranslation();
  const { mode, session, setWorkspaceId } = useSession();
  const qc = useQueryClient();
  const inbox = useQuery({
    queryKey: ["my-invitations", session?.user.id],
    queryFn: () => teams.myInvitations(supabase!),
    enabled: mode === "cloud" && Boolean(supabase),
  });

  async function answer(inv: MyInvitation, accept: boolean) {
    try {
      if (accept) {
        const ws = await teams.accept(supabase!, inv.id);
        await qc.invalidateQueries({ queryKey: ["my-workspaces"] });
        setWorkspaceId(ws);
        await qc.invalidateQueries({ queryKey: ["projects"] });
        toast.success(t("team.inbox.accepted", { workspace: inv.workspace_name }));
      } else {
        await teams.decline(supabase!, inv.id);
      }
    } catch (e) {
      toast.error(teamErrorMessage(t, e));
    } finally {
      await qc.invalidateQueries({ queryKey: ["my-invitations"] });
    }
  }

  if (!inbox.data?.length) return null;
  return (
    <div className="mb-6 space-y-2" data-testid="invitations-banner">
      {inbox.data.map((inv) => (
        <div key={inv.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-accent/30 bg-accent-subtle px-4 py-3">
          <MailOpen className="size-4 text-accent" />
          <div className="min-w-0 flex-1 text-sm">
            <div className="font-medium">{t("team.inbox.title")}</div>
            <div className="text-muted">
              {t("team.inbox.text", {
                inviter: inv.invited_by_name ?? t("team.inbox.someone"),
                workspace: inv.workspace_name,
                role: t(`team.roles.${inv.role}`).toLowerCase(),
              })}
            </div>
          </div>
          <Button size="sm" variant="ghost" onClick={() => void answer(inv, false)}>
            {t("team.inbox.decline")}
          </Button>
          <Button size="sm" onClick={() => void answer(inv, true)} data-testid="btn-accept-invitation">
            {t("team.inbox.accept")}
          </Button>
        </div>
      ))}
    </div>
  );
}
