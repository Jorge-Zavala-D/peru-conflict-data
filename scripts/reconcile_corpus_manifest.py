"""Materialize the M1-04A candidate corpus evidence from frozen local inputs."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from peru_conflicts.manifest.evidence import (
    REVIEWED_DISCOVERY_RUNS,
    DiscoveryRunInput,
    load_completed_acquisition_closure,
    load_discovery_runs,
    validate_completed_data_root_snapshot,
)
from peru_conflicts.manifest.materialize import materialize_candidate_package
from peru_conflicts.manifest.reconcile import ReconciliationContext, reconcile_manifest
from peru_conflicts.paths import DataPaths

PROTECTED_SOURCE_RECEIPT_REFS = (
    "docs/source_integrity_receipt_m1_02_2.md:963a9b317f8485c58e4b8b7f408a4c8739ea23f0260fd7c368656f99d17a4cc2",
    "docs/source_integrity_receipt_m1_03b1.md:0f0162a8af7f669cea7d95a285101f58c96a02fbe1703e21afacb6a12fd5da59",
)


def _parse_discovery_run(value: str) -> DiscoveryRunInput:
    run_id, separator, raw_path = value.partition("=")
    if not separator or not run_id or not raw_path:
        raise argparse.ArgumentTypeError("discovery run must use RUN_ID=PATH")
    return DiscoveryRunInput(run_id=run_id, directory=Path(raw_path))


def _git(repo_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _resolve_repository_provenance(repo_root: Path) -> tuple[str, str]:
    repository_head = _git(repo_root, "rev-parse", "HEAD")
    implementation_tree = _git(repo_root, "rev-parse", "HEAD^{tree}")
    for label, value in (
        ("repository HEAD", repository_head),
        ("implementation tree", implementation_tree),
    ):
        if re.fullmatch(r"[a-f0-9]{40}", value) is None:
            raise RuntimeError(f"{label} is not a lowercase 40-character Git object ID")
    return repository_head, implementation_tree


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--discovery-run",
        action="append",
        required=True,
        type=_parse_discovery_run,
        dest="discovery_runs",
        help="Exact frozen input in RUN_ID=PATH form; provide both reviewed runs.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repository-base-sha", required=True)
    arguments = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    repository_head, implementation_tree = _resolve_repository_provenance(repository_root)
    if _git(repository_root, "status", "--short", "--untracked-files=no"):
        parser.error("tracked repository state must be clean before candidate materialization")
    data_paths = DataPaths.resolve(repo_root=repository_root)
    validate_completed_data_root_snapshot(data_paths.root)
    discovery = load_discovery_runs(
        tuple(arguments.discovery_runs),
        reviewed_runs=REVIEWED_DISCOVERY_RUNS,
        repository_root=repository_root,
    )
    acquisition = load_completed_acquisition_closure(
        repository_root=repository_root,
        data_root=data_paths.root,
        plan_path=(
            repository_root / "config" / "acquisition_pilots" / "m1_03_reports_260_269_v2.yaml"
        ),
    )
    package = reconcile_manifest(
        discovery,
        acquisition,
        ReconciliationContext(
            repository_base_sha=arguments.repository_base_sha,
            implementation_tree_sha=implementation_tree,
        ),
    )
    receipt = materialize_candidate_package(
        package,
        acquisition=acquisition,
        output_dir=arguments.output,
        repository_root=repository_root,
        repository_base_sha=arguments.repository_base_sha,
        repository_head_sha=repository_head,
        protected_source_receipt_refs=PROTECTED_SOURCE_RECEIPT_REFS,
    )
    print(
        f"Materialized {len(package.manifest)} observed reports, "
        f"{len(package.source_observations)} source observations, and "
        f"{len(package.gaps)} unresolved gaps; receipt: "
        f"{receipt.relative_to(repository_root).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
