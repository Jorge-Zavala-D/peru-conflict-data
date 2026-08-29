"""Byte-pinned authorization and closed execution-tree validation."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import platform
import ssl
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from peru_conflicts.acquisition.fs_safety import DirectoryLease
from peru_conflicts.acquisition.models_v2 import (
    AuthorizationRegistryV2,
    ExecutionTreeEntryV2,
    ExecutionTreeManifestV2,
    NetworkAuthorizationArtifactV2,
    authorization_registry_core_sha256,
)
from peru_conflicts.hashing import canonical_json_bytes

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_AUTHORIZATION_PATH = (
    REPOSITORY_ROOT
    / "config"
    / "acquisition_authorizations"
    / "m1_03b2_reports_260_269_authorization_v1.json"
)
PRODUCTION_REGISTRY_PATH = (
    REPOSITORY_ROOT / "config" / "acquisition_authorizations" / "reviewed_registry_v2.json"
)
PRODUCTION_REGISTRY_PIN_PATH = (
    REPOSITORY_ROOT / "config" / "acquisition_authorizations" / "reviewed_registry_v2.sha256"
)
_REVIEWED_AUTHORIZATION_SEAL = object()
NETWORK_OVERRIDE_ENVIRONMENT = (
    "ALL_PROXY",
    "CURL_CA_BUNDLE",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
    "OPENSSL_CONF",
    "OPENSSL_CONF_INCLUDE",
    "OPENSSL_ENGINES",
    "OPENSSL_MODULES",
    "REQUESTS_CA_BUNDLE",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "SSLKEYLOGFILE",
)


class AuthorizationError(RuntimeError):
    """Base class for a fail-closed authorization boundary."""


class ArtifactDigestMismatch(AuthorizationError):
    """The caller's exact authorization bytes were not supplied."""


class RegistryTrustError(AuthorizationError):
    """The fixed registry no longer matches its compiled trust anchor."""


class AuthorizationNotReviewed(AuthorizationError):
    """The artifact has no exact semantic grant in the trusted registry."""


class LiveComparePlatformUnsupported(AuthorizationError):
    """Live comparison is limited to the reviewed Windows safety boundary."""


class ExecutionTreeMismatch(AuthorizationError):
    """Runtime executable inputs differ from the reviewed tree."""


def require_live_compare_platform() -> None:
    """Reject non-Windows live execution before protected or network state is read."""

    if os.name != "nt":
        raise LiveComparePlatformUnsupported("live-compare requires the reviewed Windows host")


@dataclass(frozen=True, slots=True)
class ReviewedNetworkAuthorizationV2:
    """Loader-sealed authorization that cannot be replaced by a raw model."""

    artifact: NetworkAuthorizationArtifactV2
    artifact_sha256: str
    protected_main_sha: str
    _seal: object

    @classmethod
    def require(cls, value: object) -> ReviewedNetworkAuthorizationV2:
        if not isinstance(value, cls) or value._seal is not _REVIEWED_AUTHORIZATION_SEAL:
            raise AuthorizationNotReviewed("live comparison requires a loader-sealed authorization")
        return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _trusted_git_executable() -> Path:
    candidate = (
        Path(r"C:\Program Files\Git\cmd\git.exe") if os.name == "nt" else Path("/usr/bin/git")
    )
    try:
        candidate.lstat()
    except OSError as error:
        raise ExecutionTreeMismatch("fixed system Git executable is unavailable") from error
    if not candidate.is_file() or candidate.is_symlink():
        raise ExecutionTreeMismatch("fixed system Git executable is not a direct file")
    return candidate


def _closed_git_environment(repo_root: Path) -> dict[str, str]:
    environment = {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_COUNT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "HOME": str(repo_root / ".git-bootstrap-no-home"),
        "PATH": "/usr/bin:/bin",
    }
    if os.name == "nt":
        environment.update(
            {
                "COMSPEC": r"C:\Windows\System32\cmd.exe",
                "PATH": (
                    r"C:\Program Files\Git\cmd;C:\Program Files\Git\mingw64\bin;"
                    r"C:\Windows\System32"
                ),
                "SYSTEMROOT": r"C:\Windows",
                "WINDIR": r"C:\Windows",
            }
        )
    return environment


def _git_command(*arguments: str) -> list[str]:
    return [
        str(_trusted_git_executable()),
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "diff.external=",
        "-c",
        "credential.helper=",
        *arguments,
    ]


def _git(repo_root: Path, *arguments: str) -> str:
    try:
        return subprocess.run(
            _git_command(*arguments),
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            env=_closed_git_environment(repo_root),
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ExecutionTreeMismatch("Git execution-tree evidence is unavailable") from error


def _git_bytes(repo_root: Path, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            _git_command(*arguments),
            cwd=repo_root,
            check=True,
            capture_output=True,
            env=_closed_git_environment(repo_root),
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ExecutionTreeMismatch("Git execution-tree bytes are unavailable") from error


def read_reviewed_git_blob(repo_root: Path, commit: str, relative_path: str) -> bytes:
    """Read one committed blob through the fixed Git executable and closed environment."""

    blob_id = _git(repo_root, "rev-parse", f"{commit}:{relative_path}")
    return _git_bytes(repo_root, "cat-file", "blob", blob_id)


def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    try:
        result = subprocess.run(
            _git_command("merge-base", "--is-ancestor", ancestor, descendant),
            cwd=repo_root,
            check=False,
            capture_output=True,
            env=_closed_git_environment(repo_root),
        )
    except OSError as error:
        raise ExecutionTreeMismatch("Git ancestry evidence is unavailable") from error
    if result.returncode not in {0, 1}:
        raise ExecutionTreeMismatch("Git ancestry evidence is invalid")
    return result.returncode == 0


def resolve_public_protected_main_sha() -> str:
    """Read public GitHub branch evidence directly with no credentials or proxy inheritance."""

    prohibited = {name.casefold() for name in NETWORK_OVERRIDE_ENVIRONMENT}
    if any(
        name.casefold() in prohibited or name.casefold().startswith("openssl_")
        for name in os.environ
    ):
        raise ExecutionTreeMismatch("proxy, TLS, or OpenSSL override environment is not approved")
    context = ssl.create_default_context()
    if (
        context.verify_mode != ssl.CERT_REQUIRED
        or not context.check_hostname
        or getattr(context, "keylog_filename", None) is not None
    ):
        raise ExecutionTreeMismatch("public GitHub TLS context is not fail closed")
    connection = http.client.HTTPSConnection(
        "api.github.com",
        timeout=30,
        context=context,
    )
    try:
        connection.request(
            "GET",
            "/repos/Jorge-Zavala-D/peru-conflict-data/git/ref/heads/main",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "peru-conflict-data-authorization-bootstrap/1",
            },
        )
        response = connection.getresponse()
        content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].casefold()
        if response.status != 200 or content_type not in {
            "application/json",
            "application/vnd.github+json",
        }:
            raise ExecutionTreeMismatch("protected GitHub main evidence was not accepted")
        body = response.read(65_537)
        if len(body) > 65_536:
            raise ExecutionTreeMismatch("protected GitHub main evidence exceeded its bound")
    except ExecutionTreeMismatch:
        raise
    except Exception as error:
        raise ExecutionTreeMismatch("protected GitHub main evidence is unavailable") from error
    finally:
        connection.close()
    try:
        payload = json.loads(body)
        sha = payload["object"]["sha"]
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ExecutionTreeMismatch("protected GitHub main evidence is malformed") from error
    if (
        not isinstance(sha, str)
        or len(sha) != 40
        or any(character not in "0123456789abcdef" for character in sha)
    ):
        raise ExecutionTreeMismatch("protected GitHub main SHA is invalid")
    return sha


def validate_authorization_against_registry(
    artifact: NetworkAuthorizationArtifactV2,
    registry: AuthorizationRegistryV2,
    *,
    artifact_sha256: str,
) -> NetworkAuthorizationArtifactV2:
    """Require one owner grant for both exact bytes and complete semantics."""

    matches = tuple(
        grant for grant in registry.grants if grant.authorization_id == artifact.authorization_id
    )
    if len(matches) != 1:
        raise AuthorizationNotReviewed("authorization ID has no unique reviewed grant")
    if matches[0].artifact_sha256 != artifact_sha256 or matches[
        0
    ].artifact_core_sha256 != authorization_registry_core_sha256(artifact):
        raise AuthorizationNotReviewed("authorization semantics differ from the reviewed grant")
    return artifact


def load_reviewed_network_authorization(
    path: Path,
    *,
    required_sha256: str,
) -> ReviewedNetworkAuthorizationV2:
    """Load exact artifact bytes only through the independently pinned registry."""

    if path.resolve(strict=False) != PRODUCTION_AUTHORIZATION_PATH.resolve(strict=False):
        raise ArtifactDigestMismatch("authorization artifact is not the fixed reviewed path")
    try:
        artifact_bytes = path.read_bytes()
    except OSError as error:
        raise ArtifactDigestMismatch("authorization artifact could not be read") from error
    if _sha256_bytes(artifact_bytes) != required_sha256:
        raise ArtifactDigestMismatch("authorization artifact SHA-256 mismatch")

    try:
        registry_bytes = PRODUCTION_REGISTRY_PATH.read_bytes()
        registry_pin_bytes = PRODUCTION_REGISTRY_PIN_PATH.read_bytes()
    except OSError as error:
        raise RegistryTrustError("fixed authorization registry or pin could not be read") from error
    try:
        registry_pin = registry_pin_bytes.decode("ascii")
    except UnicodeDecodeError as error:
        raise RegistryTrustError("authorization registry pin is not ASCII") from error
    if (
        len(registry_pin_bytes) != 65
        or not registry_pin.endswith("\n")
        or any(character not in "0123456789abcdef" for character in registry_pin[:-1])
        or _sha256_bytes(registry_bytes) != registry_pin[:-1]
    ):
        raise RegistryTrustError("authorization registry differs from its reviewed pin")

    try:
        registry = AuthorizationRegistryV2.model_validate_json(registry_bytes)
    except ValidationError as error:
        raise RegistryTrustError("fixed authorization registry is structurally invalid") from error
    try:
        artifact = NetworkAuthorizationArtifactV2.model_validate_json(artifact_bytes)
    except ValidationError as error:
        raise AuthorizationNotReviewed("authorization artifact is structurally invalid") from error
    reviewed = validate_authorization_against_registry(
        artifact,
        registry,
        artifact_sha256=required_sha256,
    )
    protected_main_sha = resolve_public_protected_main_sha()
    return ReviewedNetworkAuthorizationV2(
        artifact=reviewed,
        artifact_sha256=required_sha256,
        protected_main_sha=protected_main_sha,
        _seal=_REVIEWED_AUTHORIZATION_SEAL,
    )


def build_execution_tree_manifest(
    repo_root: Path,
    *,
    paths: Sequence[str],
) -> ExecutionTreeManifestV2:
    """Hash an explicit, closed, repository-relative execution input set."""

    if tuple(paths) != tuple(sorted(paths)) or len(set(paths)) != len(paths):
        raise ExecutionTreeMismatch("execution-tree paths must be sorted and unique")
    entries: list[ExecutionTreeEntryV2] = []
    resolved_root = repo_root.resolve(strict=True)
    for relative in paths:
        candidate = repo_root / relative
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise ExecutionTreeMismatch("execution-tree input is absent") from error
        if not resolved.is_relative_to(resolved_root) or not candidate.is_file():
            raise ExecutionTreeMismatch("execution-tree input escapes or is not a file")
        content = candidate.read_bytes()
        entries.append(
            ExecutionTreeEntryV2(
                path=relative.replace("\\", "/"),
                sha256=_sha256_bytes(content),
                byte_count=len(content),
            )
        )
    return ExecutionTreeManifestV2.from_entries(tuple(entries))


def verify_execution_tree(
    *,
    repo_root: Path,
    expected_git_commit: str,
    expected_manifest: ExecutionTreeManifestV2,
    required_paths: Sequence[str],
    external_trust_anchors: Sequence[str] = (),
    protected_main_sha: str,
) -> None:
    """Bind reviewed code to protected remote main and a closed anchor-only delta."""

    head = _git(repo_root, "rev-parse", "HEAD")
    if head != protected_main_sha:
        raise ExecutionTreeMismatch("current HEAD is not public protected GitHub main")
    if not _is_ancestor(repo_root, expected_git_commit, head):
        raise ExecutionTreeMismatch("reviewed execution commit is not an ancestor of current HEAD")
    anchors = tuple(path.replace("\\", "/") for path in external_trust_anchors)
    if tuple(sorted(anchors)) != anchors or len(set(anchors)) != len(anchors):
        raise ExecutionTreeMismatch("external trust anchors must be sorted and unique")
    changed = tuple(
        path
        for path in _git(
            repo_root,
            "diff",
            "--name-only",
            f"{expected_git_commit}..{head}",
            "--",
        ).splitlines()
        if path
    )
    if not set(changed).issubset(anchors):
        raise ExecutionTreeMismatch("trusted main changed files outside external anchors")
    status = _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise ExecutionTreeMismatch("repository is dirty or contains untracked files")
    expected_entries = {entry.path: entry for entry in expected_manifest.entries}
    if tuple(expected_entries) != tuple(required_paths):
        raise ExecutionTreeMismatch("execution-tree manifest path set differs")
    for relative_path in required_paths:
        blob_id = _git(repo_root, "rev-parse", f"{expected_git_commit}:{relative_path}")
        committed = _git_bytes(repo_root, "cat-file", "blob", blob_id)
        entry = expected_entries[relative_path]
        if len(committed) != entry.byte_count or _sha256_bytes(committed) != entry.sha256:
            raise ExecutionTreeMismatch("execution-tree manifest differs from reviewed Git blobs")
    observed = build_execution_tree_manifest(repo_root, paths=required_paths)
    if observed != expected_manifest:
        raise ExecutionTreeMismatch("execution-tree content differs from the reviewed manifest")


def compute_execution_host_identity_sha256() -> str:
    """Return a stable local host identity without reading credential or secret stores."""

    payload = {
        "computer_name": os.environ.get("COMPUTERNAME", ""),
        "host_name": platform.node(),
        "platform": os.name,
    }
    return _sha256_bytes(canonical_json_bytes(payload))


def compute_data_root_identity_sha256(
    data_root: Path,
    *,
    marker_nonce_sha256: str,
    execution_host_identity_sha256: str,
) -> str:
    """Bind path, host, volume/device, root object identity, and owner nonce."""

    resolved = data_root.resolve(strict=True)
    details = resolved.stat()
    return _data_root_identity_sha256(
        resolved_path=resolved,
        device=int(details.st_dev),
        file_id=int(details.st_ino),
        marker_nonce_sha256=marker_nonce_sha256,
        execution_host_identity_sha256=execution_host_identity_sha256,
    )


def compute_leased_data_root_identity_sha256(
    lease: DirectoryLease,
    *,
    marker_nonce_sha256: str,
    execution_host_identity_sha256: str,
) -> str:
    """Bind root identity to the retained directory lease used for child operations."""

    lease.require_bound()
    device, file_id = lease.identity
    observed = _data_root_identity_sha256(
        resolved_path=lease.resolved,
        device=int(device),
        file_id=int(file_id),
        marker_nonce_sha256=marker_nonce_sha256,
        execution_host_identity_sha256=execution_host_identity_sha256,
    )
    lease.require_bound()
    return observed


def _data_root_identity_sha256(
    *,
    resolved_path: Path,
    device: int,
    file_id: int,
    marker_nonce_sha256: str,
    execution_host_identity_sha256: str,
) -> str:
    payload = {
        "resolved_path": (str(resolved_path).casefold() if os.name == "nt" else str(resolved_path)),
        "device": device,
        "file_id": file_id,
        "execution_host_identity_sha256": execution_host_identity_sha256,
        "marker_nonce_sha256": marker_nonce_sha256,
    }
    return _sha256_bytes(canonical_json_bytes(payload))
