"""Three bounded operations over supplied native representations, never acquisition."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from peru_conflicts.execution import source_addressed_tables as engine

from . import VERSION, admission, receiver
from .io import FRAME, load_native, pin, read, require, write


def io_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "M2R05_NATIVE_REGION_ADMISSION_CONTRACT_V001",
        "coordinate_representation": FRAME,
        "rules_version": admission.RULES,
        "source": contract["source"],
        "input": contract["input"],
    }


def check_scope(contract: dict[str, Any], operation: str, output: Path) -> None:
    """A supplied run scope is an explicit boundary, not inferred owner authority."""
    require(contract["version"] == VERSION, "unsupported_pipeline_version")
    if contract["mode"] == "invented":
        return
    require(contract["mode"] == "actual", "unsupported_execution_mode")
    scope = contract["run_scope"]
    require(operation in scope["allowed_operations"], "operation_not_authorized")
    require(
        contract["input"]["sha256"] in scope["permitted_native_sha256"], "input_not_in_run_scope"
    )
    require(
        contract["input"]["physical_page"] in scope["permitted_physical_pages"],
        "page_not_in_run_scope",
    )
    target = output.resolve()
    root = Path(scope["output_root"]).resolve()
    require(target == root or target.is_relative_to(root), "output_outside_run_scope")
    require(
        not any(part.lower() in ("00_external", "01_raw", "99_archive") for part in target.parts),
        "protected_output_storage",
    )


def admit_native(contract: dict[str, Any], output: Path) -> dict[str, Any]:
    """One geometry-only call; preserve its first candidate and complete accounting."""
    require(not output.exists(), "exclusive_output_exists")
    page, evidence = load_native(io_contract(contract))
    regions, bands, hypotheses, coverage, accepted, unresolved, ambiguities = admission.admit(page)
    identity = {
        "source_pdf_sha256": contract["source"]["pdf_sha256"],
        "report_number": contract["source"]["report_number"],
        "native_sha256": contract["input"]["sha256"],
        "physical_page": contract["input"]["physical_page"],
        "coordinate_representation": FRAME,
    }
    for region in regions:
        region.update(
            identity=identity,
            rule_version=admission.RULES,
            evidence_word_pointers=[f"/words/{i}" for i in region["word_indices"]],
        )
    candidate = {
        "version": "SOURCE_NATIVE_REGION_CANDIDATE_V001",
        "rule_version": admission.RULES,
        "pipeline_version": VERSION,
        "source": contract["source"],
        "native_input": contract["input"],
        "coordinate_frame": {
            "representation": FRAME,
            "dimensions": contract["input"]["dimensions"],
        },
        "source_word_count": len(page["words"]),
        "regions": regions,
        "line_bands": bands,
        "competing_region_hypotheses": hypotheses,
        "source_negative_established": False,
        "semantic_page_completeness": False,
        "implementation": pin(Path(admission.__file__)),
        "io_implementation": pin(Path(__file__).with_name("io.py")),
        "created_utc": datetime.now(UTC).isoformat(),
    }
    ledger = {
        "version": "NATIVE_WORD_REGION_COVERAGE_V001",
        "words": coverage,
        "accepted_ownership_map": accepted,
        "unresolved_overlap_map": unresolved,
        "processing_coverage_established": True,
        "source_negative_established": False,
        "semantic_page_completeness": False,
    }
    output.mkdir()
    write(output / "initial_region_candidate.json", candidate)
    write(output / "source_word_region_coverage.json", ledger)
    write(output / "source_word_evidence.json", {"input": contract["input"], "words": evidence})
    write(output / "boundary_and_overlap_ambiguities.json", ambiguities)
    write(
        output / "admission_seal.json",
        {
            "files": [
                pin(output / name)
                for name in (
                    "initial_region_candidate.json",
                    "source_word_region_coverage.json",
                    "source_word_evidence.json",
                    "boundary_and_overlap_ambiguities.json",
                )
            ],
            "underlying_admission_calls": 1,
        },
    )
    return candidate


def run_pipeline(contract: dict[str, Any], output: Path) -> dict[str, Any]:
    """Seal admission/decisions before any authorized adapter; never retry a generator."""
    check_scope(contract, "pipeline", output)
    require(not output.exists(), "exclusive_output_exists")
    output.mkdir()
    write(
        output / "attempt_started.json",
        {
            "version": VERSION,
            "started_utc": datetime.now(UTC).isoformat(),
            "input": contract["input"],
            "run_scope": contract.get("run_scope"),
            "post_seal_regeneration_authorized": False,
        },
    )
    calls = {"admission": 0, "regional": 0, "priority": 0, "engine": 0}
    try:
        calls["admission"] += 1
        admit_native(contract, output / "admission")
        composed_contract = dict(
            contract,
            admission=pin(output / "admission" / "initial_region_candidate.json"),
            coverage=pin(output / "admission" / "source_word_region_coverage.json"),
            registry=receiver.registry(),
            context_policy=receiver.CONTEXT_POLICY,
            geometry_predicates=receiver.GEOMETRY_PREDICATES,
        )
        # Admission rules and run scope remain frozen; only sealed output references are filled.
        write(output / "composition_input.json", composed_contract)
        receiver.compose(composed_contract, output / "composition", generation_counts=calls)
        derivative = read(output / "composition" / "table_derivative.json")
        engine_status = "not_executed_no_qualified_derivative"
        if derivative["tables"]:
            from .profile import compile_profile

            expected_engine = contract.get("run_scope", {}).get(
                "engine_sha256", pin(Path(engine.__file__))["sha256"]
            )
            compile_profile(
                output / "composition" / "composed_candidate.json",
                output / "composition" / "table_derivative.json",
                output / "composition" / "engine_config.json",
                expected_engine,
            )
            write(
                output / "composition" / "engine_config_seal.json",
                {
                    "configuration": pin(output / "composition" / "engine_config.json"),
                    "engine": pin(Path(engine.__file__)),
                    "generation_started": False,
                },
            )
            require(
                contract.get("run_scope", {}).get("max_engine_calls", 1) >= 1,
                "engine_not_authorized",
            )
            if "engine_sha256" in contract.get("run_scope", {}):
                require(
                    pin(Path(engine.__file__))["sha256"] == contract["run_scope"]["engine_sha256"],
                    "engine_identity_mismatch",
                )
            calls["engine"] += 1
            rc = engine.run(
                output / "composition" / "engine_config.json",
                output / "composition" / "engine_result.json",
            )
            engine_status = "processed" if rc == 0 else "failed_preserved_no_retry"
        final = {
            "version": VERSION,
            "calls": calls,
            "engine_status": engine_status,
            "source_negative_established": False,
            "semantic_page_completeness": False,
        }
        write(output / "run_result.json", final)
        return final
    finally:
        write(
            output / "invocation_accounting.json",
            {
                "calls": calls,
                "process_local_only": True,
                "not_os_sandbox_or_uninterrupted_observation": True,
            },
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--operation", choices=("admit", "receive", "compose", "pipeline"), required=True
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        contract = read(args.manifest)
        check_scope(contract, args.operation, args.output)
        if args.operation == "admit":
            result = admit_native(contract, args.output)
        elif args.operation == "receive":
            result = receiver.receiving_only(contract, args.output)
        elif args.operation == "compose":
            result = receiver.compose(contract, args.output)
        else:
            result = run_pipeline(contract, args.output)
        print(
            json.dumps(
                {
                    "status": "preserved",
                    "version": VERSION,
                    "operation": args.operation,
                    "calls": result.get("calls"),
                    "engine_status": result.get("engine_status"),
                }
            )
        )
        return 0
    except (ValueError, TypeError, KeyError, IndexError, OSError, RuntimeError) as exc:
        print(
            json.dumps({"status": "rejected_or_failed_preserve_first", "error": str(exc)}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
