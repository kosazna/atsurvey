// ATSurvey computation report. Data arrives pre-formatted as JSON in sys.inputs.data.
#let d = json(bytes(sys.inputs.data))
#let t = d.labels

#let ink = rgb("#0f172a")
#let muted = rgb("#64748b")
#let line-c = rgb("#cbd5e1")
#let head-bg = rgb("#eef2f7")
#let ok-c = rgb("#15803d")
#let bad-c = rgb("#b91c1c")
#let warn-c = rgb("#b45309")

#set document(title: d.project, author: "ATSurvey")
#set page(
  paper: "a4",
  margin: (x: 14mm, top: 18mm, bottom: 16mm),
  header: context {
    if counter(page).get().first() > 1 [
      #set text(8pt, fill: muted)
      #d.project #h(1fr) #t.report_title
      #v(-6pt)
      #line(length: 100%, stroke: 0.4pt + line-c)
    ]
  },
  footer: context [
    #set text(7.5pt, fill: muted)
    ATSurvey · engine #d.engine_version · #d.input_hash_short #h(1fr)
    #t.page #counter(page).display("1 / 1", both: true)
  ],
)
#set text(font: ("Libertinus Serif", "New Computer Modern"), size: 9pt, fill: ink, lang: d.lang)
#set par(justify: false)
#show heading.where(level: 1): it => block(above: 14pt, below: 8pt)[
  #set text(13pt, weight: "bold")
  #it.body
  #v(-6pt)
  #line(length: 100%, stroke: 0.8pt + ink)
]
#show heading.where(level: 2): it => block(above: 12pt, below: 6pt)[
  #set text(10.5pt, weight: "bold")
  #it.body
]

#let tbl(cols, header, rows, align-spec: auto) = table(
  columns: cols,
  stroke: (x, y) => (bottom: if y == 0 { 0.6pt + ink } else { 0.3pt + line-c }),
  fill: (x, y) => if y == 0 { head-bg },
  inset: (x: 4pt, y: 3pt),
  align: if align-spec == auto { (x, y) => if x == 0 { left } else { right } } else { align-spec },
  table.header(..header.map(h => text(weight: "bold", size: 8pt, h))),
  ..rows.flatten().map(c => text(size: 8pt, c)),
)

#let status-text(s) = {
  if s == "ok" { text(fill: ok-c, weight: "bold", t.within) }
  else if s == "bad" { text(fill: bad-c, weight: "bold", t.exceeded) }
  else if s == "failed" { text(fill: bad-c, weight: "bold", t.failed) }
  else { text(fill: warn-c, weight: "bold", t.unchecked) }
}

// ------------------------------------------------------------------ title block
#block(width: 100%)[
  #text(18pt, weight: "bold", t.report_title)
  #v(-4pt)
  #text(12pt, d.project)
]
#v(4pt)
#grid(
  columns: (auto, 1fr, auto, 1fr),
  column-gutter: 8pt,
  row-gutter: 5pt,
  text(fill: muted, t.date), d.date,
  text(fill: muted, t.crs), "ΕΓΣΑ87 (EPSG:2100)",
  text(fill: muted, t.angle_unit), d.angle_unit_label,
  text(fill: muted, t.reductions), d.reductions,
)

= #t.summary
#grid(
  columns: (1fr,) * 4,
  column-gutter: 6pt,
  ..d.summary_cards.map(c => block(
    width: 100%, inset: 7pt, radius: 3pt, stroke: 0.4pt + line-c,
  )[
    #text(7.5pt, fill: muted, c.label) \
    #text(14pt, weight: "bold", c.value)
  ]),
)

#if d.traverses.len() > 0 [
  #v(6pt)
  #tbl(
    (2.6fr, 1fr, 0.6fr, 1fr, 1.1fr, 1fr, 1fr, 0.9fr, 1.2fr),
    (t.traverse, t.type, "n", t.length, "wβ / " + t.limit, "w / " + t.limit, "1:N", "wz", t.result),
    d.traverses.map(r => (r.name, r.kind, r.n, r.length, r.wb, r.w, r.rel, r.wz, status-text(r.status))),
  )
]

// ------------------------------------------------------------------ traverses
#for tr in d.traverses [
  #pagebreak(weak: true)
  = #t.traverse: #tr.name
  #grid(
    columns: (auto, 1fr, auto, 1fr, auto, 1fr),
    column-gutter: 6pt,
    row-gutter: 4pt,
    text(fill: muted, t.type), tr.kind,
    text(fill: muted, t.length), tr.length,
    text(fill: muted, t.result), status-text(tr.status),
    text(fill: muted, "wβ"), tr.wb,
    text(fill: muted, "wx / wy"), tr.wxy,
    text(fill: muted, "w"), tr.w,
    text(fill: muted, "1:N"), tr.rel,
    text(fill: muted, "wz"), tr.wz,
    text(fill: muted, t.correction), tr.corr,
  )
  == #t.angles_azimuths
  #tbl(
    (1fr, 1fr, 1fr, 1.3fr, 0.9fr, 1.3fr, 1.3fr, 1.4fr, 1.5fr, 1fr),
    (t.station, t.back, t.fore, "β", "δβ (cc)", "β'", "α", "X", "Y", "Z"),
    tr.stations,
  )
  == #t.legs
  #tbl(
    (0.8fr, 0.8fr, 1.1fr, 1.1fr, 1.1fr, 1.1fr, 1fr, 1fr, 0.9fr, 0.9fr, 1fr, 0.9fr),
    (t.from, t.to, "S₀", "k", "S", "α", "ΔX", "ΔY", "δX", "δY", "ΔH", "δH"),
    tr.legs,
  )
]

// ------------------------------------------------------------------ coordinates
#pagebreak(weak: true)
= #t.coordinates
#tbl(
  (1.2fr, 1.6fr, 1.6fr, 1fr, 1fr, 1.6fr),
  (t.name, "X (m)", "Y (m)", "Z (m)", t.code, t.kind),
  d.points,
)

#if d.issues.len() > 0 [
  = #t.issues
  #tbl(
    (0.9fr, 5fr),
    (t.severity, t.message),
    d.issues,
    align-spec: left,
  )
]

#v(12pt)
#block(inset: 7pt, radius: 3pt, fill: rgb("#f8fafc"), stroke: 0.4pt + line-c, width: 100%)[
  #set text(7.5pt, fill: muted)
  #t.disclaimer
]
