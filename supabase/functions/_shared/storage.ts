// Removes stored objects queued by the database (public.storage_deletions) and objects no
// raw_files row references. Used by storage-janitor and by delete-account (immediate erasure).
import type { SupabaseClient } from "npm:@supabase/supabase-js@2";

export const BATCH = 500;

export interface DrainResult {
  removed: number;
  failed: number;
}

/** Splits names into Storage API sized batches (the API accepts up to 1000 per call). */
export function batches<T>(items: T[], size = 100): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

export async function drainDeletions(admin: SupabaseClient): Promise<DrainResult> {
  const { data, error } = await admin.rpc("claim_storage_deletions", { p_limit: BATCH });
  if (error) throw new Error(`claim_storage_deletions: ${error.message}`);
  const rows = (data ?? []) as { id: number; bucket_id: string; name: string }[];
  let removed = 0;
  let failed = 0;
  for (const chunk of batches(rows)) {
    const byBucket = new Map<string, typeof chunk>();
    for (const r of chunk) byBucket.set(r.bucket_id, [...(byBucket.get(r.bucket_id) ?? []), r]);
    for (const [bucket, items] of byBucket) {
      const rm = await admin.storage.from(bucket).remove(items.map((r) => r.name));
      const ids = items.map((r) => r.id);
      if (rm.error) {
        failed += items.length;
        console.error("storage removal failed", bucket, rm.error.message);
        continue; // entries stay queued; the next run retries
      }
      const del = await admin.from("storage_deletions").delete().in("id", ids);
      if (del.error) throw new Error(`storage_deletions: ${del.error.message}`);
      removed += items.length;
    }
  }
  return { removed, failed };
}

export async function sweepOrphans(admin: SupabaseClient): Promise<number> {
  const { data, error } = await admin.rpc("storage_orphans", { p_limit: BATCH });
  if (error) throw new Error(`storage_orphans: ${error.message}`);
  const names = (data ?? []) as string[];
  let removed = 0;
  for (const chunk of batches(names)) {
    const rm = await admin.storage.from("raw-files").remove(chunk);
    if (rm.error) {
      console.error("orphan removal failed", rm.error.message);
      continue;
    }
    removed += chunk.length;
  }
  return removed;
}
