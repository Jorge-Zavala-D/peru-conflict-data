"""Offline setup evidence validation. No production grant or provider dispatcher.

Manual work orders cannot prevent an operator acting outside the procedure.
Evidence consistency is not authentication of a real actor/provider or owner acceptance.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, Field, TypeAdapter, field_validator, model_validator

from peru_conflicts.acquisition.fs_safety import DirectoryLease
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Sha256, StrictModel

from .access_policy import ACCESS_POLICY_V2, ACCESS_POLICY_V2_SHA256, AccessActor
from .operational_plan import (
    PRIVATE_EXECUTION_ROOT,
    build_operational_plan,
    classify_access_observation,
    evidence_json,
    make_candidate,
    validate_setup_request,
)
from .packages import publish_new, require_readiness_root
from .references import sha256

REAL_GRANTS: tuple[()] = ()
Token = Annotated[str, Field(pattern=r"^synthetic-[a-z0-9-]+$")]
Action = Literal["assert_existing", "create_new", "share", "prepare", "check", "control", "cleanup"]
Result = Literal["PASS", "FAIL", "INCONCLUSIVE", "BLOCKED"]
SYNTHETIC_ADMISSION_SEAL = object()


def production_admission(raw: bytes) -> None:
    """No real reviewed grant exists. No input parsing, filesystem or provider I/O."""
    raise ValueError("production setup closed: no registered real grant")


class Session(StrictModel):
    actor: AccessActor
    account: Token
    session: Token
    private_evidence_sha256: Sha256


class Snapshot(StrictModel):
    path: str
    resource_id: Token
    version: Token
    namespace: Token
    parent_id: Token | None
    kind: Literal["directory", "file"]
    content_sha256: Sha256 | None = None
    owner_run: Token | None = None

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not value.startswith("/")
            or value.startswith("//")
            or str(path) != value
            or any(c in value for c in ("\\", ":", "\x00"))
            or ".." in path.parts
            or any(ord(c) < 32 for c in value)
        ):
            raise ValueError("unsafe/noncanonical provider path")
        return value


class SetupAuthorization(StrictModel):
    """Versioned test-only grant shape; a model or digest alone grants nothing."""

    version: Literal["m2-setup-authority-v1"] = "m2-setup-authority-v1"
    label: Literal["SYNTHETIC_ONLY"]
    approved: Literal["SYNTHETIC_FIXTURE_NOT_OWNER_APPROVAL"]
    grant_id: Token
    run_id: Token
    evidence_store_id: Token
    request_raw_sha256: Sha256
    components: dict[str, Sha256]
    candidate_sha256: Sha256
    access_policy_sha256: Sha256
    implementation_sha256: Sha256
    root: Literal["/M2 Private Annotation Execution/m2-02-v1"]
    namespace: Token
    existing_root: Snapshot
    absent_paths: tuple[str, ...]
    sessions: tuple[Session, ...]
    private_binding_evidence: dict[str, Sha256]
    custody_evidence_sha256: Sha256
    capabilities: dict[str, Sha256]
    operations: tuple[Action, ...]
    not_before: AwareDatetime
    not_after: AwareDatetime
    observation_max_age_seconds: Annotated[int, Field(gt=0)]
    use_policy: Literal["one_run_no_redispatch"]

    @model_validator(mode="after")
    def bounded(self) -> SetupAuthorization:
        if self.not_after <= self.not_before:
            raise ValueError("invalid authority validity interval")
        if {s.actor for s in self.sessions} != {"coordinator", "annotator-a", "annotator-b"}:
            raise ValueError("exactly three independent roles required")
        if len(self.sessions) != 3 or len({s.account for s in self.sessions}) != 3:
            raise ValueError("distinct actor accounts required")
        if len({s.session for s in self.sessions}) != 3:
            raise ValueError("distinct actor sessions required")
        return self


class WorkOrder(StrictModel):
    label: Literal["SYNTHETIC_ONLY"] = "SYNTHETIC_ONLY"
    authority_sha256: Sha256
    run_id: Token
    sequence: int
    action: Action
    path: str
    session: Session
    check_id: str | None = None
    expected: Literal["ALLOW", "DENY"] = "ALLOW"
    probe_sha256: Sha256 | None = None
    probe_content: str | None = None
    share_role: AccessActor | None = None
    share_mode: Literal["viewer", "editor"] | None = None
    before: tuple[Snapshot, ...]
    issued_at: AwareDatetime
    capability_evidence: dict[str, Sha256]


class OperationEvidence(StrictModel):
    label: Literal["SYNTHETIC_ONLY"] = "SYNTHETIC_ONLY"
    order_sha256: Sha256
    run_id: Token
    sequence: int
    session: Session
    namespace: Token
    observed_at: AwareDatetime
    observation: Literal[
        "success", "authorization_denied", "not_found", "network_error", "conflict"
    ]
    before: tuple[Snapshot, ...]
    after: Snapshot | None
    capability_evidence: dict[str, Sha256]
    source_evidence: str = Field(min_length=1)
    source_sha256: Sha256
    application_checks: tuple[Literal["overwrite_rejected", "prior_hash_preserved"], ...] = ()
    application_before_sha256: Sha256 | None = None
    application_after_sha256: Sha256 | None = None
    application_replacement: Literal["conflict", "success"] | None = None
    share_role: AccessActor | None = None
    share_mode: Literal["viewer", "editor"] | None = None

    @model_validator(mode="after")
    def source_pin(self) -> OperationEvidence:
        if sha256(self.source_evidence.encode()) != self.source_sha256:
            raise ValueError("source evidence byte pin differs")
        payload = self.model_dump(mode="json", exclude={"source_evidence", "source_sha256"})
        if evidence_json(self.source_evidence.encode()) != payload:
            raise ValueError("source evidence does not substantiate exact observation")
        return self


def digest(model: StrictModel) -> str:
    return sha256(canonical_json_bytes(model.model_dump(mode="json")))


def implementation_digest() -> str:
    """Source inventory pin, NOT independent approval of these source bytes."""
    return sha256(
        canonical_json_bytes(
            {
                name: sha256(Path(__file__).with_name(name).read_bytes())
                for name in ("setup_bridge.py", "setup_synthetic.py")
            }
        )
    )


def parse_authorization(
    raw: bytes, request: bytes, components: dict[str, bytes]
) -> SetupAuthorization:
    """Consistency only; admission additionally needs fixed authority-source authentication."""
    evidence_json(raw)  # duplicate keys rejected before Pydantic's JSON decoder
    grant = SetupAuthorization.model_validate_json(raw)
    candidate = make_candidate()
    validate_setup_request(request, components, candidate)
    req = evidence_json(request)
    plan = build_operational_plan(candidate)
    if (
        grant.request_raw_sha256 != sha256(request)
        or grant.components != {n: sha256(b) for n, b in components.items()}
        or grant.candidate_sha256 != req["candidate_model_sha256"]
        or grant.access_policy_sha256 != ACCESS_POLICY_V2_SHA256
        or grant.implementation_sha256 != implementation_digest()
        or grant.absent_paths
        != tuple(r["path"] for r in plan["topology"]["directory_operations"][1:])
        or set(grant.private_binding_evidence) != set(req["private_bindings"])
        or grant.operations
        != ("assert_existing", "create_new", "share", "prepare", "check", "control", "cleanup")
        or grant.existing_root.path != "/"
        or grant.existing_root.parent_id is not None
        or grant.existing_root.namespace != grant.namespace
        or grant.existing_root.kind != "directory"
    ):
        raise ValueError("authority scope/components differ from immutable proposal")
    return grant


class JournalRecord(StrictModel):
    sequence: int
    previous_sha256: Sha256 | None
    kind: Literal["intent", "outcome"]
    order: WorkOrder
    evidence: OperationEvidence | None
    result: Result | None
    recorded_at: AwareDatetime


class SetupBridge:
    """One admitted synthetic run. No network interface or arbitrary transport injection.

    Exclusive immutable journal files detect incomplete capture, replay and chain edits;
    not rollback-resistant storage against a malicious owner/admin. One trusted writer.
    """

    def __init__(self, grant: SetupAuthorization, root: Path, *, seal: object) -> None:
        if seal is not SYNTHETIC_ADMISSION_SEAL:
            raise ValueError("fixed authority-source admission required")
        require_readiness_root(root)
        self.grant = grant
        self.root = root
        self.authority_sha256 = digest(grant)
        self.plan = build_operational_plan(make_candidate())
        self.bound = {"/": grant.existing_root}
        self.owned: dict[str, Snapshot] = {}
        self.checks: dict[str, Result] = {}
        self.controls: dict[str, Result] = {}
        self.records: list[JournalRecord] = []
        self.pending: WorkOrder | None = None
        self.stopped = False
        self.cursor = 0
        self.tasks = self._tasks()

    def _tasks(self) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = [
            {"action": r["operation"], "path": r["path"]}
            for r in self.plan["topology"]["directory_operations"]
        ]
        for role in ("annotator-a", "annotator-b"):
            for area, mode in (("issue", "viewer"), ("submission", "editor")):
                tasks.append(
                    {
                        "action": "share",
                        "path": f"{PRIVATE_EXECUTION_ROOT}/{role}/{area}",
                        "share_role": role,
                        "share_mode": mode,
                    }
                )
        for row in self.plan["checks"]:
            if row["operation"] == "read":
                tasks.append(
                    {
                        "action": "prepare",
                        "path": row["operation_target"],
                        "probe_sha256": row["probe_sha256"],
                        "probe_content": row["probe_content_utf8"],
                    }
                )
        for row in self.plan["checks"]:
            tasks.append(
                {
                    "action": "check",
                    "path": row["operation_target"],
                    "actor": row["actor"],
                    "check_id": row["check_id"],
                    "expected": row["expected_outcome"],
                    "probe_sha256": row["probe_sha256"] if row["operation"] != "list" else None,
                    "probe_content": row["probe_content_utf8"]
                    if row["operation"] == "write"
                    else None,
                }
            )
        for control in ACCESS_POLICY_V2.application_controls:
            tasks.append(
                {
                    "action": "control",
                    "path": f"{PRIVATE_EXECUTION_ROOT}/{control.resource}",
                    "check_id": control.control_id,
                }
            )
        return tasks

    def _time(self, now: datetime) -> None:
        from .setup_synthetic import require_active_fixture

        require_active_fixture(self.grant, self.root)
        if now.tzinfo is None or not self.grant.not_before <= now < self.grant.not_after:
            raise ValueError("stale/not-yet-valid authority")

    def _ancestors(self, path: str) -> tuple[Snapshot, ...]:
        names = [str(p) for p in reversed(PurePosixPath(path).parents)]
        if path == "/":
            names = []
        if path in self.bound:
            names.append(path)
        return tuple(self.bound[n] for n in names)

    def _next_order(self, now: datetime) -> WorkOrder | None:
        self._time(now)
        if self.pending:
            raise ValueError("pending intention; reconcile evidence, never redispatch")
        if self.stopped:
            raise ValueError("stopped; preserved failure/inconclusive evidence")
        if self.cursor < len(self.tasks):
            task = self.tasks[self.cursor].copy()
        elif self.owned:
            task = {"action": "cleanup", "path": next(iter(self.owned))}
        else:
            return None
        actor = task.pop("actor", "coordinator")
        order = WorkOrder.model_validate(
            dict(
                authority_sha256=self.authority_sha256,
                run_id=self.grant.run_id,
                sequence=self.cursor + 1,
                session=next(s for s in self.grant.sessions if s.actor == actor),
                before=self._ancestors(task["path"]),
                issued_at=now,
                capability_evidence=self.grant.capabilities,
                **task,
            )
        )
        return order

    def next(self, now: datetime) -> WorkOrder | None:
        order = self._next_order(now)
        if order is None:
            return None
        self._append("intent", order, None, None, now)
        self.pending = order
        return order

    def _result(self, order: WorkOrder, ev: OperationEvidence, now: datetime) -> Result:
        if (ev.order_sha256, ev.sequence, ev.run_id) != (
            digest(order),
            order.sequence,
            self.grant.run_id,
        ):
            raise ValueError("receipt order/run/sequence mismatch")
        age = (now - ev.observed_at).total_seconds()
        context = (
            ev.session == order.session
            and ev.namespace == self.grant.namespace
            and ev.before == order.before
            and 0 <= age <= self.grant.observation_max_age_seconds
            and order.issued_at <= ev.observed_at <= now
            and ev.capability_evidence == self.grant.capabilities
        )
        if not context:
            return "BLOCKED" if order.action == "cleanup" else "INCONCLUSIVE"
        if order.action == "check":
            # No concealment semantics are installed by the fixed synthetic authority source.
            result = classify_access_observation(
                order.expected, ev.observation, context_verified=True
            )
            if ev.observation != "success":
                return result
            if order.probe_content is not None:
                return result if self._new_object(order, ev, "file") else "FAIL"
            target = order.before[-1]
            if ev.after != target or (
                order.probe_sha256 and target.content_sha256 != order.probe_sha256
            ):
                return "FAIL"
            return result
        if ev.observation != "success":
            return "BLOCKED" if order.action == "cleanup" else "INCONCLUSIVE"
        if order.action in ("create_new", "prepare"):
            return (
                "PASS"
                if self._new_object(
                    order, ev, "directory" if order.action == "create_new" else "file"
                )
                else "FAIL"
            )
        if order.action == "cleanup":
            obj = self.owned.get(order.path)
            if obj is None or order.before[-1] != obj or ev.after is not None:
                return "BLOCKED"
            return "PASS"
        if ev.after != order.before[-1]:
            return "FAIL"
        if order.action == "share" and (ev.share_role, ev.share_mode) != (
            order.share_role,
            order.share_mode,
        ):
            return "FAIL"
        if order.action == "control" and (
            ev.application_checks != ("overwrite_rejected", "prior_hash_preserved")
            or ev.application_before_sha256 is None
            or ev.application_before_sha256 != ev.application_after_sha256
            or ev.application_replacement != "conflict"
        ):
            return "FAIL"
        return "PASS"

    def _new_object(self, order: WorkOrder, ev: OperationEvidence, kind: str) -> bool:
        obj = ev.after
        return (
            obj is not None
            and order.path not in self.bound
            and obj.path == order.path
            and obj.kind == kind
            and obj.parent_id == order.before[-1].resource_id
            and obj.namespace == self.grant.namespace
            and obj.owner_run == self.grant.run_id
            and obj.content_sha256 == order.probe_sha256
            and obj.resource_id not in {b.resource_id for b in self.bound.values()}
        )

    def submit(self, ev: OperationEvidence, now: datetime) -> Result:
        self._time(now)
        order = self.pending
        if order is None or (ev.order_sha256, ev.sequence, ev.run_id) != (
            digest(order),
            order.sequence,
            self.grant.run_id,
        ):
            raise ValueError("missing pending order, replay or substituted evidence")
        # Revalidate model instances too; model_copy/model_construct are not trust boundaries.
        ev = OperationEvidence.model_validate_json(ev.model_dump_json())
        result = self._result(order, ev, now)
        self._append("outcome", order, ev, result, now)
        self._accept(order, ev, result)
        return result

    def _accept(self, order: WorkOrder, ev: OperationEvidence, result: Result) -> None:
        if order.action == "check":
            assert order.check_id is not None
            self.checks[order.check_id] = result
        if order.action == "control":
            assert order.check_id is not None
            self.controls[order.check_id] = result
        if (
            result in ("PASS", "FAIL")
            and ev.observation == "success"
            and ev.after is not None
            and order.action in ("create_new", "prepare", "check")
            and self._new_object(order, ev, ev.after.kind)
        ):
            # An ACL failure must not hide a successfully created task-owned object.
            # INCONCLUSIVE context is not ownership proof; its raw evidence stays in the journal.
            self.bound[order.path] = ev.after
            if ev.after.kind == "file" and (
                order.action == "prepare" or order.probe_content is not None
            ):
                self.owned[order.path] = ev.after
        if result == "PASS" and order.action == "cleanup":
            del self.owned[order.path]
            del self.bound[order.path]
        self.stopped |= result != "PASS"
        self.cursor += 1
        self.pending = None

    def _append(
        self,
        kind: Literal["intent", "outcome"],
        order: WorkOrder,
        evidence: OperationEvidence | None,
        result: Result | None,
        now: datetime,
    ) -> None:
        record = JournalRecord(
            sequence=len(self.records) + 1,
            previous_sha256=digest(self.records[-1]) if self.records else None,
            kind=kind,
            order=order,
            evidence=evidence,
            result=result,
            recorded_at=now,
        )
        publish_new(
            self.root,
            f"{record.sequence:06d}.json",
            canonical_json_bytes(record.model_dump(mode="json")) + b"\n",
        )
        self.records.append(record)

    def restore(self) -> None:
        """Revalidate immutable ordered records; an unmatched intent stays pending/UNKNOWN."""
        with DirectoryLease.acquire(self.root) as directory:
            names = sorted(directory.list_child_names())
        for name in names:
            with (
                DirectoryLease.acquire(self.root) as directory,
                directory.open_child_read(name) as stream,
            ):
                raw = stream.read()
            evidence_json(raw)
            r = JournalRecord.model_validate_json(raw)
            if (
                name != f"{len(self.records) + 1:06d}.json"
                or r.sequence != len(self.records) + 1
                or r.previous_sha256 != (digest(self.records[-1]) if self.records else None)
                or raw != canonical_json_bytes(r.model_dump(mode="json")) + b"\n"
                or r.order.authority_sha256 != self.authority_sha256
            ):
                raise ValueError("journal chain/authority mismatch")
            if r.kind == "intent":
                if (
                    r.order != self._next_order(r.recorded_at)
                    or r.evidence is not None
                    or r.result is not None
                ):
                    raise ValueError("invalid/replayed intent")
                self.pending = r.order
            else:
                if r.order != self.pending or r.evidence is None:
                    raise ValueError("outcome without exact pending intent")
                self._time(r.recorded_at)
                expected = self._result(r.order, r.evidence, r.recorded_at)
                if expected != r.result:
                    raise ValueError("asserted journal result differs from evidence")
                self._accept(r.order, r.evidence, expected)
            self.records.append(r)

    def summary(self) -> dict[str, Any]:
        expected = {r.check_id for r in ACCESS_POLICY_V2.acl_expectations}
        controls = {r.control_id for r in ACCESS_POLICY_V2.application_controls}
        complete = (
            not self.pending
            and not self.stopped
            and not self.owned
            and set(self.checks) == expected
            and set(self.controls) == controls
            and all(v == "PASS" for v in (*self.checks.values(), *self.controls.values()))
        )
        return {
            "label": "SYNTHETIC_ONLY",
            "complete": complete,
            "checks": {s: list(self.checks.values()).count(s) for s in set(self.checks.values())},
            "not_run": sorted(expected - self.checks.keys()),
            "application_controls": len(self.controls),
            "pending": "UNKNOWN" if self.pending else None,
            "cleanup_outstanding": len(self.owned),
            "operational_approvals": 0,
        }


def setup_schema_bytes() -> bytes:
    """Additive operational shapes, outside frozen scientific/benchmark versions."""
    schema = TypeAdapter(
        SetupAuthorization | WorkOrder | OperationEvidence | JournalRecord
    ).json_schema()
    return (json.dumps(schema, sort_keys=True, indent=2) + "\n").encode()


def export_setup_schema(root: Path) -> Path:
    """Export only the additive operational family, including temporary gate fixtures."""
    path = root / "execution" / "setup_bridge_v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(setup_schema_bytes())
    return path
