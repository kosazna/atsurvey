// Printable (HTML) and CSV reports for instrument checks. Built client-side: the instrument
// model/serial/operator never leave the browser. Pure string builders (tested) + a print helper.

export interface ReportMeta {
  model: string;
  serial: string;
  operator: string;
  date: string;
}

export interface ReportTable {
  title: string;
  headers: string[];
  rows: string[][];
}

export interface Report {
  title: string;
  /** Labels for the meta fields (translated) */
  metaLabels: Record<keyof ReportMeta, string>;
  meta: ReportMeta;
  summary: [string, string][];
  tables: ReportTable[];
  notes?: string[];
}

export function emptyMeta(today = new Date()): ReportMeta {
  return { model: "", serial: "", operator: "", date: today.toISOString().slice(0, 10) };
}

const HTML_ESCAPES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => HTML_ESCAPES[c]);
}

function metaRows(r: Report): [string, string][] {
  return (Object.keys(r.metaLabels) as (keyof ReportMeta)[]).map((k) => [r.metaLabels[k], r.meta[k]]);
}

/** Self-contained HTML document (no scripts) for printing or saving as PDF. */
export function reportHtml(r: Report): string {
  const e = escapeHtml;
  const kv = (rows: [string, string][]) =>
    `<table class="kv">${rows.map(([k, v]) => `<tr><th>${e(k)}</th><td>${e(v)}</td></tr>`).join("")}</table>`;
  const tables = r.tables
    .map(
      (t) =>
        `<h2>${e(t.title)}</h2><table class="grid"><thead><tr>${t.headers.map((h) => `<th>${e(h)}</th>`).join("")}</tr></thead>` +
        `<tbody>${t.rows.map((row) => `<tr>${row.map((c) => `<td>${e(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`,
    )
    .join("");
  const notes = (r.notes ?? []).map((n) => `<p class="note">${e(n)}</p>`).join("");
  return `<!doctype html><html lang="el"><head><meta charset="utf-8"><title>${e(r.title)}</title>
<style>
body{font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:11pt;margin:18mm;color:CanvasText;background:Canvas}
h1{font-size:16pt;margin:0 0 8pt}h2{font-size:12pt;margin:14pt 0 6pt}
table{border-collapse:collapse;font-variant-numeric:tabular-nums}
.kv th{text-align:left;font-weight:500;padding:2pt 14pt 2pt 0;opacity:.7}.kv td{padding:2pt 0}
.grid{width:100%}.grid th,.grid td{border:0.5pt solid GrayText;padding:3pt 6pt;text-align:right}
.grid th:first-child,.grid td:first-child{text-align:left}.note{font-size:9pt;opacity:.75}
</style></head><body><h1>${e(r.title)}</h1>${kv(metaRows(r))}<h2>&nbsp;</h2>${kv(r.summary)}${tables}${notes}</body></html>`;
}

function csvCell(v: string, sep: string): string {
  return /["\r\n]/.test(v) || v.includes(sep) ? `"${v.replace(/"/g, '""')}"` : v;
}

/** CSV with a UTF-8 BOM (Excel): meta, summary and every table, separated by blank lines. */
export function reportCsv(r: Report, sep = ";"): string {
  const line = (cells: string[]) => cells.map((c) => csvCell(c, sep)).join(sep);
  const blocks = [
    [line([r.title]), ...metaRows(r).map(line)],
    r.summary.map(line),
    ...r.tables.map((t) => [line([t.title]), line(t.headers), ...t.rows.map(line)]),
  ];
  return "﻿" + blocks.map((b) => b.join("\r\n")).join("\r\n\r\n") + "\r\n";
}

/** Open the report in a new window and start printing. Returns false if pop-ups are blocked. */
export function printReport(r: Report): boolean {
  const w = window.open("", "_blank");
  if (!w) return false;
  w.document.open();
  w.document.write(reportHtml(r));
  w.document.close();
  w.focus();
  w.print();
  return true;
}
