// Content type for an uploaded instrument file. The raw-files bucket accepts only these types
// (supabase/migrations/20261111000002_isolation.sql); browsers report survey extensions
// inconsistently (often empty, CSV as "application/vnd.ms-excel"), so the type is set from the
// extension and never from the browser.

export type RawFileContentType =
  | "application/xml"
  | "text/csv"
  | "application/dxf"
  | "text/plain"
  | "application/octet-stream";

const BY_EXTENSION: Record<string, RawFileContentType> = {
  xml: "application/xml",
  jxl: "application/xml",
  landxml: "application/xml",
  csv: "text/csv",
  dxf: "application/dxf",
  gsi: "text/plain",
  raw: "text/plain",
  rw5: "text/plain",
  txt: "text/plain",
  gt7: "text/plain",
};

export function rawFileContentType(filename: string): RawFileContentType {
  const dot = filename.lastIndexOf(".");
  const ext = dot >= 0 ? filename.slice(dot + 1).toLowerCase() : "";
  return BY_EXTENSION[ext] ?? "application/octet-stream";
}
