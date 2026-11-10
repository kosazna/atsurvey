import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useSession } from "@/data/session";
import { type MyWorkspace, teams } from "@/data/teams";
import { teamErrorMessage } from "@/data/useTeams";
import { supabase } from "@/lib/supabase";

/** Rename, require two-factor, leave, delete (each also enforced by the database). */
export function WorkspaceSettingsCard({ ws }: { ws: MyWorkspace }) {
  const { t } = useTranslation();
  const { session, setWorkspaceId } = useSession();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState(ws.name);
  const [deleting, setDeleting] = useState(false);
  const [typed, setTyped] = useState("");
  const isOwner = ws.role === "owner";
  const manage = isOwner || ws.role === "admin";

  async function run(fn: () => Promise<void>, success?: string): Promise<boolean> {
    try {
      await fn();
      if (success) toast.success(success);
      return true;
    } catch (e) {
      toast.error(teamErrorMessage(t, e));
      return false;
    } finally {
      await qc.invalidateQueries({ queryKey: ["my-workspaces"] });
    }
  }

  async function leaveOrDelete(fn: () => Promise<void>, success: string) {
    if (await run(fn, success)) {
      setWorkspaceId(null);
      await qc.invalidateQueries({ queryKey: ["projects"] });
      void navigate({ to: "/projects" });
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("team.settings.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {manage && (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void run(() => teams.renameWorkspace(supabase!, ws.id, name), t("account.saved"));
            }}
          >
            <div className="min-w-56 flex-1 space-y-1.5">
              <Label htmlFor="ws-name">{t("team.name")}</Label>
              <Input id="ws-name" required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <Button type="submit" size="sm" variant="secondary" disabled={!name.trim() || name.trim() === ws.name}>
              {t("team.settings.rename")}
            </Button>
          </form>
        )}

        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-sm font-medium">{t("team.settings.requireMfa")}</div>
            <p className="mt-0.5 text-xs text-muted">{t("team.settings.requireMfaText")}</p>
          </div>
          <Switch
            checked={ws.require_mfa}
            disabled={!isOwner}
            onCheckedChange={(on) => void run(() => teams.setRequireMfa(supabase!, ws.id, on))}
            aria-label={t("team.settings.requireMfa")}
            data-testid="switch-require-mfa"
          />
        </div>

        <div className="flex flex-wrap gap-2 border-t pt-4">
          {!isOwner && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => void leaveOrDelete(() => teams.removeMember(supabase!, ws.id, session!.user.id), t("team.left"))}
            >
              {t("team.leave")}
            </Button>
          )}
          {isOwner && (
            <Button size="sm" variant="destructive" onClick={() => setDeleting(true)}>
              {t("team.settings.delete")}
            </Button>
          )}
        </div>
      </CardContent>

      <Dialog open={deleting} onOpenChange={setDeleting}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("team.settings.delete")}</DialogTitle>
            <DialogDescription>{t("team.settings.deleteText")}</DialogDescription>
          </DialogHeader>
          <DialogBody>
            <Input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={ws.name} aria-label={t("team.name")} />
          </DialogBody>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleting(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={typed.trim() !== ws.name}
              onClick={() => void leaveOrDelete(() => teams.deleteWorkspace(supabase!, ws.id), t("team.settings.deleted"))}
            >
              {t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
