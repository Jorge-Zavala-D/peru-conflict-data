"""OFFLINE/SYNTHETIC fixtures for real-v2 codecs, admission and durable capture.

No network implementation or credential input exists here. These fixed policies
are TEST assumptions, never owner acceptance or an admissible production grant.
"""

from __future__ import annotations

import json
import tempfile
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

from peru_conflicts.acquisition.fs_safety import DirectoryLease
from peru_conflicts.hashing import canonical_json_bytes

from .access_policy import ACCESS_POLICY_V2_SHA256
from .references import sha256
from .setup_authority import (
    REQUIRED_CAPABILITIES,
    ActorBinding,
    CooperativeConcurrency,
    SetupGrantV2,
    admit,
    require_concurrency,
    schedule,
    validate_grant,
)
from .setup_bridge import digest
from .setup_dropbox import (
    Exchange,
    FileObservation,
    FolderObservation,
    OriginalCapture,
    PreparedRequest,
    RealWorkOrder,
    dropbox_content_hash,
    encode_request,
)
from .setup_evidence import EvidenceJournal, require_offline_root
from .setup_synthetic import proposal

NOW = datetime(2026, 9, 23, 12, tzinfo=UTC)
END = datetime(2026, 9, 23, 13, tzinfo=UTC)
_ADMISSIONS: dict[object, tuple[bytes, str, str]] = {}
_WITNESSES: dict[tuple[object, str], str] = {}
_CLOCKS: dict[object, datetime] = {}
_POLICIES: dict[object, str] = {}
_CAPABILITIES: dict[object, dict[str, str]] = {}
_RELEASED: dict[tuple[object, str], bytes] = {}
_DISPATCHED: set[tuple[object, str]] = set()
_FIXTURE_BINDINGS = {
    "fixture-account-coordinator": ("dbid:offline-coordinator", "offline-coordinator-home"),
    "fixture-account-annotator-a": ("dbid:offline-annotator-a", "offline-a-home"),
    "fixture-account-annotator-b": ("dbid:offline-annotator-b", "offline-b-home"),
}


def _fixture_capabilities() -> dict[str, str]:
    # TEST assumptions, including a complete synthetic service link index.
    # Parent protection remains cooperative, never a claim of provider parent CAS.
    return {
        name: sha256(("OFFLINE ONLY cooperative fixture " + name).encode())
        for name in REQUIRED_CAPABILITIES
    }


def fixture_actor_context(permit: object, binding: ActorBinding) -> tuple[str, str]:
    """Independently grounded TEST binding source, not actor labels from uploads."""
    registered = _ADMISSIONS.get(permit)
    if registered is None:
        raise ValueError("independent source admission required")
    grant = SetupGrantV2.model_validate_json(registered[0])
    if binding not in grant.sessions or grant.private_bindings_sha256 != sha256(
        canonical_json_bytes(_FIXTURE_BINDINGS)
    ):
        raise ValueError("private binding source mismatch")
    return _FIXTURE_BINDINGS[binding.account_ref]


def admit_fixture(root: Path) -> object:
    """Fixed TEST source; not reachable through production admission or CLI grants."""
    require_offline_root(root)
    identity = "offline-" + sha256(str(root.resolve()).encode())
    grant = fixture_grant().model_copy(update={"grant_ref": identity, "run_ref": identity})
    raw = grant.model_dump_json().encode()
    request, components = proposal()
    validate_grant(raw, request, components, implementation_digest(), NOW)
    permit = object()
    _ADMISSIONS[permit] = (raw, str((root / "run").resolve()), str((root / "checkpoint").resolve()))
    _CLOCKS[permit] = NOW
    # Independent fixed fixture policy source, not a digest supplied to the journal.
    _POLICIES[permit] = digest(fixture_grant().concurrency)
    _CAPABILITIES[permit] = _fixture_capabilities()
    return permit


def require_fixture_admission(permit: object, root: Path, checkpoint: Path) -> SetupGrantV2:
    registered = _ADMISSIONS.get(permit) if type(permit) is object else None
    if registered is None or registered[1:] != (str(root.resolve()), str(checkpoint.resolve())):
        raise ValueError("independent source admission required before sink access")
    # These immutable source-owned bytes passed full proposal validation at admission.
    # Recheck changing conditions on every action without rebuilding the proposal.
    grant = SetupGrantV2.model_validate_json(registered[0])
    if (
        grant.implementation_sha256 != implementation_digest()
        or not grant.not_before <= _CLOCKS[permit] < grant.not_after
    ):
        raise ValueError("admission implementation/validity mismatch")
    require_concurrency(grant, _POLICIES.get(permit), _CLOCKS[permit])
    if grant.capability_sha256 != _CAPABILITIES.get(permit):
        raise ValueError("missing/substituted independently admitted capability evidence")
    return grant


def fixture_clock(permit: object) -> datetime:
    if permit not in _ADMISSIONS:
        raise ValueError("independent source admission required")
    return _CLOCKS[permit]


def advance_fixture_clock(permit: object, now: datetime) -> None:
    """TEST source clock only; cannot affect the closed production admission path."""
    if now < _CLOCKS[permit]:
        raise ValueError("fixture clock cannot roll back")
    _CLOCKS[permit] = now


def revoke_fixture(permit: object) -> None:
    """TEST authority-source revocation, not a live grant registry operation."""
    del _ADMISSIONS[permit]


def witnessed_digest(permit: object, order: RealWorkOrder) -> str:
    value = _WITNESSES.get((permit, digest(order)))
    if value is None:
        raise ValueError("no independently registered fixture witness")
    return value


def _record_fixture_release(permit: object, order: RealWorkOrder) -> None:  # pyright: ignore[reportUnusedFunction]
    """Internal source seam, called only after durable admitted intent publication."""
    key = (permit, digest(order))
    if key in _RELEASED:
        raise ValueError("already released; no redispatch")
    _RELEASED[key] = order.model_dump_json().encode()


def _close_fixture_dispatch(permit: object) -> None:  # pyright: ignore[reportUnusedFunction]
    """Invalidate outstanding request handles when their active writer closes."""
    for key in tuple(_RELEASED):
        if key[0] is permit:
            del _RELEASED[key]


def _consume_fixture_request(permit: object, order: RealWorkOrder) -> None:
    """One active, exact, durably released request; shared by HTTP and local controls."""
    registered = _ADMISSIONS.get(permit)
    if registered is None:
        raise ValueError("independent source admission required")
    require_fixture_admission(permit, Path(registered[1]), Path(registered[2]))
    if not order.issued_at <= fixture_clock(permit) < order.dispatch_not_after:
        raise ValueError("released request expired; fresh prerequisites required")
    key = (permit, digest(order))
    if _RELEASED.get(key) != order.model_dump_json().encode() or key in _DISPATCHED:
        raise ValueError("request was not released or was already dispatched")
    _DISPATCHED.add(key)


def implementation_digest() -> str:
    return sha256(
        canonical_json_bytes(
            {
                n: sha256(Path(__file__).with_name(n).read_bytes())
                for n in (
                    "setup_authority.py",
                    "setup_dropbox.py",
                    "setup_evidence.py",
                    "setup_offline.py",
                )
            }
        )
    )


def fixture_grant() -> SetupGrantV2:
    request, components = proposal()
    req = json.loads(request)
    grant = SetupGrantV2(
        grant_ref="offline-grant",
        run_ref="offline-run",
        proposal_raw_sha256=sha256(request),
        component_sha256={n: sha256(b) for n, b in components.items()},
        candidate_sha256=req["candidate_model_sha256"],
        access_policy_sha256=ACCESS_POLICY_V2_SHA256,
        implementation_sha256=implementation_digest(),
        schedule_sha256=sha256(canonical_json_bytes(schedule())),
        private_bindings_sha256=sha256(canonical_json_bytes(_FIXTURE_BINDINGS)),
        capability_sha256=_fixture_capabilities(),
        sink_ref="offline-sink",
        checkpoint_ref="offline-independent-checkpoint",
        owner_authority_ref="NOT-OWNER-APPROVAL",
        sessions=tuple(
            ActorBinding(
                actor=a,
                person_ref=f"fixture-person-{a}",
                account_ref=f"fixture-account-{a}",
                session_ref=f"fixture-session-{a}",
                binding_sha256=sha256(a.encode()),
            )
            for a in ("coordinator", "annotator-a", "annotator-b")
        ),
        concurrency=CooperativeConcurrency(
            reviewed_policy_ref="OFFLINE-ONLY-NOT-APPROVED",
            policy_sha256=sha256(b"fixture policy"),
            scoped_session_ref="fixture-window",
            session_evidence_sha256=sha256(b"fixture window"),
            not_before=NOW,
            not_after=END,
        ),
        not_before=NOW,
        not_after=END,
        freshness_seconds=60,
        use_policy="one_run_no_redispatch",
        cleanup_scope="receipt_owned_files_only",
    )
    return validate_grant(
        grant.model_dump_json().encode(), request, components, implementation_digest(), NOW
    )


def _metadata(obj: FolderObservation | FileObservation) -> dict[str, Any]:
    return {".tag": obj.kind, **obj.model_dump(exclude={"kind"}, exclude_none=True)}


class FakeHTTP:
    """Synthetic service state; the HTTP responder never receives an order/expected result."""

    def __init__(self, permit: object) -> None:
        if permit not in _ADMISSIONS:
            raise ValueError("fixture provider requires independent admission")
        self._permit = permit
        self.objects: dict[str, FolderObservation | FileObservation] = {}
        self.contents: dict[str, bytes] = {}
        # A separate mutable service-side account table; not a view into an order.
        self.accounts = {
            "fixture-session-coordinator": ("dbid:offline-coordinator", "offline-coordinator-home"),
            "fixture-session-annotator-a": ("dbid:offline-annotator-a", "offline-a-home"),
            "fixture-session-annotator-b": ("dbid:offline-annotator-b", "offline-b-home"),
        }
        self.shares: dict[str, dict[str, Any]] = {}
        self.links: dict[str, list[dict[str, Any]]] = {}
        self.jobs: dict[str, str] = {}
        self.async_sharing = False
        self.pending_polls = 0
        self.job_polls: dict[str, int] = {}
        self.failed_jobs: set[str] = set()
        self.page_size = 1000
        self._pages: dict[str, tuple[str, str, str, dict[str, Any]]] = {}
        self.dispatches = 0
        self.calls: list[PreparedRequest] = []

    def _path(self, args: dict[str, Any], session: str) -> str:
        if "async_job_id" in args:
            return self.shares.get(self.jobs.get(args["async_job_id"], ""), {}).get(
                "path", "/unknown-job"
            )
        if "shared_folder_id" in args:
            return self.shares.get(args["shared_folder_id"], {}).get("path", "/unknown-share")
        value = args.get("path", "/")
        if value.startswith("id:"):
            identity, _, suffix = value.partition("/")
            found = next((p for p, obj in self.objects.items() if obj.id == identity), None)
            return (found + ("/" + suffix if suffix else "")) if found else "/unknown-id"
        account = self.accounts[session][0]
        for share in self.shares.values():
            mounted = share["mounts"].get(account)
            if mounted and (value == mounted or value.startswith(mounted + "/")):
                return share["path"] + value[len(mounted) :]
        return value

    def _visible_metadata(
        self, obj: FolderObservation | FileObservation, path: str, account: str
    ) -> dict[str, Any]:
        value = _metadata(obj)
        for shared_id, share in self.shares.items():
            if path == share["path"] or path.startswith(share["path"] + "/"):
                if isinstance(obj, FolderObservation) and path == share["path"]:
                    value["sharing_info"] = {"shared_folder_id": shared_id}
                mounted = share["mounts"].get(account)
                if mounted:
                    value["path_display"] = mounted + path[len(share["path"]) :]
                    value["path_lower"] = value["path_display"].lower()
        return value

    def _can(self, account: str, path: str, *, write: bool = False) -> bool:
        if account == "dbid:offline-coordinator":
            return True
        return any(
            (path == share["path"] or path.startswith(share["path"] + "/"))
            and account in share["mounts"]
            and share["members"].get(account) in (("editor",) if write else ("viewer", "editor"))
            for share in self.shares.values()
        )

    def _snapshot(self, request: PreparedRequest, path: str | None = None) -> tuple[str, ...]:
        args = json.loads(request.api_arg or bytes.fromhex(request.body_hex) or b"{}")
        path = path if path is not None else self._path(args, request.actor_session_ref)
        paths = [str(p) for p in reversed(PurePosixPath(path).parents)] + [path]
        return tuple(
            canonical_json_bytes(_metadata(self.objects[p])).hex()
            for p in paths
            if p in self.objects
        )

    def _respond(self, request: PreparedRequest, fault: str | None) -> Exchange:
        """Actual request fields and synthetic service state are the only inputs."""
        self.calls.append(request)
        route = request.route
        args = json.loads(request.api_arg or bytes.fromhex(request.body_hex) or b"{}")
        account, namespace = self.accounts[request.actor_session_ref]
        path = self._path(args, request.actor_session_ref)
        obj = self.objects.get(path)
        status = 200
        body: Any = {}
        raw: bytes | None = None
        header = None
        error: str | None = None
        if json.loads(request.root_header).get("namespace_id") != namespace:
            status, body = 422, {"error": {".tag": "invalid_root"}}
        elif "cursor" in args:
            page = self._pages.pop(args["cursor"], None)
            if page is None or page[:3] != (route, account, namespace):
                status, body = 409, {"error": {".tag": "invalid_cursor"}}
            else:
                body = page[3]
        elif route == "users/get_current_account":
            body = {
                "account_id": account,
                "root_info": {
                    ".tag": "user",
                    "root_namespace_id": namespace,
                    "home_namespace_id": namespace,
                },
            }
        elif route in ("files/create_folder_v2", "files/upload"):
            if not self._can(account, path, write=True) and fault != "contradiction":
                error = "no_write_permission"
            elif obj is not None:
                error = "conflict"
            elif (
                str(PurePosixPath(path).parent) != "/"
                and str(PurePosixPath(path).parent) not in self.objects
            ):
                error = "not_found"
            else:
                common: dict[str, Any] = dict(
                    id=f"id:offline-{self.dispatches}",
                    name=PurePosixPath(path).name,
                    path_display=path,
                    path_lower=path.lower(),
                )
                if route == "files/create_folder_v2":
                    created = FolderObservation(**common)
                    body = {"metadata": created.model_dump(exclude={"kind"})}
                else:
                    content = bytes.fromhex(request.body_hex)
                    created = FileObservation(
                        **common,
                        rev=f"rev-{self.dispatches}",
                        size=len(content),
                        content_hash=dropbox_content_hash(content),
                    )
                    self.contents[created.id] = content
                    body = self._visible_metadata(created, path, account)
                    body.pop(".tag", None)
                self.objects[path] = created
                if fault == "contradiction":
                    error = "no_write_permission"
        elif route in ("files/download", "files/get_metadata", "files/list_folder"):
            if obj is None or not self._can(account, path):
                error = "not_found"
            elif route == "files/download":
                if not isinstance(obj, FileObservation):
                    error = "not_file"
                else:
                    raw = self.contents[obj.id]
                    header = json.dumps(self._visible_metadata(obj, path, account))
            elif route == "files/get_metadata":
                body = self._visible_metadata(obj, path, account)
            elif not isinstance(obj, FolderObservation):
                error = "not_folder"
            else:
                body = {
                    "entries": [
                        self._visible_metadata(item, p, account)
                        for p, item in self.objects.items()
                        if str(PurePosixPath(p).parent) == path
                    ],
                    "cursor": "offline-end",
                    "has_more": False,
                }
        elif route == "sharing/share_folder":
            if account != "dbid:offline-coordinator" or not isinstance(obj, FolderObservation):
                error = "not_found"
            else:
                share_id = f"share-{self.dispatches}"
                self.shares[share_id] = {
                    "path": path,
                    "folder_id": obj.id,
                    "members": {account: "owner"},
                    "pending": {},
                    "mounts": {},
                }
                complete = {
                    "shared_folder_id": share_id,
                    "name": obj.name,
                    "path_lower": path.lower(),
                    "access_type": {".tag": "owner"},
                }
                if self.async_sharing:
                    job = f"job-{self.dispatches}"
                    self.jobs[job] = share_id
                    self.job_polls[job] = self.pending_polls
                    body = {".tag": "async_job_id", "async_job_id": job}
                else:
                    body = {".tag": "complete", "complete": complete}
        elif route == "sharing/check_share_job_status":
            share_id = self.jobs.get(args["async_job_id"])
            if share_id is None:
                status, body = 409, {"error": {".tag": "invalid_async_job_id"}}
            elif args["async_job_id"] in self.failed_jobs:
                body = {".tag": "failed", "failed": {".tag": "other"}}
            elif self.job_polls.get(args["async_job_id"], 0):
                self.job_polls[args["async_job_id"]] -= 1
                body = {".tag": "in_progress"}
            else:
                share = self.shares[share_id]
                body = {
                    ".tag": "complete",
                    "complete": {
                        "shared_folder_id": share_id,
                        "name": PurePosixPath(share["path"]).name,
                        "path_lower": share["path"].lower(),
                        "access_type": {".tag": "owner"},
                    },
                }
        elif route in (
            "sharing/add_folder_member",
            "sharing/mount_folder",
            "sharing/list_folder_members",
        ):
            share = self.shares.get(args["shared_folder_id"])
            if share is None:
                error = "not_found"
            elif route == "sharing/add_folder_member":
                if account != "dbid:offline-coordinator":
                    error = "no_write_permission"
                else:
                    for member in args["members"]:
                        share["pending"][member["member"]["dropbox_id"]] = member["access_level"][
                            ".tag"
                        ]
                    body = None  # The native endpoint returns JSON null, not invented metadata.
            elif route == "sharing/mount_folder":
                if account not in share["pending"] and account not in share["members"]:
                    error = "not_found"
                else:
                    if account in share["pending"]:
                        share["members"][account] = share["pending"].pop(account)
                    locator = "/mounted-" + args["shared_folder_id"]
                    share["mounts"][account] = locator
                    body = {
                        "shared_folder_id": args["shared_folder_id"],
                        "path_lower": locator,
                        "name": PurePosixPath(share["path"]).name,
                        "access_type": {".tag": share["members"][account]},
                    }
            else:
                body = {
                    "users": [
                        {
                            "user": {"account_id": member},
                            "access_type": {".tag": role},
                            "is_inherited": False,
                        }
                        for member, role in share["members"].items()
                    ],
                    "groups": [],
                    "invitees": [
                        {
                            "invitee": {".tag": "dropbox_id", "dropbox_id": member},
                            "access_type": {".tag": role},
                        }
                        for member, role in share["pending"].items()
                    ],
                }
        elif route == "sharing/list_shared_links":
            body = {
                "links": [
                    link
                    for linked_path, links in self.links.items()
                    if linked_path == path
                    or (not args["direct_only"] and path.startswith(linked_path.rstrip("/") + "/"))
                    for link in links
                ],
                "has_more": False,
            }
        elif route == "files/delete_v2":
            if not isinstance(obj, FileObservation):
                error = "not_file"
            elif not self._can(account, path, write=True):
                error = "no_write_permission"
            elif args["parent_rev"] != obj.rev:
                error = "conflict"
            elif fault == "revision_drift":
                self.objects[path] = obj.model_copy(update={"rev": "same-bytes-new-revision"})
                error = "conflict"
            else:
                body = {"metadata": _metadata(obj)}
                del self.objects[path]
                del self.contents[obj.id]
        else:
            status, body = 409, {"error": {".tag": "other"}}
        if error:
            status, body = 409, {"error": {".tag": "path", "path": {".tag": error}}}
        if status == 200 and isinstance(body, dict):
            body = cast(dict[str, Any], body)
            page_fields = {
                "files/list_folder": ("entries", "files/list_folder/continue"),
                "files/list_folder/continue": ("entries", "files/list_folder/continue"),
                "sharing/list_folder_members": ("users", "sharing/list_folder_members/continue"),
                "sharing/list_folder_members/continue": (
                    "users",
                    "sharing/list_folder_members/continue",
                ),
                "sharing/list_shared_links": ("links", "sharing/list_shared_links"),
            }
            if route in page_fields:
                field, continuation = page_fields[route]
                values = body[field]
                if len(values) > self.page_size:
                    cursor = f"offline-page-{len(self.calls)}"
                    remainder = {**body, field: values[self.page_size :]}
                    if field == "users":
                        remainder.update(groups=[], invitees=[])
                    self._pages[cursor] = (continuation, account, namespace, remainder)
                    body = {**body, field: values[: self.page_size], "cursor": cursor}
                    if field != "users":
                        body["has_more"] = True
                else:
                    body.pop("cursor", None)
                    if field != "users":
                        body.update(cursor="offline-end", has_more=False)
        return Exchange(
            request=request,
            status=status,
            provider_request_id=f"offline-{len(self.calls)}",
            result_header=header,
            response_hex=(raw if raw is not None else canonical_json_bytes(body)).hex(),
        )

    def execute(self, order: RealWorkOrder, *, fault: str | None = None) -> bytes:
        if order.action == "control":
            raise ValueError("local component cannot dispatch to a provider")
        _consume_fixture_request(self._permit, order)
        self.dispatches += 1
        args = json.loads(order.request.api_arg or bytes.fromhex(order.request.body_hex) or b"{}")
        observed_path = self._path(args, order.request.actor_session_ref)
        before = self._snapshot(order.request, observed_path)
        exchange = self._respond(order.request, fault)
        exchanges = [exchange]
        continuation = {
            "files/list_folder": "files/list_folder/continue",
            "sharing/list_folder_members": "sharing/list_folder_members/continue",
            "sharing/list_shared_links": "sharing/list_shared_links",
        }.get(order.request.route)
        cursors: set[str] = set()
        while continuation and fault != "truncate_pages" and len(exchanges) < 200:
            try:
                page = json.loads(bytes.fromhex(exchanges[-1].response_hex))
                cursor = page.get("cursor")
                more = page.get("has_more", bool(cursor))
                if (
                    exchanges[-1].status != 200
                    or not more
                    or not isinstance(cursor, str)
                    or cursor in cursors
                ):
                    break
                cursors.add(cursor)
                request = encode_request(
                    continuation,
                    {"cursor": cursor},
                    json.loads(order.request.root_header)["namespace_id"],
                    order.request.actor_session_ref,
                )
                if fault == "wrong_page_session":
                    request = request.model_copy(
                        update={"actor_session_ref": "fixture-session-annotator-b"}
                    )
                exchanges.append(self._respond(request, None))
            except (ValueError, TypeError, AttributeError):
                break  # Retain the unknown page; normalization will be inconclusive.
        if fault == "unknown":
            raise TimeoutError("OFFLINE interrupted after request, no capture or retry")
        capture = OriginalCapture(
            order_sha256=digest(order),
            actor_session_ref=order.request.actor_session_ref,
            namespace=json.loads(order.request.root_header)["namespace_id"],
            started=fixture_clock(self._permit),
            ended=fixture_clock(self._permit),
            exchanges=tuple(exchanges),
            before_hex=before,
            after_hex=self._snapshot(order.request, observed_path),
        )
        if fault == "wrong_session":
            capture = capture.model_copy(update={"actor_session_ref": "fixture-unrelated-session"})
        raw = capture.model_dump_json().encode()
        if fault == "malformed_capture":
            raw = b'{"incomplete":'
        elif fault == "duplicate_keys":
            raw = b'{"version":"first","version":"second"}'
        _WITNESSES[self._permit, digest(order)] = sha256(raw)
        return raw


def demonstrate(root: Path, *, fault: str | None = None) -> dict[str, Any]:
    """Drive only the admitted journal's orders; never supply a caller schedule."""
    require_offline_root(root)
    root.mkdir()
    with DirectoryLease.acquire(root) as parent:
        for name in ("run", "checkpoint", "components"):
            with parent.acquire_child(name, create=True):
                pass
    permit = admit_fixture(root)
    journal = EvidenceJournal(root / "run", root / "checkpoint", permit, create=True)
    provider = FakeHTTP(permit)
    provider.async_sharing = True
    checks: dict[str, str] = {}
    fault_used = False
    stop_reason = None
    complete = False
    recovered_pending_share = False
    try:
        while True:
            try:
                order = journal.next()
            except StopIteration:
                complete = True
                break
            except ValueError as error:
                stop_reason = str(error)
                break
            chosen = None
            if (
                not fault_used
                and fault
                and (
                    fault in ("wrong_session", "unknown")
                    or (
                        fault == "contradiction"
                        and order.action == "write"
                        and order.expected == "DENY"
                    )
                    or (fault == "revision_drift" and order.action == "cleanup")
                )
            ):
                chosen, fault_used = fault, True
            if order.action == "control":
                result = journal.run_component()
            else:
                try:
                    raw = provider.execute(order, fault=chosen)
                except TimeoutError:
                    stop_reason = "UNKNOWN: interrupted operation, no redispatch"
                    break
                result = journal.import_capture(raw)
            if order.check_id:
                checks[order.check_id] = result.result
            if result.result == "PENDING" and not recovered_pending_share:
                journal.close()
                journal = EvidenceJournal(root / "run", root / "checkpoint", permit, create=False)
                recovered_pending_share = True
            if result.result not in ("PASS", "PENDING"):
                stop_reason = result.reason
                break
        expected_ids = {str(r["check_id"]) for r in schedule()}
        summary: dict[str, Any] = {
            "label": "OFFLINE_SYNTHETIC",
            "complete": complete
            and set(checks) == expected_ids
            and set(checks.values()) == {"PASS"}
            and not any(isinstance(x, FileObservation) for x in provider.objects.values()),
            "checks": len(checks),
            "controls": sum(
                r["kind"] == "outcome"
                and r["order"]["action"] == "control"
                and r["payload"]["result"] == "PASS"
                for r in journal.records
            ),
            "not_run": sorted(expected_ids - checks.keys()),
            "cleanup_outstanding": sum(
                isinstance(x, FileObservation) for x in provider.objects.values()
            ),
            "reconciliation_required": sum(
                bool(r["payload"].get("reconciliation_required"))
                for r in journal.records
                if r["kind"] == "outcome"
            ),
            "pending": "UNKNOWN" if journal.pending else None,
            "stop_reason": stop_reason,
            "live_path_coverage": "NOT_ESTABLISHED",
            "operational_approvals": 0,
            "fault_applied": fault_used,
            "recovered_pending_share": recovered_pending_share,
            "share_mutations": sum(r.route == "sharing/share_folder" for r in provider.calls),
            "fake_directory_count": sum(
                isinstance(x, FolderObservation) for x in provider.objects.values()
            ),
            "fake_leaf_share_count": len(provider.shares),
        }
    finally:
        journal.close()
    resumed = EvidenceJournal(root / "run", root / "checkpoint", permit, create=False)
    try:
        assert bool(resumed.pending) == (summary["pending"] == "UNKNOWN")
    finally:
        resumed.close()
    return summary


def main() -> None:
    with ExitStack() as stack:
        temporary = Path(tempfile.gettempdir()).absolute()
        directory = stack.enter_context(DirectoryLease.acquire(Path(temporary.anchor)))
        for part in temporary.parts[1:]:
            directory = stack.enter_context(directory.acquire_child(part))
        root = Path(
            stack.enter_context(
                tempfile.TemporaryDirectory(prefix="m2-readiness-real-v2-", dir=directory.resolved)
            )
        )
        results = {"success": demonstrate(root / "success")}
        for fault in ("contradiction", "wrong_session", "revision_drift", "unknown"):
            results[fault] = demonstrate(root / fault, fault=fault)
        try:
            admit(
                fixture_grant().model_dump_json().encode(),
                lambda: (_ for _ in ()).throw(AssertionError("lookup")),
            )
        except ValueError:
            pass
        else:
            raise AssertionError("production admitted fixture")
        print(json.dumps(results, indent=2))
        if not results["success"]["complete"]:
            raise SystemExit(
                "OFFLINE candidate incomplete; no operational authority or source release"
            )


if __name__ == "__main__":
    main()
