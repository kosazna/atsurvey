import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, RotateCcw, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { type ShelvedProject, daysUntilPurge, lifecycle } from "@/data/lifecycle";
import { canManage, canWrite, type Role } from "@/data/teams";
import { teamErrorMessage } from "@/data/useTeams";
import { supabase } from "@/lib/supabase";
import { relativeTime } from "@/lib/utils";

export type Shelf = "archived" | "trash";

/** Archived projects (restore: writers) or the trash (restore / delete forever: owner, admin). */
export function ProjectShelves({ shelf, workspaceId, role }: { shelf: Shelf; workspaceId: string; role: Role | undefined }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["projects", "shelf", shelf, workspaceId],
    queryFn: () => (shelf === "archived" ? lifecycle.archived(supabase!, workspaceId) : lifecycle.trash(supabase!, workspaceId)),
  });

  async function act(fn: () => Promise<void>, success: string) {
    try {
      await fn();
      toast.success(success);
    } catch (e) {
      const msg = (e as Error).message;
      toast.error(msg.includes("project_limit_reached") ? t("projects.limitReached") : teamErrorMessage(t, e));
    } finally {
      await qc.invalidateQueries({ queryKey: ["projects"] });
    }
  }

  const items = list.data ?? [];
  const mayRestore = shelf === "archived" ? canWrite(role) : canManage(role);
  const row = (p: ShelvedProject) => (
    <div key={p.id} className="flex flex-wrap items-center gap-3 py-2.5" data-testid="shelf-row">
      {shelf === "archived" ? <Archive className="size-4 text-muted" /> : <Trash2 className="size-4 text-muted" />}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{p.name}</div>
        <div className="text-xs text-muted">
          {shelf === "archived"
            ? relativeTime(p.archived_at ?? p.updated_at, i18n.language)
            : t("life.purgeIn", { days: daysUntilPurge(p.deleted_at ?? p.updated_at) })}
        </div>
      </div>
      {mayRestore && (
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            void act(
              () => (shelf === "archived" ? lifecycle.unarchive(supabase!, p.id) : lifecycle.restore(supabase!, p.id)),
              shelf === "archived" ? t("life.unarchived") : t("life.restored"),
            )
          }
        >
          <RotateCcw /> {shelf === "archived" ? t("life.unarchive") : t("life.restore")}
        </Button>
      )}
      {shelf === "trash" && canManage(role) && (
        <Button
          size="sm"
          variant="ghost"
          className="text-danger"
          onClick={() =>
            toast(t("life.deleteForeverConfirm", { name: p.name }), {
              action: { label: t("life.deleteForever"), onClick: () => void act(() => lifecycle.deleteForever(supabase!, p.id), t("life.deletedForever")) },
            })
          }
        >
          {t("life.deleteForever")}
        </Button>
      )}
    </div>
  );

  return (
    <div className="mt-6 rounded-xl border bg-surface px-4">
      {items.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted">{shelf === "archived" ? t("life.emptyArchived") : t("life.emptyTrash")}</p>
      ) : (
        <div className="divide-y">{items.map(row)}</div>
      )}
    </div>
  );
}
