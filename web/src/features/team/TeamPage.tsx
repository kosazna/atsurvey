import { useQuery } from "@tanstack/react-query";
import { Navigate } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { PageShell } from "@/features/account/PageShell";
import { useSession } from "@/data/session";
import { canManage, teams } from "@/data/teams";
import { useCurrentWorkspace } from "@/data/useTeams";
import { supabase } from "@/lib/supabase";
import { ActivityCard } from "./ActivityCard";
import { InvitationsCard } from "./InvitationsCard";
import { MembersCard } from "./MembersCard";
import { WorkspaceSettingsCard } from "./WorkspaceSettingsCard";

/** Management page of the selected team workspace. */
export function TeamPage() {
  const { t } = useTranslation();
  const { mode } = useSession();
  const { current, isLoading } = useCurrentWorkspace();
  const roster = useQuery({
    queryKey: ["roster", current?.id],
    queryFn: () => teams.roster(supabase!, current!.id),
    enabled: Boolean(current && !current.personal),
  });

  if (mode === "none" || mode === "demo") return <Navigate to="/projects" />;
  if (mode === "loading" || isLoading) return null;
  if (!current || current.personal) return <Navigate to="/projects" />;

  const names = new Map((roster.data ?? []).map((m) => [m.user_id, m.full_name ?? m.email]));
  return (
    <PageShell title={current.name} description={t(`team.roleHelp.${current.role}`)}>
      <div className="-mt-3 flex gap-2">
        <Badge>{t(`team.roles.${current.role}`)}</Badge>
        <Badge variant="secondary">{current.plan === "pro" ? "Pro" : "Free"}</Badge>
      </div>
      <MembersCard ws={current} />
      {canManage(current.role) && <InvitationsCard ws={current} />}
      <WorkspaceSettingsCard ws={current} />
      {canManage(current.role) && <ActivityCard ws={current} names={names} />}
    </PageShell>
  );
}
