import { describe, expect, it } from "vitest";
import {
  angleToInput,
  degToDms,
  dmsToDeg,
  formatAngle,
  formatCc,
  formatMisclosure,
  fromRad,
  gridAzimuth,
  parseAngle,
  toRad,
  wrap2pi,
  wrapPi,
} from "./angles";

describe("conversions", () => {
  it("gon round-trip", () => {
    expect(fromRad(toRad(123.4567, "gon"), "gon")).toBeCloseTo(123.4567, 10);
    expect(toRad(200, "gon")).toBeCloseTo(Math.PI, 12);
  });
  it("deg round-trip", () => {
    expect(toRad(180, "deg")).toBeCloseTo(Math.PI, 12);
    expect(fromRad(Math.PI / 2, "deg")).toBeCloseTo(90, 12);
  });
  it("dms packing", () => {
    expect(dmsToDeg(123.453)).toBeCloseTo(123 + 45 / 60 + 30 / 3600, 9);
    expect(degToDms(123 + 45 / 60 + 30 / 3600)).toBeCloseTo(123.453, 9);
    expect(fromRad(toRad(10.3015, "dms"), "dms")).toBeCloseTo(10.3015, 8);
  });
  it("wrapping", () => {
    expect(wrap2pi(-0.1)).toBeCloseTo(2 * Math.PI - 0.1, 12);
    expect(wrap2pi(7)).toBeCloseTo(7 - 2 * Math.PI, 12);
    expect(wrapPi(Math.PI * 1.5)).toBeCloseTo(-Math.PI / 2, 12);
  });
});

describe("formatting", () => {
  it("gon", () => {
    expect(formatAngle(toRad(123.4567, "gon"), "gon")).toBe("123.4567g");
  });
  it("deg", () => {
    expect(formatAngle(toRad(12.5, "deg"), "deg")).toBe("12.50000°");
  });
  it("dms", () => {
    expect(formatAngle(toRad(123.453, "dms"), "dms")).toBe(`123°45'30.0"`);
    expect(formatAngle(toRad(59.9999999 / 1, "deg"), "dms")).toBe(`60°00'00.0"`);
  });
  it("null", () => {
    expect(formatAngle(null, "gon")).toBe("—");
  });
  it("cc", () => {
    expect(formatCc(toRad(0.0012, "gon"))).toBe("+12cc");
    expect(formatCc(toRad(-0.0005, "gon"))).toBe("-5cc");
    expect(formatMisclosure(toRad(10 / 3600, "deg"), "deg")).toBe(`+10.0"`);
  });
  it("input text", () => {
    expect(angleToInput(toRad(100, "gon"), "gon")).toBe("100.00000");
  });
});

describe("parsing", () => {
  it("gon with comma", () => {
    expect(parseAngle("100,5", "gon")).toBeCloseTo(toRad(100.5, "gon"), 12);
  });
  it("dms forms", () => {
    const expected = toRad(123 + 45 / 60 + 30 / 3600, "deg");
    expect(parseAngle("123.4530", "dms")).toBeCloseTo(expected, 10);
    expect(parseAngle(`123°45'30"`, "dms")).toBeCloseTo(expected, 10);
    expect(parseAngle("123 45 30", "dms")).toBeCloseTo(expected, 10);
  });
  it("invalid", () => {
    expect(parseAngle("abc", "gon")).toBeNull();
    expect(parseAngle("", "gon")).toBeNull();
  });
});

describe("azimuth", () => {
  it("cardinal directions incl. due north (dx=0)", () => {
    expect(gridAzimuth(0, 0, 0, 10)).toBeCloseTo(0, 12);
    expect(gridAzimuth(0, 0, 10, 0)).toBeCloseTo(Math.PI / 2, 12);
    expect(gridAzimuth(0, 0, 0, -10)).toBeCloseTo(Math.PI, 12);
    expect(gridAzimuth(0, 0, -10, 0)).toBeCloseTo(1.5 * Math.PI, 12);
  });
});
