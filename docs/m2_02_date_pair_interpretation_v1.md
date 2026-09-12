# Owner-confirmed action/alert date-pair interpretation v1

Jorge explicitly ratified this interpretation in the M2-02A.1E pre-owner-readiness
review prompt on 2026-09-11. The dedicated versioned record is
`config/benchmark/m2_02_date_pair_interpretation_approval_v1.yaml`; its actual
recording timestamp is distinct from the ratification prompt date.
This supplements, and does not replace or rewrite, the historical date-correction
approval M2-DATE-SOURCE-PRESERVATION-CORRECTION-V1.

For resolved action/alert pairs, observed source date and observed source-supported
precision are required together. An observed date with not_reported, not_applicable
or structurally_unavailable precision is not a resolved valid pair. An observed
precision still requires an observed date. When neither is reported, retain each
applicable explicit no-value state; do not manufacture values or equate distinct states.

Genuinely source-ambiguous, annotation-uncertain or illegible precision alongside an
observed date remains unresolved evidence for later adjudication/forensics. It is
not finalized by projection. Never replace that evidence with inferred precision.
Explicit zero is prohibited for either date slot. Exact month/year and ISO-looking
strings remain untouched: no parsing, expansion, normalization or inference.

This is annotation-rule clarification only, not readiness approval, annotation
launch, a human submission, human gold, parser authority or M3 approval.
