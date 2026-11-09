// Demo-mode store: everything lives in the browser (localStorage). No account needed.
import { defaultSettings, normalizeSettings } from "@/lib/types";
import type { ComputeSettings, DisplayAngleUnit, ParseResult, ProjectResult } from "@/lib/types";
import { uid } from "@/lib/utils";
import {
  countProject,
  type CreateProjectInput,
  type ProjectData,
  type ProjectMeta,
  type ProjectStore,
  type StoredControlPoint,
  type StoredRun,
  type StoredSetup,
  type StoredTraverse,
} from "./store";

const INDEX_KEY = "ats:projects";
const projectKey = (id: string) => `ats:project:${id}`;
const runKey = (id: string) => `ats:run:${id}`;

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    console.warn("localStorage write failed", e);
    throw new Error("Browser storage is full or unavailable");
  }
}

export class LocalStore implements ProjectStore {
  readonly kind = "local" as const;

  async workspaceId() {
    return null;
  }

  private index(): ProjectMeta[] {
    return read<ProjectMeta[]>(INDEX_KEY, []);
  }

  private writeIndex(items: ProjectMeta[]) {
    write(INDEX_KEY, items);
  }

  private touch(id: string, data?: ProjectData) {
    const idx = this.index();
    const i = idx.findIndex((p) => p.id === id);
    if (i >= 0) {
      const run = read<StoredRun | null>(runKey(id), null);
      idx[i] = {
        ...idx[i],
        updated_at: new Date().toISOString(),
        ...(data ? { counts: countProject(data, run?.result.points.length ?? 0) } : {}),
      };
      this.writeIndex(idx);
    }
  }

  private load(id: string): ProjectData {
    const data = read<ProjectData | null>(projectKey(id), null);
    if (!data) throw new Error("Project not found");
    data.settings = normalizeSettings(data.settings);
    return data;
  }

  private save(data: ProjectData) {
    write(projectKey(data.meta.id), data);
    this.touch(data.meta.id, data);
  }

  async listProjects() {
    return this.index().sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  }

  async createProject(input: CreateProjectInput, seed?: Partial<Omit<ProjectData, "meta">>) {
    const now = new Date().toISOString();
    const meta: ProjectMeta = {
      id: uid(),
      name: input.name,
      description: input.description ?? null,
      angle_unit: input.angle_unit,
      created_at: now,
      updated_at: now,
      demo: true,
    };
    const data: ProjectData = {
      meta,
      settings: seed?.settings ?? defaultSettings(),
      control_points: seed?.control_points ?? [],
      setups: seed?.setups ?? [],
      traverses: seed?.traverses ?? [],
    };
    meta.counts = countProject(data);
    this.writeIndex([meta, ...this.index()]);
    write(projectKey(meta.id), data);
    return meta;
  }

  async renameProject(id: string, name: string, description?: string | null) {
    const data = this.load(id);
    data.meta.name = name;
    if (description !== undefined) data.meta.description = description;
    write(projectKey(id), data);
    this.writeIndex(this.index().map((p) => (p.id === id ? { ...p, name, description: data.meta.description } : p)));
    this.touch(id);
  }

  async deleteProject(id: string) {
    localStorage.removeItem(projectKey(id));
    localStorage.removeItem(runKey(id));
    this.writeIndex(this.index().filter((p) => p.id !== id));
  }

  async getProject(id: string) {
    return this.load(id);
  }

  async saveSettings(id: string, settings: ComputeSettings, angle_unit: DisplayAngleUnit) {
    const data = this.load(id);
    data.settings = settings;
    data.meta.angle_unit = angle_unit;
    this.save(data);
    this.writeIndex(this.index().map((p) => (p.id === id ? { ...p, angle_unit } : p)));
  }

  async saveControlPoints(id: string, points: StoredControlPoint[]) {
    const data = this.load(id);
    data.control_points = points;
    this.save(data);
  }

  async saveSetups(id: string, setups: StoredSetup[]) {
    const data = this.load(id);
    data.setups = setups;
    this.save(data);
  }

  async saveTraverses(id: string, traverses: StoredTraverse[]) {
    const data = this.load(id);
    data.traverses = traverses;
    this.save(data);
  }

  async uploadRawFile(_id: string, _file: File, _parsed: ParseResult) {
    return null; // demo mode keeps only the parsed observations
  }

  async saveRun(id: string, result: ProjectResult, _settings: ComputeSettings) {
    const run: StoredRun = {
      id: uid(),
      created_at: new Date().toISOString(),
      engine_version: result.engine_version,
      input_hash: result.input_hash,
      result,
    };
    write(runKey(id), run);
    this.touch(id, this.load(id));
    return run;
  }

  async latestRun(id: string) {
    return read<StoredRun | null>(runKey(id), null);
  }
}
