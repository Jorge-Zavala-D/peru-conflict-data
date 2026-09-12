# Source-date correction: scientific v0.3.0 to v0.3.1

Authority: `M2-DATE-SOURCE-PRESERVATION-CORRECTION-V1`, recorded in
`config/benchmark/m2_01_date_semantics_correction_approval_v1.yaml`.
This supplements, and does not rewrite, the M2-01/M2-02 owner approvals.

Historical v0.3.0 stores only parsed `DefensoriaAction.action_date` and
`Alert.alert_date`. Its digest remains
`cd5bdea78e6314242685ea89d43850f8ff42e639ba74606aba3d929b2e81444d`.
The complete v0.3.1 snapshot adds exactly four optional string fields:
`action_date_original`, `action_date_precision_original`, `alert_date_original`,
`alert_date_precision_original`. Existing parsed date fields remain optional derivatives.
All other scientific semantics are unchanged; ordinary schema-version identities advance.
No source string must parse as ISO and no day/month may be inferred from coarse precision.
No data migration or research-data rewrite has occurred.

## Benchmark successor

Historical benchmark v0.1.0 remains byte-identical with digest
`23a5ee953541c93b9e51898872901f8b9432588f8c9ea03758ea85a5a1ff28fa`.
The explicit `OBJECT_MATCH_FIELDS_V010` retains its parsed-date signatures.
Active v0.1.1 replaces only the first action/alert match field with original date
plus precision. `OBJECT_MATCH_FIELDS_V011` is the current mapping. TP/FP/FN,
strict denominator, page attribution, evidence arithmetic and gate thresholds do not change.
The 40 critical source-value fields remain byte-identical and are not expanded.

Active annotation records use benchmark 0.1.1. The 19-model successor export also
includes the unchanged historical M2-01 approval and M3 gate-spec governance models;
those independently retain their 0.1.0 record identity so old authority is not silently
migrated. This does not approve the draft M3 gate or create a new gate policy.

## Execution alignment, not new identity or scoring

One human actor instance supplies actor name/type and its case-role component.
One location instance supplies its visible geography and case-relationship component.
These are slots of the same instance, never joins across local ordinal spaces.
Without a case scope, a case-relation component is explicitly not applicable; within
a case, a role/relationship must be source-supported or explicitly not reported.
There is one CaseMonth field set on the base case observation. CaseName instances
are separately declared, one or more per complete case, without selecting a primary name.

Subordinate benchmark objects count toward report/family inspection truth. Empty
populations require completed explicit inspection. Every registered family is present
in the synthetic projection; absent families cannot silently become empty populations.
Unresolved/uncertain/illegible evidence remains available for later adjudication or
forensics and cannot become a confident projection. No real gold projection or launch
is implemented. The discovery-start key is not used for normative scoring.
