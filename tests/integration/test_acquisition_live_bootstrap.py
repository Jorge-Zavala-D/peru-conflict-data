"""The live executable verifies trust with stdlib before application imports."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import runpy
import ssl
import subprocess
import sys
from pathlib import Path

import pytest

from peru_conflicts.acquisition.live_compare import (
    EXECUTION_TREE_EXTERNAL_TRUST_ANCHORS,
    EXECUTION_TREE_REQUIRED_PATHS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "acquire_official_sources.py"
REJECTED_ENV = (
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
NETWORK_OVERRIDE_ENV = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "SSLKEYLOGFILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "OPENSSL_CONF",
    "OPENSSL_CONF_INCLUDE",
    "OPENSSL_ENGINES",
    "OPENSSL_MODULES",
)


def _clean_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in REJECTED_ENV:
        environment.pop(name, None)
    for name in NETWORK_OVERRIDE_ENV:
        environment.pop(name, None)
        environment.pop(name.lower(), None)
    return environment


def _live_arguments(authorization: Path, required_sha256: str) -> list[str]:
    return [
        "--mode",
        "live-compare",
        "--require-plan-sha256",
        "a" * 64,
        "--authorization",
        str(authorization),
        "--require-authorization-sha256",
        required_sha256,
    ]


def test_bootstrap_and_application_execution_path_sets_are_identical() -> None:
    namespace = runpy.run_path(str(SCRIPT), run_name="acquisition_bootstrap_contract")
    assert namespace["BOOTSTRAP_REQUIRED_PATHS"] == EXECUTION_TREE_REQUIRED_PATHS
    assert namespace["EXTERNAL_TRUST_ANCHORS"] == EXECUTION_TREE_EXTERNAL_TRUST_ANCHORS


def test_live_executable_rejects_nonisolated_startup_before_application_import(
    tmp_path: Path,
) -> None:
    authorization = tmp_path / "authorization.json"
    authorization.write_bytes(b"{}\n")
    data_root = tmp_path / "must-not-exist"
    environment = _clean_environment()
    environment["CONFLICT_DATA_ROOT"] = str(data_root)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), *_live_arguments(authorization, "a" * 64)],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "requires Python -I -S -B isolated startup" in result.stderr
    assert not data_root.exists()


def test_isolated_live_bootstrap_requires_no_bytecode_mode_before_artifact_access(
    tmp_path: Path,
) -> None:
    authorization = tmp_path / "authorization.json"
    authorization.write_bytes(b"{}\n")
    data_root = tmp_path / "must-not-exist"
    environment = _clean_environment()
    environment["CONFLICT_DATA_ROOT"] = str(data_root)

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(SCRIPT),
            *_live_arguments(authorization, "a" * 64),
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "requires Python -I -S -B isolated startup" in result.stderr
    assert not data_root.exists()


def test_isolated_startup_rejects_pythonpath_without_loading_sitecustomize(
    tmp_path: Path,
) -> None:
    hostile = tmp_path / "hostile"
    hostile.mkdir()
    marker = tmp_path / "sitecustomize-loaded"
    (hostile / "sitecustomize.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('loaded')\n",
        encoding="utf-8",
    )
    authorization = tmp_path / "authorization.json"
    authorization.write_bytes(b"{}\n")
    environment = _clean_environment()
    environment["PYTHONPATH"] = str(hostile)

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(SCRIPT),
            *_live_arguments(authorization, "a" * 64),
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "rejects Python import-control environment variables" in result.stderr
    assert not marker.exists()


@pytest.mark.parametrize(
    "name",
    ("OPENSSL_CONF", "OPENSSL_CONF_INCLUDE", "OPENSSL_ENGINES", "OPENSSL_MODULES"),
)
def test_live_bootstrap_rejects_openssl_controls_before_artifact_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
) -> None:
    authorization = tmp_path / "authorization.json"
    authorization.write_bytes(b"{}\n")
    target = tmp_path / "unapproved-openssl-target"
    data_root = tmp_path / "must-not-exist"
    environment = _clean_environment()
    environment[name] = str(target)
    environment["CONFLICT_DATA_ROOT"] = str(data_root)

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(SCRIPT),
            *_live_arguments(authorization, "a" * 64),
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "proxy, TLS, or OpenSSL override" in result.stderr
    assert not target.exists()
    assert not data_root.exists()


def test_isolated_live_bootstrap_stops_at_empty_registry_before_side_effects(
    tmp_path: Path,
) -> None:
    raw = (
        json.dumps(
            {"authorization_id": "synthetic-not-reviewed"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    authorization = tmp_path / "authorization.json"
    authorization.write_bytes(raw)
    data_root = tmp_path / "must-not-exist"
    environment = _clean_environment()
    environment["CONFLICT_DATA_ROOT"] = str(data_root)

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(SCRIPT),
            *_live_arguments(authorization, hashlib.sha256(raw).hexdigest()),
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    if os.name == "nt":
        assert "authorization artifact is not the fixed reviewed path" in result.stderr
    else:
        assert "requires the reviewed Windows host" in result.stderr
    assert not data_root.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX live bootstrap boundary")
def test_posix_live_bootstrap_rejects_before_artifact_temp_or_data_root_access(
    tmp_path: Path,
) -> None:
    authorization = tmp_path / "authorization-must-not-be-read.json"
    data_root = tmp_path / "data-root-must-not-exist"
    temp_root = tmp_path / "temp-root-must-not-exist"
    environment = _clean_environment()
    environment["CONFLICT_DATA_ROOT"] = str(data_root)
    environment["TMPDIR"] = str(temp_root)

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(SCRIPT),
            *_live_arguments(authorization, "a" * 64),
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "requires the reviewed Windows host" in result.stderr
    assert not authorization.exists()
    assert not data_root.exists()
    assert not temp_root.exists()


def test_public_main_resolver_uses_bounded_credential_free_github_request() -> None:
    namespace = runpy.run_path(str(SCRIPT), run_name="acquisition_bootstrap_github_test")
    observed: dict[str, object] = {}

    class Response:
        status = 200

        def getheader(self, name: str) -> str | None:
            assert name == "Content-Type"
            return "application/json; charset=utf-8"

        def read(self, maximum: int) -> bytes:
            assert maximum == 65_537
            return json.dumps({"object": {"sha": "c" * 40}}).encode()

    class Connection:
        def __init__(self, host: str, *, timeout: int, context: object) -> None:
            observed.update(host=host, timeout=timeout, context=context)

        def request(self, method: str, path: str, *, headers: dict[str, str]) -> None:
            observed.update(method=method, path=path, headers=headers)

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            observed["closed"] = True

    assert namespace["_resolve_protected_main_sha"](Connection) == "c" * 40
    assert observed["host"] == "api.github.com"
    assert observed["method"] == "GET"
    headers = observed["headers"]
    assert isinstance(headers, dict)
    assert "Authorization" not in headers
    assert "Cookie" not in headers
    assert observed["closed"] is True
    context = observed["context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert getattr(context, "keylog_filename", None) is None


@pytest.mark.parametrize(
    "name",
    tuple(name for canonical in NETWORK_OVERRIDE_ENV for name in (canonical, canonical.lower())),
)
def test_public_main_resolver_rejects_network_overrides_before_connection(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    namespace = runpy.run_path(str(SCRIPT), run_name="acquisition_bootstrap_network_env_test")
    calls = 0

    class Connection:
        def __init__(self, *args: object, **kwargs: object) -> None:
            nonlocal calls
            del args, kwargs
            calls += 1

    monkeypatch.setenv(name, "unapproved")
    with pytest.raises(namespace["BootstrapError"], match="proxy, TLS, or OpenSSL override"):
        namespace["_resolve_protected_main_sha"](Connection)
    assert calls == 0


def test_dependency_record_verifier_rejects_tampering_and_stdlib_shadows(
    tmp_path: Path,
) -> None:
    namespace = runpy.run_path(str(SCRIPT), run_name="acquisition_bootstrap_dependency_test")
    site_packages = tmp_path / "site-packages"
    site_packages.mkdir()
    pins: list[dict[str, str]] = []
    distributions = (
        "annotated-types",
        "pydantic",
        "pydantic-core",
        "pyyaml",
        "typing-extensions",
        "typing-inspection",
    )
    package_files: dict[str, Path] = {}
    for distribution in distributions:
        package_name = distribution.replace("-", "_")
        package_file = site_packages / f"{package_name}.py"
        package_bytes = f"VALUE = {distribution!r}\n".encode()
        package_file.write_bytes(package_bytes)
        package_files[distribution] = package_file
        record_relative = f"{distribution}-1.0.dist-info/RECORD"
        record = site_packages / record_relative
        record.parent.mkdir()
        encoded = (
            base64.urlsafe_b64encode(hashlib.sha256(package_bytes).digest()).decode().rstrip("=")
        )
        record_bytes = (
            f"{package_file.name},sha256={encoded},{len(package_bytes)}\n{record_relative},,\n"
        ).encode()
        record.write_bytes(record_bytes)
        pins.append(
            {
                "distribution": distribution,
                "record_path": record_relative,
                "record_sha256": hashlib.sha256(record_bytes).hexdigest(),
            }
        )
    artifact = {"dependency_records": pins}

    namespace["_verify_dependency_records"](site_packages, artifact)

    unlisted_extension = site_packages / "pydantic.cp312-win_amd64.pyd"
    unlisted_extension.write_bytes(b"unreviewed native module")
    with pytest.raises(namespace["BootstrapError"], match="unlisted import candidate"):
        namespace["_verify_dependency_records"](site_packages, artifact)
    unlisted_extension.unlink()

    plugin_dist = site_packages / "hostile_plugin-1.0.dist-info"
    plugin_dist.mkdir()
    (plugin_dist / "entry_points.txt").write_text(
        "[pydantic]\nhostile = hostile_plugin:plugin\n",
        encoding="utf-8",
    )
    with pytest.raises(namespace["BootstrapError"], match="distribution set is not exact"):
        namespace["_verify_dependency_records"](site_packages, artifact)
    (plugin_dist / "entry_points.txt").unlink()
    plugin_dist.rmdir()

    package_files["pydantic"].write_bytes(b"TAMPERED = True\n")
    with pytest.raises(namespace["BootstrapError"], match="installed dependency differs"):
        namespace["_verify_dependency_records"](site_packages, artifact)

    package_files["pydantic"].write_bytes(b"VALUE = 'pydantic'\n")
    marker = tmp_path / "shadow-executed"
    (site_packages / "ssl.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    with pytest.raises(namespace["BootstrapError"], match="standard-library shadow"):
        namespace["_verify_dependency_records"](site_packages, artifact)
    assert not marker.exists()

    (site_packages / "ssl.py").unlink()
    cache = site_packages / "__pycache__"
    cache.mkdir()
    (cache / "pydantic.cpython-312.pyc").write_bytes(b"unreviewed-bytecode")
    with pytest.raises(namespace["BootstrapError"], match="bytecode cache"):
        namespace["_verify_dependency_records"](site_packages, artifact)
