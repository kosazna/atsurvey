// "Export my data": every project the user can open, as JSON, plus the original instrument
// files, in one zip built in the browser (nothing is sent anywhere). GDPR data portability.
import type { SupabaseClient } from "@supabase/supabase-js";
import { strToU8, zipSync, type Zippable } from "fflate";
import type { ProjectStore } from "@/data/store";

export interface ExportProgress {
  done: number;
  total: number;
}

/** File-system safe, unique folder name for a project. */
export function folderName(name: string, id: string): string {
  const safe = name.normalize("NFC").replace(/[\\/:*?"<>|\u0000-\u001f]+/g, "_").trim().slice(0, 80) || "project";
  return `${safe} (${id.slice(0, 8)})`;
}

interface RawFileRow {
  project_id: string;
  storage_path: string;
  filename: string;
}

export async function buildDataExport(
  store: ProjectStore,
  sb: SupabaseClient,
  onProgress: (p: ExportProgress) => void,
): Promise<Blob> {
  const projects = await store.listProjects();
  const files: Zippable = {};
  const { data: rawRows, error } = await sb.from("raw_files").select("project_id, storage_path, filename");
  if (error) throw new Error(error.message);
  const raws = (rawRows ?? []) as RawFileRow[];
  const total = projects.length + raws.length;
  let done = 0;
  onProgress({ done, total });

  const folders = new Map<string, string>();
  for (const meta of projects) {
    const folder = folderName(meta.name, meta.id);
    folders.set(meta.id, folder);
    const [data, runs] = await Promise.all([store.getProject(meta.id), store.listRuns(meta.id)]);
    files[`${folder}/project.json`] = strToU8(JSON.stringify({ ...data, runs }, null, 2));
    onProgress({ done: ++done, total });
  }
  for (const raw of raws) {
    const folder = folders.get(raw.project_id) ?? `other (${raw.project_id.slice(0, 8)})`;
    const { data: blob, error: dlErr } = await sb.storage.from("raw-files").download(raw.storage_path);
    if (!dlErr && blob) {
      const name = raw.storage_path.split("/").pop() ?? raw.filename;
      files[`${folder}/original-files/${name}`] = new Uint8Array(await blob.arrayBuffer());
    }
    onProgress({ done: ++done, total });
  }
  files["README.txt"] = strToU8(
    `ATSurvey data export ${new Date().toISOString()}\n` +
      "Each folder is one project: project.json (control points, setups, observations, traverses,\n" +
      "settings, saved runs) and original-files/ (the instrument files as imported).\n",
  );
  const zipped = zipSync(files, { level: 6 });
  return new Blob([zipped.buffer as ArrayBuffer], { type: "application/zip" });
}
