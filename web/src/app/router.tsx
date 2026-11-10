import { createRootRoute, createRoute, createRouter, lazyRouteComponent, Outlet } from "@tanstack/react-router";
import { CommandPalette } from "@/components/CommandPalette";
import { useSession } from "@/data/session";
import { AuthPage } from "@/features/auth/AuthPage";
import { MfaChallenge } from "@/features/auth/MfaChallenge";
import { ResetPasswordPage } from "@/features/auth/ResetPasswordPage";
import { LandingPage } from "@/features/landing/LandingPage";
import { ProjectsPage } from "@/features/projects/ProjectsPage";
import { SECTIONS, type Section } from "@/features/workspace/sections";

/** Two-factor accounts signed in with a password only see the code prompt, on every route. */
function RootLayout() {
  const { mode } = useSession();
  if (mode === "mfa") return <MfaChallenge />;
  return (
    <>
      <Outlet />
      <CommandPalette />
    </>
  );
}

const rootRoute = createRootRoute({ component: RootLayout });

const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: LandingPage });
const loginRoute = createRoute({ getParentRoute: () => rootRoute, path: "/login", component: AuthPage });
const resetRoute = createRoute({ getParentRoute: () => rootRoute, path: "/reset-password", component: ResetPasswordPage });
const accountRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/account",
  component: lazyRouteComponent(() => import("@/features/account/AccountPage"), "AccountPage"),
});
const billingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/billing",
  component: lazyRouteComponent(() => import("@/features/account/BillingPage"), "BillingPage"),
});
const teamRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/team",
  component: lazyRouteComponent(() => import("@/features/team/TeamPage"), "TeamPage"),
});
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

const routeTree = rootRoute.addChildren([indexRoute, loginRoute, resetRoute, accountRoute, billingRoute, teamRoute, projectsRoute, projectRoute]);

export const router = createRouter({ routeTree, defaultPreload: "intent" });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
