// ATSurvey computation report.
// Data (pre-formatted strings) arrives as JSON in sys.inputs.data, colours and fonts in
// sys.inputs.theme (generated from design/tokens.json). Keep the layout minimal: hairlines,
// whitespace and one accent colour.
#let d = json(bytes(sys.inputs.data))
#let th = json(bytes(sys.inputs.theme))
#let t = d.labels
#let c(name) = rgb(th.color.at(name))

#let ink = c("text")
#let muted = c("text-muted")
#let subtle = c("text-subtle")
#let hair = c("border")
#let sunken = c("surface-sunken")
#let accent = c("accent")

#set document(title: d.project + " — " + t.report_title, author: "ATSurvey")
#set page(
  paper: "a4",
  margin: (x: 16mm, top: 20mm, bottom: 18mm),
  header: context {
    if counter(page).get().first() > 1 {
      set text(7.5pt, fill: subtle)
      grid(columns: (1fr, auto), d.project, t.report_title)
    }
  },
  footer: context {
    set text(7.5pt, fill: subtle)
    grid(
      columns: (1fr, auto),
      [ATSurvey · #t.computation_id #d.input_hash_short · engine #d.engine_version],
      counter(page).display("1 / 1", both: true),
    )
  },
)
#set text(
  font: th.font,
  size: 8.5pt,
  fill: ink,
  lang: d.lang,
  number-width: "tabular",
)
#set par(leading: 0.6em)
#set table(stroke: none)

#show heading.where(level: 1): it => block(above: 18pt, below: 9pt, width: 100%)[
  #text(11pt, weight: "semibold", it.body)
]
#show heading.where(level: 2): it => block(above: 12pt, below: 6pt)[
  #text(8pt, weight: "medium", fill: muted, it.body)
]

// Minimal table: header in muted medium text, hairline under the header and between rows.
#let tbl(cols, header, rows, align-spec: auto) = table(
  columns: cols,
  inset: (x: 5pt, y: 4.2pt),
  align: if align-spec == auto { (x, y) => if x == 0 { left } else { right } } else { align-spec },
  stroke: (x, y) => (bottom: if y == 0 { 0.5pt + c("border-strong") } else { 0.35pt + hair }),
  table.header(..header.map(h => text(7.5pt, weight: "medium", fill: muted, h))),
  ..rows.flatten(),
)

#let pill(kind) = {
  let (fg, bg, label) = if kind == "ok" {
    (c("success"), c("success-subtle"), t.within)
  } else if kind == "bad" {
    (c("danger"), c("danger-subtle"), t.exceeded)
  } else if kind == "low" {
    (c("info"), c("info-subtle"), t.sigma_low)
  } else if kind == "failed" {
    (c("danger"), c("danger-subtle"), t.failed)
  } else {
    (c("warning"), c("warning-subtle"), t.unchecked)
  }
  box(fill: bg, radius: 8pt, inset: (x: 6pt, y: 2.5pt), text(7pt, weight: "medium", fill: fg, label))
}

#let meta(pairs) = grid(
  columns: (auto, 1fr) * 2,
  column-gutter: (10pt, 24pt, 10pt),
  row-gutter: 6pt,
  ..pairs.map(((k, v)) => (text(fill: muted, k), v)).flatten(),
)

#let stat(label, value, note: none) = block(
  width: 100%,
  inset: (x: 9pt, y: 8pt),
  radius: th.radius_pt * 1pt,
  stroke: 0.5pt + hair,
)[
  #text(7.5pt, fill: muted, label)
  #v(2pt)
  #text(13pt, weight: "semibold", value)
  #if note != none [ \ #text(7pt, fill: subtle, note) ]
]

// ------------------------------------------------------------------------ cover
#text(8pt, weight: "medium", fill: accent, "ATSurvey")
#v(6pt)
#text(20pt, weight: "semibold", t.report_title)
#v(2pt)
#text(12pt, fill: muted, d.project)
#v(14pt)
#meta((
  (t.date, d.date),
  (t.crs, "ΕΓΣΑ87 · EPSG:2100"),
  (t.angle_unit, d.angle_unit_label),
  (t.reductions, d.reductions),
))
#v(4pt)
#line(length: 100%, stroke: 0.35pt + hair)

= #t.summary
#grid(
  columns: (1fr,) * 4,
  column-gutter: 8pt,
  ..d.summary_cards.map(s => stat(s.label, s.value)),
)

#if d.traverses.len() > 0 [
  #v(10pt)
  #tbl(
    (1fr, auto, auto, auto, auto, auto, auto, auto, auto),
    (t.traverse, t.type, "n", t.length, "wβ cc / " + t.limit, "w m / " + t.limit, "1:N", "wz", ""),
    d.traverses.map(r => (
      text(weight: "medium", r.name), text(fill: muted, r.kind_short), r.n, r.length, r.wb, r.w,
      r.rel, r.wz, pill(r.status),
    )),
  )
]

// ------------------------------------------------------------------- traverses
#for tr in d.traverses [
  #pagebreak(weak: true)
  #text(7.5pt, fill: muted, t.traverse)
  #v(-4pt)
  #grid(
    columns: (1fr, auto),
    align: (left + bottom, right + bottom),
    text(15pt, weight: "semibold", tr.name), pill(tr.status),
  )
  #v(2pt)
  #text(fill: muted, tr.kind + " · " + tr.length + " · " + tr.n + " " + t.angles_count)
  #v(8pt)
  #grid(
    columns: (1fr,) * 4,
    column-gutter: 8pt,
    stat(t.angular_misclosure, tr.wb_value, note: tr.wb_note),
    stat(t.linear_misclosure, tr.w_value, note: tr.w_note),
    stat(t.relative_precision, tr.rel, note: "wx " + tr.wx + " · wy " + tr.wy),
    stat(t.height_misclosure, tr.wz, note: tr.wz_note),
  )

  == #t.angles_azimuths
  #tbl(
    (0.9fr, 0.8fr, 0.8fr, 1.25fr, 0.85fr, 1.25fr, 1.25fr, 1.45fr, 1.55fr, 1fr),
    (t.station, t.back, t.fore, "β", "δβ cc", "β′", "α", "X", "Y", "Z"),
    tr.stations.map(r => (text(weight: "medium", r.at(0)), ..r.slice(1))),
  )

  == #t.legs
  #tbl(
    (0.75fr, 0.75fr, 1.05fr, 1.05fr, 1.05fr, 1.1fr, 1fr, 1fr, 0.85fr, 0.85fr, 0.95fr, 0.85fr),
    (t.from, t.to, "S₀", "k", "S", "α", "ΔX", "ΔY", "δX", "δY", "ΔH", "δH"),
    tr.legs.map(r => (text(weight: "medium", r.at(0)), ..r.slice(1))),
  )
]

// -------------------------------------------------------------- least squares
#if d.adjustment != none [
  #let adj = d.adjustment
  #pagebreak(weak: true)
  #grid(
    columns: (1fr, auto),
    align: (left + bottom, right + bottom),
    text(15pt, weight: "semibold", t.adjustment), pill(adj.status),
  )
  #v(2pt)
  #text(fill: muted, t.global_test + ": " + adj.global_test)
  #v(8pt)
  #grid(
    columns: (1fr,) * 4,
    column-gutter: 8pt,
    ..adj.stats.map(s => stat(s.at(0), s.at(1))),
  )
  #if adj.suspect != none [
    #v(8pt)
    #block(width: 100%, inset: (x: 10pt, y: 7pt), radius: th.radius_pt * 1pt, fill: c("warning-subtle"))[
      #text(weight: "medium", fill: c("warning"), t.suspect + ": ") #adj.suspect
    ]
  ]
  == #t.adj_points
  #tbl(
    (1.2fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr),
    (t.name, "σx", "σy", "σz", "a₉₅", "b₉₅", "θ (gon)"),
    adj.points.map(r => (text(weight: "medium", r.at(0)), ..r.slice(1))),
  )
  #if adj.observations.len() > 0 [
    == #t.adj_obs
    #tbl(
      (1.2fr, 2fr, 1.2fr, 0.7fr, 0.8fr, 0.4fr),
      (t.kind_obs, t.station + " → " + t.fore, t.residual, t.redundancy, "w", ""),
      adj.observations.map(r => (text(fill: muted, r.at(0)), ..r.slice(1, 5), text(fill: c("danger"), r.at(5)))),
    )
  ]
]

// ------------------------------------------------------------------- linework
#if d.linework.len() > 0 [
  = #t.linework
  #tbl(
    (1.4fr, 1fr, 0.8fr, 0.8fr, 1.2fr, 1.4fr),
    (t.line, t.code, t.points_n, t.closed, t.length + " (m)", t.area),
    d.linework.map(r => (text(weight: "medium", r.at(0)), ..r.slice(1))),
    align-spec: (x, y) => if x in (0, 1, 3) { left } else { right },
  )
]

// ----------------------------------------------------------------- coordinates
#pagebreak(weak: true)
= #t.coordinates
#tbl(
  (1.1fr, 1.6fr, 1.6fr, 1fr, 1fr, 1.7fr),
  (t.name, "X (m)", "Y (m)", "Z (m)", t.code, t.kind),
  d.points.map(r => (text(weight: "medium", r.at(0)), ..r.slice(1, 4), text(fill: muted, r.at(4)), text(fill: muted, r.at(5)))),
  align-spec: (x, y) => if x in (0, 4, 5) { left } else { right },
)

#if d.issues.len() > 0 [
  = #t.issues
  #tbl(
    (0.8fr, 5fr),
    (t.severity, t.message),
    d.issues.map(r => (
      text(weight: "medium", fill: if r.at(0) == "error" { c("danger") } else { c("warning") }, r.at(1)),
      r.at(2),
    )),
    align-spec: left,
  )
]

#v(16pt)
#block(width: 100%, inset: (x: 10pt, y: 8pt), radius: th.radius_pt * 1pt, fill: sunken)[
  #set text(7.5pt, fill: muted)
  #t.disclaimer
]
