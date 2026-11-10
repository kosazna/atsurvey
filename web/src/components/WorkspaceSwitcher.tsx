import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Check, ChevronsUpDown, Plus, Settings2, Users } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useSession } from "@/data/session";
import { teams } from "@/data/teams";
import { teamErrorMessage, useCurrentWorkspace } from "@/data/useTeams";
import { supabase } from "@/lib/supabase";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "./ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "./ui/dropdown-menu";
import { Input } from "./ui/input";
import { Label } from "./ui/label";

/** Picks the workspace whose projects are shown; creates team workspaces (Pro). */
export function WorkspaceSwitcher() {
  const { t } = useTranslation();
  const { setWorkspaceId } = useSession();
  const { workspaces, current } = useCurrentWorkspace();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  if (!current) return null;

  const select = (id: string) => {
    setWorkspaceId(id);
    void qc.invalidateQueries({ queryKey: ["projects"] });
  };

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const id = await teams.createWorkspace(supabase!, name);
      await qc.invalidateQueries({ queryKey: ["my-workspaces"] });
      select(id);
      setCreating(false);
      setName("");
      toast.success(t("team.created"));
    } catch (err) {
      toast.error(teamErrorMessage(t, err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" className="max-w-56 gap-1.5" data-testid="workspace-switcher">
            <Users className="size-3.5" />
            <span className="truncate">{current.personal ? t("team.personal") : current.name}</span>
            <ChevronsUpDown className="size-3 opacity-60" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-64">
          <DropdownMenuLabel>{t("team.switch")}</DropdownMenuLabel>
          {workspaces.map((w) => (
            <DropdownMenuItem key={w.id} onSelect={() => select(w.id)}>
              <span className="truncate">{w.personal ? t("team.personal") : w.name}</span>
              {!w.personal && (
                <Badge variant="secondary" className="ml-auto">
                  {t(`team.roles.${w.role}`)}
                </Badge>
              )}
              {w.id === current.id && <Check className={w.personal ? "ml-auto" : ""} />}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          {!current.personal && (
            <DropdownMenuItem onSelect={() => void navigate({ to: "/team" })}>
              <Settings2 /> {t("team.manage")}
            </DropdownMenuItem>
          )}
          <DropdownMenuItem onSelect={() => setCreating(true)}>
            <Plus /> {t("team.newTeam")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent>
          <form onSubmit={create}>
            <DialogHeader>
              <DialogTitle>{t("team.newTeamTitle")}</DialogTitle>
              <DialogDescription>{t("team.newTeamText")}</DialogDescription>
            </DialogHeader>
            <DialogBody className="space-y-1.5">
              <Label htmlFor="team-name">{t("team.name")}</Label>
              <Input id="team-name" required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setCreating(false)}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={busy || !name.trim()}>
                {t("team.create")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
