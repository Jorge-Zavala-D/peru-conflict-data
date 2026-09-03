# M2-01 ten-report source evidence census

## Scope and method

This census covers the fixed, protected PDF byte versions for reports 260–269 only. Their
SHA-256 values were rechecked before inspection. Native-text extraction used Poppler `pdfinfo`
26.05.0 and `pdftotext` 24.04.0 with layout preservation. Every page was inspected through the
native-text stream; no OCR, model extraction, network access, or filename-based identity inference
was used. The detailed page-level rows are local audit evidence at
`.cache/m2-01/source_evidence_census.jsonl` and are intentionally ignored by Git.

All 1,128 pages returned substantial native text; no page fell below the 100-character inspection
screen. This establishes inspectability, not annotation accuracy. Reports 261 and 263 retain
`unresolved_opaque_filename`; their report identity comes from reviewed document/data evidence.

## Report census

| Report | Month | Pages | Native characters | Recurring source structure and key pages |
|---:|:---:|---:|---:|---|
| 260 | 2025-10 | 121 | 802,781 | Report aggregates/alerts pp. 1–5; mediation pp. 6–15; agreement monitoring begins p. 16; structured demands pp. 28–29; active cases pp. 30–94; protests/violence/actions pp. 95–119; demand taxonomy pp. 120–121. |
| 261 | 2025-11 | 132 | 937,784 | Aggregates/alerts pp. 1–5; mediation pp. 6–14; agreement monitoring p. 15 onward; structured demands pp. 26–27; case inventory and monthly facts; protest/violence/action annexes; taxonomy pp. 131–132. |
| 262 | 2025-12 | 120 | 773,048 | Aggregates/alerts pp. 1–5; mediation pp. 6–15; description/agreement/month facts p. 16 onward; structured demands pp. 29–30; case inventory; violence/actions; taxonomy pp. 119–120. |
| 263 | 2026-01 | 109 | 678,489 | Aggregates/alerts pp. 1–5; mediation pp. 5–13; agreement monitoring p. 14 onward; structured demands pp. 25–26; active/reactivated/resolved case evidence; protests/violence/actions; taxonomy pp. 108–109. |
| 264 | 2026-02 | 104 | 609,154 | Aggregates/alerts pp. 1–5; mediation pp. 5–15, including `Tipo de mediación` and source-local status; agreement monitoring p. 16 onward; structured demands pp. 25–26; violence/actions; taxonomy pp. 103–104. |
| 265 | 2026-03 | 99 | 561,559 | Aggregates/alerts pp. 1–5; mediation pp. 5–10; agreement monitoring pp. 11–23; structured demands p. 24; case inventory/monthly facts; protest/violence/actions; taxonomy pp. 98–99. |
| 266 | 2026-04 | 102 | 611,619 | Aggregates/alerts pp. 1–5; mediation pp. 5–12; agreement monitoring p. 13 onward; structured demands p. 28; case inventory/monthly facts; protests/violence/actions; taxonomy pp. 101–102. |
| 267 | 2026-05 | 102 | 599,851 | Aggregates/alerts pp. 1–5; mediation pp. 6–11; agreement monitoring p. 12 onward with `Descripción del caso`, `Descripción de los acuerdos`, and `Avances de cumplimiento`; structured demands pp. 28–29; case inventory/monthly facts; protests/violence/actions; taxonomy pp. 101–102. |
| 268 | 2026-06 | 122 | 754,554 | Aggregates/alerts pp. 1–5; mediation pp. 6–16; agreement monitoring begins p. 17 with complete `Descripción del caso`, `Acuerdos`, and `Avances de cumplimiento` rows; structured demands pp. 38–39; case inventory/monthly facts; protests/violence/actions; taxonomy p. 121. |
| 269 | 2026-07 | 117 | 676,057 | Aggregates/alerts pp. 1–5; mediation pp. 5–14; agreement monitoring pp. 15–39; structured demands pp. 40–41; case inventory/monthly facts; protest/violence/action annex pp. 94–113; taxonomy p. 116. |

## Cross-report source facts

- Report identity, reference month, totals, alerts, new/reactivated/resolved status, case inventory,
  protests, violence/casualties, Defensoría actions, and a demand taxonomy recur in all ten reports.
- Case blocks expose source-original case name/denomination, type, location, actors, demand/problem,
  stock status or phase, and monthly facts. These labels are not perfectly uniform across reports.
- Agreement-monitoring tables visibly separate `Descripción del caso`, `Descripción de los
  acuerdos`/`Acuerdos`, and `Hechos del mes`/`Avances de cumplimiento` (for example report 260
  p. 16, report 267 p. 12, report 268 p. 17, and report 269 p. 15). Structural description and
  monthly evolution are therefore distinct.
- Mediation tables are report-local blocks. Report 264 p. 6 displays `Fecha de inicio`,
  `Descripción de caso`, `Estado situacional`, `Estado`, `Solicitante`, `Actores`, `Tipo de
  mediación`, and `Mediador`. `Estado` is the status field; the `Estado situacional` narrative is
  progress/situation evidence. Equivalent blocks recur, but no stable source mediation-process ID
  was observed in any report.
- Structured demand tables enumerate case denomination, theme, category, count, and competent
  entity without reproducing the case's verbatim demand sentence (for example report 260 pp.
  28–29 and report 269 pp. 40–41). The report-wide taxonomy lists 13 themes and 55 categories
  separately from case prose.
- Source-reported case and report indicators coexist with dated events. Report 269 p. 110 states
  that no wounded or dead persons were registered while p. 111 reports seven wounded people for a
  named case. Both statements must be preserved and classified as a source inconsistency rather
  than reconciled silently.
- Protest annex rows contain event number/date, action type, actor, place, and demand. These are
  report-level event rows and are not automatically linked to a conflict case.
- Defensoría action tables contain hierarchical type/subtype counts and narrative interventions.
  Alerts remain distinct source objects with location/risk/context evidence.

## Inspection limitations

The census establishes source-visible structure and ontology needs; it is not human gold and does
not enumerate every case row. Text coordinates were not reconstructed, so pilot annotators must
use page/section plus exact text span or bounding box where feasible. No page in this ten-report set
required OCR, but later historical reports may require a separately authorized OCR assessment.
