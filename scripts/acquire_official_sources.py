"""Run the dry-run plan or a future isolated, reviewed compare-only pilot."""

# ruff: noqa: E402 -- reject OpenSSL controls before OpenSSL-backed imports.

from __future__ import annotations

import os
import sys

LIVE_MODE = "live-compare"
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


def _early_live_mode_requested(arguments: tuple[str, ...]) -> bool:
    return any(
        token == f"--mode={LIVE_MODE}"
        or (token == "--mode" and index + 1 < len(arguments) and arguments[index + 1] == LIVE_MODE)
        for index, token in enumerate(arguments)
    )


def _has_network_or_openssl_override() -> bool:
    prohibited = {name.casefold() for name in NETWORK_OVERRIDE_ENVIRONMENT}
    return any(
        name.casefold() in prohibited or name.casefold().startswith("openssl_")
        for name in os.environ
    )


if _early_live_mode_requested(tuple(sys.argv[1:])) and _has_network_or_openssl_override():
    raise SystemExit(
        "live-compare bootstrap rejected: proxy, TLS, or OpenSSL override environment "
        "is not approved"
    )

import base64
import csv
import hashlib
import http.client
import importlib.util
import io
import json
import ssl
import stat
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

GITHUB_API_HOST = "api.github.com"
GITHUB_MAIN_REF_PATH = "/repos/Jorge-Zavala-D/peru-conflict-data/git/ref/heads/main"
REGISTRY_RELATIVE_PATH = "config/acquisition_authorizations/reviewed_registry_v2.json"
REGISTRY_PIN_RELATIVE_PATH = "config/acquisition_authorizations/reviewed_registry_v2.sha256"
MANIFEST_RELATIVE_PATH = "config/acquisition_authorizations/execution_tree_manifest_v2.json"
FUTURE_AUTHORIZATION_RELATIVE_PATH = (
    "config/acquisition_authorizations/m1_03b2_reports_260_269_authorization_v1.json"
)
EXTERNAL_TRUST_ANCHORS = tuple(
    sorted(
        (
            FUTURE_AUTHORIZATION_RELATIVE_PATH,
            MANIFEST_RELATIVE_PATH,
            REGISTRY_PIN_RELATIVE_PATH,
            REGISTRY_RELATIVE_PATH,
        )
    )
)
BOOTSTRAP_REQUIRED_PATHS = tuple(
    sorted(
        (
            "config/acquisition_pilots/m1_03_reports_260_269_v2.yaml",
            "docs/source_integrity_receipt_m1_03b1.md",
            "pyproject.toml",
            "scripts/acquire_official_sources.py",
            "src/peru_conflicts/__init__.py",
            "src/peru_conflicts/acquisition/__init__.py",
            "src/peru_conflicts/acquisition/attempt_transport.py",
            "src/peru_conflicts/acquisition/authorization.py",
            "src/peru_conflicts/acquisition/cli.py",
            "src/peru_conflicts/acquisition/compare_runner.py",
            "src/peru_conflicts/acquisition/engine.py",
            "src/peru_conflicts/acquisition/fs_safety.py",
            "src/peru_conflicts/acquisition/landing.py",
            "src/peru_conflicts/acquisition/ledger.py",
            "src/peru_conflicts/acquisition/live_compare.py",
            "src/peru_conflicts/acquisition/models.py",
            "src/peru_conflicts/acquisition/models_v2.py",
            "src/peru_conflicts/acquisition/persistent_ledger.py",
            "src/peru_conflicts/acquisition/plan.py",
            "src/peru_conflicts/acquisition/policy.py",
            "src/peru_conflicts/acquisition/preflight.py",
            "src/peru_conflicts/acquisition/storage.py",
            "src/peru_conflicts/acquisition/temp_recovery.py",
            "src/peru_conflicts/acquisition/transport.py",
            "src/peru_conflicts/discovery/pilot.py",
            "src/peru_conflicts/discovery/policy.py",
            "src/peru_conflicts/discovery/settings.py",
            "src/peru_conflicts/hashing.py",
            "src/peru_conflicts/models/__init__.py",
            "src/peru_conflicts/models/common.py",
            "src/peru_conflicts/paths.py",
            "uv.lock",
        )
    )
)
REJECTED_PYTHON_ENVIRONMENT = (
    "PYTHONBREAKPOINT",
    "PYTHONCASEOK",
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONPATH",
    "PYTHONPLATLIBDIR",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "PYTHONWARNINGS",
)
REQUIRED_DEPENDENCY_DISTRIBUTIONS = (
    "annotated-types",
    "pydantic",
    "pydantic-core",
    "pyyaml",
    "typing-extensions",
    "typing-inspection",
)
FORBIDDEN_SITE_SHADOWS = (
    "email",
    "hashlib.py",
    "http",
    "importlib",
    "json",
    "os.py",
    "pathlib.py",
    "ssl.py",
    "subprocess.py",
    "urllib",
)


class BootstrapError(RuntimeError):
    """The live executable did not establish its pre-import trust boundary."""


class _BootstrapHttpResponse(Protocol):
    status: int

    def getheader(self, name: str) -> str | None: ...

    def read(self, amt: int | None = None) -> bytes: ...


class _BootstrapHttpsConnection(Protocol):
    def request(self, method: str, url: str, *, headers: dict[str, str]) -> None: ...

    def getresponse(self) -> _BootstrapHttpResponse: ...

    def close(self) -> None: ...


class _BootstrapHttpsFactory(Protocol):
    def __call__(
        self,
        host: str,
        *,
        timeout: int,
        context: ssl.SSLContext,
    ) -> _BootstrapHttpsConnection: ...


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _mapping(value: object, *, description: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise BootstrapError(f"{description} is not a JSON object")
    raw = cast(dict[object, object], value)
    if any(not isinstance(key, str) for key in raw):
        raise BootstrapError(f"{description} has a non-string key")
    return {cast(str, key): item for key, item in raw.items()}


def _sequence(value: object, *, description: str) -> list[object]:
    if not isinstance(value, list):
        raise BootstrapError(f"{description} is not a JSON array")
    return cast(list[object], value)


def _text(mapping: dict[str, object], key: str, *, description: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise BootstrapError(f"{description} has no valid {key}")
    return value


def _option_value(arguments: tuple[str, ...], name: str) -> str | None:
    values: list[str] = []
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if token == name:
            if index + 1 >= len(arguments):
                raise BootstrapError(f"{name} has no value")
            values.append(arguments[index + 1])
            index += 2
            continue
        prefix = f"{name}="
        if token.startswith(prefix):
            values.append(token[len(prefix) :])
        index += 1
    if len(values) > 1:
        raise BootstrapError(f"{name} may be supplied only once")
    return values[0] if values else None


def _trusted_git_executable() -> Path:
    candidate = (
        Path(r"C:\Program Files\Git\cmd\git.exe") if os.name == "nt" else Path("/usr/bin/git")
    )
    try:
        details = candidate.lstat()
    except OSError as error:
        raise BootstrapError("fixed system Git executable is unavailable") from error
    if not stat.S_ISREG(details.st_mode) or candidate.is_symlink():
        raise BootstrapError("fixed system Git executable is not a direct file")
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


def _run_git(repo_root: Path, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            _git_command(*arguments),
            cwd=repo_root,
            check=True,
            capture_output=True,
            env=_closed_git_environment(repo_root),
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise BootstrapError("Git bootstrap evidence is unavailable") from error


def _run_git_text(repo_root: Path, *arguments: str) -> str:
    try:
        return _run_git(repo_root, *arguments).decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise BootstrapError("Git bootstrap evidence is not UTF-8") from error


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
        raise BootstrapError("Git ancestry evidence is unavailable") from error
    if result.returncode not in {0, 1}:
        raise BootstrapError("Git ancestry evidence is invalid")
    return result.returncode == 0


def _require_direct_file(repo_root: Path, relative_path: str) -> bytes:
    candidate = repo_root / relative_path
    current = repo_root
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for part in Path(relative_path).parts:
        current = current / part
        try:
            details = current.lstat()
        except OSError as error:
            raise BootstrapError("bootstrap input is absent") from error
        if current != candidate:
            if not stat.S_ISDIR(details.st_mode):
                raise BootstrapError("bootstrap parent is not a directory")
        elif not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise BootstrapError("bootstrap input is not an unaliased regular file")
        if current.is_symlink() or (
            reparse and getattr(details, "st_file_attributes", 0) & reparse
        ):
            raise BootstrapError("bootstrap path contains a symlink or reparse point")
    try:
        return candidate.read_bytes()
    except OSError as error:
        raise BootstrapError("bootstrap input cannot be read") from error


def _read_json_bytes(value: bytes, *, description: str) -> dict[str, object]:
    try:
        parsed: object = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BootstrapError(f"{description} is not valid JSON") from error
    return _mapping(parsed, description=description)


def _reject_network_override_environment() -> None:
    if _has_network_or_openssl_override():
        raise BootstrapError("proxy, TLS, or OpenSSL override environment is not approved")


def _reviewed_tls_context() -> ssl.SSLContext:
    _reject_network_override_environment()
    context = ssl.create_default_context()
    if (
        context.verify_mode != ssl.CERT_REQUIRED
        or not context.check_hostname
        or getattr(context, "keylog_filename", None) is not None
    ):
        raise BootstrapError("public GitHub TLS context is not fail closed")
    return context


def _resolve_protected_main_sha(
    connection_factory: _BootstrapHttpsFactory | None = None,
) -> str:
    """Resolve public protected-main evidence directly, without credentials or proxies."""

    context = _reviewed_tls_context()
    factory = connection_factory or http.client.HTTPSConnection
    connection = factory(GITHUB_API_HOST, timeout=30, context=context)
    try:
        connection.request(
            "GET",
            GITHUB_MAIN_REF_PATH,
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
            raise BootstrapError("protected GitHub main evidence was not accepted")
        body = response.read(65_537)
        if len(body) > 65_536:
            raise BootstrapError("protected GitHub main evidence exceeded its bound")
    except BootstrapError:
        raise
    except Exception as error:
        raise BootstrapError("protected GitHub main evidence is unavailable") from error
    finally:
        connection.close()
    payload = _read_json_bytes(body, description="protected GitHub main evidence")
    ref_object = _mapping(payload.get("object"), description="protected GitHub ref object")
    sha = _text(ref_object, "sha", description="protected GitHub ref object")
    if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha):
        raise BootstrapError("protected GitHub main SHA is invalid")
    return sha


def _verify_registry_and_artifact(
    repo_root: Path,
    arguments: tuple[str, ...],
) -> dict[str, object]:
    artifact_value = _option_value(arguments, "--authorization")
    required_sha256 = _option_value(arguments, "--require-authorization-sha256")
    if artifact_value is None or required_sha256 is None:
        raise BootstrapError("live-compare requires exact authorization path and SHA-256")
    artifact_path = Path(artifact_value)
    if artifact_path.is_absolute():
        try:
            supplied_relative = artifact_path.relative_to(repo_root).as_posix()
        except ValueError as error:
            raise BootstrapError("authorization artifact is not the fixed reviewed path") from error
    else:
        supplied_relative = artifact_path.as_posix()
    if supplied_relative != FUTURE_AUTHORIZATION_RELATIVE_PATH:
        raise BootstrapError("authorization artifact is not the fixed reviewed path")
    artifact_bytes = _require_direct_file(repo_root, FUTURE_AUTHORIZATION_RELATIVE_PATH)
    if _sha256(artifact_bytes) != required_sha256:
        raise BootstrapError("authorization artifact SHA-256 differs")
    artifact = _read_json_bytes(artifact_bytes, description="authorization artifact")

    registry_bytes = _require_direct_file(repo_root, REGISTRY_RELATIVE_PATH)
    pin_bytes = _require_direct_file(repo_root, REGISTRY_PIN_RELATIVE_PATH)
    try:
        pin = pin_bytes.decode("ascii")
    except UnicodeDecodeError as error:
        raise BootstrapError("authorization registry pin is not ASCII") from error
    if (
        len(pin_bytes) != 65
        or not pin.endswith("\n")
        or any(character not in "0123456789abcdef" for character in pin[:-1])
        or _sha256(registry_bytes) != pin[:-1]
    ):
        raise BootstrapError("authorization registry differs from its reviewed pin")
    registry = _read_json_bytes(registry_bytes, description="authorization registry")
    grants = _sequence(registry.get("grants"), description="authorization grants")
    authorization_id = _text(artifact, "authorization_id", description="artifact")
    core_sha256 = _sha256(_canonical_json(artifact))
    matches: list[dict[str, object]] = []
    for raw_grant in grants:
        grant = _mapping(raw_grant, description="authorization grant")
        if grant.get("authorization_id") == authorization_id:
            matches.append(grant)
    if (
        len(matches) != 1
        or matches[0].get("artifact_sha256") != required_sha256
        or matches[0].get("artifact_core_sha256") != core_sha256
    ):
        raise BootstrapError("authorization has no exact reviewed registry grant")
    return artifact


def _verify_preimport_execution_tree(
    repo_root: Path,
    artifact: dict[str, object],
    *,
    protected_main_sha: str,
) -> None:
    execution_commit = _text(artifact, "execution_git_commit", description="artifact")
    if len(execution_commit) != 40 or any(
        character not in "0123456789abcdef" for character in execution_commit
    ):
        raise BootstrapError("artifact execution commit is invalid")
    head = _run_git_text(repo_root, "rev-parse", "HEAD")
    if head != protected_main_sha:
        raise BootstrapError("current HEAD is not the public protected GitHub main head")
    if not _is_ancestor(repo_root, execution_commit, head):
        raise BootstrapError("reviewed execution commit is not an ancestor of HEAD")
    changed = tuple(
        line
        for line in _run_git_text(
            repo_root,
            "diff",
            "--name-only",
            f"{execution_commit}..{head}",
            "--",
        ).splitlines()
        if line
    )
    if not set(changed).issubset(EXTERNAL_TRUST_ANCHORS):
        raise BootstrapError("protected main changed files outside external trust anchors")
    if _run_git_text(repo_root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise BootstrapError("repository is dirty or contains untracked files")

    manifest_bytes = _require_direct_file(repo_root, MANIFEST_RELATIVE_PATH)
    if _sha256(manifest_bytes) != _text(
        artifact, "execution_tree_manifest_sha256", description="artifact"
    ):
        raise BootstrapError("execution-tree manifest SHA-256 differs")
    manifest = _read_json_bytes(manifest_bytes, description="execution-tree manifest")
    entries = _sequence(manifest.get("entries"), description="execution-tree entries")
    paths: list[str] = []
    for raw_entry in entries:
        entry = _mapping(raw_entry, description="execution-tree entry")
        paths.append(_text(entry, "path", description="execution-tree entry"))
    if tuple(paths) != BOOTSTRAP_REQUIRED_PATHS:
        raise BootstrapError("execution-tree manifest path set is not closed")
    if _sha256(_canonical_json(entries)) != _text(
        manifest, "execution_tree_sha256", description="execution-tree manifest"
    ) or manifest.get("execution_tree_sha256") != artifact.get("execution_tree_sha256"):
        raise BootstrapError("execution-tree content hash differs")

    for raw_entry, relative_path in zip(entries, paths, strict=True):
        entry = _mapping(raw_entry, description="execution-tree entry")
        expected_sha256 = _text(entry, "sha256", description="execution-tree entry")
        expected_count = entry.get("byte_count")
        if not isinstance(expected_count, int) or isinstance(expected_count, bool):
            raise BootstrapError("execution-tree byte count is invalid")
        working_bytes = _require_direct_file(repo_root, relative_path)
        blob_id = _run_git_text(repo_root, "rev-parse", f"{execution_commit}:{relative_path}")
        committed_bytes = _run_git(repo_root, "cat-file", "blob", blob_id)
        if (
            len(working_bytes) != expected_count
            or len(committed_bytes) != expected_count
            or _sha256(working_bytes) != expected_sha256
            or _sha256(committed_bytes) != expected_sha256
        ):
            raise BootstrapError("execution-tree input differs from reviewed Git bytes")


def _import_name_for_root(root_name: str) -> str:
    if root_name.casefold().endswith(".py"):
        return Path(root_name).stem
    return root_name.split(".", 1)[0]


def _verify_dependency_records(
    site_packages: Path,
    artifact: dict[str, object],
) -> tuple[str, ...]:
    raw_pins = _sequence(artifact.get("dependency_records"), description="dependency records")
    pins = tuple(_mapping(item, description="dependency record pin") for item in raw_pins)
    names = tuple(_text(pin, "distribution", description="dependency record pin") for pin in pins)
    if names != REQUIRED_DEPENDENCY_DISTRIBUTIONS:
        raise BootstrapError("authorization dependency record set is not exact")
    for shadow in FORBIDDEN_SITE_SHADOWS:
        if os.path.lexists(site_packages / shadow):
            raise BootstrapError("site-packages contains a forbidden standard-library shadow")

    import_roots: set[str] = set()
    allowed_paths: set[str] = set()
    expected_dist_infos: set[str] = set()
    for pin in pins:
        relative = _text(pin, "record_path", description="dependency record pin")
        record_path = Path(relative)
        if (
            len(record_path.parts) != 2
            or record_path.parts[1] != "RECORD"
            or not record_path.parts[0].casefold().endswith(".dist-info")
            or record_path.parts[0] in expected_dist_infos
        ):
            raise BootstrapError("dependency RECORD path is not an exact distribution root")
        expected_dist_infos.add(record_path.parts[0])
        record_bytes = _require_direct_file(site_packages, relative)
        if _sha256(record_bytes) != _text(
            pin,
            "record_sha256",
            description="dependency record pin",
        ):
            raise BootstrapError("dependency RECORD differs from the reviewed authorization")
        try:
            rows = tuple(csv.reader(io.StringIO(record_bytes.decode("utf-8"), newline="")))
        except (UnicodeDecodeError, csv.Error) as error:
            raise BootstrapError("dependency RECORD is invalid") from error
        listed: set[str] = set()
        record_seen = False
        for row in rows:
            if len(row) != 3:
                raise BootstrapError("dependency RECORD row is malformed")
            path_text, encoded_hash, byte_count_text = row
            path = Path(path_text)
            if (
                not path_text
                or "\\" in path_text
                or path.is_absolute()
                or ".." in path.parts
                or path.as_posix() != path_text
                or path_text in listed
            ):
                raise BootstrapError("dependency RECORD path is unsafe or duplicated")
            listed.add(path_text)
            allowed_paths.add(path_text)
            if path_text.casefold() == relative.casefold():
                if encoded_hash or byte_count_text:
                    raise BootstrapError("dependency RECORD self-row must omit its digest")
                record_seen = True
                continue
            first_component = path.parts[0]
            if not first_component.casefold().endswith(".dist-info"):
                import_roots.add(first_component)
            if not encoded_hash.startswith("sha256="):
                raise BootstrapError("dependency RECORD entry is not SHA-256 pinned")
            try:
                expected_count = int(byte_count_text)
            except ValueError as error:
                raise BootstrapError("dependency RECORD byte count is invalid") from error
            dependency_bytes = _require_direct_file(site_packages, path_text)
            encoded = base64.urlsafe_b64encode(hashlib.sha256(dependency_bytes).digest()).decode()
            if len(dependency_bytes) != expected_count or encoded.rstrip("=") != encoded_hash[7:]:
                raise BootstrapError("installed dependency differs from its reviewed RECORD")
        if not record_seen:
            raise BootstrapError("dependency RECORD lacks its self-row")

    observed_dist_infos = {
        child.name
        for child in site_packages.iterdir()
        if child.is_dir() and child.name.casefold().endswith(".dist-info")
    }
    if observed_dist_infos != expected_dist_infos:
        raise BootstrapError("installed dependency distribution set is not exact")

    closed_roots = import_roots | expected_dist_infos
    for root_name in closed_roots:
        root = site_packages / root_name
        if not os.path.lexists(root):
            raise BootstrapError("reviewed dependency root is unavailable")
        candidates = (root,) if root.is_file() else tuple(root.rglob("*"))
        for candidate in candidates:
            try:
                details = candidate.lstat()
            except OSError as error:
                raise BootstrapError("dependency closure cannot be inspected") from error
            reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            if candidate.is_symlink() or (
                reparse and getattr(details, "st_file_attributes", 0) & reparse
            ):
                raise BootstrapError("dependency closure contains a link or reparse point")
            if stat.S_ISREG(details.st_mode):
                relative_candidate = candidate.relative_to(site_packages).as_posix()
                if relative_candidate not in allowed_paths:
                    raise BootstrapError("dependency closure contains an unlisted file")

    import_names = {_import_name_for_root(root_name) for root_name in import_roots}
    for root_name in import_roots:
        import_name = _import_name_for_root(root_name)
        for candidate in site_packages.iterdir():
            if candidate.name == root_name:
                continue
            if candidate.name == import_name or candidate.name.startswith(f"{import_name}."):
                raise BootstrapError("site-packages contains an unlisted import candidate")
    for root_name in import_roots:
        root = site_packages / root_name
        if root.suffix.casefold() == ".py":
            cache = site_packages / "__pycache__"
            if cache.exists() and any(cache.glob(f"{root.stem}.*.pyc")):
                raise BootstrapError("reviewed dependency has unverified bytecode cache")
        elif root.is_dir() and any(root.rglob("*.pyc")):
            raise BootstrapError("reviewed dependency has unverified bytecode cache")
    return tuple(sorted(import_names))


def _configure_isolated_imports(
    repo_root: Path,
    artifact: dict[str, object],
) -> tuple[Path, Path, tuple[str, ...]]:
    if not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode:
        raise BootstrapError("live-compare requires Python -I -S -B isolated startup")
    if any(name in os.environ for name in REJECTED_PYTHON_ENVIRONMENT):
        raise BootstrapError("live-compare rejects Python import-control environment variables")
    if any(name in sys.modules for name in ("site", "sitecustomize", "usercustomize")):
        raise BootstrapError("live-compare startup already processed site customization")
    initial_paths = tuple(sys.path)
    if any(
        not value or Path(value).resolve(strict=False).is_relative_to(repo_root)
        for value in initial_paths
    ):
        raise BootstrapError("isolated startup contains a working-directory import path")

    executable = Path(os.path.abspath(sys.executable))
    venv_root = executable.parent.parent
    expected_venv = repo_root / ".venv-live"
    if os.path.normcase(str(venv_root)) != os.path.normcase(str(expected_venv)):
        raise BootstrapError("live-compare must use the dedicated frozen environment")
    if os.name == "nt":
        site_packages = venv_root / "Lib" / "site-packages"
    else:
        version = f"python{sys.version_info.major}.{sys.version_info.minor}"
        site_packages = venv_root / "lib" / version / "site-packages"
    source_root = repo_root / "src"
    for directory in (source_root, site_packages):
        try:
            details = directory.lstat()
        except OSError as error:
            raise BootstrapError("isolated import root is unavailable") from error
        if not stat.S_ISDIR(details.st_mode) or directory.is_symlink():
            raise BootstrapError("isolated import root is not a direct directory")
    dependency_modules = _verify_dependency_records(site_packages, artifact)
    os.environ["PYDANTIC_DISABLE_PLUGINS"] = "__all__"
    sys.path.extend((str(source_root), str(site_packages)))
    required_modules = (
        ("peru_conflicts", source_root),
        *((module_name, site_packages) for module_name in dependency_modules),
    )
    for module_name, expected_root in required_modules:
        spec = importlib.util.find_spec(module_name)
        if spec is None or spec.origin is None:
            raise BootstrapError("required isolated module cannot be resolved")
        origin = Path(spec.origin).resolve(strict=True)
        if not origin.is_relative_to(expected_root.resolve(strict=True)):
            raise BootstrapError("required module resolves outside its isolated root")
    return (
        source_root.resolve(strict=True),
        site_packages.resolve(strict=True),
        dependency_modules,
    )


def _require_isolated_startup() -> None:
    if not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode:
        raise BootstrapError("live-compare requires Python -I -S -B isolated startup")
    if any(name in os.environ for name in REJECTED_PYTHON_ENVIRONMENT):
        raise BootstrapError("live-compare rejects Python import-control environment variables")


def _verify_loaded_module_origins(
    source_root: Path,
    site_packages: Path,
    dependency_modules: tuple[str, ...],
) -> None:
    for name, module in tuple(sys.modules.items()):
        assert isinstance(module, ModuleType)
        raw_file = getattr(module, "__file__", None)
        if not isinstance(raw_file, str):
            continue
        origin = Path(raw_file).resolve(strict=True)
        if name == "peru_conflicts" or name.startswith("peru_conflicts."):
            if not origin.is_relative_to(source_root):
                raise BootstrapError("project module loaded outside reviewed source root")
        elif name.split(".", 1)[0] in dependency_modules and not origin.is_relative_to(
            site_packages
        ):
            raise BootstrapError("dependency module loaded outside frozen environment")


def _requested_mode(arguments: tuple[str, ...]) -> str:
    return _option_value(arguments, "--mode") or "dry-run"


def _dispatch() -> int:
    arguments = tuple(sys.argv[1:])
    source_root: Path | None = None
    site_packages: Path | None = None
    dependency_modules: tuple[str, ...] = ()
    if _requested_mode(arguments) == LIVE_MODE:
        _require_isolated_startup()
        if os.name != "nt":
            raise BootstrapError("live-compare requires the reviewed Windows host")
        repo_root = Path(os.path.abspath(__file__)).parent.parent
        root_details = repo_root.lstat()
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if repo_root.is_symlink() or (
            reparse and getattr(root_details, "st_file_attributes", 0) & reparse
        ):
            raise BootstrapError("repository root is a symlink or reparse point")
        artifact = _verify_registry_and_artifact(repo_root, arguments)
        protected_main_sha = _resolve_protected_main_sha()
        _verify_preimport_execution_tree(
            repo_root,
            artifact,
            protected_main_sha=protected_main_sha,
        )
        source_root, site_packages, dependency_modules = _configure_isolated_imports(
            repo_root, artifact
        )

    os.environ["PYDANTIC_DISABLE_PLUGINS"] = "__all__"
    from peru_conflicts.acquisition.cli import main

    if source_root is not None and site_packages is not None:
        _verify_loaded_module_origins(source_root, site_packages, dependency_modules)
    return main(arguments)


if __name__ == "__main__":
    try:
        raise SystemExit(_dispatch())
    except BootstrapError as error:
        raise SystemExit(f"live-compare bootstrap rejected: {error}") from None
