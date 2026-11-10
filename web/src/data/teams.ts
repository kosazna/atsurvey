// Team workspaces: thin typed wrappers over the RPCs of migration 20261111000006 (membership by
// invitation and consent) and the audit log. Every rule is enforced by the database; these
// functions only call it and surface its error codes.
import type { SupabaseClient } from "@supabase/supabase-js";

export type Role = "owner" | "admin" | "member" | "viewer";
export const ROLES: Role[] = ["owner", "admin", "member", "viewer"];
export const INVITABLE_ROLES: Role[] = ["admin", "member", "viewer"];

export interface MyWorkspace {
  id: string;
  name: string;
  personal: boolean;
  role: Role;
  plan: "free" | "pro";
  require_mfa: boolean;
}

export interface RosterEntry {
  user_id: string;
  full_name: string | null;
  email: string;
  role: Role;
  has_mfa: boolean;
  joined_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: Role;
  created_at: string;
  expires_at: string;
}

export interface MyInvitation {
  id: string;
  workspace_id: string;
  workspace_name: string;
  role: Role;
  invited_by_name: string | null;
  expires_at: string;
}

export interface AuditEvent {
  id: number;
  project_id: string | null;
  actor: string | null;
  action: string;
  details: Record<string, unknown>;
  created_at: string;
}

/** Database error code (raise ... message = '<code>') carried as the Error message. */
export class TeamError extends Error {}

function ok<T>(res: { data: T | null; error: { message: string } | null }): T {
  if (res.error) throw new TeamError(res.error.message);
  return res.data as T;
}

export const canManage = (role: Role | undefined) => role === "owner" || role === "admin";
export const canWrite = (role: Role | undefined) => role === "owner" || role === "admin" || role === "member";

/** Roles an inviter may hand out: owners invite admins too; admins invite members and viewers. */
export function rolesInvitableBy(role: Role | undefined): Role[] {
  if (role === "owner") return INVITABLE_ROLES;
  if (role === "admin") return ["member", "viewer"];
  return [];
}

export const teams = {
  myWorkspaces: async (sb: SupabaseClient) => ok(await sb.rpc("my_workspaces")) as MyWorkspace[],
  createWorkspace: async (sb: SupabaseClient, name: string) =>
    (ok(await sb.from("workspaces").insert({ name: name.trim(), personal: false }).select("id").single()) as { id: string }).id,
  renameWorkspace: async (sb: SupabaseClient, id: string, name: string) =>
    void ok(await sb.from("workspaces").update({ name: name.trim() }).eq("id", id)),
  setRequireMfa: async (sb: SupabaseClient, id: string, on: boolean) =>
    void ok(await sb.from("workspaces").update({ require_mfa: on }).eq("id", id)),
  deleteWorkspace: async (sb: SupabaseClient, id: string) => void ok(await sb.from("workspaces").delete().eq("id", id)),
  roster: async (sb: SupabaseClient, id: string) => ok(await sb.rpc("workspace_roster", { p_workspace_id: id })) as RosterEntry[],
  setRole: async (sb: SupabaseClient, workspaceId: string, userId: string, role: Role) =>
    void ok(await sb.from("workspace_members").update({ role }).eq("workspace_id", workspaceId).eq("user_id", userId)),
  removeMember: async (sb: SupabaseClient, workspaceId: string, userId: string) =>
    void ok(await sb.from("workspace_members").delete().eq("workspace_id", workspaceId).eq("user_id", userId)),
  transferOwnership: async (sb: SupabaseClient, workspaceId: string, userId: string) =>
    void ok(await sb.rpc("transfer_ownership", { p_workspace_id: workspaceId, p_new_owner: userId })),
  invitations: async (sb: SupabaseClient, workspaceId: string) =>
    ok(
      await sb
        .from("workspace_invitations")
        .select("id, email, role, created_at, expires_at")
        .eq("workspace_id", workspaceId)
        .is("accepted_at", null)
        .is("declined_at", null)
        .is("revoked_at", null)
        .gt("expires_at", new Date().toISOString())
        .order("created_at", { ascending: false }),
    ) as Invitation[],
  invite: async (sb: SupabaseClient, workspaceId: string, email: string, role: Role) =>
    ok(await sb.rpc("invite_member", { p_workspace_id: workspaceId, p_email: email, p_role: role })) as string,
  revoke: async (sb: SupabaseClient, id: string) => void ok(await sb.rpc("revoke_invitation", { p_id: id })),
  myInvitations: async (sb: SupabaseClient) => ok(await sb.rpc("my_invitations")) as MyInvitation[],
  accept: async (sb: SupabaseClient, id: string) => ok(await sb.rpc("accept_invitation", { p_id: id })) as string,
  decline: async (sb: SupabaseClient, id: string) => void ok(await sb.rpc("decline_invitation", { p_id: id })),
  moveProject: async (sb: SupabaseClient, projectId: string, workspaceId: string) =>
    void ok(await sb.from("projects").update({ workspace_id: workspaceId }).eq("id", projectId)),
  activity: async (sb: SupabaseClient, workspaceId: string, limit = 200) =>
    ok(
      await sb
        .from("audit_events")
        .select("id, project_id, actor, action, details, created_at")
        .eq("workspace_id", workspaceId)
        .order("created_at", { ascending: false })
        .limit(limit),
    ) as AuditEvent[],
};
