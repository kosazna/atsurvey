import type * as C from "./cogoTypes";
import { env } from "./env";
import { getAccessToken } from "./supabase";
import type {
  DisplayAngleUnit,
  ExportRequest,
  Me,
  ParseResult,
  ProjectInput,
  ProjectResult,
  RawFormat,
  TolerancePreset,
  TraverseSpec,
} from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  /** machine code from {detail: {code}} (e.g. "plan_required") */
  code: string | null = null;
  /** seconds to wait (HTTP 429 Retry-After) */
  retryAfter: number | null = null;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function authHeaders(): Promise<Record<string, string>> {
  const token = await getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handle(res: Response): Promise<Response> {
  if (res.ok) return res;
  if (res.status === 429) {
    const ra = Number(res.headers.get("Retry-After"));
    const err = new ApiError(429, "rate_limited");
    err.code = "rate_limited";
    err.retryAfter = Number.isFinite(ra) && ra > 0 ? ra : null;
    throw err;
  }
  if (res.status === 413) {
    const err = new ApiError(413, "too_large");
    err.code = "too_large";
    throw err;
  }
  let detail: unknown = undefined;
  let message = `${res.status} ${res.statusText}`;
  try {
    detail = await res.json();
    const d = (detail as { detail?: unknown })?.detail;
    if (typeof d === "string") message = d;
    else if (d && typeof d === "object" && "code" in d) {
      const err = new ApiError(res.status, String((d as { code: unknown }).code), detail);
      err.code = String((d as { code: unknown }).code);
      throw err;
    }
    else if (Array.isArray(d) && d[0]?.msg) message = `${d[0].msg} (${(d[0].loc ?? []).join(".")})`;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    /* not JSON */
  }
  throw new ApiError(res.status, message, detail);
}

/** Shared by feature clients (lib/*Api.ts). */
export async function request(path: string, init: RequestInit = {}): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${env.apiUrl}${path}`, {
      ...init,
      headers: { ...(init.headers ?? {}), ...(await authHeaders()) },
    });
  } catch (e) {
    throw new ApiError(0, `Network error: ${(e as Error).message}`);
  }
  return handle(res);
}

export async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  return (await res.json()) as T;
}

export function filenameFrom(res: Response, fallback: string): string {
  const cd = res.headers.get("Content-Disposition") ?? "";
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  if (star) return decodeURIComponent(star[1]);
  const plain = /filename="?([^";]+)"?/i.exec(cd);
  return plain ? plain[1] : fallback;
}

/** True when the API does not (yet) expose the endpoint — the UI degrades gracefully. */
export function isNotAvailable(e: unknown): boolean {
  return e instanceof ApiError && (e.status === 404 || e.status === 405 || e.status === 501);
}

export const cogo = {
  inverse: (r: C.InverseRequest) => postJson<C.InverseResult>("/v1/cogo/inverse", r),
  polar: (r: C.PolarRequest) => postJson<C.PolarResult>("/v1/cogo/polar", r),
  intersectionAngles: (r: C.IntersectionAnglesRequest) => postJson<C.IntersectionResult>("/v1/cogo/intersection/angles", r),
  intersectionDistances: (r: C.IntersectionDistancesRequest) => postJson<C.IntersectionResult>("/v1/cogo/intersection/distances", r),
  intersectionLines: (r: C.IntersectionLinesRequest) => postJson<C.IntersectionResult>("/v1/cogo/intersection/lines", r),
  resection: (r: C.ResectionRequest) => postJson<C.ResectionResult>("/v1/cogo/resection", r),
  area: (r: C.AreaRequest) => postJson<C.AreaResult>("/v1/cogo/area", r),
  transform: (r: C.TransformRequest) => postJson<C.TransformResult>("/v1/cogo/transform", r),
  offset: (r: C.OffsetRequest) => postJson<C.OffsetResult>("/v1/cogo/offset", r),
  stakeout: (r: C.StakeoutRequest) => postJson<C.StakeoutResult>("/v1/cogo/stakeout", r),
  leveling: (r: C.LevelingRequest) => postJson<C.LevelingResult>("/v1/leveling", r),
};

export const api = {
  async health(): Promise<{ status: string; engine_version: string }> {
    const res = await request("/health");
    return res.json();
  },
  async me(workspaceId?: string | null): Promise<Me> {
    const res = await request(`/v1/me${workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : ""}`);
    return res.json();
  },
  async parse(file: File, opts: { angle_unit?: DisplayAngleUnit | null; format?: RawFormat | null } = {}): Promise<ParseResult> {
    const fd = new FormData();
    fd.append("file", file);
    if (opts.angle_unit) fd.append("angle_unit", opts.angle_unit);
    if (opts.format) fd.append("format", opts.format);
    const res = await request("/v1/parse", { method: "POST", body: fd });
    return res.json();
  },
  compute(input: ProjectInput, signal?: AbortSignal): Promise<ProjectResult> {
    return postJson<ProjectResult>("/v1/compute", input, signal);
  },
  async tolerancePresets(): Promise<TolerancePreset[]> {
    const res = await request("/v1/presets/tolerances");
    return res.json();
  },
  async suggestTraverses(input: ProjectInput): Promise<TraverseSpec[]> {
    const r = await postJson<{ suggestions: TraverseSpec[] }>("/v1/suggest-traverses", input);
    return r.suggestions;
  },
  async exportFile(req: ExportRequest): Promise<{ blob: Blob; filename: string }> {
    const res = await request("/v1/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    const ext = req.format === "shp" ? "zip" : req.format === "landxml" ? "xml" : req.format;
    return { blob: await res.blob(), filename: filenameFrom(res, `${req.project_name}.${ext}`) };
  },
};
