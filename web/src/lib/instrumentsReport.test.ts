import { describe, expect, it } from "vitest";
import { pillarPairs } from "./instrumentsApi";
import { emptyMeta, escapeHtml, type Report, reportCsv, reportHtml } from "./instrumentsReport";

const REPORT: Report = {
  title: "Έλεγχος <χωροβάτη>",
  metaLabels: { model: "Μοντέλο", serial: "Σειριακός", operator: "Χειριστής", date: "Ημερομηνία" },
  meta: { model: 'Leica "NA2"', serial: "123;45", operator: "<script>x</script>", date: "2026-11-10" },
  summary: [["ε", "+2.0 mm / 30 m"]],
  tables: [{ title: "Αναγνώσεις", headers: ["Στάση", "A", "B"], rows: [["1", "1.5230", "1.2110"]] }],
  notes: ["Förstner"],
};

describe("instrument reports", () => {
  it("escapes user text in the printable HTML", () => {
    const html = reportHtml(REPORT);
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("Leica &quot;NA2&quot;");
    expect(html).toContain("<td>1.5230</td>");
    expect(escapeHtml(`a&b'`)).toBe("a&amp;b&#39;");
  });

  it("writes CSV blocks with quoting and a BOM", () => {
    const csv = reportCsv(REPORT);
    expect(csv.startsWith("﻿Έλεγχος <χωροβάτη>\r\n")).toBe(true);
    expect(csv).toContain('Μοντέλο;"Leica ""NA2"""');
    expect(csv).toContain('Σειριακός;"123;45"');
    expect(csv).toContain("\r\n\r\nΑναγνώσεις\r\nΣτάση;A;B\r\n1;1.5230;1.2110\r\n");
  });

  it("defaults the date to today", () => {
    expect(emptyMeta(new Date("2026-03-04T10:00:00Z")).date).toBe("2026-03-04");
  });

  it("lists every pillar combination once", () => {
    expect(pillarPairs(["P0", "P1", "P2", "P3"])).toHaveLength(6);
    expect(pillarPairs(["A", "B", "C"])).toEqual([
      ["A", "B"],
      ["A", "C"],
      ["B", "C"],
    ]);
  });
});
