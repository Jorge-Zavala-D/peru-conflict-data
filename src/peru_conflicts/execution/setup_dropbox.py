"""Allowlisted Dropbox codecs, without HTTP, OAuth or credential lookup.

Endpoint types follow dropbox-api-spec 404afad5c508a45ea9004c9d8c0cd4a56f0fbf22.
Provider observations are not authenticated by this parser. Original capture and
separately grounded witness admission belong to setup_evidence.
"""

from __future__ import annotations

import hashlib
import json
from itertools import pairwise
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal, cast

from pydantic import AwareDatetime, Field

from peru_conflicts.models.common import Sha256, StrictModel

from .operational_plan import evidence_json
from .references import sha256
from .setup_authority import ActorBinding

PROBE = b"M2-02B.2A SYNTHETIC ACCESS PROBE v1\n"


def dropbox_content_hash(body: bytes) -> str:
    blocks = b"".join(
        hashlib.sha256(body[i : i + 4194304]).digest() for i in range(0, len(body), 4194304)
    )
    return hashlib.sha256(blocks).hexdigest()


def provider_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or str(path) != value
        or ".." in path.parts
        or any(c in value for c in ("\\", ":"))
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("unsafe provider path")
    return value


class FolderObservation(StrictModel):
    kind: Literal["folder"] = "folder"
    id: str = Field(min_length=1)
    name: str
    path_display: str | None = None
    path_lower: str | None = None


class FileObservation(StrictModel):
    kind: Literal["file"] = "file"
    id: str = Field(min_length=1)
    name: str
    rev: str = Field(min_length=1)
    size: int = Field(ge=0)
    content_hash: str
    path_display: str | None = None
    path_lower: str | None = None


def metadata(value: dict[str, Any], *, folder: bool = False) -> FolderObservation | FileObservation:
    """Select only documented provider fields; retain the full bytes outside this model."""
    fields = {k: value[k] for k in ("id", "name", "path_display", "path_lower") if k in value}
    tag = "folder" if folder else value.get(".tag")
    if tag == "folder":
        return FolderObservation.model_validate(fields)
    if tag == "file":
        fields.update({k: value[k] for k in ("rev", "size", "content_hash") if k in value})
        return FileObservation.model_validate(fields)
    raise ValueError("unknown metadata variant: retain raw capture, INCONCLUSIVE")


def folder_metadata(raw: bytes) -> FolderObservation:
    result = metadata(evidence_json(raw)["metadata"], folder=True)
    assert isinstance(result, FolderObservation)
    return result


class PreparedRequest(StrictModel):
    route: str
    scope: str
    root_header: str
    api_arg: str | None
    body_hex: str
    actor_session_ref: str


# No arbitrary URLs, SDK configuration, token handling, retries or transport dispatch.
_SCOPES = {
    "users/get_current_account": "account_info.read",
    "files/get_metadata": "files.metadata.read",
    "files/create_folder_v2": "files.content.write",
    "files/list_folder": "files.metadata.read",
    "files/list_folder/continue": "files.metadata.read",
    "files/upload": "files.content.write",
    "files/download": "files.content.read",
    "files/delete_v2": "files.content.write",
    "sharing/share_folder": "sharing.write",
    "sharing/check_share_job_status": "sharing.write",
    "sharing/add_folder_member": "sharing.write",
    "sharing/mount_folder": "sharing.write",
    "sharing/get_folder_metadata": "sharing.read",
    "sharing/list_folder_members": "sharing.read",
    "sharing/list_folder_members/continue": "sharing.read",
    "sharing/list_shared_links": "sharing.read",
}
_FIELDS: dict[str, set[str]] = {
    "users/get_current_account": set(),
    "files/get_metadata": {"path", "include_deleted"},
    "files/create_folder_v2": {"path", "autorename"},
    "files/list_folder": {"path", "recursive", "include_deleted"},
    "files/list_folder/continue": {"cursor"},
    "files/upload": {"path", "mode", "autorename", "strict_conflict"},
    "files/download": {"path"},
    "files/delete_v2": {"path", "parent_rev"},
    "sharing/share_folder": {"path", "acl_update_policy", "force_async"},
    "sharing/check_share_job_status": {"async_job_id"},
    "sharing/add_folder_member": {"shared_folder_id", "members", "quiet"},
    "sharing/mount_folder": {"shared_folder_id"},
    "sharing/get_folder_metadata": {"shared_folder_id"},
    "sharing/list_folder_members": {"shared_folder_id", "limit"},
    "sharing/list_folder_members/continue": {"cursor"},
    "sharing/list_shared_links": {"path", "direct_only"},
}


def encode_request(
    route: str,
    arguments: dict[str, Any],
    namespace: str,
    session_ref: str,
    *,
    upload: bytes | None = None,
) -> PreparedRequest:
    """Encoding only. Scope/target authorization must precede release by the bridge."""
    if route not in _SCOPES:
        raise ValueError("route not allowlisted")
    fields = (
        {"cursor"}
        if route == "sharing/list_shared_links" and "cursor" in arguments
        else _FIELDS[route]
    )
    if set(arguments) != fields or not namespace or not session_ref:
        raise ValueError("unexpected/missing controlled request fields")
    if "path" in arguments:
        path = arguments["path"]
        if not isinstance(path, str) or not path:
            raise ValueError("missing target")
        if path.startswith("id:"):
            identity, separator, suffix = path[3:].partition("/")
            if not identity:
                raise ValueError("unsafe provider ID")
            provider_path("/" + identity)
            if separator:
                provider_path("/" + suffix)
                if not suffix:
                    raise ValueError("unsafe provider ID suffix")
        else:
            provider_path(path)
    if route == "files/list_folder" and (
        arguments["recursive"] is not False or arguments["include_deleted"] is not False
    ):
        raise ValueError("recursive/deleted enumeration prohibited")
    if route == "sharing/share_folder" and (
        arguments["acl_update_policy"] != "owner"
        or arguments["force_async"] is not False
        or not arguments["path"].startswith("id:")
    ):
        raise ValueError("share conversion requires known folder ID and owner-managed ACL")
    if route == "sharing/add_folder_member":
        if not isinstance(arguments["members"], list):
            raise ValueError("one exact bound leaf member required")
        members = cast(list[Any], arguments["members"])
        if (
            arguments["quiet"] is not False
            or len(members) != 1
            or not isinstance(members[0], dict)
            or set(cast(dict[str, Any], members[0])) != {"member", "access_level"}
            or not isinstance(members[0]["member"], dict)
            or set(cast(dict[str, Any], members[0]["member"])) != {".tag", "dropbox_id"}
            or members[0]["member"][".tag"] != "dropbox_id"
            or members[0]["access_level"] not in ({".tag": "viewer"}, {".tag": "editor"})
        ):
            raise ValueError("one exact bound leaf member required")
    if route == "files/create_folder_v2" and arguments.get("autorename") is not False:
        raise ValueError("exclusive folder creation required")
    if route == "files/upload" and (
        arguments.get("mode") != {".tag": "add"}
        or arguments.get("autorename") is not False
        or arguments.get("strict_conflict") is not True
        or upload != PROBE
    ):
        raise ValueError("exclusive fixed-probe upload required")
    if route == "files/delete_v2" and (
        set(arguments) != {"path", "parent_rev"}
        or not str(arguments["path"]).startswith("id:")
        or not arguments["parent_rev"]
    ):
        raise ValueError("cleanup requires file ID and exact file revision")
    # ensure_ascii is required for HTTP header values; UTF-8 body JSON is distinct.
    encoded = json.dumps(arguments, ensure_ascii=True, separators=(",", ":"))
    content = route in ("files/upload", "files/download")
    return PreparedRequest(
        route=route,
        scope=_SCOPES[route],
        root_header=json.dumps({".tag": "namespace_id", "namespace_id": namespace}),
        api_arg=encoded if content else None,
        body_hex=(upload if upload is not None else b"" if content else encoded.encode()).hex(),
        actor_session_ref=session_ref,
    )


def cleanup_arguments(
    owned: FolderObservation | FileObservation,
    current: FolderObservation | FileObservation,
    *,
    owned_logical_path: str | None = None,
) -> dict[str, str]:
    """Exact ledger-owned ID/revision/path, not byte equality or a pathname fallback."""
    if not isinstance(owned, FileObservation) or not isinstance(current, FileObservation):
        raise ValueError("folder deletion prohibited")
    same = (
        owned == current
        if owned_logical_path is None
        else (_same_object(owned, current) and current.path_display == owned_logical_path)
    )
    if not same or current.path_display is None:
        raise ValueError("cleanup BLOCKED: identity/revision/ancestry drift")
    provider_path(current.path_display)
    return {"path": owned.id, "parent_rev": owned.rev}


def _same_object(
    a: FolderObservation | FileObservation, b: FolderObservation | FileObservation
) -> bool:
    """Compare provider identity/version/bytes; caller must separately bind actor paths."""
    return a.model_dump(exclude={"path_display", "path_lower"}) == b.model_dump(
        exclude={"path_display", "path_lower"}
    )


class NamespaceRootObservation(StrictModel):
    kind: Literal["namespace_root"] = "namespace_root"
    account_id: str
    root_namespace_id: str
    home_namespace_id: str


Observation = Annotated[
    NamespaceRootObservation | FolderObservation | FileObservation, Field(discriminator="kind")
]


class BoundObservation(StrictModel):
    """Ledger relationship, explicitly NOT a provider parent ID or folder revision."""

    namespace: str
    logical_path: str
    observation: Observation
    ancestor_ids: tuple[str, ...]
    relation_source: Literal["bound_path_observation"] = "bound_path_observation"
    observed_at: AwareDatetime
    original_capture_sha256: Sha256


class RealWorkOrder(StrictModel):
    version: Literal["m2-real-work-order-v2"] = "m2-real-work-order-v2"
    authority_sha256: Sha256
    run_ref: str
    sequence: int = Field(gt=0)
    action: Literal[
        "root",
        "create",
        "share",
        "invite",
        "mount",
        "mount_verify",
        "membership",
        "links",
        "share_status",
        "prepare",
        "list",
        "read",
        "write",
        "cleanup",
        "cleanup_metadata",
        "cleanup_read",
        "control",
    ]
    actor: ActorBinding
    logical_path: str
    namespace: str
    actor_locator: str
    # Private expectations supplied by admitted bindings, never a capture assertion.
    expected_account_id: str | None = None
    expected_member_roles: dict[str, Literal["owner", "viewer", "editor"]] = Field(
        default_factory=dict
    )
    shared_folder_id: str | None = None
    async_job_id: str | None = None
    control_id: Literal["APP-ACCEPTED-BYTES-A", "APP-ACCEPTED-BYTES-B"] | None = None
    link_coverage: Literal["not_established", "offline_complete"] = "not_established"
    check_id: str | None = None
    expected: Literal["ALLOW", "DENY"] = "ALLOW"
    before: tuple[BoundObservation, ...]
    target: BoundObservation | None
    request: PreparedRequest
    issued_at: AwareDatetime
    dispatch_not_after: AwareDatetime


class Exchange(StrictModel):
    request: PreparedRequest
    status: int = Field(ge=100, le=599)
    # Whitelisted secret-free capture fields. Never persist arbitrary HTTP headers.
    provider_request_id: str | None
    result_header: str | None = None
    response_hex: str = Field(max_length=2097152)


class OriginalCapture(StrictModel):
    version: Literal["m2-real-setup-capture-v2"] = "m2-real-setup-capture-v2"
    order_sha256: Sha256
    actor_session_ref: str
    namespace: str
    started: AwareDatetime
    ended: AwareDatetime
    exchanges: tuple[Exchange, ...] = Field(min_length=1, max_length=200)
    # Independently captured get_metadata observations, not claimed normalized snapshots.
    before_hex: tuple[str, ...]
    after_hex: tuple[str, ...]


class ValidatedOutcome(StrictModel):
    result: Literal["PASS", "FAIL", "INCONCLUSIVE", "BLOCKED", "PENDING"]
    reason: str
    after: Observation | None = None
    reconciliation_required: bool = False
    shared_folder_id: str | None = None
    async_job_id: str | None = None
    mount_locator: str | None = None
    component_sha256: Sha256 | None = None


def _objects(hexes: tuple[str, ...]) -> tuple[FolderObservation | FileObservation, ...]:
    return tuple(metadata(evidence_json(bytes.fromhex(x))) for x in hexes)


def classify_capture(
    order: RealWorkOrder,
    capture: OriginalCapture,
    *,
    concealment_admitted: bool = False,
) -> ValidatedOutcome:
    """Semantic validation only; trusted ingress authenticates original capture separately.

    concealment_admitted is supplied only by admitted policy state, never imported
    from the capture. No live admission source currently exists.
    """
    from .setup_bridge import digest

    inconclusive = ValidatedOutcome(result="INCONCLUSIVE", reason="unestablished context/evidence")
    if (
        capture.order_sha256 != digest(order)
        or capture.actor_session_ref != order.actor.session_ref
        or capture.namespace != order.namespace
        or capture.started < order.issued_at
        or capture.ended < capture.started
        or capture.exchanges[0].request != order.request
        or any(x.provider_request_id is None for x in capture.exchanges)
    ):
        return inconclusive
    try:
        continuation = {
            "list": "files/list_folder/continue",
            "membership": "sharing/list_folder_members/continue",
            "links": "sharing/list_shared_links",
        }.get(order.action)
        if continuation is None and len(capture.exchanges) != 1:
            return inconclusive
        cursors: set[str] = set()
        # Validate the entire request sequence before any semantic early return,
        # including successful denials. Supplementary observations belong in
        # before_hex/after_hex, not additional unapproved exchanges.
        for previous, exchange in pairwise(capture.exchanges):
            if continuation is None or previous.status != 200:
                return inconclusive
            page = evidence_json(bytes.fromhex(previous.response_hex))
            cursor = page.get("cursor")
            more = bool(cursor) if order.action == "membership" else page.get("has_more")
            if not more or not isinstance(cursor, str) or not cursor or cursor in cursors:
                return inconclusive
            cursors.add(cursor)
            if exchange.request != encode_request(
                continuation, {"cursor": cursor}, order.namespace, order.actor.session_ref
            ):
                return inconclusive
        before, after = _objects(capture.before_hex), _objects(capture.after_hex)
        expected_before = tuple(b.observation for b in order.before)
        if len(before) != len(expected_before) or any(
            not isinstance(expected, FolderObservation | FileObservation)
            or not _same_object(observed, expected)
            or observed.path_display != binding.logical_path
            for observed, expected, binding in zip(
                before, expected_before, order.before, strict=True
            )
        ):
            return inconclusive
        first = capture.exchanges[0]
        raw = bytes.fromhex(first.response_hex)
        obj = (
            evidence_json(raw)
            if raw
            and (order.action not in ("read", "cleanup_read") or first.status != 200)
            and not (order.action == "invite" and first.status == 200 and raw == b"null")
            else {}
        )
        current = after[-1] if after else None
        target = order.target.observation if order.target else None
        if first.status != 200:
            # An error cannot conceal a changed object/ancestry. Preserve suspect evidence.
            if after != before:
                return ValidatedOutcome(
                    result="FAIL",
                    reason="denial contradicts post-state",
                    after=current,
                    reconciliation_required=True,
                )
            error = obj.get("error", {})
            denied = (
                first.status == 409
                and error.get(".tag") == "path"
                and error.get("path", {}).get(".tag") == "no_write_permission"
                and order.action == "write"
                and target is None
            )
            concealed = (
                concealment_admitted
                and first.status == 409
                and error == {".tag": "path", "path": {".tag": "not_found"}}
                and order.action in ("list", "read")
                and target is not None
            )
            if denied or concealed:
                return ValidatedOutcome(
                    result="PASS" if order.expected == "DENY" else "FAIL",
                    reason="scoped denial evidence",
                )
            return inconclusive
        if order.expected == "DENY":
            return ValidatedOutcome(
                result="FAIL",
                reason="unexpected forbidden success",
                after=current,
                reconciliation_required=after != before,
            )
        if order.action in ("create", "prepare", "write"):
            returned = (
                metadata(obj["metadata"], folder=True)
                if order.action == "create"
                else metadata({".tag": "file", **obj})
            )
            if (
                target is not None
                or (order.action == "create") != isinstance(returned, FolderObservation)
                or returned.path_display != order.actor_locator
                or len(after) != len(before) + 1
                or after[:-1] != before
                or not _same_object(after[-1], returned)
                or after[-1].path_display != order.logical_path
                or returned.id in {x.id for x in before}
                or (
                    isinstance(returned, FileObservation)
                    and (
                        returned.size != len(PROBE)
                        or returned.content_hash != dropbox_content_hash(PROBE)
                    )
                )
            ):
                return ValidatedOutcome(
                    result="FAIL",
                    reason="exclusive creation/ancestry contradiction",
                    after=current,
                    reconciliation_required=True,
                )
            return ValidatedOutcome(result="PASS", reason="verified new object", after=returned)
        if order.action == "cleanup":
            if not isinstance(target, FileObservation):
                return ValidatedOutcome(result="BLOCKED", reason="no owned file")
            returned = metadata(obj["metadata"])
            args = evidence_json(bytes.fromhex(order.request.body_hex))
            if (
                returned != target
                or args != cleanup_arguments(target, target)
                or after != before[:-1]
            ):
                return ValidatedOutcome(
                    result="BLOCKED",
                    reason="cleanup identity/revision drift",
                    after=current,
                    reconciliation_required=True,
                )
            return ValidatedOutcome(result="PASS", reason="conditional owned-file delete")
        if after != before:
            return ValidatedOutcome(
                result="FAIL",
                reason="read-only operation changed target",
                after=current,
                reconciliation_required=True,
            )
        if order.action in ("read", "cleanup_read"):
            received = (
                metadata({".tag": "file", **evidence_json(first.result_header.encode())})
                if first.result_header
                else None
            )
            if (
                not isinstance(target, FileObservation)
                or not isinstance(received, FileObservation)
                or raw != PROBE
                or (received.id, received.rev, received.size, received.content_hash)
                != (target.id, target.rev, target.size, target.content_hash)
                or received.path_lower != order.actor_locator.lower()
                or sha256(raw) != sha256(PROBE)
            ):
                return inconclusive
            if order.action == "cleanup_read":
                return ValidatedOutcome(
                    result="PASS", reason="fresh exact cleanup bytes", after=received
                )
        elif order.action == "cleanup_metadata":
            returned = metadata(obj)
            if (
                not isinstance(target, FileObservation)
                or not isinstance(returned, FileObservation)
                or not _same_object(target, returned)
                or returned.path_display != order.logical_path
                or not after
                or returned != after[-1]
            ):
                return inconclusive
            return ValidatedOutcome(
                result="PASS", reason="fresh receipt-owned file metadata", after=returned
            )
        elif order.action in ("list", "membership", "links"):
            seen_members: dict[str, str] = {}
            for index, exchange in enumerate(capture.exchanges):
                page = evidence_json(bytes.fromhex(exchange.response_hex))
                if exchange.status != 200:
                    return inconclusive
                if order.action == "list" and not isinstance(page.get("entries"), list):
                    return inconclusive
                if order.action == "membership" and (page.get("groups") or page.get("invitees")):
                    return inconclusive
                if order.action == "membership":
                    if not order.expected_member_roles or not all(
                        isinstance(page.get(k), list) for k in ("users", "groups", "invitees")
                    ):
                        return inconclusive
                    for member in page["users"]:
                        account = member["user"]["account_id"]
                        role = member["access_type"][".tag"]
                        if not isinstance(account, str) or account in seen_members:
                            return inconclusive
                        if member.get("is_inherited") is not False:
                            return inconclusive
                        if order.expected_member_roles.get(account) != role:
                            return ValidatedOutcome(
                                result="FAIL", reason="unexpected active member/access level"
                            )
                        seen_members[account] = role
                if order.action == "links":
                    if not isinstance(page.get("links"), list):
                        return inconclusive
                    if page["links"]:
                        return ValidatedOutcome(
                            result="FAIL", reason="forbidden shared link observed"
                        )
                more = page.get(
                    "has_more", bool(page.get("cursor")) if order.action == "membership" else None
                )
                if more is not (index < len(capture.exchanges) - 1):
                    return inconclusive
            if order.action == "membership" and seen_members != order.expected_member_roles:
                return inconclusive
            if order.action == "links" and order.link_coverage != "offline_complete":
                return inconclusive  # A user-scoped empty page is not universal absence.
        elif order.action in ("share", "share_status"):
            tag = obj.get(".tag")
            pending_tag = "async_job_id" if order.action == "share" else "in_progress"
            if tag == pending_tag:
                fields = {".tag", "async_job_id"} if order.action == "share" else {".tag"}
                if set(obj) != fields:
                    return inconclusive
                job = obj.get("async_job_id") if order.action == "share" else order.async_job_id
                if not isinstance(job, str) or not job:
                    return inconclusive
                return ValidatedOutcome(
                    result="PENDING",
                    reason="share conversion pending; never resubmit",
                    async_job_id=job,
                )
            if tag != "complete" or any(
                k in obj for k in ("failed", "async_job_id", "in_progress")
            ):
                return inconclusive
            if "complete" in obj and set(obj) != {".tag", "complete"}:
                return inconclusive
            completed = obj.get("complete", obj)
            shared = completed.get("shared_folder_id")
            if (
                not isinstance(shared, str)
                or not shared
                or not isinstance(target, FolderObservation)
                or completed.get("path_lower") != order.logical_path.lower()
                or completed.get("name") != target.name
            ):
                return inconclusive
            return ValidatedOutcome(
                result="PASS", reason="captured share conversion", shared_folder_id=shared
            )
        elif order.action == "root":
            info = obj.get("root_info", {})
            if (
                not order.expected_account_id
                or obj.get("account_id") != order.expected_account_id
                or info.get("root_namespace_id") != order.namespace
            ):
                return inconclusive
        elif order.action == "mount":
            locator = obj.get("path_lower")
            if (
                not order.shared_folder_id
                or obj.get("shared_folder_id") != order.shared_folder_id
                or not isinstance(locator, str)
                or obj.get("access_type", {}).get(".tag")
                != order.expected_member_roles.get(order.expected_account_id or "")
            ):
                return inconclusive
            provider_path(locator)
            return ValidatedOutcome(
                result="PASS",
                reason="mount acknowledged; verify folder identity next",
                shared_folder_id=order.shared_folder_id,
                mount_locator=locator,
            )
        elif order.action == "mount_verify":
            returned = metadata(obj)
            if (
                not isinstance(target, FolderObservation)
                or not isinstance(returned, FolderObservation)
                or returned.id != target.id
                or returned.name != target.name
                or returned.path_lower != order.actor_locator.lower()
                or obj.get("sharing_info", {}).get("shared_folder_id") != order.shared_folder_id
            ):
                return inconclusive
            return ValidatedOutcome(
                result="PASS",
                reason="actor mount identity verified",
                after=returned,
                shared_folder_id=order.shared_folder_id,
                mount_locator=order.actor_locator,
            )
        return ValidatedOutcome(result="PASS", reason="consistent captured operation")
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        # Unknown provider variants are retained in original capture, never guessed.
        return inconclusive
