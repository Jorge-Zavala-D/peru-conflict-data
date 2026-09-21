"""Native pre-Python byte verification using synthetic temporary files only."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts/verify_m2_environment_candidate.ps1"


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
        assert (
            c.validate_environment_candidate(raw, expected_sha256=expected)[
                "production_environment_approved"
            ]
            is False
        )
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
