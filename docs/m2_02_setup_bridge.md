# Setup-authority bridge v1 — SYNTHETIC_ONLY

This source implementation connects the unchanged V3 proposal to a **manual-assisted
work-order/evidence procedure**, demonstrated only against an in-memory provider.
It performs no Dropbox calls, account authentication, real setup, issuance or annotation.
There is no registered real grant. `production_admission` rejects before parsing inputs,
filesystem activity or provider dispatch, including synthetic-grant injection. No flag,
environment variable or CLI option opens production admission.

## Run the synthetic example

```powershell
$env:UV_PYTHON = '3.12'
uv run python -m peru_conflicts.execution.setup_synthetic
```

The example uses a dedicated temporary `m2-readiness-setup-*` directory and isolated
success/collision cases. It prints SYNTHETIC_ONLY results for 30 created directories,
108 access observations, two separate application controls and exact probe cleanup,
plus a stopped collision and a production-admission rejection. Temporary evidence is
disposed when this example exits; tests exercise retained stores and interruption.
It uses no report PDFs, private personnel data or real account sessions. A fake-provider
conditional guarantee is not proof of equivalent Dropbox behavior.

The command verifies the original system-temporary-directory ancestry with the existing
directory leases before allocating its disposable child using the canonical spelling.
This accepts a genuine Windows short-name spelling of the same directory, not junction
or symlink redirection. Direct `create_demo` callers still supply a new, canonical,
dedicated temporary child; store identity and resume semantics are unchanged.

## Minimal offline interface

`create_demo(new_owned_temp_child)` admits a grant from the **fixed synthetic authority
source**, returning a `SetupBridge` and its in-memory `FakeProvider`. Each fixture grant
is bound to one exact temporary evidence-store identity; supplying its bytes for another
store fails. The authority source is not a caller-provided trust object or expected digest.
`parse_authorization` alone checks syntax/consistency and explicitly does **not** admit
authority. Models, hashes and approved-looking values are insufficient. Duplicate JSON
keys, coercible approval values, unexpected fields, mixed components, broadened operation
scope, wrong candidate/namespace/session and stale/revoked fixture grants are rejected.
Synthetic fixture creation is intentionally available to tests; it is never a mechanism
for installing owner authority. Production admission has no path to these registrations.

The separate strict grant binds the raw REQUEST and five raw component byte hashes,
existing candidate canonical-model hash, access policy, implementation source inventory,
exact root/absent paths, existing namespace/root identity, distinct opaque actor/session
references, private evidence pins, capability references and explicit validity/use scope.
The fixture's date interval and 300-second freshness bound are **test values, not owner
policy**. Future real values and their independent reviewed source require a new grant
and an explicitly reviewed live admission mechanism. No signature infrastructure is added.

1. `run.next(now)` validates current authority and emits **one** serialized `WorkOrder`.
   Its durable intent precedes release. Pending intent blocks redispatch and further orders.
2. A future independently authenticated operator would perform that exact action outside
   this software. The demonstration calls only `provider.execute(order)` in memory.
3. `run.submit(OperationEvidence, now)` validates the bound source record, timestamp,
   actor/session, namespace, exact target, operation/sequence and pre/post identity/bytes.
   It derives a result; there is no accepted caller-supplied PASS. A manual “done” statement
   is not evidence. Evidence consistency is distinct from authenticating a real actor,
   real provider behavior or owner acceptance.
4. `resume_demo(store)` replays and revalidates the immutable journal against the exact
   schedule. An unmatched intent stays UNKNOWN; only its exact returned evidence may
   reconcile it. Replays, substituted orders, incomplete records and asserted results fail.
   It never automatically repeats an uncertain external action.

Software can refuse evidence and stop later orders. It **cannot prevent a human from
acting outside the procedure**. Returning an apparently consistent source record is not
independent authentication of a real event. A production operator/evidence-authentication
mechanism and usable live capabilities remain unimplemented/unverified gates.

## Identity, operations and containment

The retained V3 REQUEST is unchanged, including six null private bindings and three false
authorization flags. The bridge does not fill or mutate that template. Existing V2/V3
generation remains reproducible; PR16 predecessor authority is not repinned to latest main.

The order is the proposal's one assert-existing `/`, 30 create-new directories, four
role-specific viewer/editor leaf grants, known read probes, 108 access checks, two
application controls and exact owned-probe cleanup. No A/B parent or coordinator sharing.
Expected list/read/write semantics and synthetic bytes are unchanged. List creates no file;
read requires the known coordinator-created probe; write requires an absent target and
exclusive creation, never overwrite/autorename. Permission simulation derives from the
four installed fake leaf grants, not from a returned PASS or a coordinator impersonation.

Before creation there are exact absent paths and an existing-root snapshot, not invented
future IDs. Returned objects must match path, type, namespace, owner-run and bound parent
identity and have a new unique ID. Every later order carries the full known ancestry and
version snapshots. Current mismatches, collisions, relocation/replacement and namespace
changes stop the run; unrelated same-byte objects cannot be adopted. Observations are
time-bound. A prior lookup cannot remove a replacement race: the fixture separately models
conditional parent identity, exclusive create and conditional delete capabilities.

Missing objects, wrong sessions/namespaces, client/network errors and stale observations
are INCONCLUSIVE, not denial PASS. No provider-concealment rule is registered in this
fixture; not-found stays INCONCLUSIVE. Real concealment semantics would require separate
review and independently established target existence, as in the unchanged classifier.
Unexpected successful forbidden access is FAIL and stops further normal orders. Failed,
inconclusive, NOT RUN and completed checks remain distinct. All 108 IDs must be present
exactly once; the two application controls remain a separate coverage set.

Receipts bind authority/run/session, ordered intent, operation, exact resource/version,
probe bytes, observations, source evidence and predecessor record. Existing readiness
`publish_new` provides exclusive, flushed, directory-bound publication. Partial outcome
capture is not success. Failure receipts remain immutable; no later success overwrites them.
Returned work orders and retained journal entries use detached deep copies, so mutable
capability mappings in caller-held orders/evidence cannot rewrite the durable intention
or its predecessor hashes. Substituted order evidence leaves the original intent UNKNOWN;
recovery requires evidence for that original order, never automatic redispatch.
Denial evidence must agree with operation-specific pre/post state: a denied exclusive
write cannot show a created file, and denied list/read checks cannot substitute the target.
Contradictory raw receipts are retained and stop normal work. Suspect post-state appears
under `reconciliation_required`, separately from owned cleanup objects; it supplies no
deletion authority. This obligation survives resume and prevents complete status.
The journal assumes one trusted writer and protected local storage. Its hash chain is
**not rollback protection against malicious administrators or deletion/restoration of the
whole evidence store**. Independent real authority-use custody/high-water protection is
a live capability gate, not claimed by this synthetic test store.

Cleanup is a separately enumerated grant scope. Only an object established by a successful
creation receipt is eligible, with its exact run, ID, path, bytes and version. The fake
provider conditionally deletes that exact object; it preserves replaced, other-owned or
changed-byte objects. Missing conditional guarantees cause BLOCKED, not a path delete
after a hash comparison. The implementation does not perform recursive folder removal or
automatic permission revocation. After a failed/inconclusive run, normal orders stop,
including automatic cleanup; outstanding objects remain explicitly listed for later
separately reviewed reconciliation. No silent retry or automatic repair.

## Still closed

The new schema is additive under `schemas/execution/setup_bridge_v1.json`; it changes no
scientific, benchmark, evaluator, partition, dependency, package/reference/view/runtime or
historical approval contract. All seven real operational decisions remain unresolved.
Synthetic coverage does not establish real isolation acceptance, environment approval,
issuance acceptance, annotation-launch or locking authority. Real protected provisioning,
actor authentication, evidence custody, conditional provider semantics and owner-approved
live admission remain required before any live work order may be released.
