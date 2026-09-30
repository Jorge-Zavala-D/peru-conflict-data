"""Bounded native Dropbox capture. No SDK, retries, redirects or ambient endpoints.

The application can only reach this module after fixed-source admission. Synthetic
installations additionally require a replaced low-level connection; they cannot
open the native network boundary. No installation or credential ships here.
"""

from __future__ import annotations

import ctypes
import http.client
import json
import os
import ssl
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import PurePosixPath
from typing import Any, cast

from .operational_plan import evidence_json
from .setup_bridge import digest
from .setup_deployment import installed_source
from .setup_dropbox import (
    Exchange,
    FileObservation,
    FolderObservation,
    OriginalCapture,
    PreparedRequest,
    ValidatedOutcome,
    _same_object,  # pyright: ignore[reportPrivateUsage]
    encode_request,
    metadata,
)
from .setup_evidence import EvidenceJournal

_connection = http.client.HTTPSConnection
_MAX_RESPONSE = 1048576
_TIMEOUT = 15.0
_MAX_HEADERS = 32768
_MAX_HEADER_COUNT = 64
_MAX_READS = 4096
_ACTION_BYTES = 8388608
_ACTION_REQUESTS = 256
_MAX_PAGES = 200


class _NativeCapabilityUnavailable(Exception):
    """Static capability failure; never carries provider or credential text."""


class _InterruptedExchange(Exception):
    """Bounded, secret-screened original; never eligible for semantic success."""

    def __init__(self, exchange: Exchange, complete: bool):
        super().__init__("native response interrupted")
        self.exchange = exchange
        self.complete = complete


def _read_credential(reference: str) -> str:
    """Future Windows generic credential, exact independently pinned target only.

    This function is never invoked by development tests or empty-registry entry.
    There is no enumeration, interactive login, environment token or fallback.
    """
    if os.name != "nt" or not reference.startswith("m2-setup/") or len(reference) > 200:
        raise ValueError("unsupported installed credential reference")
    from ctypes import wintypes

    class Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(Credential)),
    ]
    api.CredReadW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    pointer = ctypes.POINTER(Credential)()
    if not api.CredReadW(reference, 1, 0, ctypes.byref(pointer)):
        raise ValueError("installed credential unavailable")
    try:
        if not 0 < pointer.contents.CredentialBlobSize <= 8192:
            raise ValueError("invalid installed credential")
        return ctypes.string_at(
            pointer.contents.CredentialBlob, pointer.contents.CredentialBlobSize
        ).decode("ascii")
    finally:
        api.CredFree(pointer)


def _canonical(request: PreparedRequest) -> None:
    root = json.loads(request.root_header)
    arguments = json.loads(request.api_arg or bytes.fromhex(request.body_hex) or b"{}")
    if request != encode_request(
        request.route,
        arguments,
        root["namespace_id"],
        request.actor_session_ref,
        upload=bytes.fromhex(request.body_hex) if request.route == "files/upload" else None,
    ):
        raise ValueError("unapproved request encoding")


def _exchange(
    request: PreparedRequest,
    credential_ref: str,
    before_send: Callable[[], None],
    credentials: dict[str, str],
    remaining: list[int] | None = None,
) -> Exchange:
    """One request only. Exceptions never render provider/credential text."""
    _canonical(request)
    # Read names only, never environment secrets. No ambient proxy/TLS overrides.
    if any(
        k.upper() in {"HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR"}
        for k in os.environ
    ):
        raise ValueError("ambient network configuration is not admitted")
    secret: str | None = credentials.get(credential_ref)
    with suppress(Exception):
        if secret is None:
            secret = _read_credential(credential_ref)
    if secret is None:
        raise ValueError("installed credential unavailable; consumed intent remains UNKNOWN")
    if not secret or len(secret) > 8192 or not secret.isascii() or any(c.isspace() for c in secret):
        raise ValueError("invalid installed credential")
    credentials[credential_ref] = secret
    tls = ssl.create_default_context()
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    host = (
        "content.dropboxapi.com"
        if request.route in ("files/upload", "files/download")
        else "api.dropboxapi.com"
    )
    headers = {
        "Authorization": "Bearer " + secret,
        "Dropbox-API-Path-Root": request.root_header,
        "Content-Type": "application/octet-stream" if request.api_arg else "application/json",
    }
    if request.api_arg is not None:
        headers["Dropbox-API-Arg"] = request.api_arg
    connection: Any = None
    failure = False
    result: Exchange | None = None
    body = bytearray()
    admissible = False
    complete = False
    request_id = result_header = None
    status = 0
    start = time.monotonic()

    def charge(size: int) -> None:
        if remaining is not None:
            if size > remaining[0]:
                raise ValueError("operation byte bound exhausted")
            remaining[0] -= size

    try:
        payload = bytes.fromhex(request.body_hex)
        # Encoded HTTP/1 application fields, not TLS/raw-wire measurement.
        header_size = sum(
            len(k.encode("ascii")) + len(v.encode("latin-1")) + 4 for k, v in headers.items()
        )
        if header_size > _MAX_HEADERS:
            raise ValueError("request header bound")
        automatic = (
            f"POST /2/{request.route} HTTP/1.1\r\nHost: {host}\r\n"
            f"Content-Length: {len(payload)}\r\nAccept-Encoding: identity\r\n\r\n"
        ).encode("ascii")
        charge(len(payload) + header_size + len(automatic))
        before_send()
        connection = _connection(host, timeout=_TIMEOUT, context=tls)
        before_send()
        connection.request("POST", "/2/" + request.route, payload, headers)
        response = connection.getresponse()
        status = response.status
        if not isinstance(status, int) or not 100 <= status <= 599:
            raise ValueError("invalid HTTP status")
        received_headers = response.getheaders()
        if len(received_headers) > _MAX_HEADER_COUNT:
            raise ValueError("response header count bound")
        parsed: dict[str, list[str]] = {}
        header_size = 0
        for key, value in received_headers:
            if not key or not key.isascii() or any(not (c.isalnum() or c == "-") for c in key):
                raise ValueError("invalid response header name")
            if len(value) > 16384 or any(ord(c) < 32 and c != "\t" for c in value):
                raise ValueError("invalid response header value")
            header_size += len(key.encode("ascii")) + len(value.encode("latin-1")) + 4
            parsed.setdefault(key.lower(), []).append(value)
        if header_size > _MAX_HEADERS:
            raise ValueError("parsed response header bound")
        charge(header_size)
        for key in (
            "content-length",
            "transfer-encoding",
            "x-dropbox-request-id",
            "dropbox-api-result",
        ):
            if len(parsed.get(key, [])) > 1:
                raise ValueError("duplicate response discriminator")
        length = next(iter(parsed.get("content-length", [])), None)
        transfer = next(iter(parsed.get("transfer-encoding", [])), None)
        if transfer not in (None, "chunked") or (transfer and length is not None):
            raise ValueError("ambiguous response framing")
        if length is not None and (
            not length.isascii() or not length.isdecimal() or len(length) > 10
        ):
            raise ValueError("invalid response length")
        expected_length = int(length) if length is not None else None
        if expected_length is not None and expected_length > _MAX_RESPONSE:
            raise ValueError("response length bound")
        request_id = next(iter(parsed.get("x-dropbox-request-id", [])), None)
        result_header = next(iter(parsed.get("dropbox-api-result", [])), None)
        if any(
            token in field
            for token in credentials.values()
            for field in (request_id or "", result_header or "")
        ):
            raise ValueError("credential-bearing response discriminator")
        admissible = True
        for read_index in range(_MAX_READS):
            if time.monotonic() - start > _TIMEOUT:
                raise ValueError("response elapsed bound")
            allowance = min(65536, _MAX_RESPONSE - len(body))
            if remaining is not None:
                allowance = min(allowance, remaining[0])
            if allowance <= 0:
                raise ValueError("response allowance exhausted without complete framing")
            chunk = response.read1(allowance)
            if len(chunk) > allowance:
                admissible = False
                raise ValueError("HTTP body API exceeded admitted read")
            body.extend(chunk)
            charge(len(chunk))
            if time.monotonic() - start > _TIMEOUT:
                raise ValueError("response elapsed bound")
            if not chunk:
                break
            if (
                read_index + 1 == _MAX_READS
                or len(body) == _MAX_RESPONSE
                or (remaining is not None and remaining[0] == 0)
            ) and response.isclosed():
                # HTTP framing/EOF evidence, not an uncharged sentinel or read(0).
                # This bounds returned application bytes, not buffered/TLS ingress.
                break
        else:
            raise ValueError("response read count bound")
        if expected_length is not None and len(body) != expected_length:
            raise ValueError("incomplete or contradictory response length")
        complete = True
        result = Exchange(
            request=request,
            status=status,
            provider_request_id=request_id,
            result_header=result_header,
            response_hex=body.hex(),
        )
    except Exception:
        failure = True
    finally:
        headers.clear()
        secret = ""
        if connection is not None:
            try:
                connection.close()
            except Exception:
                failure = True
    # Screen partial bodies against all credentials resolved for this action.
    # This bounded exclusion is not a universal secret-free proof.
    if any(token.encode() in body for token in credentials.values()):
        admissible = False
        result = None
        failure = True
    if failure or result is None:
        if admissible and body:
            interrupted = Exchange(
                request=request,
                status=status,
                provider_request_id=request_id,
                result_header=result_header,
                response_hex=body.hex(),
            )
            raise _InterruptedExchange(interrupted, complete)
        raise ValueError("native exchange unavailable; consumed intent remains UNKNOWN")
    return result


def capture_once(journal: EvidenceJournal) -> ValidatedOutcome:
    """Never expose provider, resolver or persistence exception text or chains."""
    if type(journal) is not EvidenceJournal:
        raise ValueError("installed journal admission required")
    outcome = None
    unavailable = False
    try:
        outcome = _capture_once(journal)
    except _NativeCapabilityUnavailable:
        unavailable = True
    except Exception:
        pass
    if unavailable:
        raise ValueError("required native hard-deadline/raw-ingress/parser bounds unavailable")
    if outcome is None:
        raise ValueError("native capture stopped; inspect admitted journal; no automatic retry")
    return outcome


def _capture_once(journal: EvidenceJournal) -> ValidatedOutcome:
    """Consume one admitted intent and capture it. No implicit release or retry."""
    if type(journal) is not EvidenceJournal:
        raise ValueError("installed journal admission required")
    context = journal._admission  # pyright: ignore[reportPrivateUsage]
    source = installed_source(context)
    pin = source.installation
    if pin.transport_profile != "simulated_application_only":
        # Stdlib inactivity timeouts and post-return clocks cannot cancel DNS/read,
        # bound raw TLS ingress or prevent header-parser allocation. A policy pin
        # cannot manufacture these missing native capabilities.
        raise _NativeCapabilityUnavailable
    if pin.kind == "synthetic_test" and _connection is http.client.HTTPSConnection:
        raise ValueError("synthetic admission cannot use native network")
    order = journal.pending
    if order is None:
        raise ValueError("no released intent")
    if order.action == "control":
        raise ValueError("component controls cannot dispatch to a provider")
    _canonical(order.request)
    reference = pin.credential_refs.get(order.actor.session_ref)
    if reference is None or order.request.scope not in pin.scopes.get(order.actor.session_ref, ()):
        raise ValueError("missing installed session/scope binding")
    started = context.now()
    journal.consume(order)

    def before_send() -> None:
        journal._check_admission()  # pyright: ignore[reportPrivateUsage]
        if (
            order != journal.pending
            or not order.issued_at <= context.now() < order.dispatch_not_after
        ):
            raise ValueError("protected request expired or changed before network dispatch")

    grant = journal._check_admission()  # pyright: ignore[reportPrivateUsage]
    coordinator = next(s for s in grant.sessions if s.actor == "coordinator")
    coordinator_account, coordinator_namespace = context.actor(coordinator)
    credentials: dict[str, str] = {}
    count = 0
    remaining = [_ACTION_BYTES]

    def send(request: PreparedRequest, phase: str = "operation") -> Exchange:
        nonlocal count
        binding = next(
            (s for s in grant.sessions if s.session_ref == request.actor_session_ref), None
        )
        if binding is None:
            raise ValueError("unadmitted session")
        namespace = context.actor(binding)[1]
        if json.loads(request.root_header) != {".tag": "namespace_id", "namespace_id": namespace}:
            raise ValueError("unadmitted namespace")
        credential = pin.credential_refs.get(binding.session_ref)
        if credential is None or request.scope not in pin.scopes.get(binding.session_ref, ()):
            raise ValueError("missing installed session/scope binding")
        if count >= _ACTION_REQUESTS:
            raise ValueError("operation request/byte budget exhausted")
        count += 1
        interruption = None
        response = None
        try:
            response = _exchange(request, credential, before_send, credentials, remaining)
        except _InterruptedExchange as error:
            interruption = error
        if interruption is not None:
            response = interruption.exchange
        if response is None:
            raise ValueError("native exchange unavailable")
        # Retention does not renew dispatch permission or reset action consumption.
        if phase == "operation" or interruption is not None:
            journal._native_exchange(  # pyright: ignore[reportPrivateUsage]
                order,
                response.model_dump(mode="json"),
                interrupted_phase=phase if interruption is not None else None,
                complete=interruption.complete if interruption is not None else False,
            )
        else:
            journal._native_observation(order, phase, response.model_dump(mode="json"))  # pyright: ignore[reportPrivateUsage]
        if interruption is not None:
            raise ValueError("received response interrupted; intent remains UNKNOWN")
        return response

    def observe_account(session: str, namespace: str, account: str) -> None:
        observed = send(
            encode_request("users/get_current_account", {}, namespace, session), "actor"
        )
        value = evidence_json(bytes.fromhex(observed.response_hex))
        if (
            observed.status != 200
            or not observed.provider_request_id
            or value.get("account_id") != account
            or value.get("root_info", {}).get("root_namespace_id") != namespace
        ):
            raise ValueError("inconclusive actor/account/root prerequisite")

    def snapshot(phase: str) -> tuple[str, ...]:
        paths = [b.logical_path for b in order.before]
        if order.logical_path not in paths:
            paths.append(order.logical_path)
        originals: list[str] = []
        for path in paths:
            observed = send(
                encode_request(
                    "files/get_metadata",
                    {
                        "path": path,
                        "include_deleted": False,
                    },
                    coordinator_namespace,
                    coordinator.session_ref,
                ),
                phase,
            )
            value = evidence_json(bytes.fromhex(observed.response_hex))
            if not observed.provider_request_id:
                raise ValueError("inconclusive metadata prerequisite")
            if observed.status == 200:
                current = metadata(value)
                if current.path_display != path:
                    raise ValueError("metadata locator mismatch")
                originals.append(observed.response_hex)
            elif not (
                observed.status == 409
                and value.get("error")
                == {
                    ".tag": "path",
                    "path": {".tag": "not_found"},
                }
            ):
                raise ValueError("inconclusive metadata observation")
        return tuple(originals)

    try:
        before: tuple[str, ...] = ()
        if order.action != "root":
            observe_account(
                order.actor.session_ref, order.namespace, order.expected_account_id or ""
            )
            if order.actor != coordinator:
                observe_account(coordinator.session_ref, coordinator_namespace, coordinator_account)
            before = snapshot("before")
            observed_before = tuple(metadata(evidence_json(bytes.fromhex(x))) for x in before)
            if len(observed_before) != len(order.before) or any(
                not isinstance(bound.observation, (FileObservation, FolderObservation))
                or not _same_object(current, bound.observation)
                or current.path_display != bound.logical_path
                for current, bound in zip(observed_before, order.before, strict=True)
            ):
                raise ValueError("fresh prerequisite identity/revision/ancestry contradiction")
            if order.shared_folder_id and order.action not in ("share", "share_status"):
                shared = [
                    evidence_json(bytes.fromhex(raw))
                    for raw in before
                    if metadata(evidence_json(bytes.fromhex(raw))).path_display
                    == order.logical_path
                ]
                if (
                    len(shared) != 1
                    or shared[0].get("sharing_info", {}).get("shared_folder_id")
                    != order.shared_folder_id
                ):
                    raise ValueError("completed share prerequisite changed")
            if (
                order.actor.actor != "coordinator"
                and order.action in ("list", "read", "write")
                and order.actor_locator.startswith("/")
                and order.actor_locator != order.logical_path
            ):
                # Only re-observe an admitted own mount, never the unshared parent.
                logical, locator = order.logical_path, order.actor_locator
                if order.action == "write":
                    logical = str(PurePosixPath(logical).parent)
                    locator = str(PurePosixPath(locator).parent)
                bound = next(
                    (b.observation for b in order.before if b.logical_path == logical), None
                )
                observed = send(
                    encode_request(
                        "files/get_metadata",
                        {"path": locator, "include_deleted": False},
                        order.namespace,
                        order.actor.session_ref,
                    ),
                    # Actor evidence is separate from coordinator before/after
                    # snapshots and from the exact action exchange sequence.
                    "actor",
                )
                if observed.status != 200 or not observed.provider_request_id:
                    raise ValueError("verified actor mount unavailable")
                current = metadata(evidence_json(bytes.fromhex(observed.response_hex)))
                if (
                    not isinstance(bound, (FileObservation, FolderObservation))
                    or not _same_object(current, bound)
                    or current.path_lower != locator.lower()
                ):
                    raise ValueError("verified actor mount identity/locator changed")
            if order.action == "cleanup" and (
                order.target is None or not isinstance(order.target.observation, FileObservation)
            ):
                raise ValueError("cleanup requires receipt-owned file")
        exchanges = [send(order.request)]
        continuation = {
            "list": "files/list_folder/continue",
            "membership": "sharing/list_folder_members/continue",
            "links": "sharing/list_shared_links",
        }.get(order.action)
        cursors: set[str] = set()
        while continuation and exchanges[-1].status == 200:
            try:
                page = evidence_json(bytes.fromhex(exchanges[-1].response_hex))
            except (ValueError, TypeError):
                break  # Retained malformed page is classified, not replaced.
            more = (
                bool(page.get("cursor")) if order.action == "membership" else page.get("has_more")
            )
            cursor = page.get("cursor")
            if not more:
                break
            if len(exchanges) >= _MAX_PAGES:
                raise ValueError("continuation page bound exhausted")
            if not isinstance(cursor, str) or not cursor or cursor in cursors:
                break  # Terminal incompleteness is a classifier stop, never PASS.
            cursors.add(cursor)
            exchanges.append(
                send(
                    encode_request(
                        continuation, {"cursor": cursor}, order.namespace, order.actor.session_ref
                    )
                )
            )
        after = snapshot("after") if order.action != "root" else ()
        if order.action in ("share", "share_status") and exchanges[-1].status == 200:
            response = evidence_json(bytes.fromhex(exchanges[-1].response_hex))
            if response.get(".tag") == "complete":
                completed = response.get("complete")
                observed = [
                    evidence_json(bytes.fromhex(raw))
                    for raw in after
                    if metadata(evidence_json(bytes.fromhex(raw))).path_display
                    == order.logical_path
                ]
                if (
                    not isinstance(completed, dict)
                    or len(observed) != 1
                    or not isinstance(observed[0].get("sharing_info"), dict)
                    or cast(dict[str, Any], completed).get("shared_folder_id")
                    != observed[0]["sharing_info"].get("shared_folder_id")
                    or not cast(dict[str, Any], completed).get("shared_folder_id")
                ):
                    raise ValueError("completed share differs from independently observed resource")
        raw = (
            OriginalCapture(
                order_sha256=digest(order),
                actor_session_ref=order.actor.session_ref,
                namespace=order.namespace,
                started=started,
                ended=context.now(),
                exchanges=tuple(exchanges),
                before_hex=before,
                after_hex=after,
            )
            .model_dump_json()
            .encode()
        )
        return journal._native_capture(raw)  # pyright: ignore[reportPrivateUsage]
    finally:
        credentials.clear()
