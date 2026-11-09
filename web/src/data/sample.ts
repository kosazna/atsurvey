// Deterministic demo dataset: an EGSA87 link traverse near Athens with detail points.
//
// "True" coordinates are defined first; observations are then synthesised with the same
// reduction model the engine uses (grid → ground distance via EGSA87 Simpson line scale
// and elevation factor, heights with curvature & refraction), plus small seeded noise
// (±4cc directions, ±2mm distances) so the traverse closes with a realistic misclosure.
import { CC, gridAzimuth, wrap2pi } from "@/lib/angles";
import { defaultSettings } from "@/lib/types";
import type { ProjectData, StoredControlPoint, StoredObservation, StoredSetup, StoredTraverse } from "./store";

const R = 6371000;
const KAPPA = 0.13;

export function egsa87PointScale(e: number): number {
  const d = (e - 500000) / 1e6;
  return 0.9996 + 0.012311 * d * d;
}

export function egsa87LineScale(e1: number, e2: number): number {
  return (egsa87PointScale(e1) + 4 * egsa87PointScale((e1 + e2) / 2) + egsa87PointScale(e2)) / 6;
}

/** Seeded PRNG (mulberry32) */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type P = { x: number; y: number; z: number; code?: string };

export const SAMPLE_KNOWN: Record<string, P> = {
  T1: { x: 476120.0, y: 4205380.0, z: 152.3 },
  T2: { x: 476300.0, y: 4205250.0, z: 148.75 },
  T3: { x: 476950.0, y: 4205330.0, z: 139.2 },
  T4: { x: 477110.0, y: 4205520.0, z: 141.05 },
};

export const SAMPLE_TRUE_STATIONS: Record<string, P> = {
  S1: { x: 476458.317, y: 4205121.644, z: 145.118 },
  S2: { x: 476641.902, y: 4205183.207, z: 141.863 },
  S3: { x: 476802.455, y: 4205262.981, z: 140.097 },
};

export const SAMPLE_ROUTE = ["T1", "T2", "S1", "S2", "S3", "T3", "T4"];

// detail points: [name, station, code, dx, dy, dz] relative to station
const DETAIL: [string, string, string, number, number, number][] = [
  ["1", "S1", "OIK", 18.4, 22.1, 0.35],
  ["2", "S1", "OIK", 31.2, 19.8, 0.4],
  ["3", "S1", "OIK", 29.7, 4.6, 0.31],
  ["4", "S1", "OIK", 16.9, 6.8, 0.28],
  ["5", "S1", "FRAX", -12.5, 35.4, 0.8],
  ["6", "S2", "FRAX", 8.6, 41.2, 1.1],
  ["7", "S2", "DROM", -20.3, -14.9, -0.42],
  ["8", "S2", "DROM", 15.8, -18.7, -0.55],
  ["9", "S2", "DEN", 27.4, 12.2, 0.15],
  ["10", "S2", "DEN", -9.6, 24.8, 0.6],
  ["11", "S3", "DROM", -35.1, -12.6, -0.2],
  ["12", "S3", "DROM", 22.7, -9.4, -0.12],
  ["13", "S3", "FRAX", 40.2, 28.9, 0.45],
  ["14", "S3", "OIK", -6.3, 33.7, 0.9],
  ["15", "S3", "OIK", 12.8, 37.5, 0.95],
];

export function sampleTruePoints(): Record<string, P> {
  const pts: Record<string, P> = { ...SAMPLE_KNOWN, ...SAMPLE_TRUE_STATIONS };
  for (const [name, st, code, dx, dy, dz] of DETAIL) {
    const s = pts[st];
    pts[name] = { x: s.x + dx, y: s.y + dy, z: s.z + dz, code };
  }
  return pts;
}

/** Synthesize an observation of `to` from `from` (face I), ground values. */
function synth(from: P, to: P, hi: number, ht: number) {
  const dGrid = Math.hypot(to.x - from.x, to.y - from.y);
  const k = egsa87LineScale(from.x, to.x);
  const hm = (from.z + to.z) / 2;
  const ef = R / (R + hm);
  const hd = dGrid / (k * ef);
  const cr = ((1 - KAPPA) * hd * hd) / (2 * R);
  const vert = to.z - from.z - hi + ht - cr; // = SD cos z
  const sd = Math.hypot(hd, vert);
  const zen = Math.atan2(hd, vert);
  return { az: gridAzimuth(from.x, from.y, to.x, to.y), sd, zen };
}

export function buildSampleProject(): Omit<ProjectData, "meta"> {
  const rand = rng(20261109);
  const noise = (amp: number) => (rand() * 2 - 1) * amp;
  const pts = sampleTruePoints();
  const hi = 1.55;
  const ht = 1.6;
  const id = (p: string) => `sample-${p}`;

  const traverseNeighbors: Record<string, string[]> = {
    T2: ["T1", "S1"],
    S1: ["T2", "S2"],
    S2: ["S1", "S3"],
    S3: ["S2", "T3"],
    T3: ["S3", "T4"],
  };

  const setups: StoredSetup[] = [];
  let setupIdx = 0;
  for (const [station, targets] of Object.entries(traverseNeighbors)) {
    setupIdx += 1;
    const from = pts[station];
    // circle orientation: backsight reads a small arbitrary value
    const bsAz = gridAzimuth(from.x, from.y, pts[targets[0]].x, pts[targets[0]].y);
    const zeroOffset = wrap2pi(bsAz - (0.0123 + setupIdx * 0.0007) * (Math.PI / 200));
    const obs: StoredObservation[] = [];
    let n = 0;
    const add = (o: Omit<StoredObservation, "id">) => {
      n += 1;
      obs.push({ id: id(`${station}-${n}`), ...o });
    };
    for (const face of [1, 2] as const) {
      for (const t of targets) {
        const m = synth(from, pts[t], hi, ht);
        const hz = wrap2pi(m.az - zeroOffset + noise(4 * CC) + (face === 2 ? Math.PI : 0));
        const zen = m.zen + noise(6 * CC);
        add({
          target: t,
          hz,
          v: face === 1 ? zen : 2 * Math.PI - zen,
          sd: m.sd + noise(0.002),
          target_height: ht,
          code: null,
          excluded: false,
        });
      }
    }
    for (const [name, st, code] of DETAIL) {
      if (st !== station) continue;
      const m = synth(from, pts[name], hi, 1.8);
      add({
        target: name,
        hz: wrap2pi(m.az - zeroOffset + noise(8 * CC)),
        v: m.zen + noise(10 * CC),
        sd: m.sd + noise(0.003),
        target_height: 1.8,
        code,
        excluded: false,
      });
    }
    setups.push({
      id: id(`setup-${station}`),
      station,
      instrument_height: hi,
      backsight: targets[0],
      observations: obs,
    });
  }

  const control_points: StoredControlPoint[] = Object.entries(SAMPLE_KNOWN).map(([name, p]) => ({
    id: id(`cp-${name}`),
    name,
    x: p.x,
    y: p.y,
    z: p.z,
    code: "TRIG",
  }));

  const traverses: StoredTraverse[] = [
    { id: id("trav-1"), name: "Όδευση Τ2–Τ3", route: [...SAMPLE_ROUTE], kind: "auto", end_orientation: null, enabled: true },
  ];

  return { settings: defaultSettings(), control_points, setups, traverses };
}
