"""Exclusive original evidence and publication components; no admitted live sink.

Trusted administrators can restore both a run and its independent checkpoint.
Local hashes cannot protect against that trust-model violation.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from contextlib import ExitStack, suppress
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from peru_conflicts.acquisition.fs_safety import DirectoryLease, DirectoryLeaseError
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Sha256, StrictModel

from .references import sha256
from .setup_authority import SetupGrantV2
from .setup_bridge import digest
from .setup_context import require_context
from .setup_dropbox import (
    PROBE,
    BoundObservation,
    FileObservation,
    FolderObservation,
    OriginalCapture,
    PreparedRequest,
    RealWorkOrder,
    ValidatedOutcome,
    classify_capture,
    cleanup_arguments,
    encode_request,
)


def require_offline_root(root: Path) -> None:
    """Synthetic-only boundary; never admits a real private sink or arbitrary path."""
    absolute = root.absolute()
    with ExitStack() as stack:
        directory = stack.enter_context(DirectoryLease.acquire(Path(absolute.anchor)))
        for part in absolute.parent.parts[1:]:
            directory = stack.enter_context(directory.acquire_child(part))
        temporary = Path(tempfile.gettempdir()).resolve(strict=True)
        if not directory.resolved.is_relative_to(temporary) or not any(
            p.startswith("m2-readiness-") for p in absolute.parts
        ):
            raise ValueError("dedicated OFFLINE temporary child required")


def publish(directory: DirectoryLease, name: str, raw: bytes) -> None:
    """Reuse retained-directory, no-replace, sync and readback primitives."""
    with directory.open_child_exclusive(name) as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory.sync_directory()
    with directory.open_child_read(name) as stream:
        if stream.read() != raw:
            raise ValueError("partial evidence retained; UNKNOWN")


def reject_credential_fields(raw: bytes) -> None:
    """Defense in depth for the admitted secret-free ingress, not a secret detector.

    Inspect JSON key tokens even in malformed originals, and decoded capture hex
    fields. Semantic parsing still follows durable retention. Arbitrary response
    bytes cannot be certified secret-free by this check; the trusted source must
    exclude credentials before capture.
    """
    pending = [raw]
    inspected = 0
    while pending:
        value = pending.pop()
        inspected += len(value)
        if inspected > 16777216:
            raise ValueError("credential exclusion inspection bound exceeded")
        for match in re.finditer(rb'("(?:[^"\\]|\\.)*")\s*:', value):
            try:
                key = json.loads(match[1]).casefold()
            except (ValueError, UnicodeError):
                continue
            if key in {
                "authorization",
                "proxy-authorization",
                "cookie",
                "set-cookie",
                "access_token",
                "refresh_token",
                "client_secret",
            }:
                raise ValueError("credential-bearing field prohibited before retention")
            encoded = re.match(rb'\s*("(?:[^"\\]|\\.)*")', value[match.end() :])
            if encoded is not None:
                with suppress(ValueError, UnicodeError):
                    decoded = json.loads(encoded[1])
                    if key.endswith("_hex"):
                        pending.append(bytes.fromhex(decoded))
                    elif '"' in decoded:
                        pending.append(decoded.encode("utf-8"))


class ComponentReceipt(StrictModel):
    control_id: Literal["APP-ACCEPTED-BYTES-A", "APP-ACCEPTED-BYTES-B"]
    level: Literal["COMPONENT"] = "COMPONENT"
    original_sha256: Sha256
    preserved_sha256: Sha256
    supersession_sha256: Sha256
    replacement: Literal["FileExistsError"]
    live_path_coverage: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"
    logical_resource: str
    primitive_source_sha256: Sha256
    procedure_source_sha256: Sha256
    executable_sha256: Sha256
    executable_version: str
    isolated_store_sha256: Sha256


def application_control(root: Path, control_id: str) -> ComponentReceipt:
    """Run actual no-replace/supersession primitives on disposable synthetic bytes."""
    require_offline_root(root)
    from peru_conflicts.acquisition import fs_safety

    from .access_policy import ACCESS_POLICY_V2

    if control_id not in ("APP-ACCEPTED-BYTES-A", "APP-ACCEPTED-BYTES-B"):
        raise ValueError("unknown application control")
    # Caller must supply the already admitted offline temporary component store.
    original = b"OFFLINE SYNTHETIC accepted component bytes\n"
    with (
        DirectoryLease.acquire(root) as parent,
        parent.acquire_child(control_id, create=True) as directory,
    ):
        isolated_store_sha256 = sha256(str(directory.resolved).encode())
        publish(directory, "accepted.json", original)
        try:
            publish(directory, "accepted.json", b"different synthetic bytes")
        except DirectoryLeaseError as error:
            if not isinstance(error.__cause__, FileExistsError):
                raise
        else:
            raise ValueError("no-replace primitive failed")
        with directory.open_child_read("accepted.json") as stream:
            preserved = stream.read()
        if preserved != original:
            raise ValueError("original changed")
        supersession = canonical_json_bytes(
            {
                "label": "OFFLINE_SYNTHETIC_COMPONENT",
                "predecessor_sha256": sha256(original),
                "replacement": "new identity",
            }
        )
        publish(directory, "supersession.json", supersession)
        with directory.open_child_read("accepted.json") as stream:
            if stream.read() != original:
                raise ValueError("supersession changed predecessor")
    return ComponentReceipt.model_validate(
        {
            "control_id": control_id,
            "original_sha256": sha256(original),
            "preserved_sha256": sha256(preserved),
            "supersession_sha256": sha256(supersession),
            "replacement": "FileExistsError",
            "logical_resource": next(
                c.resource
                for c in ACCESS_POLICY_V2.application_controls
                if c.control_id == control_id
            ),
            "primitive_source_sha256": sha256(Path(fs_safety.__file__).read_bytes()),
            "procedure_source_sha256": sha256(Path(__file__).read_bytes()),
            "executable_sha256": sha256(Path(sys.executable).read_bytes()),
            "executable_version": sys.version.split()[0],
            "isolated_store_sha256": isolated_store_sha256,
        }
    )


class EvidenceJournal:
    """Exclusive immutable records plus a separately retained high-water index.

    Construction is internal to an admitted source (currently offline only). A
    checkpoint mismatch is a stop, never an opportunity to reconstruct/reset it.
    No method dispatches or retries operations. An unmatched intent is UNKNOWN.
    """

    def __init__(self, root: Path, checkpoint: Path, admission: object, *, create: bool) -> None:
        # Reuse kernel locking implementation, not any M1 authority or ledger state.
        from peru_conflicts.acquisition.persistent_ledger import (
            _KernelLock,  # pyright: ignore[reportPrivateUsage]
        )

        # Validate independent admission before acquiring any private directory.
        context = require_context(admission)
        grant = context.check(root, checkpoint)
        from .operational_plan import build_operational_plan, make_candidate

        # Immutable per-admission source snapshot, not caller-supplied procedure state.
        self._plan_bytes = canonical_json_bytes(build_operational_plan(make_candidate()))
        self._admission = context
        self._closed = False
        self._root, self._checkpoint = root, checkpoint
        self._grant_bytes = grant.model_dump_json().encode()
        authority_sha256 = digest(grant)

        if (
            root.resolve() == checkpoint.resolve()
            or root in checkpoint.parents
            or checkpoint in root.parents
        ):
            raise ValueError("checkpoint must be independent of replaceable run store")
        context.validate_store(root, checkpoint)
        self._stack = ExitStack()
        try:
            self._store = self._stack.enter_context(DirectoryLease.acquire(root))
            self._index = self._stack.enter_context(DirectoryLease.acquire(checkpoint))
            # Pin validation before acquisition cannot authenticate a later replacement.
            context.validate_store(root, checkpoint)
            self._store.require_bound()
            self._index.require_bound()
            stream = self._stack.enter_context(self._index.open_child_append("writer.lock"))
            lock = _KernelLock(stream)
            lock.acquire()
            self._stack.callback(lock.release)
            self._authority_sha256 = authority_sha256
            self._records: list[dict[str, Any]] = []
            self._outcomes: list[tuple[RealWorkOrder, ValidatedOutcome, str, datetime]] = []
            self._pending: RealWorkOrder | None = None
            self._consumed: set[str] = set()
            self._released: str | None = None
            self._stopped = False
            claim = canonical_json_bytes(
                {
                    "authority": authority_sha256,
                    "store": str(self._store.resolved),
                    "checkpoint": str(self._index.resolved),
                }
            )
            if create:
                if self._store.list_child_names():
                    raise ValueError("new store must be empty")
                publish(self._index, "claim.json", claim)
                publish(self._store, "claim.json", claim)
            for directory in (self._store, self._index):
                with directory.open_child_read("claim.json") as source:
                    if source.read() != claim:
                        raise ValueError("grant/use claim mismatch")
            names = sorted(n for n in self._store.list_child_names() if n != "claim.json")
            anchors = sorted(
                n for n in self._index.list_child_names() if n not in ("claim.json", "writer.lock")
            )
            if names != anchors:
                raise ValueError("checkpoint mismatch: interrupted publication/rollback")
            for name in names:
                with self._store.open_child_read(name) as source:
                    raw = source.read()
                with self._index.open_child_read(name) as source:
                    if source.read() != sha256(raw).encode():
                        raise ValueError("checkpoint head mismatch")
                from .operational_plan import evidence_json

                record = evidence_json(raw)
                if (
                    record["previous"]
                    != (sha256(canonical_json_bytes(self._records[-1])) if self._records else None)
                    or name != f"{len(self._records) + 1:06d}.json"
                    or record["authority"] != authority_sha256
                    or raw != canonical_json_bytes(record)
                ):
                    raise ValueError("journal chain mismatch")
                self._apply(record, replay_grant=grant)
                self._records.append(record)
            self._check_admission()
            context.attach(self.consume)
        except BaseException:
            self._stack.close()
            raise

    def close(self) -> None:
        self._closed = True
        self._admission.detach()
        self._stack.close()

    @property
    def authority_sha256(self) -> str:
        return self._authority_sha256

    def _check_admission(self):
        if self._closed:
            raise ValueError("admitted writer is closed")
        grant = self._admission.check(self._root, self._checkpoint)
        if grant.model_dump_json().encode() != self._grant_bytes:
            raise ValueError("admission changed during active run")
        return grant

    def preview(self) -> RealWorkOrder:
        """Detached non-dispatchable proposal. Only next/release publishes intent."""
        grant = self._check_admission()
        return self._propose(self._admission.now(), grant)

    def _propose(self, now: datetime, grant: SetupGrantV2) -> RealWorkOrder:
        from .access_policy import ACCESS_POLICY_V2
        from .operational_plan import PRIVATE_EXECUTION_ROOT

        if self._pending or self._stopped:
            raise ValueError("UNKNOWN/stopped: no redispatch")
        if not grant.not_before <= now < grant.not_after:
            raise ValueError("intent outside admitted validity")
        plan = json.loads(self._plan_bytes)
        # Ordered scope comes from retained source objects, never caller work orders.
        steps: list[tuple[str, str, str, str | None, str]] = [
            ("root", "/", actor, None, "ALLOW")
            for actor in ("coordinator", "annotator-a", "annotator-b")
        ]
        steps.extend(
            ("create", row["path"], "coordinator", None, "ALLOW")
            for row in plan["topology"]["directory_operations"][1:]
        )
        for actor in ("annotator-a", "annotator-b"):
            for area in ("issue", "submission"):
                path = f"{PRIVATE_EXECUTION_ROOT}/{actor}/{area}"
                steps.extend(
                    (
                        action,
                        path,
                        actor if action in ("mount", "mount_verify") else "coordinator",
                        None,
                        "ALLOW",
                    )
                    for action in (
                        "share",
                        "invite",
                        "mount",
                        "mount_verify",
                        "membership",
                        "links",
                    )
                )
        steps.extend(
            ("prepare", row["operation_target"], "coordinator", None, "ALLOW")
            for row in plan["checks"]
            if row["operation"] == "read"
        )
        steps.extend(
            (
                row["operation"],
                row["operation_target"],
                row["actor"],
                row["check_id"],
                row["expected_outcome"],
            )
            for row in plan["checks"]
        )
        steps.extend(
            ("control", f"{PRIVATE_EXECUTION_ROOT}/{c.resource}", "coordinator", None, "ALLOW")
            for c in ACCESS_POLICY_V2.application_controls
        )
        bound: dict[str, BoundObservation] = {}
        owned: dict[str, FileObservation] = {}
        all_owned: dict[str, FileObservation] = {}
        fresh_metadata: dict[str, tuple[FileObservation, datetime]] = {}
        fresh_reads: dict[str, tuple[FileObservation, datetime]] = {}
        shares: dict[str, str] = {}
        proposed_mounts: dict[tuple[str, str], str] = {}
        mounts: dict[tuple[str, str], str] = {}
        roots: dict[str, datetime] = {}
        pending_job: tuple[str, str, int] | None = None
        cursor = 0
        # Decode once at durable append/replay. These private values never escape;
        # outward orders and forensic records remain detached serializations.
        for prior, result, original_sha256, observed_at in self._outcomes:
            if result.result == "PENDING":
                if prior.action not in ("share", "share_status") or not result.async_job_id:
                    raise ValueError("unbound pending operation")
                attempts = pending_job[2] + 1 if pending_job else 0
                pending_job = (prior.logical_path, result.async_job_id, attempts)
                continue
            if result.result != "PASS":
                raise ValueError("stopped outcome cannot authorize another order")
            cursor += 1
            if prior.action == "root":
                roots[prior.actor.actor] = observed_at
            if prior.action in ("share", "share_status"):
                if not result.shared_folder_id:
                    raise ValueError("missing share identity")
                shares[prior.logical_path] = result.shared_folder_id
                pending_job = None
            if prior.action == "mount" and result.mount_locator:
                proposed_mounts[prior.actor.actor, prior.logical_path] = result.mount_locator
            if prior.action == "mount_verify" and result.mount_locator:
                mounts[prior.actor.actor, prior.logical_path] = result.mount_locator
            if prior.action in ("create", "prepare", "write") and isinstance(
                result.after, FolderObservation | FileObservation
            ):
                bound[prior.logical_path] = BoundObservation(
                    namespace=prior.namespace,
                    logical_path=prior.logical_path,
                    observation=result.after,
                    ancestor_ids=tuple(
                        b.observation.id
                        for b in prior.before
                        if isinstance(b.observation, FolderObservation)
                    ),
                    observed_at=observed_at,
                    original_capture_sha256=original_sha256,
                )
                if isinstance(result.after, FileObservation):
                    owned[prior.logical_path] = result.after
                    all_owned[prior.logical_path] = result.after
            if prior.action == "cleanup_metadata" and isinstance(result.after, FileObservation):
                fresh_metadata[prior.logical_path] = (result.after, observed_at)
            if prior.action == "cleanup_read" and isinstance(result.after, FileObservation):
                fresh_reads[prior.logical_path] = (result.after, observed_at)
            if prior.action == "cleanup":
                owned.pop(prior.logical_path, None)
                bound.pop(prior.logical_path, None)
        completed = sum(r["kind"] == "intent" for r in self._records)
        steps.extend(
            (action, path, "coordinator", None, "ALLOW")
            for path in all_owned
            for action in ("cleanup_metadata", "cleanup_read", "cleanup")
        )
        # Account observations are part of the protected procedure, including
        # return handoffs to the coordinator; actor labels never stand in for them.
        handoff_steps: list[tuple[str, str, str, str | None, str]] = []
        previous_actor = None
        for step in steps:
            if step[0] != "root" and step[2] != previous_actor:
                handoff_steps.append(("root", "/", step[2], None, "ALLOW"))
            handoff_steps.append(step)
            previous_actor = step[2]
        steps = handoff_steps
        if cursor >= len(steps):
            if owned or pending_job:
                raise ValueError("unresolved ownership/pending obligations")
            raise StopIteration("OFFLINE procedure complete; no real acceptance")
        if pending_job:
            if pending_job[2] >= 3:
                raise ValueError("pending share status observation bound exhausted")
            path, job, _ = pending_job
            action, actor, check_id, expected = "share_status", "coordinator", None, "ALLOW"
        else:
            action, path, actor, check_id, expected = steps[cursor]
            job = None
        binding = next(s for s in grant.sessions if s.actor == actor)
        expected_account, namespace = self._admission.actor(binding)
        if action != "root" and (
            actor not in roots or (now - roots[actor]).total_seconds() > grant.freshness_seconds
        ):
            raise ValueError("fresh actor account context required")
        ancestors = [str(p) for p in reversed(PurePosixPath(path).parents)]
        before = tuple(bound[p] for p in (*ancestors, path) if p in bound)
        target = bound.get(path)
        if action in ("cleanup_metadata", "cleanup_read", "cleanup") and (
            grant.cleanup_scope != "receipt_owned_files_only" or path not in owned
        ):
            raise ValueError("cleanup lacks scope or receipt ownership")
        if action in ("cleanup_read", "cleanup"):
            observed = fresh_metadata.get(path)
            if (
                not observed
                or not 0 <= (now - observed[1]).total_seconds() <= grant.freshness_seconds
            ):
                raise ValueError("cleanup blocked: missing/stale current metadata")
            cleanup_arguments(owned[path], observed[0], owned_logical_path=path)
            if target is None:
                raise ValueError("missing ownership relationship")
            target = target.model_copy(update={"observation": observed[0]})
        if action == "cleanup":
            read = fresh_reads.get(path)
            if not read or not 0 <= (now - read[1]).total_seconds() <= grant.freshness_seconds:
                raise ValueError("cleanup blocked: missing/stale exact-byte observation")
            cleanup_arguments(owned[path], read[0], owned_logical_path=path)
            if read[0] != fresh_metadata[path][0]:
                raise ValueError("cleanup observations disagree")
        deadlines = [grant.not_after, now + timedelta(seconds=grant.freshness_seconds)]
        if action != "root":
            deadlines.append(roots[actor] + timedelta(seconds=grant.freshness_seconds))
        if action in ("cleanup_read", "cleanup"):
            deadlines.append(fresh_metadata[path][1] + timedelta(seconds=grant.freshness_seconds))
        if action == "cleanup":
            deadlines.append(fresh_reads[path][1] + timedelta(seconds=grant.freshness_seconds))
        route: str
        args: dict[str, Any]
        locator = path
        shared = shares.get(path)
        member_actor = PurePosixPath(path).parent.name
        coordinator = next(s for s in grant.sessions if s.actor == "coordinator")
        owner_account = self._admission.actor(coordinator)[0]
        expected_members = {owner_account: "owner"}
        if member_actor in ("annotator-a", "annotator-b"):
            member_binding = next(s for s in grant.sessions if s.actor == member_actor)
            member_account = self._admission.actor(member_binding)[0]
            expected_members[member_account] = "viewer" if path.endswith("/issue") else "editor"
        if action == "mount_verify":
            locator = proposed_mounts.get((actor, path), "")
            if not locator:
                raise ValueError("missing independently returned actor mount locator")
        elif actor != "coordinator" and action in ("list", "read", "write"):
            for (who, logical), observed in mounts.items():
                if who == actor and (path == logical or path.startswith(logical + "/")):
                    locator = observed + path[len(logical) :]
            if action == "write" and locator == path:
                parent = bound.get(str(PurePosixPath(path).parent))
                if parent is None or not isinstance(parent.observation, FolderObservation):
                    raise ValueError(
                        "inaccessible target has no independently bound parent locator"
                    )
                locator = parent.observation.id + "/" + PurePosixPath(path).name
        if action == "root":
            route, args = "users/get_current_account", {}
        elif action == "share_status":
            route, args = "sharing/check_share_job_status", {"async_job_id": job}
        elif action == "mount_verify":
            route, args = "files/get_metadata", {"path": locator, "include_deleted": False}
        elif action == "cleanup_metadata":
            route, args = "files/get_metadata", {"path": owned[path].id, "include_deleted": False}
        elif action == "cleanup_read":
            route, args = "files/download", {"path": owned[path].id}
        elif action == "cleanup":
            route, args = (
                "files/delete_v2",
                cleanup_arguments(owned[path], fresh_reads[path][0], owned_logical_path=path),
            )
        elif action == "control":
            route, args = "local/application_publication", {}
        elif action == "create":
            route, args = "files/create_folder_v2", {"path": path, "autorename": False}
        elif action in ("prepare", "write"):
            route, args = (
                "files/upload",
                {
                    "path": locator,
                    "mode": {".tag": "add"},
                    "autorename": False,
                    "strict_conflict": True,
                },
            )
        elif action in ("read", "list"):
            if target is None or not isinstance(
                target.observation, FolderObservation | FileObservation
            ):
                raise ValueError("missing observed target")
            route = "files/download" if action == "read" else "files/list_folder"
            args = {"path": target.observation.id}
            if action == "list":
                args.update(recursive=False, include_deleted=False)
        elif action == "share":
            if target is None or not isinstance(target.observation, FolderObservation):
                raise ValueError("share requires captured folder identity")
            route, args = (
                "sharing/share_folder",
                {"path": target.observation.id, "acl_update_policy": "owner", "force_async": False},
            )
        else:
            if not isinstance(shared, str) or not shared:
                raise ValueError("share identity unresolved")
            if action == "invite":
                member_binding = next(s for s in grant.sessions if s.actor == member_actor)
                member_account = self._admission.actor(member_binding)[0]
                route, args = (
                    "sharing/add_folder_member",
                    {
                        "shared_folder_id": shared,
                        "members": [
                            {
                                "member": {
                                    ".tag": "dropbox_id",
                                    "dropbox_id": member_account,
                                },
                                "access_level": {
                                    ".tag": "viewer" if path.endswith("/issue") else "editor"
                                },
                            }
                        ],
                        "quiet": False,
                    },
                )
            elif action == "mount":
                route, args = "sharing/mount_folder", {"shared_folder_id": shared}
            elif action == "membership":
                route, args = (
                    "sharing/list_folder_members",
                    {"shared_folder_id": shared, "limit": 1000},
                )
            elif action == "links":
                route, args = "sharing/list_shared_links", {"path": path, "direct_only": False}
            else:
                raise ValueError("unimplemented admitted transition")
        request = (
            PreparedRequest(
                route=route,
                scope="COMPONENT_ONLY",
                root_header="{}",
                api_arg=None,
                body_hex="7b7d",
                actor_session_ref=binding.session_ref,
            )
            if action == "control"
            else encode_request(
                route,
                args,
                namespace,
                binding.session_ref,
                upload=PROBE if action in ("prepare", "write") else None,
            )
        )
        return RealWorkOrder.model_validate(
            dict(
                authority_sha256=self.authority_sha256,
                run_ref=grant.run_ref,
                sequence=completed + 1,
                action=action,
                actor=binding,
                logical_path=path,
                namespace=namespace,
                actor_locator=locator,
                check_id=check_id,
                expected=expected,
                before=before,
                target=target,
                request=request,
                issued_at=now,
                dispatch_not_after=min(deadlines),
                expected_account_id=expected_account,
                shared_folder_id=shared,
                async_job_id=job,
                expected_member_roles=expected_members if action in ("mount", "membership") else {},
                # Complete TEST service index, not native Dropbox universal visibility.
                link_coverage=self._admission.link_coverage()
                if action == "links"
                else "not_established",
                control_id=next(
                    (
                        c.control_id
                        for c in ACCESS_POLICY_V2.application_controls
                        if path == f"{PRIVATE_EXECUTION_ROOT}/{c.resource}"
                    ),
                    None,
                )
                if action == "control"
                else None,
            )
        )

    def next(self) -> RealWorkOrder:
        """Synchronize original intent before releasing the admitted next request."""
        return self.release(self.preview())

    def run_component(self) -> ValidatedOutcome:
        """Execute only the admitted pending local control; no imported PASS or provider call."""
        self._check_admission()
        order = self._pending
        if order is None or order.action != "control" or not order.control_id:
            raise ValueError("no admitted local component intent")
        self.consume(order)
        receipt = application_control(self._admission.component_store(), order.control_id)
        raw = receipt.model_dump_json().encode()
        self._append(
            "capture", order, {"original_hex": raw.hex(), "source": "local_publication_primitive"}
        )
        outcome = ValidatedOutcome(
            result="PASS", reason="COMPONENT/OFFLINE only", component_sha256=sha256(raw)
        )
        self._append("outcome", order, outcome.model_dump(mode="json"))
        return outcome

    @property
    def pending(self) -> RealWorkOrder | None:
        return self._pending.model_copy(deep=True) if self._pending else None

    @property
    def stopped(self) -> bool:
        return self._stopped

    @property
    def records(self) -> list[dict[str, Any]]:
        return json.loads(json.dumps(self._records))

    def _apply(self, record: dict[str, Any], *, replay_grant: SetupGrantV2 | None = None) -> None:
        order = RealWorkOrder.model_validate_json(json.dumps(record["order"]))
        if record["kind"] == "intent":
            if self._pending or self._stopped or order.authority_sha256 != self.authority_sha256:
                raise ValueError("invalid/replayed intent")
            # Historical orders use the grant verified before acquisition/replay.
            # Construction rechecks live authority after replay, before attaching
            # the consumer; current release/consume checks are never memoized.
            grant = replay_grant if replay_grant is not None else self._check_admission()
            if order != self._propose(order.issued_at, grant):
                raise ValueError("durable intent does not match admitted procedure")
            self._pending = order
        elif record["kind"] == "dispatch":
            identity = digest(order)
            if order != self._pending or identity in self._consumed:
                raise ValueError("request not released or already dispatched")
            self._consumed.add(identity)
        elif record["kind"] == "capture":
            if order != self._pending:
                raise ValueError("capture without protected original intent")
        elif record["kind"] in ("native_exchange", "native_observation", "native_interruption"):
            if order != self._pending or digest(order) not in self._consumed:
                raise ValueError("native exchange without consumed intent")
        elif record["kind"] == "outcome":
            if (
                order != self._pending
                or not self._records
                or self._records[-1]["kind"] != "capture"
            ):
                raise ValueError("outcome without original capture")
            result = ValidatedOutcome.model_validate_json(json.dumps(record["payload"]))
            original = bytes.fromhex(self._records[-1]["payload"]["original_hex"])
            observed_at = order.issued_at
            if order.action == "control":
                raw = bytes.fromhex(self._records[-1]["payload"]["original_hex"])
                receipt = ComponentReceipt.model_validate_json(raw)
                if receipt.control_id != order.control_id or result.component_sha256 != sha256(raw):
                    raise ValueError("component receipt does not bind the original control")
            elif result.result in ("PASS", "PENDING"):
                observed_at = OriginalCapture.model_validate_json(original).ended
            self._outcomes.append((order, result, sha256(original), observed_at))
            self._stopped |= result.result not in ("PASS", "PENDING")
            self._pending = None
        else:
            raise ValueError("unknown record kind")

    def _append(self, kind: str, order: RealWorkOrder, payload: dict[str, Any]) -> None:
        if self._stopped:
            raise ValueError("UNKNOWN/stopped: no further publication")
        record = {
            "authority": self.authority_sha256,
            "kind": kind,
            "previous": sha256(canonical_json_bytes(self._records[-1])) if self._records else None,
            "order": order.model_dump(mode="json"),
            "payload": payload,
        }
        raw = canonical_json_bytes(record)
        name = f"{len(self._records) + 1:06d}.json"
        try:
            publish(self._store, name, raw)
            publish(self._index, name, sha256(raw).encode())
        except Exception:
            self._stopped = True
        if self._stopped:
            # Keep every partial file; do not expose persistence exception chains.
            raise ValueError("evidence publication interrupted; UNKNOWN; reopen for reconciliation")
        self._apply(record)
        self._records.append(json.loads(raw))

    def release(self, order: RealWorkOrder) -> RealWorkOrder:
        if self._pending or self._stopped:
            raise ValueError("UNKNOWN/stopped: no redispatch")
        detached = RealWorkOrder.model_validate_json(order.model_dump_json())
        if detached != self.preview():
            raise ValueError("request does not equal the admitted next order")
        self._append("intent", detached, {})
        self._released = digest(detached)
        return detached.model_copy(deep=True)

    def consume(self, order: RealWorkOrder) -> None:
        """Durably spend one exact released intent before any credential/send operation."""
        self._check_admission()
        if not order.issued_at <= self._admission.now() < order.dispatch_not_after:
            raise ValueError("released request expired; fresh prerequisites required")
        identity = digest(order)
        if order != self._pending or identity != self._released or identity in self._consumed:
            raise ValueError("request not released or already dispatched; UNKNOWN cannot retry")
        self._append("dispatch", order, {})

    def import_capture_file(self) -> ValidatedOutcome:
        """Read only the installed witness source's fixed, digest-addressed original.

        No caller path or uploaded locator selects a file. Admission precedes reads;
        retention of an already consumed response does not renew dispatch authority.
        """
        from .setup_deployment import installed_source

        grant = self._check_admission()
        order = self._pending
        if order is None or digest(order) not in self._consumed:
            raise ValueError("transferred capture requires consumed original intent")
        if any(
            r["kind"] == "capture" and r["order"] == order.model_dump(mode="json")
            for r in self._records
        ):
            raise ValueError("replayed capture; UNKNOWN requires reconciliation")
        source = installed_source(self._admission)
        witness = source.witness(order)
        raw = source.capture_original(witness)
        if len(raw) > 8388608 or sha256(raw) != witness:
            raise ValueError("altered/substituted or oversized transferred capture")
        reject_credential_fields(raw)
        self._require_native_retention(order)
        return self._retain_capture(raw, order, witness, grant, self._admission.now())

    def import_capture(
        self,
        raw: bytes,
    ) -> ValidatedOutcome:
        """Internal ingress: witness pin must come from independently admitted source.

        It is NOT read from uploaded capture JSON. Public live entry cannot reach
        this consistency layer because its registry is empty.
        """
        grant = self._check_admission()
        now = self._admission.now()

        order = self._pending
        if order is None or any(
            r["kind"] == "capture" and r["order"] == order.model_dump(mode="json")
            for r in self._records
        ):
            raise ValueError("missing intent/replayed capture; UNKNOWN requires reconciliation")
        expected_witness_sha256 = self._admission.witness(order)
        if len(raw) > 8388608 or sha256(raw) != expected_witness_sha256:
            raise ValueError("missing independent witness or altered/substituted capture")
        reject_credential_fields(raw)
        return self._retain_capture(raw, order, expected_witness_sha256, grant, now)

    def _native_exchange(
        self,
        order: RealWorkOrder,
        exchange: dict[str, Any],
        *,
        interrupted_phase: str | None = None,
        complete: bool = False,
    ) -> None:
        """Collector-owned original retention, before response JSON interpretation."""
        self._require_native_retention(order)
        reject_credential_fields(canonical_json_bytes(exchange))
        if interrupted_phase is not None:
            if interrupted_phase not in ("operation", "actor", "before", "after"):
                raise ValueError("invalid observation phase")
            self._append(
                "native_interruption",
                order,
                {
                    "phase": interrupted_phase,
                    "exchange": exchange,
                    "complete": complete,
                    "state": "UNKNOWN_NO_REDISPATCH",
                },
            )
        else:
            self._append("native_exchange", order, exchange)

    def _require_native_retention(self, order: RealWorkOrder) -> None:
        # Retention is not another dispatch authorization. A response received after
        # expiry still belongs to the consumed intent and its already-held sink.
        if self._closed or order != self._pending or digest(order) not in self._consumed:
            raise ValueError("native capture requires consumed original intent")
        self._store.require_bound()
        self._index.require_bound()

    def _native_capture(self, raw: bytes) -> ValidatedOutcome:
        """Internal ingress from direct capture, not an uploaded self-authenticated digest."""
        grant = self._check_admission()
        order = self._pending
        if order is None or digest(order) not in self._consumed or len(raw) > 8388608:
            raise ValueError("native capture requires bounded consumed intent")
        reject_credential_fields(raw)
        # The trusted collector already retained each exchange before normalization.
        # Compare the assembled envelope against those originals; imported envelopes
        # must continue through the independently witnessed public ingress instead.
        capture = OriginalCapture.model_validate_json(raw)
        retained = [
            r["payload"]
            for r in self._records
            if r["kind"] == "native_exchange" and r["order"] == order.model_dump(mode="json")
        ]
        if retained != [e.model_dump(mode="json") for e in capture.exchanges]:
            raise ValueError("native capture differs from retained exchanges")
        for phase, originals in (("before", capture.before_hex), ("after", capture.after_hex)):
            observed = tuple(
                r["payload"]["exchange"]["response_hex"]
                for r in self._records
                if r["kind"] == "native_observation"
                and r["order"] == order.model_dump(mode="json")
                and r["payload"]["phase"] == phase
                and r["payload"]["exchange"]["status"] == 200
            )
            if observed != originals:
                raise ValueError("native observation envelope differs from retained originals")
        return self._retain_capture(raw, order, None, grant, self._admission.now())

    def _native_observation(
        self, order: RealWorkOrder, phase: str, exchange: dict[str, Any]
    ) -> None:
        """Supplementary originals are not extra action exchanges (C1)."""
        self._require_native_retention(order)
        if phase not in ("actor", "before", "after"):
            raise ValueError("observation requires protected consumed intent")
        reject_credential_fields(canonical_json_bytes(exchange))
        self._append("native_observation", order, {"phase": phase, "exchange": exchange})

    def _retain_capture(
        self,
        raw: bytes,
        order: RealWorkOrder,
        witness: str | None,
        grant: SetupGrantV2,
        now: datetime,
    ) -> ValidatedOutcome:
        from .operational_plan import evidence_json

        provenance = (
            {"source": "independent_witness", "witness_sha256": witness}
            if witness is not None
            else {"source": "native_collector", "original_sha256": sha256(raw)}
        )
        self._append("capture", order, {"original_hex": raw.hex(), **provenance})
        try:
            evidence_json(raw)
            capture = OriginalCapture.model_validate_json(raw)
            # Fixed test source assumption only; no real concealment policy is admitted.
            outcome = classify_capture(
                order, capture, concealment_admitted=self._admission.concealment()
            )
            if not 0 <= (now - capture.ended).total_seconds() <= grant.freshness_seconds:
                outcome = ValidatedOutcome(result="INCONCLUSIVE", reason="stale/future capture")
        except (ValueError, TypeError, KeyError):
            outcome = ValidatedOutcome(result="INCONCLUSIVE", reason="retained malformed original")
        self._append("outcome", order, outcome.model_dump(mode="json"))
        return outcome
