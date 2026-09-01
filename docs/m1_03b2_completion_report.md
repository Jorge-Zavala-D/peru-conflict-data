# M1-03B.2 completion report

## Outcome

The owner-authorized compare-only pilot completed once on 31 August 2026. The
authorization `m1-03b2-reports-260-269-compare-v2` was installed on protected main
`0e789e333b4948836d06bdbdf1e739d5d36aefdd` and bound execution to reviewed commit
`116bcd249b8adf88a8b4834bc1d0e03464e88c34`.

The single invocation used deterministic run ID
`m103b-1dff6ef0b40dec88e4382932a8c5cf48`. It began at
`2026-08-31T15:13:04.003090Z` and reached its durable terminal at
`2026-08-31T15:13:50.718271Z`.

## Bounded execution evidence

- 21 requests completed: one robots request, ten landing pages, and ten PDFs.
- Total accepted response bytes were 33,882,447.
- All ten official remote PDFs for reports 260–269 were byte-identical to the
  protected local sources.
- Reports 261 and 263 retain `unresolved_opaque_filename`; exact byte identity did
  not upgrade their documentary association evidence.
- The ledger contains zero issue records.
- Terminal sequence 124 is `completed / all_ten_remote_bytes_identical`.
- The authorization-use index terminal is sequence 127 and anchors ledger sequence
  124.
- The one-shot authorization is spent and must not be invoked again.
- No raw staging, raw promotion, or duplicate raw object occurred.
- All eleven protected research-source hashes remained unchanged, and Git remained
  unchanged during execution.

## Durable operational evidence

The completed append-only evidence remains in these protected relative paths:

- `01_raw/manifests/m1-03b-namespace-v2.json`
- `01_raw/manifests/authorization-use-index-v2.jsonl`
- `01_raw/manifests/authorization-1dff6ef0b40dec88e4382932a8c5cf48.v2.jsonl`
- `01_raw/manifests/.m1-03b-v2.lock`

These files are operational evidence, not Git artifacts. M1-04 consumes them
read-only. The next stage is deterministic corpus-manifest reconciliation; no further
M1-03B.2 network use is authorized.
