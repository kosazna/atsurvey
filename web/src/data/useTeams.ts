import { useQuery } from "@tanstack/react-query";
import type { TFunction } from "i18next";
import { useEffect } from "react";
import { supabase } from "@/lib/supabase";
import { useSession } from "./session";
import { type MyWorkspace, teams } from "./teams";

export function useMyWorkspaces() {
  const { mode, session } = useSession();
  return useQuery({
    queryKey: ["my-workspaces", session?.user.id],
    queryFn: () => teams.myWorkspaces(supabase!),
    enabled: mode === "cloud" && Boolean(supabase),
    staleTime: 30_000,
  });
}

/** The selected workspace, falling back to the personal one (also when the stored choice is gone). */
export function useCurrentWorkspace(): { workspaces: MyWorkspace[]; current: MyWorkspace | null; isLoading: boolean } {
  const { workspaceId, setWorkspaceId } = useSession();
  const q = useMyWorkspaces();
  const workspaces = q.data ?? [];
  const current = workspaces.find((w) => w.id === workspaceId) ?? workspaces.find((w) => w.personal) ?? workspaces[0] ?? null;
  useEffect(() => {
    if (current && current.id !== workspaceId) setWorkspaceId(current.id);
  }, [current, workspaceId, setWorkspaceId]);
  return { workspaces, current, isLoading: q.isLoading };
}

/** Translated message for a database error code raised by the team RPCs and guards. */
export function teamErrorMessage(t: TFunction, e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e);
  const code = Object.keys(t("team.errors", { returnObjects: true }) as Record<string, string>).find((k) => raw.includes(k));
  if (code) return t(`team.errors.${code}`);
  if (raw.includes("row-level security") || raw.includes("permission denied")) return t("team.errors.not_allowed");
  return raw;
}
