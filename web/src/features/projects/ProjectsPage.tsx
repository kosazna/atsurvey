import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useNavigate } from "@tanstack/react-router";
import { FolderOpen, MoreHorizontal, Pencil, Plus, Search, Sparkles, Trash2, Triangle } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { usePageCommands, type Command } from "@/components/commands";
import { Logo } from "@/components/Logo";
import { UserMenu } from "@/components/UserMenu";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty";
import { Input, Textarea } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { buildSampleProject } from "@/data/sample";
import { useSession } from "@/data/session";
import type { ProjectMeta } from "@/data/store";
import type { DisplayAngleUnit } from "@/lib/types";
import { relativeTime } from "@/lib/utils";

function ProjectFormDialog({
  open,
  onOpenChange,
  initial,
  title,
  submitLabel,
  onSubmit,
  showUnit,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  initial?: { name: string; description: string | null; angle_unit: DisplayAngleUnit };
  title: string;
  submitLabel: string;
  showUnit?: boolean;
  onSubmit: (v: { name: string; description: string | null; angle_unit: DisplayAngleUnit }) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [unit, setUnit] = useState<DisplayAngleUnit>(initial?.angle_unit ?? "gon");
  const [busy, setBusy] = useState(false);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form
          className="flex min-h-0 flex-col"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!name.trim()) return;
            setBusy(true);
            try {
              await onSubmit({ name: name.trim(), description: description.trim() || null, angle_unit: unit });
              onOpenChange(false);
            } catch (err) {
              if ((err as Error).name === "ProjectLimitError") toast.warning(t("projects.limitReached"));
              else toast.error((err as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="pname">{t("projects.name")}</Label>
              <Input id="pname" autoFocus required value={name} onChange={(e) => setName(e.target.value)} placeholder="π.χ. Αφίδνες — Οικόπεδο 12" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pdesc">
                {t("projects.description")} <span className="font-normal text-muted">({t("common.optional")})</span>
              </Label>
              <Textarea id="pdesc" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
            </div>
            {showUnit && (
              <div className="space-y-1.5">
                <Label htmlFor="punit">{t("projects.angleUnit")}</Label>
                <Select<DisplayAngleUnit>
                  id="punit"
                  value={unit}
                  onValueChange={setUnit}
                  options={[
                    { value: "gon", label: t("units.gon") },
                    { value: "deg", label: t("units.deg") },
                    { value: "dms", label: t("units.dms") },
                  ]}
                />
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={busy || !name.trim()}>
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ProjectCard({ p, onRename, onDelete }: { p: ProjectMeta; onRename: () => void; onDelete: () => void }) {
  const { t, i18n } = useTranslation();
  return (
    <div className="group relative flex flex-col rounded-xl border bg-surface p-4 transition-colors hover:border-border-strong ">
      <Link to="/p/$projectId" params={{ projectId: p.id }} className="absolute inset-0 rounded-xl" aria-label={p.name} />
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent-subtle text-accent">
            <Triangle className="size-4" />
          </span>
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">{p.name}</div>
            <div className="text-xs text-muted">{t("projects.updated", { when: relativeTime(p.updated_at, i18n.language) })}</div>
          </div>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" className="relative z-10 opacity-60 group-hover:opacity-100" aria-label="Menu">
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={onRename}>
              <Pencil /> {t("common.rename")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem destructive onSelect={onDelete}>
              <Trash2 /> {t("common.delete")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {p.description && <p className="mt-3 line-clamp-2 text-xs text-muted">{p.description}</p>}
      <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-4">
        {p.counts && <span className="text-xs text-muted tabular">{t("projects.counts", { ...p.counts })}</span>}
        <Badge variant="secondary" className="ml-auto">
          {p.angle_unit === "gon" ? "grad" : p.angle_unit === "deg" ? "deg" : "DMS"}
        </Badge>
      </div>
    </div>
  );
}

export function ProjectsPage() {
  const { t } = useTranslation();
  const { mode, store } = useSession();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [renaming, setRenaming] = useState<ProjectMeta | null>(null);
  const [deleting, setDeleting] = useState<ProjectMeta | null>(null);

  const projects = useQuery({
    queryKey: ["projects", mode],
    queryFn: () => store!.listProjects(),
    enabled: Boolean(store),
  });

  const createSample = useMutation({
    mutationFn: async () => {
      const seed = buildSampleProject();
      return store!.createProject({ name: t("projects.sampleName"), description: t("projects.sampleDescription"), angle_unit: "gon" }, seed);
    },
    onSuccess: (p) => {
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void navigate({ to: "/p/$projectId", params: { projectId: p.id } });
    },
    onError: (e) => ((e as Error).name === "ProjectLimitError" ? toast.warning(t("projects.limitReached")) : toast.error((e as Error).message)),
  });

  const commands = useMemo<Command[]>(
    () => [
      { id: "new", group: t("cmd.actions"), label: t("projects.new"), icon: <Plus />, run: () => setCreateOpen(true) },
      { id: "sample", group: t("cmd.actions"), label: t("projects.openSample"), icon: <Sparkles />, run: () => createSample.mutate() },
      ...(projects.data ?? []).map((p) => ({
        id: `p-${p.id}`,
        group: t("cmd.projects"),
        label: p.name,
        icon: <FolderOpen />,
        run: () => void navigate({ to: "/p/$projectId", params: { projectId: p.id } }),
      })),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [projects.data, t],
  );
  usePageCommands(commands);

  if (mode === "none") return <Navigate to="/" />;

  const filtered = (projects.data ?? []).filter((p) => !q || `${p.name} ${p.description ?? ""}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-20 border-b bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4">
          <Logo />
          {mode === "demo" && <Badge variant="warning">{t("common.demo")}</Badge>}
          <div className="ml-auto flex items-center gap-2">
            <button
              className="hidden h-8 items-center gap-2 rounded-md border bg-surface px-2.5 text-xs text-muted hover:text-fg sm:flex"
              onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }))}
            >
              <Search className="size-3.5" /> {t("common.search")} <Kbd>⌘K</Kbd>
            </button>
            <UserMenu />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{t("projects.title")}</h1>
            {mode === "demo" && <p className="mt-1 text-xs text-muted">{t("projects.demoBanner")}</p>}
          </div>
          <div className="ml-auto flex items-center gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("common.search")} className="w-48 pl-8 sm:w-64" aria-label={t("common.search")} />
            </div>
            <Button variant="outline" onClick={() => createSample.mutate()} disabled={createSample.isPending}>
              <Sparkles /> <span className="hidden sm:inline">{t("projects.openSample")}</span>
            </Button>
            <Button onClick={() => setCreateOpen(true)} data-testid="new-project">
              <Plus /> {t("projects.new")}
            </Button>
          </div>
        </div>

        <div className="mt-6">
          {projects.isLoading ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-32 rounded-xl" />
              ))}
            </div>
          ) : (projects.data ?? []).length === 0 ? (
            <div className="rounded-xl border border-dashed">
              <EmptyState
                icon={<FolderOpen />}
                title={t("projects.empty")}
                description={t("projects.emptyHint")}
                action={
                  <div className="flex gap-2">
                    <Button variant="outline" onClick={() => createSample.mutate()} data-testid="open-sample">
                      <Sparkles /> {t("projects.openSample")}
                    </Button>
                    <Button onClick={() => setCreateOpen(true)}>
                      <Plus /> {t("projects.new")}
                    </Button>
                  </div>
                }
              />
            </div>
          ) : filtered.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted">{t("projects.noMatch")}</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.map((p) => (
                <ProjectCard key={p.id} p={p} onRename={() => setRenaming(p)} onDelete={() => setDeleting(p)} />
              ))}
            </div>
          )}
        </div>
      </main>

      {createOpen && (
        <ProjectFormDialog
          open
          showUnit
          onOpenChange={setCreateOpen}
          title={t("projects.new")}
          submitLabel={t("common.create")}
          onSubmit={async (v) => {
            const p = await store!.createProject(v);
            await qc.invalidateQueries({ queryKey: ["projects"] });
            void navigate({ to: "/p/$projectId", params: { projectId: p.id } });
          }}
        />
      )}
      {renaming && (
        <ProjectFormDialog
          open
          onOpenChange={(o) => !o && setRenaming(null)}
          initial={renaming}
          title={t("projects.renameTitle")}
          submitLabel={t("common.save")}
          onSubmit={async (v) => {
            await store!.renameProject(renaming.id, v.name, v.description);
            await qc.invalidateQueries({ queryKey: ["projects"] });
          }}
        />
      )}
      <Dialog open={Boolean(deleting)} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("projects.deleteTitle")}</DialogTitle>
            <DialogDescription>{t("projects.deleteBody", { name: deleting?.name })}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={async () => {
                if (!deleting) return;
                try {
                  await store!.deleteProject(deleting.id);
                  await qc.invalidateQueries({ queryKey: ["projects"] });
                } catch (e) {
                  toast.error((e as Error).message);
                }
                setDeleting(null);
              }}
            >
              <Trash2 /> {t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
