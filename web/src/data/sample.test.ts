// Independent check that the synthetic demo dataset is geometrically consistent:
// a minimal Bowditch traverse computed from the observations must close within a few
// mm / cc and reproduce the true station coordinates.
import { describe, expect, it } from "vitest";
import { CC, gridAzimuth, wrap2pi, wrapPi } from "@/lib/angles";
import { buildSampleProject, egsa87LineScale, SAMPLE_KNOWN, SAMPLE_ROUTE, SAMPLE_TRUE_STATIONS } from "./sample";
import type { StoredSetup } from "./store";

const R = 6371000;

function reduced(setup: StoredSetup, target: string) {
  const obs = setup.observations.filter((o) => o.target === target);
  const dirs: number[] = [];
  const hds: number[] = [];
  for (const o of obs) {
    let hz = o.hz;
    let v = o.v!;
    if (v > Math.PI) {
      hz = wrap2pi(hz - Math.PI);
      v = 2 * Math.PI - v;
    }
    dirs.push(hz);
    hds.push(o.sd! * Math.sin(v));
  }
  const ref = dirs[0];
  const dir = wrap2pi(ref + dirs.reduce((s, d) => s + wrapPi(d - ref), 0) / dirs.length);
  return { dir, hd: hds.reduce((a, b) => a + b, 0) / hds.length };
}

describe("sample dataset", () => {
  const data = buildSampleProject();
  const byStation = new Map(data.setups.map((s) => [s.station, s]));

  it("has expected structure", () => {
    expect(data.control_points).toHaveLength(4);
    expect(data.setups).toHaveLength(5);
    const detail = data.setups.flatMap((s) => s.observations).filter((o) => /^\d+$/.test(o.target));
    expect(detail.length).toBe(15);
    expect(data.traverses[0].route).toEqual(SAMPLE_ROUTE);
  });

  it("is deterministic", () => {
    const again = buildSampleProject();
    expect(again.setups[2].observations[3].hz).toBe(data.setups[2].observations[3].hz);
  });

  it("closes as a link traverse within realistic tolerance", () => {
    const known: Record<string, { x: number; y: number }> = { ...SAMPLE_KNOWN };
    const route = SAMPLE_ROUTE;
    let az = gridAzimuth(known.T1.x, known.T1.y, known.T2.x, known.T2.y);
    const azs: number[] = [];
    for (let i = 1; i < route.length - 1; i++) {
      const s = byStation.get(route[i])!;
      const beta = wrap2pi(reduced(s, route[i + 1]).dir - reduced(s, route[i - 1]).dir);
      az = wrap2pi(az + beta + Math.PI);
      azs.push(az);
    }
    const azEnd = gridAzimuth(known.T3.x, known.T3.y, known.T4.x, known.T4.y);
    const wAng = wrapPi(azEnd - az);
    expect(Math.abs(wAng) / CC).toBeLessThan(25);
    expect(Math.abs(wAng) / CC).toBeGreaterThan(0.01); // noise is present

    const corr = wAng / azs.length;
    let x = known.T2.x;
    let y = known.T2.y;
    const zs = { ...SAMPLE_KNOWN, ...SAMPLE_TRUE_STATIONS };
    const legs: { dx: number; dy: number; d: number }[] = [];
    for (let i = 1; i < route.length - 2; i++) {
      const a = route[i];
      const b = route[i + 1];
      const fwd = reduced(byStation.get(a)!, b).hd;
      const bwd = reduced(byStation.get(b)!, a).hd;
      const hd = (fwd + bwd) / 2;
      const hm = (zs[a].z + zs[b].z) / 2;
      const d = hd * (R / (R + hm)) * egsa87LineScale(zs[a].x, zs[b].x);
      const azc = azs[i - 1] + corr * i;
      legs.push({ dx: d * Math.sin(azc), dy: d * Math.cos(azc), d });
    }
    const sx = legs.reduce((s, l) => s + l.dx, 0);
    const sy = legs.reduce((s, l) => s + l.dy, 0);
    const wx = known.T3.x - (x + sx);
    const wy = known.T3.y - (y + sy);
    const w = Math.hypot(wx, wy);
    expect(w).toBeLessThan(0.02);
    const L = legs.reduce((s, l) => s + l.d, 0);
    // Bowditch and compare stations to truth
    for (let i = 0; i < legs.length - 1; i++) {
      x += legs[i].dx + (wx * legs[i].d) / L;
      y += legs[i].dy + (wy * legs[i].d) / L;
      const truth = SAMPLE_TRUE_STATIONS[route[i + 2]];
      expect(Math.hypot(x - truth.x, y - truth.y)).toBeLessThan(0.015);
    }
  });
});

describe("sample ids", () => {
  it("are UUIDs (Supabase stores them in uuid columns)", () => {
    const d = buildSampleProject();
    const ids = [
      ...d.control_points.map((c) => c.id),
      ...d.setups.flatMap((s) => [s.id, ...s.observations.map((o) => o.id)]),
      ...d.traverses.map((t) => t.id),
    ];
    for (const id of ids) expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
