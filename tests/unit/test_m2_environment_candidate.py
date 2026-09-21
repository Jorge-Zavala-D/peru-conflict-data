"""Native pre-Python byte verification using synthetic temporary files only."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts/verify_m2_environment_candidate.ps1"


@pytest.mark.skipif(os.name != "nt", reason="native retained handles require Windows")
def test_native_manifest_size_is_bounded_before_destination_creation(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload.py").write_bytes(b"synthetic")
    manifest = tmp_path / "manifest.json"
    raw = json.dumps(
        {
            "file_hashes": {"payload.py": hashlib.sha256(b"synthetic").hexdigest()},
            "padding": " " * (8 * 1024 * 1024),
        }
    ).encode()
    manifest.write_bytes(raw)
    target = tmp_path / ".cache/m2-02b2/production_environment_candidate/oversized"
    shell = shutil.which("pwsh")
    assert shell is not None
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-File",
            str(SCRIPT),
            "-ManifestPath",
            str(manifest),
            "-ExpectedManifestSha256",
            hashlib.sha256(raw).hexdigest(),
            "-SourceRoot",
            str(source),
            "-WorkspaceRoot",
            str(tmp_path),
            "-Destination",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not target.exists()


@pytest.mark.skipif(os.name != "nt", reason="retained-handle native preparation is Windows-only")
@pytest.mark.parametrize(
    "attack",
    [
        "duplicate",
        "manifest_replace",
        "source_parent",
        "destination_parent",
        "extra",
        "interrupted",
        "destination_race",
    ],
)
def test_native_retained_custody(tmp_path: Path, attack: str) -> None:
    shell = shutil.which("pwsh")
    assert shell is not None, "PowerShell 7 required for native custody tests"
    source = tmp_path / "source"
    source.mkdir()
    (source / "original.py").write_bytes(b"original")
    (source / "substituted.py").write_bytes(b"substituted")
    manifest = tmp_path / "manifest.json"
    pins = {"original.py": hashlib.sha256(b"original").hexdigest()}
    raw = json.dumps({"file_hashes": pins}).encode()
    if attack == "duplicate":
        raw = raw[:-1] + b',"file_hashes":' + json.dumps(pins).encode() + b"}"
    manifest.write_bytes(raw)
    output = tmp_path / ".cache/m2-02b2/production_environment_candidate/native"
    output.parent.mkdir(parents=True)
    replacement = tmp_path / "replacement.json"
    replacement.write_text(
        json.dumps({"file_hashes": {"substituted.py": hashlib.sha256(b"substituted").hexdigest()}})
    )
    script = SCRIPT.read_text()
    # Test-only interleaving in a copy of the real script; no production hook.
    if attack == "manifest_replace":
        marker = "$manifest ="
        injection = (
            f"[IO.File]::WriteAllBytes($ManifestPath, "
            f"[IO.File]::ReadAllBytes('{replacement.as_posix()}'))\n"
        )
    else:
        marker = (
            "# COPY_BOUNDARY"
            if "# COPY_BOUNDARY" in script
            else "New-Item -ItemType Directory -Path $target"
        )
        if attack in {"extra", "interrupted"} and "# PUBLICATION_BOUNDARY" in script:
            marker = "# PUBLICATION_BOUNDARY"
        injection = {
            "source_parent": "[IO.Directory]::Move($source, $source + '-moved')\n",
            "destination_parent": (
                "[IO.Directory]::Move([IO.Path]::GetDirectoryName($target), "
                "[IO.Path]::GetDirectoryName($target) + '-moved')\n"
            ),
            "extra": (
                "[IO.Directory]::CreateDirectory($target) | "
                "Out-Null\n[IO.File]::WriteAllText((Join-Path $target 'extra.txt'), "
                "'extra')\n"
            ),
            "interrupted": "throw 'simulated interrupted copy'\n",
            "destination_race": "[IO.Directory]::CreateDirectory($target) | Out-Null\n",
            "duplicate": "",
        }[attack]
    assert marker in script
    instrumented = tmp_path / "instrumented.ps1"
    instrumented.write_text(script.replace(marker, injection + marker, 1))
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-File",
            str(instrumented),
            "-ManifestPath",
            str(manifest),
            "-ExpectedManifestSha256",
            hashlib.sha256(raw).hexdigest(),
            "-SourceRoot",
            str(source),
            "-WorkspaceRoot",
            str(tmp_path),
            "-Destination",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    receipt = output / "CANDIDATE_RECEIPT.json"
    if attack == "manifest_replace" and result.returncode == 0:
        assert (output / "original.py").read_bytes() == b"original"
        assert not (output / "substituted.py").exists()
    else:
        assert result.returncode != 0, result.stdout
        assert not receipt.exists()


def environment_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, Any], dict[str, bytes], dict[str, bytes]]:
    """Small complete synthetic manifests; pins replace test authority, not production authority."""
    from peru_conflicts.execution import operational_plan as c
    from peru_conflicts.execution.python_environment_policy import BOUNDARY, EXCLUSIONS, json_bytes

    dep = json_bytes(
        {
            "file_hashes": {"package/module.py": "a" * 64},
            "versions": {"package": "1"},
            "python_version": "3.12",
        }
    )
    py: dict[str, Any] = {
        "policy": "m2-python-environment-rehearsal-v1",
        "production_approved": False,
        "external_trust_boundary": BOUNDARY,
        "exclusions": list(EXCLUSIONS),
        "identity": {
            "implementation": "CPython",
            "version": "3.12",
            "build": "synthetic",
            "compiler": "synthetic",
            "system": "Windows",
            "machine": "AMD64",
            "pointer_bits": "64",
            "abi": "synthetic",
        },
        "stdlib_path": "Lib",
        "interpreter_path": "python.exe",
        "interpreter_sha256": "b" * 64,
        "dependency_sha256": c.sha256(dep),
        "file_hashes": {"python.exe": "b" * 64, "Lib/os.py": "c" * 64},
        "symlinks": {},
    }
    py["python_environment_sha256"] = c.sha256(json_bytes(py))
    py_raw = json_bytes(py)
    runtime_files = {
        "CONTRACT.json": "d" * 64,
        "FIELD_REGISTRY.json": "e" * 64,
        "DEPENDENCIES.json": c.sha256(dep),
        "PYTHON_ENVIRONMENT.json": c.sha256(py_raw),
    }
    runtime = {
        "policy": "m2-neutral-runtime-source-selection-v1",
        "runtime_sha256": c.sha256(
            json_bytes(
                {"policy": "m2-neutral-runtime-source-selection-v1", "file_hashes": runtime_files}
            )
        ),
        "file_hashes": runtime_files,
        "contract_sha256": "d" * 64,
        "registry_sha256": "e" * 64,
        "launcher_sha256": "f" * 64,
        "interpreter_sha256": "b" * 64,
        "dependency_sha256": c.sha256(dep),
        "python_environment_sha256": py["python_environment_sha256"],
        "python_environment_manifest_sha256": c.sha256(py_raw),
        "python_environment": py,
        "dependency_versions": {"package": "1"},
        "python_version": "3.12",
    }
    manifests = {"python-v2": py_raw, "dependencies-v1": dep, "runtime-v1": json_bytes(runtime)}
    for key, value in {
        "python_environment_manifest_sha256": c.sha256(py_raw),
        "dependency_sha256": c.sha256(dep),
        "runtime_file_set_sha256": c.sha256(
            json.dumps(runtime_files, sort_keys=True, separators=(",", ":")).encode()
        ),
        "interpreter_sha256": "b" * 64,
        "launcher_sha256": "f" * 64,
    }.items():
        monkeypatch.setitem(c.REVIEW_BINDINGS, key, value)
    monkeypatch.setattr(
        c, "RUNTIME_MANIFEST_RAW_SHA256", c.sha256(manifests["runtime-v1"]), raising=False
    )
    inventory: dict[str, str] = {}
    receipts: dict[str, bytes] = {}
    for stage, raw in manifests.items():
        files = json.loads(raw)["file_hashes"]
        inventory.update({f"{stage}/{k}": v for k, v in files.items()})
        receipts[stage] = json_bytes(
            {
                "kind": "NATIVE_PREPYTHON_CANDIDATE_BYTE_VERIFICATION_V2",
                "stage": stage,
                "expected_manifest_sha256": c.sha256(raw),
                "inventory_sha256": c.sha256(
                    json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
                ),
                "verifier_sha256": "1" * 64,
                "files_verified": len(files),
                "production_candidate_prepared": True,
                "production_environment_approved": False,
                "python_executed": False,
            }
        )
        inventory[f"{stage}/CANDIDATE_RECEIPT.json"] = c.sha256(receipts[stage])
    inventory["runtime-v1/RUNTIME_MANIFEST.json"] = c.sha256(manifests["runtime-v1"])
    inventory["trusted_launcher.py"] = "f" * 64
    data = {
        "kind": "PRODUCTION_ENVIRONMENT_CANDIDATE_V3_NOT_APPROVED",
        "protected_main": c.MERGE_SHA,
        "predecessor_raw_sha256": "2" * 64,
        "verifier_sha256": "1" * 64,
        "file_hashes": inventory,
        "inventory_sha256": c.sha256(
            json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
        ),
        "production_candidate_prepared": True,
        "production_environment_approved": False,
        "candidate_python_executed": False,
        "external_provenance_verified": False,
        "independent_provisioning_verified": False,
        "provenance_evidence_raw_sha256": "3" * 64,
    }
    return data, manifests, receipts


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "name",
        "stdlib",
        "dependency",
        "runtime",
        "stage",
        "missing",
        "startup",
        "receipt",
        "extra",
        "duplicate",
        "outer_pin",
        "constituent_pin",
    ],
)
def test_complete_constituent_chain(monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    from peru_conflicts.execution import operational_plan as c

    data, manifests, receipts = environment_chain(monkeypatch)
    inventory = data["file_hashes"]
    if mutation == "name":
        inventory["python-v2/Lib/other.py"] = inventory.pop("python-v2/Lib/os.py")
    elif mutation in ("stdlib", "dependency", "runtime"):
        inventory[
            {
                "stdlib": "python-v2/Lib/os.py",
                "dependency": "dependencies-v1/package/module.py",
                "runtime": "runtime-v1/CONTRACT.json",
            }[mutation]
        ] = "0" * 64
    elif mutation == "stage":
        inventory["python-v2/package/module.py"] = inventory.pop(
            "dependencies-v1/package/module.py"
        )
    elif mutation == "missing":
        del inventory["runtime-v1/CONTRACT.json"]
    elif mutation == "startup":
        inventory["python-v2/pyvenv.cfg"] = inventory.pop("python-v2/Lib/os.py")
    elif mutation == "receipt":
        receipts["python-v2"] = receipts["dependencies-v1"]
    elif mutation == "extra":
        data["owner_approved"] = True
    elif mutation == "constituent_pin":
        manifests["python-v2"] += b" "
    data["inventory_sha256"] = c.sha256(
        json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    )
    raw = json.dumps(data).encode()
    if mutation == "duplicate":
        raw = raw[:-1] + b',"production_environment_approved":false}'
    kwargs: dict[str, Any] = {
        "expected_sha256": "0" * 64 if mutation == "outer_pin" else c.sha256(raw),
        "constituent_bytes": manifests,
        "receipt_bytes": receipts,
        "expected_verifier_sha256": "1" * 64,
    }
    if mutation == "none":
        result = c.validate_environment_candidate(raw, **kwargs)
        assert result["production_environment_approved"] is False
        assert len(result["file_hashes"]) == 12
    else:
        with pytest.raises(ValueError):
            c.validate_environment_candidate(raw, **kwargs)


@pytest.mark.parametrize("location", ["envelope", "receipt"])
@pytest.mark.parametrize("value", [0, 1, "false", None])
def test_evidence_authority_booleans_never_coerce(
    monkeypatch: pytest.MonkeyPatch, location: str, value: object
) -> None:
    from peru_conflicts.execution import operational_plan as c

    data, manifests, receipts = environment_chain(monkeypatch)
    if location == "envelope":
        data["production_environment_approved"] = value
    else:
        receipt = json.loads(receipts["python-v2"])
        receipt["python_executed"] = value
        receipts["python-v2"] = json.dumps(receipt).encode()
        data["file_hashes"]["python-v2/CANDIDATE_RECEIPT.json"] = c.sha256(receipts["python-v2"])
        data["inventory_sha256"] = c.inventory_sha256(data["file_hashes"])
    raw = json.dumps(data).encode()
    with pytest.raises(ValueError):
        c.validate_environment_candidate(
            raw,
            expected_sha256=c.sha256(raw),
            constituent_bytes=manifests,
            receipt_bytes=receipts,
            expected_verifier_sha256="1" * 64,
        )


@pytest.mark.parametrize(
    "mutation",
    ["none", "approval", "coercion", "pin", "omitted", "interpreter", "runtime", "malformed_stage"],
)
def test_portable_manifest_authority_and_tamper_checks(mutation: str) -> None:
    from peru_conflicts.execution import operational_plan as c

    inventory = {f"python-v2/synthetic-{i}.py": "a" * 64 for i in range(2220)}
    inventory["python-v2/python.exe"] = c.REVIEW_BINDINGS["interpreter_sha256"]
    inventory["trusted_launcher.py"] = c.REVIEW_BINDINGS["launcher_sha256"]
    data: dict[str, Any] = {
        "kind": "PRODUCTION_ENVIRONMENT_CANDIDATE_NOT_APPROVED",
        "protected_main": c.MERGE_SHA,
        "runtime_file_set_sha256": c.REVIEW_BINDINGS["runtime_file_set_sha256"],
        "dependency_manifest_sha256": c.REVIEW_BINDINGS["dependency_sha256"],
        "production_candidate_prepared": True,
        "production_environment_approved": False,
        "candidate_python_executed": False,
        "file_hashes": inventory,
        **dict.fromkeys(
            ("os", "platform", "trust_boundary", "python_provenance", "launcher_usage"),
            "SYNTHETIC metadata only; not native proof",
        ),
        "stages": {
            name: {
                "receipt": {
                    "files_verified": count,
                    "expected_manifest_sha256": pin,
                    "production_candidate_prepared": True,
                    "production_environment_approved": False,
                    "python_executed": False,
                }
            }
            for name, count, pin in (
                ("python-v2", 2046, c.REVIEW_BINDINGS["python_environment_manifest_sha256"]),
                ("dependencies-v1", 152, c.REVIEW_BINDINGS["dependency_sha256"]),
                (
                    "runtime-v1",
                    19,
                    "4d5f8273ff210cf39eb2b105743b26ac8f3e1e1e5851e342dee09f41a9c8b346",
                ),
            )
        },
    }
    before = hashlib.sha256(json.dumps(data).encode()).hexdigest()
    if mutation == "approval":
        data["production_environment_approved"] = True
    elif mutation == "coercion":
        data["production_environment_approved"] = 0
    elif mutation == "omitted":
        del inventory["python-v2/synthetic-0.py"]
    elif mutation == "interpreter":
        inventory["python-v2/python.exe"] = "0" * 64
    elif mutation == "runtime":
        data["runtime_file_set_sha256"] = "0" * 64
    elif mutation == "malformed_stage":
        data["stages"]["python-v2"] = []
    raw = json.dumps(data).encode()
    expected = "0" * 64 if mutation == "pin" else hashlib.sha256(raw).hexdigest()
    if mutation == "none":
        # Historical impossible positive: counts are not constituent evidence.
        with pytest.raises(ValueError):
            c.validate_environment_candidate(raw, expected_sha256=expected)
    else:
        # Even a recomputed self-consistent pin cannot replace the required authority/state.
        with pytest.raises(ValueError):
            c.validate_environment_candidate(raw, expected_sha256=expected)
        with pytest.raises(ValueError):
            c.validate_environment_candidate(
                raw, expected_sha256="0" * 64 if mutation == "pin" else before
            )


@pytest.mark.parametrize(
    "mutation",
    [
        "destination_startup",
        "pin",
        "omitted",
        "stdlib",
        "dependency",
        "launcher",
        "escape",
        "existing",
        "traversal",
        "reparse",
    ],
)
@pytest.mark.skipif(os.name != "nt", reason="native retained handles require Windows")
def test_native_adversarial_boundaries(tmp_path: Path, mutation: str) -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("native PowerShell unavailable; portable candidate tests remain active")
    source = tmp_path / "source"
    source.mkdir()
    names = ("python.exe", "stdlib.py", "dependency.pyd", "launcher.py")
    pins: dict[str, str] = {}
    for name in names:
        (source / name).write_bytes(b"synthetic")
        pins[name] = hashlib.sha256(b"synthetic").hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"file_hashes": pins}))
    expected = hashlib.sha256(manifest.read_bytes()).hexdigest()
    output = tmp_path / ".cache/m2-02b2/production_environment_candidate/candidate"
    if mutation == "destination_startup":
        output.parent.mkdir(parents=True)
        (output.parent / "pyvenv.cfg").write_text("unexpected")
    elif mutation == "pin":
        expected = "0" * 64
    elif mutation == "omitted":
        del pins["stdlib.py"]
        manifest.write_text(json.dumps({"file_hashes": pins}))
    elif mutation in ("stdlib", "dependency", "launcher"):
        name = {"stdlib": "stdlib.py", "dependency": "dependency.pyd", "launcher": "launcher.py"}[
            mutation
        ]
        (source / name).write_bytes(b"changed")
    elif mutation == "escape":
        output = tmp_path / "outside"
    elif mutation == "existing":
        output.mkdir(parents=True)
    elif mutation == "traversal":
        pins["../outside"] = pins.pop("stdlib.py")
        manifest.write_text(json.dumps({"file_hashes": pins}))
        expected = hashlib.sha256(manifest.read_bytes()).hexdigest()
    elif mutation == "reparse":
        link = tmp_path / "linked-source"
        if __import__("os").name == "nt":
            junction_script = tmp_path / "junction.ps1"
            junction_script.write_text(
                "param($Link,$Target)\n"
                "New-Item -ItemType Junction -Path $Link -Target $Target -ErrorAction Stop\n"
            )
            created = subprocess.run(
                [shell, "-NoProfile", "-File", str(junction_script), str(link), str(source)],
                capture_output=True,
                text=True,
                check=False,
            )
            assert created.returncode == 0, created.stderr
        else:
            link.symlink_to(source, target_is_directory=True)
        source = link
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-File",
            str(SCRIPT),
            "-ManifestPath",
            str(manifest),
            "-ExpectedManifestSha256",
            expected,
            "-SourceRoot",
            str(source),
            "-WorkspaceRoot",
            str(tmp_path),
            "-Destination",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, result.stdout
    assert not (output / "CANDIDATE_RECEIPT.json").exists()
    if mutation != "existing":
        assert not output.exists()


def test_portable_candidate_rejects_unpinned_or_approved_environment() -> None:
    from peru_conflicts.execution import operational_plan as c

    assert hasattr(c, "validate_environment_candidate")
    for payload in ({}, {"production_environment_approved": True}):
        raw = json.dumps(payload).encode()
        with pytest.raises(ValueError):
            c.validate_environment_candidate(raw, expected_sha256=hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize("control", ["python312._pth", "pyvenv.cfg", "parent-pyvenv"])
@pytest.mark.skipif(os.name != "nt", reason="native retained handles require Windows")
def test_unlisted_startup_controls_rejected_before_candidate_creation(
    tmp_path: Path, control: str
) -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("native PowerShell unavailable")
    source = tmp_path / "source"
    source.mkdir()
    raw = b"synthetic interpreter"
    (source / "python.exe").write_bytes(raw)
    target = tmp_path / ".cache/m2-02b2/production_environment_candidate/native"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"file_hashes": {"python.exe": hashlib.sha256(raw).hexdigest()}})
    )
    path = tmp_path / "pyvenv.cfg" if control == "parent-pyvenv" else source / control
    path.write_text("unexpected startup configuration")
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-File",
            str(SCRIPT),
            "-ManifestPath",
            str(manifest),
            "-ExpectedManifestSha256",
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "-SourceRoot",
            str(source),
            "-WorkspaceRoot",
            str(tmp_path),
            "-Destination",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, result.stdout
    assert not target.exists()


@pytest.mark.parametrize("tamper", [False, True])
@pytest.mark.skipif(os.name != "nt", reason="native retained handles require Windows")
def test_native_verifier_requires_exact_independent_bytes(tmp_path: Path, tamper: bool) -> None:
    assert SCRIPT.is_file(), "native pre-Python verifier missing"
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("native PowerShell unavailable; portable contracts run separately")
    source = tmp_path / "source"
    source.mkdir()
    (source / "python.exe").write_bytes(b"synthetic-not-executable")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"file_hashes": {"python.exe": hashlib.sha256(b"synthetic-not-executable").hexdigest()}}
        )
    )
    pin = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if tamper:
        (source / "python.exe").write_bytes(b"changed")
    output = tmp_path / ".cache/m2-02b2/production_environment_candidate/python"
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-File",
            str(SCRIPT),
            "-ManifestPath",
            str(manifest),
            "-ExpectedManifestSha256",
            pin,
            "-SourceRoot",
            str(source),
            "-WorkspaceRoot",
            str(tmp_path),
            "-Destination",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) is (not tamper), result.stdout + result.stderr
    if tamper:
        assert not output.exists()
    else:
        receipt = json.loads((output / "CANDIDATE_RECEIPT.json").read_bytes())
        assert receipt["production_environment_approved"] is False
        assert receipt["python_executed"] is False
        assert (output / "python.exe").read_bytes() == b"synthetic-not-executable"
