# Open questions requiring evidence or approval

## M2-01 ontology questions: owner-approved and closed

All ten fixed reports 260–269 were inspected with native PDF text. The full evidence
and migration rationale are preserved in `docs/m2_01_ontology_decisions.md`.

1. **Owner-approved:** `Demand.text_original`
   is nullable for structured rows, but at least one original demand dimension is required.
2. **Owner-approved:** source-reported case-month
   indicators are separate from dated events and derived indicators.
3. **Owner-approved:** report-specific structural
   case description is distinct from monthly facts.
4. **Owner-approved:** mediation observation is
   report-local; persistent process identity is optional and requires separate evidence.
5. **Owner-approved for v0.3.0:** only the evidenced case description,
   case-reported indicator, and mediation-observation changes are added. Closed taxonomies,
   automatic annex-to-case links, automatic mediation continuity, reconstructed cumulative
   violence replacing source values, and timeless descriptions remain rejected.

Historical format stability beyond reports 260–269 remains unresolved and must not be
inferred from these decisions.

## Other evidence and approval questions

- Exact official URLs, publication dates, and reference months for reports 260-269 and the future full corpus.
- Whether reports 260-269 form one parser regime; when official codes and taxonomies begin or change.
- Which historical reports are absent, revised, scanned, or internally reorganized.
- Which source sections are complete enumerations and how workbook violence/dialogue fields map to PDF evidence.
- Historical INEI crosswalk authority and annotation/adjudication storage details.
- Source-document and derived-data redistribution rights.
- Acceptable future OCR/model budgets and benchmark annotation depth.
- Whether missing Java/Tesseract Spanish/qpdf/Ghostscript should be installed for a later measured need.
- M1-03B network authorization artifact, final merged pre-network baseline, and any
  later raw-write/promotion approval; M1-03A fixed the command, bounds, and rate-limit
  design without authorizing network or Dropbox mutation.
- M1-03B hard-kill/power-loss recovery: durable pre-publication intent and startup
  reconciliation must be designed and tested before raw promotion; M1-03A's typed
  recovery guarantee is limited to catchable in-process errors and interruptions.
- Which report-269 alert and case-timing observations are confirmed source inconsistencies after independent page-level benchmark review.
