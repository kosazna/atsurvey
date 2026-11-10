// Project lifecycle on the signed-in store (migration 20261111000007): archive, trash with 30-day
// recovery, delete forever, duplicate, original files. Rules are enforced by the database.
import type { SupabaseClient } from "@supabase/supabase-js";

export const TRASH_DAYS = 30;

export interface ShelvedProject {
  id: string;
  name: string;
  archived_at: string | null;
  deleted_at: string | null;
  updated_at: string;
}

export interface RawFileInfo {
  id: string;
  filename: string;
  format: string;
  size_bytes: number | null;
  storage_path: string;
  created_at: string;
}

function ok<T>(res: { data: T | null; error: { message: string } | null }): T {
  if (res.error) throw new Error(res.error.message);
  return res.data as T;
}

/** Whole days left before a trashed project is purged (never negative). */
export function daysUntilPurge(deletedAt: string, now = new Date()): number {
  const purgeAt = new Date(deletedAt).getTime() + TRASH_DAYS * 86_400_000;
  return Math.max(0, Math.ceil((purgeAt - now.getTime()) / 86_400_000));
}

export const lifecycle = {
  archived: async (sb: SupabaseClient, workspaceId: string) =>
    ok(
      await sb
        .from("projects")
        .select("id, name, archived_at, deleted_at, updated_at")
        .eq("workspace_id", workspaceId)
        .not("archived_at", "is", null)
        .is("deleted_at", null)
        .order("archived_at", { ascending: false }),
    ) as ShelvedProject[],
  trash: async (sb: SupabaseClient, workspaceId: string) =>
    ok(
      await sb
        .from("projects")
        .select("id, name, archived_at, deleted_at, updated_at")
        .eq("workspace_id", workspaceId)
        .not("deleted_at", "is", null)
        .order("deleted_at", { ascending: false }),
    ) as ShelvedProject[],
  archive: async (sb: SupabaseClient, id: string) =>
    void ok(await sb.from("projects").update({ archived_at: new Date().toISOString() }).eq("id", id)),
  unarchive: async (sb: SupabaseClient, id: string) => void ok(await sb.from("projects").update({ archived_at: null }).eq("id", id)),
  restore: async (sb: SupabaseClient, id: string) => void ok(await sb.rpc("restore_project", { p_project_id: id })),
  deleteForever: async (sb: SupabaseClient, id: string) => void ok(await sb.from("projects").delete().eq("id", id)),
  duplicate: async (sb: SupabaseClient, id: string, name: string) =>
    ok(await sb.rpc("duplicate_project", { p_project_id: id, p_name: name })) as string,
  rawFiles: async (sb: SupabaseClient, projectId: string) =>
    ok(
      await sb
        .from("raw_files")
        .select("id, filename, format, size_bytes, storage_path, created_at")
        .eq("project_id", projectId)
        .order("created_at", { ascending: false }),
    ) as RawFileInfo[],
  /** Short-lived (60 s) signed download link; Storage checks the caller's access first. */
  downloadUrl: async (sb: SupabaseClient, file: RawFileInfo) => {
    const { data, error } = await sb.storage.from("raw-files").createSignedUrl(file.storage_path, 60, { download: file.filename });
    if (error || !data) throw new Error(error?.message ?? "download failed");
    return data.signedUrl;
  },
};
