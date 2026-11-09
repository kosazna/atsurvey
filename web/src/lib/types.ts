// TypeScript mirrors of engine/src/atsurvey/core/models.py and docs/contracts.md.
// Field names are kept identical (snake_case). Angles are radians, lengths metres.

export type AngleUnit = "gon" | "deg" | "dms" | "rad";
export type DisplayAngleUnit = Exclude<AngleUnit, "rad">;
export type PointKind = "control" | "traverse" | "detail";
export type Severity = "error" | "warning" | "info";

// ---------------------------------------------------------------- inputs

export interface ControlPoint {
  name: string;
  x: number;
  y: number;
  z?: number | null;
  code?: string | null;
}

export interface Observation {
  target: string;
  /** Horizontal circle reading, radians */
  hz: number;
  /** Zenith angle, radians */
  v?: number | null;
  /** Slope distance, metres */
  sd?: number | null;
  target_height?: number;
  code?: string | null;
  excluded?: boolean;
  id?: string | null;
}

export interface Setup {
  station: string;
  instrument_height?: number;
  observations: Observation[];
  backsight?: string | null;
  id?: string | null;
}

export type TraverseKind = "auto" | "open" | "link" | "closed";

export interface TraverseSpec {
  route: string[];
  kind?: TraverseKind;
  end_orientation?: boolean | null;
  name?: string | null;
  id?: string | null;
  enabled?: boolean;
}

export type ScaleMode = "leg_simpson" | "leg_mean" | "traverse_mean" | "none" | "fixed";
export type ElevationMode = "leg" | "traverse";

export interface ReductionSettings {
  scale_mode: ScaleMode;
  fixed_scale: number;
  elevation_reduction: boolean;
  elevation_mode: ElevationMode;
  geoid_undulation: number;
  default_elevation: number;
  curvature_refraction: boolean;
  refraction_coefficient: number;
  earth_radius: number;
}

export interface Tolerances {
  angular_base_cc: number;
  angular_per_sqrt_n_cc: number;
  linear_base_m: number;
  linear_per_sqrt_km_m: number;
  min_relative_precision: number;
  height_base_m: number;
  height_per_sqrt_km_m: number;
  round_spread_cc: number;
  leg_distance_fb_m: number;
  leg_height_fb_m: number;
  orientation_spread_cc: number;
  detail_duplicate_m: number;
  check_shot_m: number;
}

export type AdjustmentMethod = "bowditch" | "least_squares";

export interface AdjustmentSettings {
  method: AdjustmentMethod;
  sigma_direction_cc: number;
  sigma_distance_mm: number;
  sigma_distance_ppm: number;
  sigma_centering_mm: number;
  sigma_height_mm: number;
  alpha_global: number;
  alpha_w: number;
  max_iterations: number;
}

export interface LineworkSettings {
  line_codes: string[];
  start_tokens: string[];
  close_tokens: string[];
  end_tokens: string[];
  case_sensitive: boolean;
}

export interface ComputeSettings {
  reduction: ReductionSettings;
  tolerances: Tolerances;
  adjustment: AdjustmentSettings;
  linework: LineworkSettings;
  compute_detail: boolean;
}

export interface ProjectInput {
  control_points: ControlPoint[];
  setups: Setup[];
  traverses: TraverseSpec[];
  settings: ComputeSettings;
}

export const DEFAULT_REDUCTION: ReductionSettings = {
  scale_mode: "leg_simpson",
  fixed_scale: 1.0,
  elevation_reduction: true,
  elevation_mode: "leg",
  geoid_undulation: 0.0,
  default_elevation: 0.0,
  curvature_refraction: true,
  refraction_coefficient: 0.13,
  earth_radius: 6371000.0,
};

export const DEFAULT_TOLERANCES: Tolerances = {
  angular_base_cc: 0.0,
  angular_per_sqrt_n_cc: 40.0,
  linear_base_m: 0.02,
  linear_per_sqrt_km_m: 0.05,
  min_relative_precision: 5000.0,
  height_base_m: 0.02,
  height_per_sqrt_km_m: 0.05,
  round_spread_cc: 50.0,
  leg_distance_fb_m: 0.02,
  leg_height_fb_m: 0.03,
  orientation_spread_cc: 60.0,
  detail_duplicate_m: 0.03,
  check_shot_m: 0.03,
};

export const DEFAULT_ADJUSTMENT: AdjustmentSettings = {
  method: "bowditch",
  sigma_direction_cc: 10.0,
  sigma_distance_mm: 2.0,
  sigma_distance_ppm: 2.0,
  sigma_centering_mm: 1.0,
  sigma_height_mm: 5.0,
  alpha_global: 0.05,
  alpha_w: 0.001,
  max_iterations: 10,
};

export const DEFAULT_LINEWORK: LineworkSettings = {
  line_codes: [],
  start_tokens: ["ST", "B", "ΑΡΧ"],
  close_tokens: ["CL", "C", "ΚΛ"],
  end_tokens: ["E", "END", "ΤΕΛ"],
  case_sensitive: false,
};

export function defaultSettings(): ComputeSettings {
  return {
    reduction: { ...DEFAULT_REDUCTION },
    tolerances: { ...DEFAULT_TOLERANCES },
    adjustment: { ...DEFAULT_ADJUSTMENT },
    linework: { ...DEFAULT_LINEWORK, line_codes: [], start_tokens: [...DEFAULT_LINEWORK.start_tokens], close_tokens: [...DEFAULT_LINEWORK.close_tokens], end_tokens: [...DEFAULT_LINEWORK.end_tokens] },
    compute_detail: true,
  };
}

/** Merge partially stored settings (e.g. from DB jsonb) with defaults. */
export function normalizeSettings(s: Partial<ComputeSettings> | null | undefined): ComputeSettings {
  const d = defaultSettings();
  if (!s) return d;
  return {
    reduction: { ...d.reduction, ...(s.reduction ?? {}) },
    tolerances: { ...d.tolerances, ...(s.tolerances ?? {}) },
    adjustment: { ...d.adjustment, ...(s.adjustment ?? {}) },
    linework: { ...d.linework, ...(s.linework ?? {}) },
    compute_detail: s.compute_detail ?? d.compute_detail,
  };
}

// ---------------------------------------------------------------- outputs

export interface Issue {
  severity: Severity;
  code: string;
  message: string;
  params: Record<string, unknown>;
  traverse?: string | null;
  setup?: string | null;
}

export interface ResultPoint {
  name: string;
  x: number;
  y: number;
  z: number | null;
  kind: PointKind;
  code?: string | null;
  source?: string | null;
  n: number;
  sx?: number | null;
  sy?: number | null;
  sz?: number | null;
  ellipse?: ErrorEllipse | null;
}

export interface ErrorEllipse {
  /** semi-major axis, m (1σ) */
  a: number;
  b: number;
  /** azimuth of the major axis, rad */
  theta: number;
  /** scale factor for a 95 % ellipse */
  k95: number;
}

export type ObservationKind = "direction" | "distance" | "height";

export interface AdjustedObservation {
  kind: ObservationKind;
  station: string;
  target: string;
  observed: number;
  adjusted: number;
  residual: number;
  sigma: number;
  redundancy: number;
  w: number | null;
  flagged: boolean;
}

export interface GlobalTest {
  statistic: number;
  lower: number;
  upper: number;
  passed: boolean;
}

export interface AdjustmentResult {
  method: "least_squares";
  converged: boolean;
  iterations: number;
  n_observations: number;
  n_unknowns: number;
  dof: number;
  sigma0: number;
  global_test: GlobalTest | null;
  w_critical: number;
  max_w: number | null;
  suspect: AdjustedObservation | null;
  observations: AdjustedObservation[];
}

export interface Polyline {
  code: string;
  name: string;
  points: string[];
  closed: boolean;
  length: number;
  area: number | null;
}

export interface TraverseStation {
  station: string;
  backsight: string;
  foresight: string;
  angle_measured: number;
  angle_correction: number;
  angle_corrected: number;
  azimuth: number;
  x: number;
  y: number;
  z: number | null;
  known: boolean;
}

export interface TraverseLeg {
  frm: string;
  to: string;
  hd_measured: number;
  n_measurements: number;
  distance_fb_diff: number | null;
  reduction_scale: number;
  elevation_factor: number;
  distance_grid: number;
  azimuth: number;
  dx: number;
  dy: number;
  corr_x: number;
  corr_y: number;
  dh: number | null;
  height_fb_diff: number | null;
  corr_h: number;
}

export interface TraverseResult {
  id: string | null;
  name: string;
  kind: "open" | "link" | "closed";
  end_orientation: boolean;
  route: string[];
  status: "ok" | "warning" | "failed";
  n_angles: number;
  length: number;
  angular_misclosure: number | null;
  angular_tolerance: number | null;
  wx: number | null;
  wy: number | null;
  linear_misclosure: number | null;
  linear_tolerance: number | null;
  relative_precision: number | null;
  wz: number | null;
  height_tolerance: number | null;
  within_tolerance: boolean | null;
  stations: TraverseStation[];
  legs: TraverseLeg[];
  new_points: string[];
}

export interface DetailShot {
  station: string;
  target: string;
  direction: number;
  zenith: number | null;
  sd: number | null;
  hd: number | null;
  distance_grid: number | null;
  azimuth: number;
  x: number | null;
  y: number | null;
  z: number | null;
  code: string | null;
  check: boolean;
  residual: number | null;
}

export interface SetupOrientation {
  station: string;
  setup: string | null;
  orientation: number | null;
  references: string[];
  spread: number | null;
}

export interface Summary {
  n_control: number;
  n_traverse_points: number;
  n_detail_points: number;
  n_traverses: number;
  n_traverses_ok: number;
  n_errors: number;
  n_warnings: number;
  extent: [number, number, number, number] | null;
}

export interface ProjectResult {
  engine_version: string;
  input_hash: string;
  points: ResultPoint[];
  traverses: TraverseResult[];
  detail: DetailShot[];
  orientations: SetupOrientation[];
  issues: Issue[];
  summary: Summary;
  adjustment?: AdjustmentResult | null;
  linework?: Polyline[];
}

// ---------------------------------------------------------------- API envelopes

export type RawFormat = "leica_gsi" | "trimble_jobxml" | "landxml" | "nikon_raw" | "rw5" | "csv" | "dxf";

export interface ParseResult {
  format: RawFormat;
  angle_unit: DisplayAngleUnit | null;
  setups: Setup[];
  control_points: ControlPoint[];
  warnings: string[];
  stats: { setups: number; observations: number; control_points?: number };
}

export type ExportFormat = "csv" | "xlsx" | "shp" | "dxf" | "pdf" | "landxml" | "kml" | "geojson";

export interface ExportOptions {
  angle_unit?: DisplayAngleUnit;
  decimals?: number;
  csv_delimiter?: string;
  csv_header?: boolean;
  include?: PointKind[];
  dxf_text_height?: number;
  /** exaggeration of 95 % error ellipses in DXF (0 = omit) */
  dxf_ellipse_scale?: number;
  language?: "el" | "en";
}

export interface ExportRequest {
  format: ExportFormat;
  project_name: string;
  input: ProjectInput;
  options: ExportOptions;
  workspace_id?: string | null;
}

export interface Me {
  user_id: string | null;
  plan: "anonymous" | "free" | "pro";
  export_formats: ExportFormat[];
}

export const ALL_EXPORT_FORMATS: ExportFormat[] = ["csv", "xlsx", "shp", "dxf", "pdf", "landxml", "kml", "geojson"];
