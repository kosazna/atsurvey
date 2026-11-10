// Client + types for the instruments feature: levelling network adjustment and instrument
// checks. Mirrors engine/src/atsurvey/core/{levelnet,instruments}.py (angles in radians).
import { postJson } from "./api";
import type { Issue } from "./types";

// ------------------------------------------------------------------ levelling network
export interface LevelNetBenchmark {
  name: string;
  h: number;
}

export interface LevelNetLine {
  frm: string;
  to: string;
  dh: number;
  length_km?: number | null;
  setups?: number | null;
}

export type LevelNetWeighting = "length" | "setups";
export type LevelNetDatum = "fixed" | "free";

export interface LevelNetRequest {
  benchmarks: LevelNetBenchmark[];
  lines: LevelNetLine[];
  weighting: LevelNetWeighting;
  sigma_mm_per_sqrt_km: number;
  sigma_mm_per_setup: number;
  datum: LevelNetDatum;
  free_points?: string[] | null;
  alpha_global?: number;
  alpha_w?: number;
  tolerance_base_mm: number;
  tolerance_mm_per_sqrt_km: number;
  tolerance_mm_per_sqrt_setup?: number | null;
}

export interface LevelNetPoint {
  name: string;
  h: number;
  sigma_h: number;
  kind: "fixed" | "adjusted";
  known_h: number | null;
  known_diff: number | null;
}

export interface LevelNetLineResult {
  index: number;
  frm: string;
  to: string;
  dh: number;
  dh_adjusted: number;
  residual: number;
  sigma: number;
  redundancy: number;
  w: number | null;
  mdb: number | null;
  flagged: boolean;
}

export interface LevelNetLoop {
  kind: "loop" | "connection";
  points: string[];
  lines: number[];
  signs: number[];
  misclosure: number;
  length_km: number | null;
  setups: number | null;
  tolerance: number | null;
  within_tolerance: boolean | null;
}

export interface GlobalTest {
  statistic: number;
  lower: number;
  upper: number;
  passed: boolean;
}

export interface LevelNetResult {
  datum: LevelNetDatum;
  points: LevelNetPoint[];
  lines: LevelNetLineResult[];
  loops: LevelNetLoop[];
  n_observations: number;
  n_unknowns: number;
  dof: number;
  sigma0: number | null;
  variance_factor: number;
  global_test: GlobalTest | null;
  w_critical: number;
  suspect_line: number | null;
  excluded_points: string[];
  issues: Issue[];
}

// ------------------------------------------------------------------ two-face test
export interface TwoFaceTarget {
  name: string;
  hz1: number;
  hz2: number;
  v1: number;
  v2: number;
}

export interface TwoFaceRequest {
  targets: TwoFaceTarget[];
  trunnion: "auto" | "always" | "never";
}

export interface TwoFaceRow {
  name: string;
  zenith: number;
  hz: number;
  delta: number;
  index: number;
  residual_hz: number;
  residual_v: number;
}

export interface TwoFaceResult {
  collimation: number;
  sigma_collimation: number | null;
  trunnion: number | null;
  sigma_trunnion: number | null;
  index: number;
  sigma_index: number | null;
  s0_hz: number | null;
  s0_v: number | null;
  dof_hz: number;
  dof_v: number;
  trunnion_estimated: boolean;
  rows: TwoFaceRow[];
  issues: Issue[];
}

// ------------------------------------------------------------------ two-peg test
export type PegMethod = "forstner" | "kukkamaki" | "middle_end" | "custom";

export interface PegSetup {
  a: number;
  b: number;
  dist_a: number;
  dist_b: number;
}

export interface TwoPegRequest {
  method: PegMethod;
  setup1: PegSetup;
  setup2: PegSetup;
  tolerance_mm_per_30m: number;
}

export interface TwoPegResult {
  epsilon: number;
  angle: number;
  error_mm_per_30m: number;
  error_arcsec: number;
  error_cc: number;
  dh_true: number;
  dh_setup1: number;
  dh_setup2: number;
  corrected_a2: number;
  corrected_b2: number;
  tolerance_mm_per_30m: number;
  within_tolerance: boolean;
}

/** Sight lengths (m) of the two setups for each method: [A1, B1, A2, B2]. */
export const PEG_LAYOUTS: Record<Exclude<PegMethod, "custom">, [number, number, number, number]> = {
  // Förstner: A–B 45 m, instrument 15 m from A, then 15 m from B
  forstner: [15, 30, 30, 15],
  // Kukkamäki: A–B 20 m, instrument in the middle, then 20 m beyond B on the line
  kukkamaki: [10, 10, 40, 20],
  // middle and end: A–B 30 m, instrument in the middle, then ~3 m behind B
  middle_end: [15, 15, 33, 3],
};

// ------------------------------------------------------------------ EDM constant
export interface EdmObservation {
  frm: string;
  to: string;
  distance: number;
}

export interface EdmRequest {
  pillars: string[];
  observations: EdmObservation[];
  positions?: number[] | null;
}

export interface EdmRow {
  frm: string;
  to: string;
  distance: number;
  adjusted: number;
  residual: number;
}

export interface EdmResult {
  constant: number;
  sigma_constant: number | null;
  scale_ppm: number | null;
  sigma_scale_ppm: number | null;
  s0: number | null;
  dof: number;
  positions: number[];
  sigma_positions: (number | null)[];
  rows: EdmRow[];
  issues: Issue[];
}

export const instrumentsApi = {
  levelNetwork: (r: LevelNetRequest) => postJson<LevelNetResult>("/v1/leveling/network", r),
  twoFace: (r: TwoFaceRequest) => postJson<TwoFaceResult>("/v1/instruments/two-face", r),
  twoPeg: (r: TwoPegRequest) => postJson<TwoPegResult>("/v1/instruments/two-peg", r),
  edmConstant: (r: EdmRequest) => postJson<EdmResult>("/v1/instruments/edm-constant", r),
};

/** Every pair of pillars (i < j): the observation plan of a baseline calibration. */
export function pillarPairs(pillars: string[]): [string, string][] {
  const out: [string, string][] = [];
  pillars.forEach((a, i) => pillars.slice(i + 1).forEach((b) => out.push([a, b])));
  return out;
}
