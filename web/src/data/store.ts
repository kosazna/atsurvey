import type {
  ComputeSettings,
  ControlPoint,
  DisplayAngleUnit,
  Observation,
  ParseResult,
  ProjectInput,
  ProjectResult,
  Setup,
  Summary,
  TraverseSpec,
} from "@/lib/types";
import type { ReadingKind } from "@/lib/cogoTypes";

export interface ProjectCounts {
  control: number;
  setups: number;
  observations: number;
  traverses: number;
  points: number;
}

export interface ProjectMeta {
  id: string;
  name: string;
  description: string | null;
  angle_unit: DisplayAngleUnit;
  created_at: string;
  updated_at: string;
  counts?: ProjectCounts;
  demo?: boolean;
}

export interface StoredControlPoint extends ControlPoint {
  id: string;
  note?: string | null;
}

export interface StoredObservation extends Observation {
  id: string;
  edited?: boolean;
}

export interface StoredSetup extends Setup {
  id: string;
  raw_file_id?: string | null;
  note?: string | null;
  observations: StoredObservation[];
}

export interface StoredTraverse extends TraverseSpec {
  id: string;
}

/** One row of the levelling readings grid. Rows with the same `setup` number form one setup. */
export interface LevelRow {
  id: string;
  setup: number;
  point: string;
  kind: ReadingKind;
  reading: number | null;
  distance: number | null;
}

export interface LevelingData {
  benchmarks: { id: string; name: string; h: number | null }[];
  rows: LevelRow[];
  /** Return run of double-run levelling (μετάβαση–επιστροφή), measured end → start */
  return_rows?: LevelRow[];
  /** Comma-separated section points for double-run levelling (empty = automatic) */
  section_points?: string;
  tolerance_base_mm: number;
  tolerance_mm_per_sqrt_km: number;
  distribute: "distance" | "setups";
}

/** Free-form per-project data stored in projects.extras (jsonb). */
export interface ProjectExtras {
  leveling?: LevelingData;
  ui?: { ellipseScale?: number };
}

export interface ProjectData {
  meta: ProjectMeta;
  settings: ComputeSettings;
  control_points: StoredControlPoint[];
  setups: StoredSetup[];
  traverses: StoredTraverse[];
  extras: ProjectExtras;
}

export interface StoredRun {
  id: string;
  created_at: string;
  engine_version: string;
  input_hash: string;
  result: ProjectResult;
}

export interface RunSummary {
  id: string;
  created_at: string;
  engine_version: string;
  input_hash: string;
  summary: Summary | null;
}

export interface CreateProjectInput {
  name: string;
  description?: string | null;
  angle_unit: DisplayAngleUnit;
}

export interface ProjectStore {
  readonly kind: "local" | "supabase";
  /** Workspace id for entitlement checks (null in demo mode). */
  workspaceId(): Promise<string | null>;
  listProjects(): Promise<ProjectMeta[]>;
  createProject(input: CreateProjectInput, seed?: Partial<Omit<ProjectData, "meta">>): Promise<ProjectMeta>;
  renameProject(id: string, name: string, description?: string | null): Promise<void>;
  deleteProject(id: string): Promise<void>;
  getProject(id: string): Promise<ProjectData>;
  saveSettings(id: string, settings: ComputeSettings, angle_unit: DisplayAngleUnit): Promise<void>;
  saveControlPoints(id: string, points: StoredControlPoint[]): Promise<void>;
  saveSetups(id: string, setups: StoredSetup[]): Promise<void>;
  saveTraverses(id: string, traverses: StoredTraverse[]): Promise<void>;
  /** Persist the original raw file (Supabase storage). Returns the raw_file id, if any. */
  uploadRawFile(id: string, file: File, parsed: ParseResult): Promise<string | null>;
  saveExtras(id: string, extras: ProjectExtras): Promise<void>;
  saveRun(id: string, result: ProjectResult, settings: ComputeSettings): Promise<StoredRun>;
  latestRun(id: string): Promise<StoredRun | null>;
  listRuns(id: string): Promise<RunSummary[]>;
  getRun(id: string, runId: string): Promise<StoredRun | null>;
}

/** Build the clean engine payload (strips UI/DB-only fields — the engine forbids extras). */
export function toProjectInput(data: Pick<ProjectData, "settings" | "control_points" | "setups" | "traverses">): ProjectInput {
  return {
    settings: data.settings,
    control_points: data.control_points
      .filter((p) => p.name.trim() !== "" && Number.isFinite(p.x) && Number.isFinite(p.y))
      .map((p) => ({
        name: p.name.trim(),
        x: p.x,
        y: p.y,
        z: p.z ?? null,
        code: p.code || null,
      })),
    setups: data.setups
      .filter((s) => s.station.trim() !== "")
      .map((s) => ({
        id: s.id,
        station: s.station.trim(),
        instrument_height: s.instrument_height ?? 0,
        backsight: s.backsight || null,
        observations: s.observations
          .filter((o) => o.target.trim() !== "" && Number.isFinite(o.hz))
          .map((o) => ({
            id: o.id,
            target: o.target.trim(),
            hz: o.hz,
            v: o.v ?? null,
            sd: o.sd ?? null,
            target_height: o.target_height ?? 0,
            code: o.code || null,
            excluded: Boolean(o.excluded),
          })),
      })),
    traverses: data.traverses
      .filter((t) => t.route.length > 0)
      .map((t) => ({
        id: t.id,
        name: t.name || null,
        route: t.route,
        kind: t.kind ?? "auto",
        end_orientation: t.end_orientation ?? null,
        enabled: t.enabled ?? true,
      })),
  };
}

export function countProject(data: Pick<ProjectData, "control_points" | "setups" | "traverses">, points = 0): ProjectCounts {
  return {
    control: data.control_points.length,
    setups: data.setups.length,
    observations: data.setups.reduce((n, s) => n + s.observations.length, 0),
    traverses: data.traverses.length,
    points,
  };
}
