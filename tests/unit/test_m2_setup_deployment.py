"""Independently arranged test installation; never installs a real grant."""

import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest

from peru_conflicts.execution import setup_authority
from peru_conflicts.hashing import canonical_json_bytes


def clean_startup_environment() -> dict[str, str]:
    """Test-owned launcher environment, established before spawning Python.

    Production continues to reject these controls; synthetic admission must not
    accidentally inherit the parent runner's loader/TLS/import configuration.
    """
    return {
        key: value
        for key, value in os.environ.items()
        if not key.lower().startswith(("python", "pytest", "openssl_", "ld_", "dyld_", "m2_"))
    }


@pytest.fixture
def runtime_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Invented bytes test the pin boundary without changing the installed runtime."""
    import sysconfig

    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    base = tmp_path / "base"
    home = base if os.name == "nt" else base / "bin"
    home.mkdir(parents=True)
    base_executable = home / ("python.exe" if os.name == "nt" else f"python{version}")
    base_executable.write_bytes(b"SYNTHETIC-INTERPRETER")
    venv = tmp_path / "venv"
    executable = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    executable.parent.mkdir(parents=True)
    executable.write_bytes(base_executable.read_bytes())
    config = venv / "pyvenv.cfg"
    config.write_text(
        f"home = {home}\ninclude-system-site-packages = false\nversion = {version}\n",
        encoding="utf-8",
    )
    site = venv / ("Lib/site-packages" if os.name == "nt" else f"lib/python{version}/site-packages")
    site.mkdir(parents=True)
    package = site / "example.py"
    package.write_bytes(b"VALUE = 'SYNTHETIC'\n")
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "_base_executable", str(base_executable))
    monkeypatch.setattr(sys, "base_prefix", str(base))
    original = sysconfig.get_path

    def fixture_path(name: str) -> str:
        return str(site) if name in {"purelib", "platlib"} else original(name)

    monkeypatch.setattr(sysconfig, "get_path", fixture_path)
    return executable, base_executable, config, package


def test_runtime_inventory_binds_configuration_and_copied_interpreter(runtime_tree: Any):
    from peru_conflicts.execution.references import sha256
    from peru_conflicts.execution.setup_deployment import runtime_inventory

    assert runtime_inventory() == {str(path): sha256(path.read_bytes()) for path in runtime_tree}


@pytest.mark.parametrize(
    "fault",
    [
        "missing_config",
        "wrong_home",
        "system_site",
        "duplicate_home",
        "wrong_version",
        "wrong_base",
        "unrecognized_executable",
        "package_root",
    ]
    + (
        ["copied_bytes", "interpreter_alias", "dependency_directory_alias"]
        if os.name != "nt"
        else []
    ),
)
def test_runtime_relationship_substitution_is_rejected(
    runtime_tree: Any, monkeypatch: pytest.MonkeyPatch, fault: str, tmp_path: Path
):
    import sysconfig

    from peru_conflicts.execution.setup_deployment import runtime_inventory

    executable, base, config, package = runtime_tree
    if fault == "missing_config":
        config.unlink()
    elif fault in {"wrong_home", "system_site", "duplicate_home", "wrong_version"}:
        raw = config.read_text(encoding="utf-8")
        if fault == "wrong_home":
            raw = raw.replace(str(base.parent), str(tmp_path))
        elif fault == "system_site":
            raw = raw.replace("false", "true")
        elif fault == "duplicate_home":
            raw += f"home = {base.parent}\n"
        else:
            raw = raw.replace("version = ", "version = 0.")
        config.write_text(raw, encoding="utf-8")
    elif fault == "wrong_base":
        monkeypatch.setattr(sys, "_base_executable", str(tmp_path / "other-python"))
    elif fault == "unrecognized_executable":
        alternate = executable.with_name("unrecognized-python")
        alternate.write_bytes(executable.read_bytes())
        monkeypatch.setattr(sys, "executable", str(alternate))
    elif fault == "package_root":

        def wrong_root(_name: str) -> str:
            return str(tmp_path)

        monkeypatch.setattr(sysconfig, "get_path", wrong_root)
    elif fault == "copied_bytes":
        executable.write_bytes(b"SUBSTITUTED-INTERPRETER")
    elif fault == "interpreter_alias":
        alternate = tmp_path / "intermediate-python"
        alternate.symlink_to(base)
        executable.unlink()
        executable.symlink_to(alternate)
    else:
        outside = tmp_path / "unmeasured"
        outside.mkdir()
        (outside / "example.py").write_bytes(b"UNMEASURED")
        (package.parent / "unmeasured_package").symlink_to(outside, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        runtime_inventory()


@pytest.mark.parametrize("layout", ["copy", "link"] if os.name != "nt" else ["copy"])
def test_runtime_inventory_tracks_launch_bytes_and_configuration(runtime_tree: Any, layout: str):
    from peru_conflicts.execution.references import sha256
    from peru_conflicts.execution.setup_deployment import runtime_inventory

    executable, base, config, _ = runtime_tree
    if layout == "link":
        executable.unlink()
        executable.symlink_to(base)
    inventory = runtime_inventory()
    expected = os.fsencode(os.readlink(executable)) if layout == "link" else executable.read_bytes()
    assert inventory[str(executable)] == sha256(expected)
    assert inventory[str(base)] == sha256(base.read_bytes())
    original = config.read_bytes()
    config.write_bytes(original + b"prompt = changed\n")
    changed = runtime_inventory()
    assert changed[str(config)] == sha256(original + b"prompt = changed\n")
    assert changed[str(config)] != inventory[str(config)]


@pytest.mark.parametrize("boundary", ["base", "venv", "package"])
def test_runtime_directory_alias_boundary(
    runtime_tree: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, boundary: str
):
    from peru_conflicts.execution.references import sha256
    from peru_conflicts.execution.setup_deployment import runtime_inventory

    executable, base, config, package = runtime_tree
    if boundary == "base":
        target = Path(sys.base_prefix)
        alias = tmp_path / "base-alias"
    elif boundary == "venv":
        target = executable.parent.parent
        alias = tmp_path / "venv-alias"
    else:
        target = tmp_path / "direct-packages"
        alias = package.parent
        alias.rename(target)
    if os.name == "nt":
        result = subprocess.run(
            [r"C:\Windows\System32\cmd.exe", "/d", "/c", "mklink", "/J", str(alias), str(target)],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    else:
        alias.symlink_to(target, target_is_directory=True)
    if boundary == "base":
        configured = alias / base.relative_to(target)
        monkeypatch.setattr(sys, "base_prefix", str(alias))
        monkeypatch.setattr(sys, "_base_executable", str(configured))
        config.write_text(
            config.read_text(encoding="utf-8").replace(str(base.parent), str(configured.parent)),
            encoding="utf-8",
        )
        inventory = runtime_inventory()
        assert inventory[str(base)] == sha256(base.read_bytes())
        assert str(configured) not in inventory
        assert inventory[str(config)] == sha256(config.read_bytes())
    else:
        if boundary == "venv":
            monkeypatch.setattr(sys, "executable", str(alias / executable.relative_to(target)))
        with pytest.raises(ValueError, match="aliased input"):
            runtime_inventory()


def test_deployment_loader_exists_beyond_empty_registry(monkeypatch: pytest.MonkeyPatch):
    # A reviewed nonempty source must select a real loader, not still unconditionally
    # reject as if the registry were empty. The synthetic entry is deliberately bad.
    monkeypatch.setattr(setup_authority, "registry_bytes", lambda: b'{"grants":[{}]}')
    with pytest.raises(ValueError, match=r"installation|registry entry"):
        setup_authority.admit(b"{}", lambda: pytest.fail("premature private read"))


@lru_cache(maxsize=1)
def measured_runtime() -> tuple[dict[str, str], str]:
    from peru_conflicts.execution.python_environment_policy import capture_document
    from peru_conflicts.execution.references import sha256
    from peru_conflicts.execution.setup_deployment import runtime_inventory

    runtime = runtime_inventory()
    environment = capture_document(sha256(canonical_json_bytes(runtime)))
    return runtime, str(environment["python_environment_sha256"])


def installation_fixture(tmp_path: Path) -> tuple[Path, bytes, bytes, bytes]:
    from peru_conflicts.execution.references import sha256
    from peru_conflicts.execution.setup_bridge import digest
    from peru_conflicts.execution.setup_deployment import (
        Installation,
        source_inventory,
        store_pin,
    )
    from peru_conflicts.execution.setup_offline import (
        _FIXTURE_BINDINGS,  # pyright: ignore[reportPrivateUsage]
        END,
        fixture_grant,
    )

    root = tmp_path / "m2-readiness-installed-test"
    root.mkdir()
    for name in ("run", "checkpoint", "witness", "components-pinned"):
        (root / name).mkdir(mode=0o700)
    bindings = canonical_json_bytes(_FIXTURE_BINDINGS)
    source_root = Path(__file__).resolve().parents[2]
    files = source_inventory(source_root)
    runtime, environment = measured_runtime()
    grant = fixture_grant().model_copy(
        update={
            "implementation_sha256": sha256(canonical_json_bytes(files)),
            "grant_ref": "test-installed-one-use",
            "run_ref": "test-installed-run",
        }
    )
    raw = grant.model_dump_json().encode()
    pin = Installation(
        grant_sha256=sha256(raw),
        source_root=str(source_root),
        source_files=files,
        runtime_files=runtime,
        python_environment_sha256=environment,
        binding_sha256=sha256(bindings),
        policy_sha256=digest(grant.concurrency),
        capability_sha256=grant.capability_sha256,
        store=store_pin(root / "run"),
        checkpoint=store_pin(root / "checkpoint"),
        witness_store=store_pin(root / "witness"),
        component_store=store_pin(root / "components-pinned"),
        forbidden_roots=(str(source_root),),
        validity_end=END,
        kind="synthetic_test",
        transport_profile="simulated_application_only",
        credential_refs={a.session_ref: "SYNTHETIC-NOT-A-TOKEN" for a in grant.sessions},
        scopes={a.session_ref: ("account_info.read",) for a in grant.sessions},
    )
    return root, raw, pin.model_dump_json().encode(), bindings


def test_nonfixture_loader_runs_shared_journal_without_fixture_globals(tmp_path: Path):
    from peru_conflicts.execution.references import sha256
    from peru_conflicts.execution.setup_deployment import (
        _load_verified,  # pyright: ignore[reportPrivateUsage]
    )
    from peru_conflicts.execution.setup_evidence import EvidenceJournal
    from peru_conflicts.execution.setup_offline import NOW

    root, raw, installation, bindings = installation_fixture(tmp_path)
    context = _load_verified(
        raw,
        installation,
        sha256(installation),
        lambda: bindings,
        lambda: installation,
        clock=lambda: NOW,
    )
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        order = journal.next()
        assert order.actor.actor == "coordinator"
        assert order.expected_account_id == "dbid:offline-coordinator"
        journal.consume(order)
        assert [r["kind"] for r in journal.records] == ["intent", "dispatch"]
    finally:
        journal.close()

    # A separate interpreter receives its test trust pin from this test process,
    # not from the grant/capture being authenticated. This is not an application
    # trust-source option. Synthetic installation files have no private identities.
    (root / "grant.json").write_bytes(raw)
    (root / "installation.json").write_bytes(installation)
    (root / "bindings.json").write_bytes(bindings)
    code = """
import sys
from pathlib import Path
from datetime import datetime
sys.modules['peru_conflicts.execution.setup_offline'] = None
from peru_conflicts.execution.setup_deployment import _load_verified
from peru_conflicts.execution.setup_evidence import EvidenceJournal
root = Path(sys.argv[1])
installation = (root / 'installation.json').read_bytes()
context = _load_verified((root / 'grant.json').read_bytes(), installation, sys.argv[2],
    lambda: (root / 'bindings.json').read_bytes(), lambda: installation,
    clock=lambda: datetime.fromisoformat('2026-09-23T12:00:00+00:00'))
journal = EvidenceJournal(root / 'run', root / 'checkpoint', context, create=False)
try:
    assert [r['kind'] for r in journal.records] == ['intent', 'dispatch']
    assert journal.pending is not None
    try:
        journal.consume(journal.pending)
    except ValueError:
        print('UNKNOWN_NO_REDISPATCH')
    else:
        raise AssertionError('redispatched')
finally:
    journal.close()
"""
    process = subprocess.run(
        [sys.executable, "-c", code, str(root), sha256(installation)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "UNKNOWN_NO_REDISPATCH"
    # New admitted context, no process-local fixture admission registration.
    reopened = _load_verified(
        raw,
        installation,
        sha256(installation),
        lambda: bindings,
        lambda: installation,
        clock=lambda: NOW,
    )
    journal = EvidenceJournal(root / "run", root / "checkpoint", reopened, create=False)
    try:
        assert journal.pending == order
        with pytest.raises(ValueError, match="UNKNOWN"):
            journal.next()
        with pytest.raises(ValueError, match="already dispatched"):
            journal.consume(order)
    finally:
        journal.close()


@pytest.mark.parametrize(
    "fault",
    [
        "expired_installation",
        "revoked",
        "runtime",
        "source",
        "policy",
        "capability",
        "grant",
        "pin",
    ],
)
def test_untrusted_or_expired_installation_rejects_before_private_reader(
    tmp_path: Path, fault: str
):
    from peru_conflicts.execution.references import sha256
    from peru_conflicts.execution.setup_deployment import (
        Installation,
        _load_verified,  # pyright: ignore[reportPrivateUsage]
    )
    from peru_conflicts.execution.setup_offline import NOW

    _, raw, original, _ = installation_fixture(tmp_path)
    pin = Installation.model_validate_json(original)
    changes: dict[str, dict[str, Any]] = {
        "expired_installation": {"validity_end": NOW},
        "revoked": {"revoked": True},
        "runtime": {"runtime_files": {}},
        "source": {"source_files": {}},
        "policy": {"policy_sha256": "0" * 64},
        "capability": {"capability_sha256": {}},
        "grant": {"grant_sha256": "0" * 64},
        "pin": {},
    }
    changed = pin.model_copy(update=changes[fault]).model_dump_json().encode()
    with pytest.raises(ValueError):
        _load_verified(
            raw,
            changed,
            "0" * 64 if fault == "pin" else sha256(changed),
            lambda: pytest.fail("private lookup before authority acceptance"),
            lambda: changed,
            clock=lambda: NOW,
        )
