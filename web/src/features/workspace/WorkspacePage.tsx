import { Link, Navigate, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import {
  ArrowLeft,
  Calculator,
  Eye,
  GitCompareArrows,
  Redo2,
  Undo2,
  Download,
  Map as MapIcon,
  PanelRightClose,
  PanelRightOpen,
  Play,
  Save,
  SlidersHorizontal,
  Upload,
} from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { usePageCommands, type Command } from "@/components/commands";
import { Logo } from "@/components/Logo";
import { UserMenu } from "@/components/UserMenu";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty";
import { Kbd } from "@/components/ui/kbd";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tooltip } from "@/components/ui/tooltip";
import { useMyWorkspaces } from "@/data/useTeams";
import { useSession } from "@/data/session";
import { toggleTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { ShortcutsDialog } from "@/components/ShortcutsDialog";
import { ExportDialog } from "./dialogs/ExportDialog";
import { ImportDialog } from "./dialogs/ImportDialog";
import { SettingsDialog } from "./dialogs/SettingsDialog";
import { NAV, SECTION_ICONS } from "./navigation";
import { isModule, MODULE_TOOLS, type ModuleId, type Section } from "./sections";
import { MODULE_PAGES } from "./sections/modules";
import { ControlSection } from "./sections/ControlSection";
import { IssuesSection } from "./sections/IssuesSection";
import { ObservationsSection } from "./sections/ObservationsSection";
import { OverviewSection } from "./sections/OverviewSection";
import { ReportsSection } from "./sections/ReportsSection";
import { ResultsSection } from "./sections/ResultsSection";
import { TraversesSection } from "./sections/TraversesSection";
import { MapDock } from "./map/MapDock";
import { StatusPill } from "./StatusPill";
import { useProjectQuery, useWorkspace, WorkspaceProvider } from "./useWorkspace";

const AdjustmentSection = lazy(() => import("./sections/AdjustmentSection"));
const LevelingSection = lazy(() => import("./sections/LevelingSection"));
const LineworkSection = lazy(() => import("./sections/LineworkSection"));
const RunsSection = lazy(() => import("./sections/RunsSection"));

export function WorkspacePage() {
  const { mode } = useSession();
  const { projectId } = useParams({ from: "/p/$projectId" });
  const search = useSearch({ from: "/p/$projectId" });
  const navigate = useNavigate();
  const section: Section = search.section ?? "overview";
  const onSection = useCallback(
    (s: Section, tool?: string) => void navigate({ to: "/p/$projectId", params: { projectId }, search: tool ? { section: s, tool } : { section: s } }),
    [navigate, projectId],
  );
  const onTool = useCallback(
    (tool: string) => void navigate({ to: "/p/$projectId", params: { projectId }, search: { section, tool }, replace: true }),
    [navigate, projectId, section],
  );

  if (mode === "none") return <Navigate to="/" />;
  if (mode === "loading") return null;
  return <WorkspaceLoader key={projectId} projectId={projectId} section={section} tool={search.tool} onSection={onSection} onTool={onTool} />;
}

interface WorkspaceLoaderProps {
  projectId: string;
  section: Section;
  tool: string | undefined;
  onSection: (s: Section, tool?: string) => void;
  onTool: (tool: string) => void;
}

function WorkspaceLoader({ projectId, section, tool, onSection, onTool }: WorkspaceLoaderProps) {
  const { t } = useTranslation();
  const q = useProjectQuery(projectId);
  const workspaces = useMyWorkspaces();
  const role = workspaces.data?.find((w) => w.id === q.data?.data.meta.workspace_id)?.role;
  if (q.isLoading) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex h-12 items-center gap-3 border-b px-3">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="ml-auto h-7 w-72" />
        </div>
        <div className="flex flex-1">
          <div className="hidden w-52 space-y-2 border-r p-3 md:block">
            {NAV.slice(0, 12).map((n) => (
              <Skeleton key={n.id} className="h-7" />
            ))}
          </div>
          <div className="flex-1 p-6">
            <Skeleton className="h-40" />
          </div>
        </div>
      </div>
    );
  }
  if (q.isError || !q.data) {
    return (
      <EmptyState
        className="h-full"
        icon={<MapIcon />}
        title={t("ws.notFound")}
        description={(q.error as Error | null)?.message}
        action={
          <Button asChild variant="outline">
            <Link to="/projects">
              <ArrowLeft /> {t("projects.title")}
            </Link>
          </Button>
        }
      />
    );
  }
  return (
    <WorkspaceProvider
      initial={q.data.data}
      initialRun={q.data.run}
      section={section}
      tool={tool}
      onSection={onSection}
      onTool={onTool}
      readOnly={role === "viewer"}
    >
      <WorkspaceLayout />
    </WorkspaceProvider>
  );
}

function isTextField(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el) return false;
  return el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable;
}

function WorkspaceLayout() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const { mode } = useSession();
  const navRef = useRef<HTMLElement>(null);
  // keep the current page in view in the sidebar (horizontal bar on phones, scrolling list on short screens)
  useEffect(() => {
    navRef.current?.querySelector(`[data-testid="nav-${ws.section}"]`)?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [ws.section]);
  const issueCount = ws.result?.issues.filter((i) => i.severity !== "info").length ?? 0;
  const errorCount = ws.result?.issues.filter((i) => i.severity === "error").length ?? 0;

  useEffect(() => {
    document.title = `${ws.data.meta.name} · ATSurvey`;
    return () => {
      document.title = "ATSurvey";
    };
  }, [ws.data.meta.name]);

  // keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key === "Enter") {
        e.preventDefault();
        ws.compute();
      } else if (mod && e.shiftKey && e.key.toLowerCase() === "m") {
        e.preventDefault();
        ws.setMapVisible(!ws.mapVisible);
      } else if (mod && e.key.toLowerCase() === "i" && !e.shiftKey) {
        e.preventDefault();
        ws.setDialog("import");
      } else if (mod && e.key.toLowerCase() === "e" && !e.shiftKey) {
        e.preventDefault();
        ws.setDialog("export");
      } else if (mod && e.key.toLowerCase() === "z" && !isTextField(e.target)) {
        e.preventDefault();
        if (e.shiftKey) ws.redo();
        else ws.undo();
      } else if (mod && e.key.toLowerCase() === "y" && !isTextField(e.target)) {
        e.preventDefault();
        ws.redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ws]);

  const commands = useMemo<Command[]>(
    () => [
      ...NAV.map((n) => ({ id: `nav-${n.id}`, group: t("cmd.navigation"), label: t(`ws.sections.${n.id}`), icon: n.icon, run: () => ws.goTo(n.id) })),
      ...(Object.keys(MODULE_TOOLS) as ModuleId[])
        .filter((m) => MODULE_TOOLS[m].length > 1)
        .flatMap((m) =>
          MODULE_TOOLS[m].map((tool) => ({
            id: `tool-${m}-${tool}`,
            group: t("cmd.tools"),
            label: `${t(`ws.sections.${m}`)} · ${t(`tools.tabs.${tool}`)}`,
            icon: SECTION_ICONS[m],
            run: () => ws.goTo(m, { tool }),
          })),
        ),
      { id: "compute", group: t("cmd.actions"), label: t("ws.compute"), icon: <Play />, shortcut: "⌘↵", run: ws.compute },
      { id: "import", group: t("cmd.actions"), label: t("imp.title"), icon: <Upload />, shortcut: "⌘I", run: () => ws.setDialog("import") },
      { id: "export", group: t("cmd.actions"), label: t("exp.title"), icon: <Download />, shortcut: "⌘E", run: () => ws.setDialog("export") },
      { id: "settings", group: t("cmd.actions"), label: t("set.title"), icon: <SlidersHorizontal />, run: () => ws.setDialog("settings") },
      { id: "save-run", group: t("cmd.actions"), label: t("ws.saveRun"), icon: <Save />, run: () => void ws.saveRun() },
      { id: "map", group: t("cmd.actions"), label: t("cmd.toggleMap"), icon: <MapIcon />, shortcut: "⌘⇧M", run: () => ws.setMapVisible(!ws.mapVisible) },
      { id: "undo", group: t("cmd.actions"), label: t("ws.undo"), icon: <Undo2 />, shortcut: "⌘Z", run: ws.undo },
      { id: "redo", group: t("cmd.actions"), label: t("ws.redo"), icon: <Redo2 />, shortcut: "⇧⌘Z", run: ws.redo },
      { id: "compare", group: t("cmd.actions"), label: t("runs.compare"), icon: <GitCompareArrows />, run: () => ws.goTo("runs") },
      { id: "shortcuts", group: t("cmd.actions"), label: t("shortcuts.title"), shortcut: "?", run: () => window.dispatchEvent(new CustomEvent("ats:shortcuts")) },
      { id: "theme2", group: t("cmd.actions"), label: t("cmd.toggleTheme"), run: toggleTheme },
    ],
    [t, ws],
  );
  usePageCommands(commands);

  const content = (() => {
    if (isModule(ws.section)) {
      const Page = MODULE_PAGES[ws.section];
      return <Page />;
    }
    switch (ws.section) {
      case "overview":
        return <OverviewSection />;
      case "control":
        return <ControlSection />;
      case "observations":
        return <ObservationsSection />;
      case "traverses":
        return <TraversesSection />;
      case "results":
        return <ResultsSection />;
      case "reports":
        return <ReportsSection />;
      case "issues":
        return <IssuesSection />;
      case "adjustment":
        return <AdjustmentSection />;
      case "leveling":
        return <LevelingSection />;
      case "linework":
        return <LineworkSection />;
      case "runs":
        return <RunsSection />;
    }
  })();

  return (
    <div className="flex h-full flex-col">
      {/* top bar */}
      <header className="flex h-(--topbar-height) shrink-0 items-center gap-2 border-b bg-surface px-2 sm:px-4">
        <Tooltip content={t("projects.title")}>
          <Link to="/projects" className="flex items-center gap-1 rounded-md p-1 hover:bg-surface-sunken" aria-label={t("projects.title")}>
            <Logo withText={false} />
          </Link>
        </Tooltip>
        <span className="text-subtle">/</span>
        <div className="flex min-w-0 items-center gap-2">
          <h1 className="truncate text-sm font-semibold" data-testid="project-name">
            {ws.data.meta.name}
          </h1>
          {mode === "demo" && (
            <Badge variant="warning" className="hidden sm:inline-flex">
              {t("common.demo")}
            </Badge>
          )}
          <span className="hidden text-xs text-muted md:inline">
            {ws.saveState === "saved" ? t("common.saved") : ws.saveState === "saving" ? t("common.saving") : t("common.unsaved")}
          </span>
        </div>
        <div className="ml-2 hidden lg:block">
          <StatusPill />
        </div>
        <div className="ml-auto flex items-center gap-1">
          {ws.readOnly ? (
            <Tooltip content={t("team.readOnlyHint")}>
              <Badge variant="warning" data-testid="badge-read-only">
                {t("team.readOnly")}
              </Badge>
            </Tooltip>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => ws.setDialog("import")} data-testid="btn-import">
              <Upload /> <span className="hidden sm:inline">{t("common.import")}</span>
            </Button>
          )}
          <div className="flex items-center rounded-md border bg-surface">
            <Tooltip content={<span className="flex items-center gap-1.5">{t("ws.compute")} <Kbd className="border-bg bg-bg/10 text-bg">⌘↵</Kbd></span>}>
              <Button variant="ghost" size="sm" onClick={ws.compute} disabled={ws.status === "computing"} className="rounded-r-none" data-testid="btn-compute">
                <Calculator className={cn(ws.status === "computing" && "animate-pulse")} />
                <span className="hidden sm:inline">{ws.status === "computing" ? t("ws.computing") : t("ws.compute")}</span>
              </Button>
            </Tooltip>
            <Tooltip content={t("ws.autoCompute")}>
              <label className="flex h-7 items-center gap-1.5 border-l px-2 text-xs text-muted">
                <Switch checked={ws.autoCompute} onCheckedChange={ws.setAutoCompute} aria-label={t("ws.autoCompute")} className="h-4 w-7 [&>span]:size-3 [&>span]:data-[state=checked]:translate-x-[13px]" />
                <span className="hidden xl:inline">Auto</span>
              </label>
            </Tooltip>
          </div>
          <div className="hidden items-center sm:flex">
            <Tooltip content={<span className="flex items-center gap-1.5">{t("ws.undo")} <Kbd className="border-bg bg-bg/10 text-bg">⌘Z</Kbd></span>}>
              <Button variant="ghost" size="icon-sm" onClick={ws.undo} disabled={!ws.canUndo} aria-label={t("ws.undo")} data-testid="btn-undo">
                <Undo2 />
              </Button>
            </Tooltip>
            <Tooltip content={<span className="flex items-center gap-1.5">{t("ws.redo")} <Kbd className="border-bg bg-bg/10 text-bg">⇧⌘Z</Kbd></span>}>
              <Button variant="ghost" size="icon-sm" onClick={ws.redo} disabled={!ws.canRedo} aria-label={t("ws.redo")}>
                <Redo2 />
              </Button>
            </Tooltip>
          </div>
          <Tooltip content={t("ws.saveRun")}>
            <Button variant="ghost" size="icon-sm" onClick={() => void ws.saveRun()} disabled={!ws.result || ws.readOnly} aria-label={t("ws.saveRun")}>
              <Save />
            </Button>
          </Tooltip>
          <Button size="sm" onClick={() => ws.setDialog("export")} disabled={!ws.result} data-testid="btn-export">
            <Download /> <span className="hidden sm:inline">{t("common.export")}</span>
          </Button>
          <Tooltip content={t("set.title")}>
            <Button variant="ghost" size="icon-sm" onClick={() => ws.setDialog("settings")} aria-label={t("set.title")} data-testid="btn-settings">
              <SlidersHorizontal />
            </Button>
          </Tooltip>
          <Tooltip content={<span className="flex items-center gap-1.5">{ws.mapVisible ? t("ws.hideMap") : t("ws.showMap")} <Kbd className="border-bg bg-bg/10 text-bg">⌘⇧M</Kbd></span>}>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => ws.setMapVisible(!ws.mapVisible)}
              aria-label={ws.mapVisible ? t("ws.hideMap") : t("ws.showMap")}
              aria-pressed={ws.mapVisible}
              data-testid="btn-map"
            >
              {ws.mapVisible ? <PanelRightClose /> : <PanelRightOpen />}
            </Button>
          </Tooltip>
          <UserMenu />
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        {/* sidebar */}
        <nav ref={navRef} className="flex shrink-0 gap-0.5 overflow-x-auto border-b bg-bg p-1.5 md:w-(--sidebar-width) md:flex-col md:overflow-x-hidden md:overflow-y-auto md:border-b-0 md:border-r md:p-2" aria-label="Sections">
          {NAV.map((n, idx) => {
            const active = ws.section === n.id;
            const groupLabel = n.group && n.group !== NAV[idx - 1]?.group ? (
              <div key={`g-${n.group}`} className="hidden px-2.5 pb-1 pt-3 text-xs font-medium text-subtle md:block">
                {t(`ws.groups.${n.group}`)}
              </div>
            ) : null;
            const badge =
              n.id === "issues" && issueCount > 0 ? (
                <Badge variant={errorCount ? "destructive" : "warning"} className="ml-auto tabular">
                  {issueCount}
                </Badge>
              ) : n.id === "control" ? (
                <span className="ml-auto text-xs tabular text-muted">{ws.data.control_points.length || ""}</span>
              ) : n.id === "observations" ? (
                <span className="ml-auto text-xs tabular text-muted">{ws.data.setups.length || ""}</span>
              ) : n.id === "traverses" ? (
                <span className="ml-auto text-xs tabular text-muted">{ws.data.traverses.length || ""}</span>
              ) : null;
            return [
              groupLabel,
              <button
                key={n.id}
                onClick={() => ws.goTo(n.id)}
                data-testid={`nav-${n.id}`}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-8 shrink-0 cursor-pointer items-center gap-2 rounded-md px-2.5 text-sm text-muted transition-colors hover:bg-surface-sunken hover:text-fg [&_svg]:size-4",
                  active && "bg-surface font-medium text-fg ring-1 ring-border",
                )}
              >
                {n.icon}
                <span className="whitespace-nowrap">{t(`ws.sections.${n.id}`)}</span>
                <span className="hidden md:contents">{badge}</span>
              </button>,
            ];
          })}
          <div className="mt-auto hidden px-2 pb-1 pt-4 text-xs leading-relaxed text-muted md:block">
            <div className="flex items-center gap-1.5">
              <Kbd>⌘K</Kbd> {t("cmd.actions")}
            </div>
            {ws.result && <div className="mt-1.5 opacity-70">engine {ws.result.engine_version}</div>}
          </div>
        </nav>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col lg:flex-row">
          <main className="min-h-0 min-w-0 flex-1 overflow-auto lg:overflow-hidden" data-testid={`section-${ws.section}`}>
            <div className="lg:hidden px-3 pt-2">
              <StatusPill />
            </div>
            {ws.viewing && (
              <div className="flex items-center gap-2 border-b bg-warning-subtle px-4 py-2 text-xs text-warning" data-testid="viewing-banner">
                <Eye className="size-3.5" />
                <span className="font-medium">{t("runs.viewingBanner", { when: new Date(ws.viewing.created_at).toLocaleString() })}</span>
                <Button variant="outline" size="sm" className="ml-auto" onClick={() => ws.setViewing(null)}>
                  {t("runs.backToLive")}
                </Button>
              </div>
            )}
            <Suspense fallback={<Skeleton className="m-4 h-64" />}>{content}</Suspense>
          </main>
          <MapDock />
        </div>
      </div>

      <ImportDialog />
      <ExportDialog />
      <SettingsDialog />
      <ShortcutsDialog />
    </div>
  );
}
