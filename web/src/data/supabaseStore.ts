// Supabase-backed store. Tables and RPCs per docs/contracts.md. RLS scopes everything
// to the user's workspace; we only need the workspace id when creating rows.
import type { SupabaseClient } from "@supabase/supabase-js";
import { normalizeSettings } from "@/lib/types";
import type { ComputeSettings, DisplayAngleUnit, ParseResult, ProjectResult } from "@/lib/types";
import { uid } from "@/lib/utils";
import type {
  CreateProjectInput,
  ProjectData,
  ProjectExtras,
  ProjectMeta,
  RunSummary,
  ProjectStore,
  StoredControlPoint,
  StoredRun,
  StoredSetup,
  StoredTraverse,
} from "./store";

interface ProjectRow {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  angle_unit: DisplayAngleUnit;
  settings: Partial<ComputeSettings> | null;
  /** added by migration 20261110000001; absent on older databases */
  extras?: ProjectExtras | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

function check<T>(res: { data: T; error: { message: string } | null }): T {
  if (res.error) throw new Error(res.error.message);
  return res.data;
}

const CHUNK = 500;
function chunks<T>(items: T[]): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += CHUNK) out.push(items.slice(i, i + CHUNK));
  return out;
}

export class SupabaseStore implements ProjectStore {
  readonly kind = "supabase" as const;
  private wsId: string | null = null;
  private sb: SupabaseClient;

  constructor(sb: SupabaseClient) {
    this.sb = sb;
  }

  private async userId(): Promise<string> {
    const { data } = await this.sb.auth.getUser();
    if (!data.user) throw new Error("Not signed in");
    return data.user.id;
  }

  async workspace(): Promise<string> {
    if (this.wsId) return this.wsId;
    const rows = check(await this.sb.from("workspaces").select("id, personal").order("personal", { ascending: false })) as {
      id: string;
      personal: boolean;
    }[];
    if (!rows.length) throw new Error("No workspace found for this account");
    this.wsId = (rows.find((r) => r.personal) ?? rows[0]).id;
    return this.wsId;
  }

  async workspaceId() {
    return this.workspace();
  }

  private toMeta(r: ProjectRow, counts?: ProjectMeta["counts"]): ProjectMeta {
    return {
      id: r.id,
      name: r.name,
      description: r.description,
      angle_unit: r.angle_unit ?? "gon",
      created_at: r.created_at,
      updated_at: r.updated_at,
      counts,
    };
  }

  async listProjects() {
    const rows = check(
      await this.sb
        .from("projects")
        .select("*, control_points(count), setups(count), traverses(count)")
        .is("archived_at", null)
        .order("updated_at", { ascending: false }),
    ) as unknown as (ProjectRow & {
      control_points: { count: number }[];
      setups: { count: number }[];
      traverses: { count: number }[];
    })[];
    return rows.map((r) =>
      this.toMeta(r, {
        control: r.control_points?.[0]?.count ?? 0,
        setups: r.setups?.[0]?.count ?? 0,
        observations: 0,
        traverses: r.traverses?.[0]?.count ?? 0,
        points: 0,
      }),
    );
  }

  async createProject(input: CreateProjectInput, seed?: Partial<Omit<ProjectData, "meta">>) {
    const workspace_id = await this.workspace();
    const res = await this.sb
      .from("projects")
      .insert({
        workspace_id,
        name: input.name,
        description: input.description ?? null,
        angle_unit: input.angle_unit,
        settings: seed?.settings ?? {},
        ...(seed?.extras && Object.keys(seed.extras).length ? { extras: seed.extras } : {}),
        created_by: await this.userId(),
      })
      .select()
      .single();
    if (res.error && (res.error.message.includes("project_limit_reached") || res.error.code === "P0001")) {
      throw new ProjectLimitError();
    }
    const row = check(res) as ProjectRow;
    try {
      if (seed?.control_points?.length) await this.saveControlPoints(row.id, seed.control_points);
      if (seed?.setups?.length) await this.saveSetups(row.id, seed.setups);
      if (seed?.traverses?.length) await this.saveTraverses(row.id, seed.traverses);
    } catch (e) {
      // Do not leave a half-seeded project behind (it would also count against the plan limit).
      await this.sb.from("projects").delete().eq("id", row.id);
      throw e;
    }
    return this.toMeta(row);
  }

  async renameProject(id: string, name: string, description?: string | null) {
    const patch: Record<string, unknown> = { name };
    if (description !== undefined) patch.description = description;
    check(await this.sb.from("projects").update(patch).eq("id", id));
  }

  async deleteProject(id: string) {
    check(await this.sb.from("projects").delete().eq("id", id));
  }

  async getProject(id: string): Promise<ProjectData> {
    const [p, cps, setups, obs, travs] = await Promise.all([
      this.sb.from("projects").select("*").eq("id", id).single(),
      this.sb.from("control_points").select("*").eq("project_id", id).order("name"),
      this.sb.from("setups").select("*").eq("project_id", id).order("ordinal"),
      this.sb.from("observations").select("*").eq("project_id", id).order("ordinal"),
      this.sb.from("traverses").select("*").eq("project_id", id).order("ordinal"),
    ]);
    const prow = check(p) as ProjectRow;
    type ObsRow = {
      id: string;
      setup_id: string;
      target: string;
      hz: number;
      v: number | null;
      sd: number | null;
      target_height: number;
      code: string | null;
      excluded: boolean;
      edited: boolean;
    };
    const obsBySetup = new Map<string, ObsRow[]>();
    for (const o of check(obs) as ObsRow[]) {
      const list = obsBySetup.get(o.setup_id) ?? [];
      list.push(o);
      obsBySetup.set(o.setup_id, list);
    }
    type SetupRow = {
      id: string;
      station: string;
      instrument_height: number;
      backsight: string | null;
      raw_file_id: string | null;
      note: string | null;
    };
    type TravRow = {
      id: string;
      name: string | null;
      route: string[];
      kind: StoredTraverse["kind"];
      end_orientation: boolean | null;
      enabled: boolean;
    };
    return {
      meta: this.toMeta(prow),
      settings: normalizeSettings(prow.settings),
      extras: prow.extras ?? {},
      control_points: (check(cps) as StoredControlPoint[]).map((c) => ({
        id: c.id,
        name: c.name,
        x: c.x,
        y: c.y,
        z: c.z,
        code: c.code,
        note: c.note,
      })),
      setups: (check(setups) as SetupRow[]).map((s) => ({
        id: s.id,
        station: s.station,
        instrument_height: s.instrument_height,
        backsight: s.backsight,
        raw_file_id: s.raw_file_id,
        note: s.note,
        observations: (obsBySetup.get(s.id) ?? []).map((o) => ({
          id: o.id,
          target: o.target,
          hz: o.hz,
          v: o.v,
          sd: o.sd,
          target_height: o.target_height,
          code: o.code,
          excluded: o.excluded,
          edited: o.edited,
        })),
      })),
      traverses: (check(travs) as TravRow[]).map((t) => ({
        id: t.id,
        name: t.name,
        route: t.route,
        kind: t.kind,
        end_orientation: t.end_orientation,
        enabled: t.enabled,
      })),
    };
  }

  async saveSettings(id: string, settings: ComputeSettings, angle_unit: DisplayAngleUnit) {
    check(await this.sb.from("projects").update({ settings, angle_unit }).eq("id", id));
  }

  /** Upsert rows by id, then delete rows of the project not present anymore. */
  private async sync(table: string, projectId: string, rows: Record<string, unknown>[], scope?: { col: string; ids: string[] }) {
    for (const part of chunks(rows)) {
      if (part.length) check(await this.sb.from(table).upsert(part, { onConflict: "id" }));
    }
    const keep = rows.map((r) => r.id as string);
    let q = this.sb.from(table).delete().eq("project_id", projectId);
    if (scope) q = q.in(scope.col, scope.ids.length ? scope.ids : ["00000000-0000-0000-0000-000000000000"]);
    if (keep.length) q = q.not("id", "in", `(${keep.join(",")})`);
    check(await q);
  }

  async saveControlPoints(id: string, points: StoredControlPoint[]) {
    await this.sync(
      "control_points",
      id,
      points.map((p) => ({
        id: p.id,
        project_id: id,
        name: p.name,
        x: p.x,
        y: p.y,
        z: p.z ?? null,
        code: p.code ?? null,
        note: p.note ?? null,
      })),
    );
  }

  async saveSetups(id: string, setups: StoredSetup[]) {
    await this.sync(
      "setups",
      id,
      setups.map((s, i) => ({
        id: s.id,
        project_id: id,
        ordinal: i,
        station: s.station,
        instrument_height: s.instrument_height ?? 0,
        backsight: s.backsight ?? null,
        raw_file_id: s.raw_file_id ?? null,
        note: s.note ?? null,
      })),
    );
    const obsRows = setups.flatMap((s) =>
      s.observations.map((o, i) => ({
        id: o.id,
        setup_id: s.id,
        project_id: id,
        ordinal: i,
        target: o.target,
        hz: o.hz,
        v: o.v ?? null,
        sd: o.sd ?? null,
        target_height: o.target_height ?? 0,
        code: o.code ?? null,
        excluded: Boolean(o.excluded),
        edited: Boolean(o.edited),
      })),
    );
    await this.sync("observations", id, obsRows);
  }

  async saveTraverses(id: string, traverses: StoredTraverse[]) {
    await this.sync(
      "traverses",
      id,
      traverses.map((t, i) => ({
        id: t.id,
        project_id: id,
        ordinal: i,
        name: t.name ?? null,
        route: t.route,
        kind: t.kind ?? "auto",
        end_orientation: t.end_orientation ?? null,
        enabled: t.enabled ?? true,
      })),
    );
  }

  async uploadRawFile(id: string, file: File, parsed: ParseResult) {
    const workspace_id = await this.workspace();
    const path = `${workspace_id}/${id}/${uid()}-${file.name.replace(/[^\w.\-]+/g, "_")}`;
    const up = await this.sb.storage.from("raw-files").upload(path, file, { upsert: false });
    if (up.error) throw new Error(up.error.message);
    const buf = await file.arrayBuffer();
    const hash = await crypto.subtle.digest("SHA-256", buf);
    const sha256 = Array.from(new Uint8Array(hash))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
    const row = check(
      await this.sb
        .from("raw_files")
        .insert({
          project_id: id,
          storage_path: path,
          filename: file.name,
          format: parsed.format,
          size_bytes: file.size,
          sha256,
          angle_unit: parsed.angle_unit,
          created_by: await this.userId(),
        })
        .select("id")
        .single(),
    ) as { id: string };
    return row.id;
  }

  async saveRun(id: string, result: ProjectResult, settings: ComputeSettings): Promise<StoredRun> {
    const runId = check(
      await this.sb.rpc("save_computation_run", { p_project_id: id, p_result: result, p_settings: settings }),
    ) as string;
    return {
      id: runId,
      created_at: new Date().toISOString(),
      engine_version: result.engine_version,
      input_hash: result.input_hash,
      result,
    };
  }

  async saveExtras(id: string, extras: ProjectExtras) {
    check(await this.sb.from("projects").update({ extras }).eq("id", id));
  }

  async listRuns(id: string): Promise<RunSummary[]> {
    return check(
      await this.sb
        .from("computation_runs")
        .select("id, created_at, engine_version, input_hash, summary")
        .eq("project_id", id)
        .order("created_at", { ascending: false })
        .limit(50),
    ) as RunSummary[];
  }

  async getRun(id: string, runId: string): Promise<StoredRun | null> {
    const rows = check(
      await this.sb
        .from("computation_runs")
        .select("id, created_at, engine_version, input_hash, result")
        .eq("project_id", id)
        .eq("id", runId)
        .limit(1),
    ) as StoredRun[];
    return rows[0] ?? null;
  }

  async latestRun(id: string): Promise<StoredRun | null> {
    const rows = check(
      await this.sb
        .from("computation_runs")
        .select("id, created_at, engine_version, input_hash, result")
        .eq("project_id", id)
        .order("created_at", { ascending: false })
        .limit(1),
    ) as StoredRun[];
    return rows[0] ?? null;
  }
}

export class ProjectLimitError extends Error {
  constructor() {
    super("project_limit_reached");
    this.name = "ProjectLimitError";
  }
}
