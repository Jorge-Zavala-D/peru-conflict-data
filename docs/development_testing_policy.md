# Development testing and checkpoint commits

Prospective owner-approved policy, 2026-10-15 (W10I). This scheduling change
does not change scientific, source-safety, test-assertion or release contracts.

## Local checkpoint commits

Use ordinary `git commit` through the installed pre-commit framework. Every
applicable existing non-pytest hook remains required: static/data-policy checks,
formatting, both platform type checks and generated-schema currentness.
Relevant focused tests must also pass on the final candidate before a local
commit. Record their exact command, node identities, candidate identity and
outcome. Unknown results do not count as passes. No hook bypass is permitted.

The existing full `pytest` hook is retained with `stages: [manual]`; it no longer
runs automatically inside each local commit and is not moved to pre-push.
The full canonical commands remain available:

```text
uv run pytest
uv run pre-commit run pytest --hook-stage manual --all-files
```

`make quality` remains an explicitly requested comprehensive local command,
including the full suite. It is not required inside every checkpoint commit.
Use the already installed tools and applicable frozen/offline execution policy;
this change does not authorize dependency synchronization or provisioning.

## Full validation before merge or release

Full canonical validation remains required before merge/release, through actual
current-head CI or a separately approved exact whole-test partition procedure.
The existing required CI workflow, full Linux selections and exact Windows
whole-test union remain unchanged. A checkpoint commit is not CI success,
merge/release approval or scientific acceptance. Hosted-runtime feasibility and
actual current-head results require their own evidence; moving work to CI does
not guarantee that its existing time limits fit the workload.

W10H remains timed out/interrupted, without session finish or final JUnit.
Verified same-candidate per-test observations and fresh whole-test batches may
be counted as explicitly labelled multi-execution development evidence. Their
union does not manufacture the missing session, prove uninterrupted ordering or
session-finalizer behavior, or become a successful historical gate or fresh CI.
Keep failures, skips and unknown closure separate; document every skip reason
and any remaining identity set. Bind each execution to its actual source tree;
do not assign old observations to a later policy/documentation tree.

Never split a protected operator transaction to fit a budget, resume an
interrupted journal, delete scenarios, weaken assertions or add skips. Rerun an
interrupted test from its beginning with fresh mutable fixtures. Additional
settings, source/rule amendments, publication and scientific work require their
own authority; none is implied by this scheduling decision.
