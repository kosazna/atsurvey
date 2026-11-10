import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSession } from "@/data/session";
import { buildDataExport, type ExportProgress } from "@/lib/exportData";
import { FunctionError, invokeFunction } from "@/lib/functions";
import { supabase } from "@/lib/supabase";
import { downloadBlob } from "@/lib/utils";

/** Sign out everywhere, export my data, delete my account. */
export function DataCard({ email }: { email: string }) {
  const { t } = useTranslation();
  const { store, signOut } = useSession();
  const navigate = useNavigate();
  const [progress, setProgress] = useState<ExportProgress | null>(null);
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);

  async function exportData() {
    if (!store || !supabase) return;
    try {
      const blob = await buildDataExport(store, supabase, setProgress);
      downloadBlob(blob, `atsurvey-export-${new Date().toISOString().slice(0, 10)}.zip`);
      toast.success(t("sec.data.exported"));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setProgress(null);
    }
  }

  async function signOutEverywhere() {
    await signOut("global");
    void navigate({ to: "/" });
  }

  async function deleteAccount() {
    setBusy(true);
    try {
      await invokeFunction("delete-account", { confirm: true });
      await signOut("local");
      toast.success(t("sec.data.deleted"));
      void navigate({ to: "/" });
    } catch (e) {
      if (e instanceof FunctionError && (e.code === "reauth_required" || e.code === "mfa_required")) {
        toast.error(t("sec.data.reauth"), {
          action: { label: t("sec.data.signInAgain"), onClick: () => void signOut("local").then(() => navigate({ to: "/login" })) },
        });
      } else if (e instanceof FunctionError && e.code === "sole_owner") {
        const names = ((e.body.workspaces as { name: string }[] | undefined) ?? []).map((w) => w.name).join(", ");
        toast.error(t("sec.data.soleOwner", { names }));
      } else {
        toast.error((e as Error).message);
      }
    } finally {
      setBusy(false);
      setOpen(false);
      setTyped("");
    }
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>{t("sec.sessions.title")}</CardTitle>
          <CardDescription>{t("sec.sessions.description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button size="sm" variant="secondary" onClick={() => void signOutEverywhere()} data-testid="btn-signout-all">
            {t("sec.sessions.signOutAll")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("sec.data.title")}</CardTitle>
          <CardDescription>{t("sec.data.exportDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <Button size="sm" variant="secondary" disabled={progress !== null} onClick={() => void exportData()} data-testid="btn-export-data">
            {progress ? t("sec.data.exporting", { done: progress.done, total: progress.total }) : t("sec.data.export")}
          </Button>
          <div className="border-t pt-4">
            <div className="text-sm font-medium text-danger">{t("sec.data.deleteTitle")}</div>
            <p className="mt-1 text-sm text-muted">{t("sec.data.deleteDescription")}</p>
            <Button size="sm" variant="destructive" className="mt-3" onClick={() => setOpen(true)} data-testid="btn-delete-account">
              {t("sec.data.delete")}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("sec.data.deleteTitle")}</DialogTitle>
            <DialogDescription>{t("sec.data.deleteDescription")}</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-1.5">
            <Label htmlFor="confirm-email">{t("sec.data.deleteConfirmLabel")}</Label>
            <Input id="confirm-email" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={email} />
          </DialogBody>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="destructive" disabled={busy || typed.trim().toLowerCase() !== email.toLowerCase()} onClick={() => void deleteAccount()} data-testid="btn-delete-forever">
              {t("sec.data.deleteForever")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
