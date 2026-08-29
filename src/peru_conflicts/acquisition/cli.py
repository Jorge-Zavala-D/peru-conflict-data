"""Command-line boundary for the M1-03A dry run."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from peru_conflicts.acquisition.authorization import (
    load_reviewed_network_authorization,
    require_live_compare_platform,
)
from peru_conflicts.acquisition.live_compare import execute_live_compare
from peru_conflicts.acquisition.plan import load_reviewed_pilot_plan
from peru_conflicts.acquisition.preflight import run_dry_run_preflight, write_dry_run_result
from peru_conflicts.hashing import canonical_json_bytes


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main(argv: Sequence[str] | None = None) -> int:
    """Validate and emit a plan without constructing any network transport."""

    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--mode", choices=("dry-run", "live-compare"), default="dry-run")
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path("config/acquisition_pilots/m1_03_reports_260_269_v2.yaml"),
    )
    parser.add_argument("--require-plan-sha256", required=True)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--require-authorization-sha256")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".cache/m1-03a/dry-run-plan.json"),
    )
    supplied = tuple(sys.argv[1:] if argv is None else argv)
    arguments = parser.parse_args(supplied)
    if arguments.mode == "live-compare":
        if any(token == "--output" or token.startswith("--output=") for token in supplied):
            parser.error("live-compare has a fixed operational-ledger destination")
        if arguments.authorization is None or arguments.require_authorization_sha256 is None:
            parser.error("live-compare requires exact authorization path and required SHA-256")
    elif arguments.authorization is not None or arguments.require_authorization_sha256 is not None:
        parser.error("authorization arguments are valid only for live-compare")

    if arguments.mode == "live-compare":
        require_live_compare_platform()

    data_root_value = os.environ.get("CONFLICT_DATA_ROOT", "").strip()
    if not data_root_value:
        parser.error("CONFLICT_DATA_ROOT is required")

    repo_root = _repository_root()
    plan_path = arguments.plan if arguments.plan.is_absolute() else repo_root / arguments.plan
    output_path = (
        arguments.output if arguments.output.is_absolute() else repo_root / arguments.output
    )
    data_root = Path(data_root_value)
    loaded_plan = load_reviewed_pilot_plan(
        plan_path,
        required_sha256=arguments.require_plan_sha256,
    )
    if arguments.mode == "live-compare":
        assert arguments.authorization is not None
        assert arguments.require_authorization_sha256 is not None
        authorization_path = (
            arguments.authorization
            if arguments.authorization.is_absolute()
            else repo_root / arguments.authorization
        )
        authorization = load_reviewed_network_authorization(
            authorization_path,
            required_sha256=arguments.require_authorization_sha256,
        )
        execute_live_compare(
            loaded_plan=loaded_plan,
            authorization=authorization,
            repo_root=repo_root,
            data_root=data_root,
        )
        return 0
    result = run_dry_run_preflight(
        loaded_plan=loaded_plan,
        repo_root=repo_root,
        data_root=data_root,
    )
    write_dry_run_result(
        output_path,
        result,
        repo_root=repo_root,
        data_root=data_root,
    )
    print(canonical_json_bytes(result.model_dump(mode="json")).decode("utf-8"))
    return 0
