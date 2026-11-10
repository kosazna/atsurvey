// TypeScript mirrors of engine/src/atsurvey/core/cogo_models.py (COGO + levelling).
// Angles in radians, lengths in metres, x = Easting, y = Northing.
import type { ReductionSettings } from "./types";

export interface XY {
  x: number;
  y: number;
  z?: number | null;
  name?: string | null;
}

export interface InverseRequest {
  a: XY;
  b: XY;
  reduction?: ReductionSettings | null;
}
export interface InverseResult {
  dx: number;
  dy: number;
  dz: number | null;
  distance: number;
  azimuth: number;
  azimuth_back: number;
  distance_ground?: number | null;
  slope_distance?: number | null;
  gradient_percent?: number | null;
}

export interface PolarRequest {
  station: XY;
  distance: number;
  azimuth?: number | null;
  backsight?: XY | null;
  angle?: number | null;
  dz?: number | null;
  name?: string | null;
}
export interface PolarResult {
  point: XY;
  azimuth: number;
}

export interface IntersectionAnglesRequest {
  a: XY;
  b: XY;
  angle_a: number;
  angle_b: number;
  name?: string | null;
}
export interface IntersectionDistancesRequest {
  a: XY;
  r_a: number;
  b: XY;
  r_b: number;
}
export interface IntersectionLinesRequest {
  p1: XY;
  p2: XY;
  p3: XY;
  p4: XY;
}
export interface IntersectionResult {
  solutions: XY[];
  message?: string | null;
}

export interface ResectionObservation {
  point: XY;
  direction: number;
  distance?: number | null;
}
export interface ResectionRequest {
  station_name?: string | null;
  observations: ResectionObservation[];
}
export interface ResectionResidual {
  name: string | null;
  direction_residual: number;
  distance_residual?: number | null;
}
export interface ResectionResult {
  station: XY;
  orientation: number;
  sigma0?: number | null;
  sx?: number | null;
  sy?: number | null;
  residuals: ResectionResidual[];
  danger_circle: boolean;
  method: string;
}

export interface AreaRequest {
  points: XY[];
  reduction?: ReductionSettings | null;
}
export interface AreaResult {
  area: number;
  perimeter: number;
  orientation: "clockwise" | "counterclockwise";
  centroid: XY;
  scale_factor_mean?: number | null;
  area_ellipsoid?: number | null;
}

export interface CommonPoint {
  name: string;
  src: XY;
  dst: XY;
  use: boolean;
}
export type TransformMethod = "helmert" | "affine";
export interface TransformRequest {
  method: TransformMethod;
  common: CommonPoint[];
  points: XY[];
}
export interface TransformResidual {
  name: string;
  vx: number;
  vy: number;
  v: number;
  used: boolean;
}
export interface TransformResult {
  method: TransformMethod;
  params: Record<string, number>;
  rms: number | null;
  residuals: TransformResidual[];
  points: XY[];
}

export interface OffsetRequest {
  a: XY;
  b: XY;
  points: XY[];
}
export interface OffsetRow {
  name: string | null;
  chainage: number;
  offset: number;
  foot: XY;
}
export interface OffsetResult {
  line_length: number;
  azimuth: number;
  rows: OffsetRow[];
}

// ------------------------------------------------------------------ levelling

export type ReadingKind = "bs" | "fs" | "is";
export interface LevelingReading {
  point: string;
  reading: number;
  kind: ReadingKind;
  distance?: number | null;
}
export interface LevelingSetup {
  readings: LevelingReading[];
}
export interface Benchmark {
  name: string;
  h: number;
}
export interface LevelingRequest {
  benchmarks: Benchmark[];
  setups: LevelingSetup[];
  tolerance_base_mm: number;
  tolerance_mm_per_sqrt_km: number;
  distribute: "distance" | "setups";
  return_setups?: LevelingSetup[] | null;
  section_points?: string[] | null;
}
export interface LevelingSection {
  frm: string;
  to: string;
  dh_forward: number;
  dh_return: number;
  discrepancy: number;
  dh_mean: number;
  length: number | null;
  tolerance: number | null;
  within_tolerance: boolean | null;
}
export interface LevelingPoint {
  name: string;
  h: number;
  h_unadjusted: number;
  correction: number;
  kind: "benchmark" | "turning" | "intermediate";
}
export interface LevelingRow {
  setup: number;
  backsight: string;
  foresight: string;
  dh: number;
  length: number | null;
}
export interface LevelingResult {
  points: LevelingPoint[];
  rows: LevelingRow[];
  start: string;
  end: string;
  misclosure: number | null;
  tolerance: number | null;
  within_tolerance: boolean | null;
  length_km: number | null;
  n_setups: number;
  message?: string | null;
  sections?: LevelingSection[];
}

// ------------------------------------------------------------------ stakeout

export interface StakeoutRequest {
  station: XY;
  backsight?: XY | null;
  backsight_azimuth?: number | null;
  instrument_height?: number;
  target_height?: number;
  points: XY[];
  reduction?: ReductionSettings | null;
}
export interface StakeoutRow {
  name: string | null;
  azimuth: number;
  angle: number;
  distance: number;
  distance_ground?: number | null;
  dz?: number | null;
  zenith?: number | null;
  slope_distance?: number | null;
}
export interface StakeoutResult {
  rows: StakeoutRow[];
}
