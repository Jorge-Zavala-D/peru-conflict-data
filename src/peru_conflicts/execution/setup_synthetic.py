"""Fixed synthetic authority source and in-memory provider. Never accepts a live adapter.

Run with ``python -m peru_conflicts.execution.setup_synthetic``. All identities,
sessions, capability assertions and grants below are test fixtures, not owner evidence.
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .access_policy import ACCESS_EXPECTATIONS_BY_ID
from .operational_plan import build_setup_request, make_candidate
from .references import sha256
from .setup_bridge import (
    REAL_GRANTS as REAL_GRANTS,
)
from .setup_bridge import (
    SYNTHETIC_ADMISSION_SEAL,
    OperationEvidence,
    Session,
    SetupAuthorization,
    SetupBridge,
    Snapshot,
    WorkOrder,
    digest,
    implementation_digest,
    parse_authorization,
)
from .setup_bridge import (
    production_admission as production_admission,
)

NOW = datetime(2026, 9, 22, 12, tzinfo=UTC)
REVOKED_SYNTHETIC_GRANTS: frozenset[str] = frozenset()
_REGISTERED: dict[str, str] = {}


def _store_id(root: Path) -> str:
    return "synthetic-" + sha256(str(root.absolute()).encode())


def proposal() -> tuple[bytes, dict[str, bytes]]:
    req, parts = build_setup_request(make_candidate())
    return (json.dumps(req, sort_keys=True, ensure_ascii=True, indent=2) + "\n").encode(), parts


def fixture_bytes(store_id: str = "synthetic-fixture") -> bytes:
    """Fixed independent TEST source, not caller-selected trust or a real registry.

    Source pins here detect changes within a demonstration, not owner approval.
    No CLI/environment switch can convert this fixture into production authority.
    """
    raw, parts = proposal()
    req = json.loads(raw)
    topology = json.loads(parts["topology.json"])
    return (
        SetupAuthorization(
            label="SYNTHETIC_ONLY",
            approved="SYNTHETIC_FIXTURE_NOT_OWNER_APPROVAL",
            grant_id=store_id,
            run_id=store_id,
            evidence_store_id=store_id,
            request_raw_sha256=sha256(raw),
            components={n: sha256(b) for n, b in parts.items()},
            candidate_sha256=req["candidate_model_sha256"],
            access_policy_sha256=req["access_policy_sha256"],
            implementation_sha256=implementation_digest(),
            root=topology["root"],
            namespace="synthetic-home",
            existing_root=Snapshot(
                path="/",
                resource_id="synthetic-root",
                version="synthetic-v1",
                namespace="synthetic-home",
                parent_id=None,
                kind="directory",
            ),
            absent_paths=tuple(r["path"] for r in topology["directory_operations"][1:]),
            sessions=tuple(
                Session(
                    actor=a,
                    account=f"synthetic-account-{a}",
                    session=f"synthetic-session-{a}",
                    private_evidence_sha256=sha256(a.encode()),
                )
                for a in ("coordinator", "annotator-a", "annotator-b")
            ),
            private_binding_evidence={
                k: sha256(("synthetic-" + k).encode()) for k in req["private_bindings"]
            },
            custody_evidence_sha256=sha256(b"synthetic-private-custody"),
            capabilities={
                k: sha256(("synthetic-reviewed-" + k).encode())
                for k in (
                    "conditional_parent_identity",
                    "exclusive_create_no_autorename",
                    "conditional_delete_identity_version",
                    "independent_sessions",
                    "private_membership_and_links",
                    "application_no_replace",
                )
            },
            operations=(
                "assert_existing",
                "create_new",
                "share",
                "prepare",
                "check",
                "control",
                "cleanup",
            ),
            not_before=NOW,
            not_after=NOW.replace(day=23),
            observation_max_age_seconds=300,
            use_policy="one_run_no_redispatch",
        )
        .model_dump_json()
        .encode()
    )


def _admit(raw: bytes, root: Path) -> SetupAuthorization:
    request, parts = proposal()
    grant = parse_authorization(raw, request, parts)
    if raw != fixture_bytes(_store_id(root)):
        raise ValueError("not registered in fixed SYNTHETIC_ONLY authority source")
    if grant.grant_id in REVOKED_SYNTHETIC_GRANTS:
        raise ValueError("synthetic grant revoked")
    _REGISTERED[grant.grant_id] = digest(grant)
    return grant


def require_active_fixture(grant: SetupAuthorization, root: Path) -> None:
    """Only fixed test source admission, not a caller-supplied trust object."""
    if grant.grant_id in REVOKED_SYNTHETIC_GRANTS:
        raise ValueError("synthetic grant revoked")
    if (
        grant.evidence_store_id != _store_id(root)
        or _REGISTERED.get(grant.grant_id) != digest(grant)
        or grant.implementation_sha256 != implementation_digest()
    ):
        raise ValueError("missing/stale synthetic authority source or wrong use scope")


def create_demo(root: Path, *, grant_raw: bytes | None = None) -> tuple[SetupBridge, FakeProvider]:
    grant = _admit(fixture_bytes(_store_id(root)) if grant_raw is None else grant_raw, root)
    # Exclusive run root claims this synthetic fixture's use in that evidence store.
    # There is deliberately no claim of global production anti-rollback/one-use custody.
    if root.exists():
        raise ValueError("synthetic use already claimed; resume exact store instead")
    if (
        root.parent.resolve(strict=True) != root.parent.absolute()
        or not root.absolute().is_relative_to(Path(tempfile.gettempdir()).resolve())
        or not any(p.startswith("m2-readiness-") for p in root.parts)
    ):
        raise ValueError("synthetic store must be a dedicated unaliased temporary child")
    root.mkdir()
    run = SetupBridge(grant, root, seal=SYNTHETIC_ADMISSION_SEAL)
    return run, FakeProvider(grant)


def resume_demo(root: Path) -> SetupBridge:
    run = SetupBridge(
        _admit(fixture_bytes(_store_id(root)), root), root, seal=SYNTHETIC_ADMISSION_SEAL
    )
    run.restore()
    return run


class FakeProvider:
    """In-memory single-writer conditional operations; NOT proof of Dropbox semantics."""

    def __init__(self, grant: SetupAuthorization) -> None:
        self.grant = grant
        self.objects = {"/": grant.existing_root}
        self.counter = 0
        self.dispatches = 0
        self.grants: dict[tuple[str, str], str] = {}
        self.application_bytes: dict[str, bytes] = {}

    def execute(self, order: WorkOrder | None, *, fault: str | None = None) -> OperationEvidence:
        if order is None:
            raise ValueError("no admissible work order")
        self.dispatches += 1
        before = tuple(self.objects[s.path] for s in order.before if s.path in self.objects)
        after = self.objects.get(order.path)
        if after is not None and all(s.path != order.path for s in before):
            before = (*before, after)
        observation = "success"
        capabilities = self.grant.capabilities.copy()
        session = order.session
        namespace = self.grant.namespace
        app_before = app_after = None
        app_replacement = None
        if fault == "namespace":
            namespace = "synthetic-other"
        if fault == "session":
            session = session.model_copy(update={"session": "synthetic-other-session"})
        if fault == "parent":
            before = (
                *before[:-1],
                before[-1].model_copy(update={"resource_id": "synthetic-moved"}),
            )
        if fault == "no_conditional":
            capabilities.pop("conditional_delete_identity_version")
        if fault in ("replacement", "wrong_owner", "wrong_bytes"):
            assert after is not None
            field, value = {
                "replacement": ("version", "synthetic-replaced"),
                "wrong_owner": ("owner_run", "synthetic-other-run"),
                "wrong_bytes": ("content_sha256", sha256(b"other")),
            }[fault]
            after = after.model_copy(update={field: value})
            self.objects[order.path] = after
            before = (*before[:-1], after)
        valid = (
            before == order.before
            and namespace == self.grant.namespace
            and session == order.session
            and capabilities == self.grant.capabilities
        )
        if fault == "network":
            observation = "network_error"
        elif fault == "not_found":
            observation = "not_found"
        elif not valid or fault == "collision":
            observation = "conflict"
        elif order.action == "cleanup":
            if after is None or after.owner_run != self.grant.run_id:
                observation = "conflict"
            else:
                del self.objects[order.path]
                after = None
        elif order.action == "share":
            assert order.share_role is not None and order.share_mode is not None
            self.grants[(order.share_role, order.path)] = order.share_mode
        elif order.action == "control":
            # Exercise immutable application storage, not an ACL permission assertion.
            self.application_bytes[order.path] = b"SYNTHETIC accepted bytes"
            app_before = sha256(self.application_bytes[order.path])
            try:
                self._application_publish_new(order.path, b"replacement")
                app_replacement = "success"
            except FileExistsError:
                app_replacement = "conflict"
            app_after = sha256(self.application_bytes[order.path])
        else:
            row = ACCESS_EXPECTATIONS_BY_ID.get(order.check_id or "")
            mode = (
                self.grants.get((session.actor, f"{self.grant.root}/{row.resource}"))
                if row
                else None
            )
            allowed = session.actor == "coordinator" or (
                row is not None
                and mode in ("viewer", "editor")
                and (row.operation != "write" or mode == "editor")
            )
            denied = row is not None and not allowed and fault != "unexpected_allow"
            creates = order.action in ("create_new", "prepare") or (
                order.action == "check" and row is not None and row.operation == "write"
            )
            if denied:
                observation = "authorization_denied"
            elif creates:
                if after is not None:
                    observation = "conflict"
                else:
                    self.counter += 1
                    parent = self.objects[str(PurePosixPath(order.path).parent)]
                    after = Snapshot(
                        path=order.path,
                        resource_id=f"synthetic-object-{self.counter}",
                        version="synthetic-v1",
                        namespace=self.grant.namespace,
                        parent_id=parent.resource_id,
                        kind="directory" if order.action == "create_new" else "file",
                        content_sha256=order.probe_sha256,
                        owner_run=self.grant.run_id,
                    )
                    self.objects[order.path] = after
            elif after is None:
                observation = "not_found"
        payload: dict[str, Any] = dict(
            label="SYNTHETIC_ONLY",
            order_sha256=digest(order),
            run_id=order.run_id,
            sequence=order.sequence,
            session=session,
            namespace=namespace,
            observed_at=NOW,
            observation=observation,
            before=before,
            after=after,
            capability_evidence=capabilities,
            application_checks=("overwrite_rejected", "prior_hash_preserved")
            if order.action == "control"
            else (),
            application_before_sha256=app_before,
            application_after_sha256=app_after,
            application_replacement=app_replacement,
            share_role=order.share_role,
            share_mode=order.share_mode,
        )
        # JSON transport roundtrip uses the same strict decoder as manual returned evidence.
        source = json.dumps(
            payload,
            sort_keys=True,
            default=lambda v: (
                v.isoformat().replace("+00:00", "Z")
                if isinstance(v, datetime)
                else v.model_dump(mode="json")
            ),
        )
        payload = json.loads(source)
        payload.update(source_evidence=source, source_sha256=sha256(source.encode()))
        return OperationEvidence.model_validate_json(json.dumps(payload))

    def _application_publish_new(self, path: str, data: bytes) -> None:
        if path in self.application_bytes:
            raise FileExistsError(path)
        self.application_bytes[path] = data


def demonstrate(root: Path) -> dict[str, Any]:
    run, provider = create_demo(root)
    while (order := run.next(NOW)) is not None:
        run.submit(provider.execute(order), NOW)
    result = run.summary()
    result["created_directories"] = sum(
        o.kind == "directory" for p, o in provider.objects.items() if p != "/"
    )
    result["remaining_probes"] = sum(o.kind == "file" for o in provider.objects.values())
    return result


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="m2-readiness-setup-") as temp:
        root = Path(temp)
        success = demonstrate(root / "success")
        run, provider = create_demo(root / "collision")
        run.submit(provider.execute(run.next(NOW)), NOW)
        run.submit(provider.execute(run.next(NOW), fault="collision"), NOW)
        production = "ERROR: production admission unexpectedly returned"
        try:
            production_admission(fixture_bytes())
        except ValueError as error:
            production = str(error)
        print(
            json.dumps(
                {
                    "success": success,
                    "stopped_collision": run.summary(),
                    "production_rejection": production,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    # -m loads this file as __main__; use the same registry the bridge imports.
    from .setup_synthetic import main as run_example

    run_example()
