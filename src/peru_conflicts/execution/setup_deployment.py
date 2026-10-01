"""Pinned installation verification and private context. No installation ships here.

The fixed application loader chooses the installation, never a grant, CLI flag or
environment variable. Test installations exercise this code via a private harness.
Trusted OS/operator and independently protected pin/checkpoint are prerequisites;
an administrator restoring both stores is not defeated by local hashes.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
from collections.abc import Callable
from contextlib import ExitStack, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import AwareDatetime, model_validator

from peru_conflicts.acquisition.fs_safety import DirectoryLease
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Sha256, StrictModel

from .operational_plan import build_setup_request, evidence_json, make_candidate
from .references import sha256
from .setup_authority import ActorBinding, SetupGrantV2, require_concurrency, validate_grant
from .setup_bridge import digest
from .setup_context import AdmittedContext, _issue_context  # pyright: ignore[reportPrivateUsage]
from .setup_dropbox import RealWorkOrder


class StorePin(StrictModel):
    path: str
    device: int
    inode: int
    access_sha256: Sha256


def access_identity(path: Path) -> str:
    """Measure only the explicitly admitted directory, never enumerate custody."""
    if os.name != "nt":
        st = path.stat()
        if st.st_mode & 0o077:
            raise ValueError("private store permits group/other access")
        return sha256(f"{st.st_uid}:{st.st_gid}:{st.st_mode}".encode())
    # Independently approved owner/DACL descriptor, not an inference from a path.
    from ctypes import wintypes

    get = ctypes.WinDLL("advapi32", use_last_error=True).GetFileSecurityW
    get.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    get.restype = wintypes.BOOL
    size = wintypes.DWORD()
    get(str(path), 7, None, 0, ctypes.byref(size))
    if not 0 < size.value <= 65536:
        raise ValueError("private store access descriptor unavailable")
    buffer = ctypes.create_string_buffer(size.value)
    if not get(str(path), 7, buffer, size.value, ctypes.byref(size)):
        raise ValueError("private store access descriptor unavailable")
    return sha256(buffer.raw[: size.value])


def store_pin(path: Path) -> StorePin:
    """Measurement only; only an independently pinned installation admits a result."""
    absolute = path.absolute()
    with ExitStack() as stack:
        lease = stack.enter_context(DirectoryLease.acquire(Path(absolute.anchor)))
        for part in absolute.parts[1:]:
            lease = stack.enter_context(lease.acquire_child(part))
        return StorePin(
            path=str(lease.resolved),
            device=lease.identity[0],
            inode=lease.identity[1],
            access_sha256=access_identity(lease.resolved),
        )


def source_inventory(root: Path) -> dict[str, str]:
    """Entire project import/entry closure, not just the four collector modules."""
    paths = [
        *root.joinpath("src").rglob("*.py"),
        *root.joinpath("scripts").rglob("*.py"),
        root / "uv.lock",
        root / "pyproject.toml",
    ]
    return {p.relative_to(root).as_posix(): sha256(p.read_bytes()) for p in sorted(paths)}


def runtime_inventory() -> dict[str, str]:
    """Exact venv config, interpreter/link and dependency bytes; stdlib pin is separate."""
    import sysconfig

    from .setup_bootstrap import runtime_layout

    _, site, result = runtime_layout()
    if any(Path(sysconfig.get_path(name)) != site for name in ("purelib", "platlib")):
        raise ValueError("runtime package layout differs")
    for path in sorted(site.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
            raise ValueError("aliased dependency")
        if path.suffix == ".pyc":
            raise ValueError("unmeasured dependency executable")
        if path.is_file():
            result[str(path)] = sha256(path.read_bytes())
        elif not path.is_dir():
            raise ValueError("nonregular dependency")
    return result


class Installation(StrictModel):
    """Private independently pinned installation; contains no tokens."""

    grant_sha256: Sha256
    source_root: str
    source_files: dict[str, Sha256]
    runtime_files: dict[str, Sha256]
    python_environment_sha256: Sha256
    binding_sha256: Sha256
    policy_sha256: Sha256
    capability_sha256: dict[str, Sha256]
    store: StorePin
    checkpoint: StorePin
    witness_store: StorePin
    component_store: StorePin
    forbidden_roots: tuple[str, ...]
    validity_end: AwareDatetime
    revoked: bool = False
    kind: Literal["production", "synthetic_test"]
    credential_refs: dict[str, str]
    scopes: dict[str, tuple[str, ...]]
    transport_profile: Literal["native_required_guarantees", "simulated_application_only"] = (
        "native_required_guarantees"
    )
    test_service_evidence: Literal["complete_synthetic_service"] | None = None

    @model_validator(mode="after")
    def test_evidence_boundary(self) -> Installation:
        if self.test_service_evidence is not None and self.kind != "synthetic_test":
            raise ValueError("synthetic service evidence is not production evidence")
        if self.transport_profile == "simulated_application_only" and self.kind != "synthetic_test":
            raise ValueError("simulated transport cannot establish native capabilities")
        return self


_SOURCE_SEAL = object()


def installation_schema_bytes() -> bytes:
    """Additive operational configuration shape; pins remain independent authority."""
    return (json.dumps(Installation.model_json_schema(), sort_keys=True, indent=2) + "\n").encode()


def export_installation_schema(root: Path) -> Path:
    path = root / "execution" / "setup_installation_v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(installation_schema_bytes())
    return path


def installed_source(context: AdmittedContext) -> InstalledSource:
    """Internal native boundary: fixture contexts cannot select production transport."""
    from .setup_context import require_context

    source = require_context(context)._source  # pyright: ignore[reportPrivateUsage]
    if type(source) is not InstalledSource:
        raise ValueError("installed admission required for native transport")
    return source


class InstalledSource:
    def __init__(
        self,
        *,
        seal: object,
        installation: Installation,
        grant: SetupGrantV2,
        bindings: bytes,
        revalidate: Callable[[], bytes],
        clock: Callable[[], datetime],
    ) -> None:
        if seal is not _SOURCE_SEAL:
            raise ValueError("independent installation admission required")
        self._installation_raw = installation.model_dump_json().encode()
        # Private parsed copy of fixed bytes, not a cached admission decision.
        # Public inspection still returns a detached model; every check below
        # rereads authority and measures current source/resource identities.
        self._installation = Installation.model_validate_json(self._installation_raw)
        self._grant_raw = grant.model_dump_json().encode()
        self._bindings_raw = bytes(bindings)
        self._revalidate = revalidate
        self._clock = clock
        self._last_time = clock()

    @property
    def installation(self) -> Installation:
        return Installation.model_validate_json(self._installation_raw)

    def now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now < self._last_time:
            raise ValueError("authority clock rollback")
        self._last_time = now
        return now

    def check(self, root: Path, checkpoint: Path) -> SetupGrantV2:
        pin = self._installation
        current = None
        with suppress(Exception):
            current = self._revalidate()
        # Raise outside the handler so an authority-reader diagnostic cannot leak.
        if current is None:
            raise ValueError("installation authority could not be revalidated")
        if current != self._installation_raw or pin.revoked:
            raise ValueError("installation changed/revoked")
        grant = SetupGrantV2.model_validate_json(self._grant_raw)
        now = self.now()
        if not grant.not_before <= now < min(grant.not_after, pin.validity_end):
            raise ValueError("admission validity expired")
        # Reject caller-selected alternate addresses before following their parents.
        if (
            root.absolute() != Path(pin.store.path)
            or checkpoint.absolute() != Path(pin.checkpoint.path)
            or root.resolve() != Path(pin.store.path)
            or checkpoint.resolve() != Path(pin.checkpoint.path)
        ):
            raise ValueError("admission store mismatch")
        if source_inventory(Path(pin.source_root)) != pin.source_files:
            raise ValueError("implementation changed")
        require_concurrency(grant, pin.policy_sha256, now)
        if grant.capability_sha256 != pin.capability_sha256:
            raise ValueError("capability evidence mismatch")
        self._validate_store_pins()
        return grant

    def validate_store(self, root: Path, checkpoint: Path) -> None:
        self.check(root, checkpoint)

    def _validate_store_pins(self) -> None:
        pin = self._installation
        stores = (pin.store, pin.checkpoint, pin.witness_store, pin.component_store)
        for expected in stores:
            path = Path(expected.path)
            if not path.is_absolute() or any(
                path.is_relative_to(Path(x)) for x in pin.forbidden_roots
            ):
                raise ValueError("private store location not admitted")
            if store_pin(path) != expected:
                raise ValueError("private store identity/access changed")
        for i, left in enumerate(stores):
            for right in stores[i + 1 :]:
                a, b = Path(left.path), Path(right.path)
                if a.is_relative_to(b) or b.is_relative_to(a):
                    raise ValueError("private stores must be independent")

    def actor(self, binding: ActorBinding) -> tuple[str, str]:
        grant = SetupGrantV2.model_validate_json(self._grant_raw)
        if binding not in grant.sessions:
            raise ValueError("actor not admitted")
        values = evidence_json(self._bindings_raw)[binding.account_ref]
        if (
            not isinstance(values, list)
            or len(cast(list[Any], values)) != 2
            or not all(isinstance(x, str) and x for x in cast(list[Any], values))
        ):
            raise ValueError("private actor binding malformed")
        return cast(str, values[0]), cast(str, values[1])

    def witness(self, order: RealWorkOrder) -> str:
        # Independent owner-controlled ingress index, not a digest from the upload.
        value = None
        with suppress(Exception):
            raw = self._read_witness_file(digest(order) + ".json", 8192)
            record = evidence_json(raw)
            candidate = record["capture"]
            if (
                set(record) == {"order", "capture"}
                and record["order"] == digest(order)
                and isinstance(candidate, str)
                and len(candidate) == 64
                and all(x in "0123456789abcdef" for x in candidate)
            ):
                value = candidate
        if value is None:
            raise ValueError("independent witness unavailable or invalid")
        return value

    def _read_witness_file(self, name: str, limit: int) -> bytes:
        raw = None
        with suppress(Exception):
            pin = self._installation.witness_store
            if store_pin(Path(pin.path)) != pin:
                raise ValueError("witness store changed")
            with DirectoryLease.acquire(Path(pin.path)) as lease:
                # Validate the acquired resource, not only the earlier pathname.
                if (
                    lease.identity != (pin.device, pin.inode)
                    or access_identity(lease.resolved) != pin.access_sha256
                ):
                    raise ValueError("witness acquisition changed")
                with lease.open_child_read(name) as stream:
                    received = stream.read(limit + 1)
                lease.require_bound()
                if len(received) <= limit:
                    raw = received
        if raw is None:
            raise ValueError("admitted witness source read failed or exceeded bound")
        return raw

    def capture_original(self, expected: str) -> bytes:
        """The admitted witness store also holds its transferred originals.

        The independently registered digest is the only permitted file address;
        there is no uploaded locator or caller-selected capture directory.
        """
        if len(expected) != 64 or any(x not in "0123456789abcdef" for x in expected):
            raise ValueError("invalid independent capture address")
        return self._read_witness_file(expected + ".capture", 8388608)

    def concealment(self) -> bool:
        return self._installation.test_service_evidence == "complete_synthetic_service"

    def component_store(self) -> Path:
        self._validate_store_pins()
        return Path(self._installation.component_store.path)

    def link_coverage(self) -> Literal["not_established", "offline_complete"]:
        # Only an independently pinned TEST service can provide complete visibility.
        if self._installation.test_service_evidence == "complete_synthetic_service":
            return "offline_complete"
        return "not_established"


def _load_verified(  # pyright: ignore[reportUnusedFunction]
    raw: bytes,
    installation_raw: bytes,
    expected_installation_sha256: str,
    private_reader: Callable[[], bytes],
    revalidate: Callable[[], bytes],
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> AdmittedContext:
    """Internal verifier; the fixed application trust source supplies the expected pin.

    Tests independently pin an installation at this seam, not in uploaded grants.
    No application option selects this source or permits synthetic installations.
    """
    if sha256(installation_raw) != expected_installation_sha256:
        raise ValueError("installation pin mismatch")
    evidence_json(installation_raw)
    pin = Installation.model_validate_json(installation_raw)
    now = clock()
    if now.tzinfo is None or now >= pin.validity_end:
        raise ValueError("installation validity expired")
    if pin.revoked or sha256(raw) != pin.grant_sha256:
        raise ValueError("unregistered/revoked grant")
    if source_inventory(Path(pin.source_root)) != pin.source_files:
        raise ValueError("reviewed implementation mismatch")
    if runtime_inventory() != pin.runtime_files:
        raise ValueError("reviewed runtime mismatch")
    from .python_environment_policy import capture_document

    dependency = sha256(canonical_json_bytes(pin.runtime_files))
    if capture_document(dependency)["python_environment_sha256"] != pin.python_environment_sha256:
        raise ValueError("reviewed Python environment mismatch")
    if pin.kind == "production" and not sys.flags.isolated:
        raise ValueError("isolated reviewed launcher required")
    request, components = build_setup_request(make_candidate())
    request_raw = (json.dumps(request, sort_keys=True, ensure_ascii=True, indent=2) + "\n").encode()
    grant = validate_grant(
        raw, request_raw, components, sha256(canonical_json_bytes(pin.source_files)), clock()
    )
    require_concurrency(grant, pin.policy_sha256, clock())
    if (
        grant.private_bindings_sha256 != pin.binding_sha256
        or grant.capability_sha256 != pin.capability_sha256
    ):
        raise ValueError("independently pinned binding/capability mismatch")
    # Private resolution happens only after public authority/runtime validation.
    bindings = private_reader()
    if sha256(bindings) != pin.binding_sha256:
        raise ValueError("private binding source mismatch")
    source = InstalledSource(
        seal=_SOURCE_SEAL,
        installation=pin,
        grant=grant,
        bindings=bindings,
        revalidate=revalidate,
        clock=clock,
    )
    source.validate_store(Path(pin.store.path), Path(pin.checkpoint.path))
    return _issue_context(source)
