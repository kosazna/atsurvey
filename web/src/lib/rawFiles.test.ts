import { describe, expect, it } from "vitest";
import { rawFileContentType } from "./rawFiles";

describe("rawFileContentType", () => {
  it("maps survey extensions to the bucket's allowed types", () => {
    expect(rawFileContentType("job.JXL")).toBe("application/xml");
    expect(rawFileContentType("survey.landxml")).toBe("application/xml");
    expect(rawFileContentType("points.csv")).toBe("text/csv");
    expect(rawFileContentType("plan.dxf")).toBe("application/dxf");
    expect(rawFileContentType("leica.gsi")).toBe("text/plain");
    expect(rawFileContentType("carlson.rw5")).toBe("text/plain");
  });

  it("falls back to octet-stream, never to a type a browser would render", () => {
    expect(rawFileContentType("page.html")).toBe("application/octet-stream");
    expect(rawFileContentType("image.svg")).toBe("application/octet-stream");
    expect(rawFileContentType("noextension")).toBe("application/octet-stream");
  });
});
