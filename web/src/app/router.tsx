import { createRootRoute, createRoute, createRouter, lazyRouteComponent, Outlet } from "@tanstack/react-router";
import { CommandPalette } from "@/components/CommandPalette";
import { AuthPage } from "@/features/auth/AuthPage";
import { ProjectsPage } from "@/features/projects/ProjectsPage";
import { SECTIONS, type Section } from "@/features/workspace/sections";

const rootRoute = createRootRoute({
  component: () => (
    <>
      <Outlet />
      <CommandPalette />
    </>
  ),
});

const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: AuthPage });
const projectsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/projects", component: ProjectsPage });
export const projectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/p/$projectId",
  validateSearch: (search: Record<string, unknown>): { section?: Section } => {
    const s = search.section;
    return typeof s === "string" && (SECTIONS as readonly string[]).includes(s) ? { section: s as Section } : {};
  },
  component: lazyRouteComponent(() => import("@/features/workspace/WorkspacePage"), "WorkspacePage"),
});

const routeTree = rootRoute.addChildren([indexRoute, projectsRoute, projectRoute]);

export const router = createRouter({ routeTree, defaultPreload: "intent" });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
