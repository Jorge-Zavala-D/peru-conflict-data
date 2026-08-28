from __future__ import annotations

import hashlib
import http.client
import importlib
import importlib.util
import json
import socket
import subprocess
import urllib.request
from pathlib import Path

import pytest
import yaml

from peru_conflicts.acquisition.models import AcquisitionPilotPlan, DryRunResult
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.paths import EXPECTED_TOP_LEVEL


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=repo, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _tree_receipt(root: Path) -> tuple[tuple[str, str, int, int, str | None], ...]:
    rows: list[tuple[str, str, int, int, str | None]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        stat = path.stat()
        if path.is_file():
            content = path.read_bytes()
            rows.append(
                (
                    relative,
                    "file",
                    len(content),
                    stat.st_mtime_ns,
                    hashlib.sha256(content).hexdigest(),
                )
            )
        else:
            rows.append((relative, "directory", 0, stat.st_mtime_ns, None))
    return tuple(rows)


def _complete_cli_fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "config", "user.name", "M1-03A Integration")
    _git(repo, "config", "core.autocrlf", "false")
    receipt = repo / "docs" / "source_integrity_receipt.md"
    receipt.parent.mkdir()
    receipt_bytes = b"synthetic merged integrity receipt\n"
    receipt.write_bytes(receipt_bytes)
    _git(repo, "add", "docs/source_integrity_receipt.md")
    _git(repo, "commit", "-m", "Synthetic merged baseline")
    baseline = _git(repo, "rev-parse", "HEAD")

    data_root = tmp_path / "external-data"
    for zone in EXPECTED_TOP_LEVEL:
        (data_root / zone).mkdir(parents=True)

    payload = yaml.safe_load(
        Path("config/acquisition_pilots/m1_03_reports_260_269_v2.yaml").read_text(encoding="utf-8")
    )
    payload["baseline_receipt_path"] = "docs/source_integrity_receipt.md"
    payload["baseline_receipt_git_commit"] = baseline
    payload["baseline_receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    for target in payload["targets"]:
        number = target["report_number"]
        content = f"%PDF-1.7\nsynthetic report {number}\n".encode()
        relative = f"01_raw/reports/2026/report-{number}.pdf"
        source = data_root.joinpath(*relative.split("/"))
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(content)
        target["existing_local_relative_path"] = relative
        target["existing_local_byte_count"] = len(content)
        target["existing_local_sha256"] = hashlib.sha256(content).hexdigest()

    validated = AcquisitionPilotPlan.model_validate(payload)
    plan_path = repo / "config" / "synthetic-v2.yaml"
    plan_path.parent.mkdir()
    plan_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
        newline="\n",
    )
    digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    semantic = hashlib.sha256(canonical_json_bytes(validated.model_dump(mode="json"))).hexdigest()
    targets = hashlib.sha256(
        canonical_json_bytes(validated.model_dump(mode="json")["targets"])
    ).hexdigest()
    return repo, data_root, plan_path, f"{digest}:{semantic}:{targets}"


def test_acquisition_cli_module_exists() -> None:
    try:
        specification = importlib.util.find_spec("peru_conflicts.acquisition.cli")
    except ModuleNotFoundError:
        specification = None
    assert specification is not None


def test_acquisition_cli_exposes_main() -> None:
    module = importlib.import_module("peru_conflicts.acquisition.cli")

    assert callable(getattr(module, "main", None))


@pytest.mark.parametrize(
    "forbidden_arguments",
    (
        ("--mode", "network"),
        ("--force",),
        ("--authorize",),
    ),
)
def test_cli_has_no_network_or_authorization_escape_hatch(
    forbidden_arguments: tuple[str, ...],
) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.cli")

    with pytest.raises(SystemExit):
        module.main(forbidden_arguments)


def test_cli_runs_only_preflight_then_writes_and_prints_zero_side_effect_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.cli")
    plan = tmp_path / "plan.yaml"
    output = tmp_path / "dry-run.json"
    data_root = tmp_path / "external-data"
    monkeypatch.setenv("CONFLICT_DATA_ROOT", str(data_root))
    loaded = object()
    result = DryRunResult(
        schema_version="0.1.0",
        run_type="m1_03a_dry_run",
        plan_id="m1-03-reports-260-269-v2",
        plan_file_sha256="1" * 64,
        plan_semantic_sha256="2" * 64,
        target_set_sha256="3" * 64,
        baseline_git_commit="4" * 40,
        baseline_receipt_path="docs/source_integrity_receipt_m1_02_2.md",
        baseline_receipt_sha256="5" * 64,
        verified_source_count=10,
        verified_source_bytes=1,
        logical_url_count=20,
        network_requests=0,
        dropbox_writes=0,
        actions=(),
    )
    calls: list[tuple[str, object]] = []

    def fake_load(path: Path, *, required_sha256: str) -> object:
        calls.append(("load", (path, required_sha256)))
        return loaded

    def fake_preflight(*, loaded_plan: object, repo_root: Path, data_root: Path) -> DryRunResult:
        calls.append(("preflight", (loaded_plan, repo_root, data_root)))
        return result

    def fake_write(
        path: Path,
        value: DryRunResult,
        *,
        repo_root: Path,
        data_root: Path,
    ) -> None:
        calls.append(("write", (path, value, repo_root, data_root)))

    monkeypatch.setattr(module, "load_reviewed_pilot_plan", fake_load, raising=False)
    monkeypatch.setattr(module, "run_dry_run_preflight", fake_preflight, raising=False)
    monkeypatch.setattr(module, "write_dry_run_result", fake_write, raising=False)

    exit_code = module.main(
        [
            "--mode",
            "dry-run",
            "--plan",
            str(plan),
            "--require-plan-sha256",
            "a" * 64,
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert [name for name, _ in calls] == ["load", "preflight", "write"]
    printed = json.loads(capsys.readouterr().out)
    assert printed["network_requests"] == 0
    assert printed["dropbox_writes"] == 0


def test_complete_cli_dry_run_has_zero_network_and_preserves_data_tree_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.cli")
    plan_module = importlib.import_module("peru_conflicts.acquisition.plan")
    repo, data_root, plan_path, digests = _complete_cli_fixture(tmp_path)
    file_digest, semantic_digest, target_digest = digests.split(":")
    monkeypatch.setattr(plan_module, "REVIEWED_V2_PLAN_FILE_SHA256", file_digest)
    monkeypatch.setattr(plan_module, "REVIEWED_V2_PLAN_SEMANTIC_SHA256", semantic_digest)
    monkeypatch.setattr(plan_module, "REVIEWED_TARGET_SET_SHA256", target_digest)
    monkeypatch.setattr(module, "_repository_root", lambda: repo)
    monkeypatch.setenv("CONFLICT_DATA_ROOT", str(data_root))

    def reject_network(*_: object, **__: object) -> None:
        raise AssertionError("complete dry-run CLI attempted network access")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(urllib.request, "urlopen", reject_network)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", reject_network)
    before = _tree_receipt(data_root)
    output = repo / ".cache" / "m1-03a" / "dry-run.json"

    exit_code = module.main(
        [
            "--mode",
            "dry-run",
            "--plan",
            str(plan_path),
            "--require-plan-sha256",
            file_digest,
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert _tree_receipt(data_root) == before
    assert not (data_root / "01_raw" / "manifests").exists()
    assert not (data_root / "01_raw" / ".staging").exists()
    rendered = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert rendered == printed
    assert rendered["network_requests"] == 0
    assert rendered["dropbox_writes"] == 0
