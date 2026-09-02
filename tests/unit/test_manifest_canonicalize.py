from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from peru_conflicts.manifest import canonicalize
from peru_conflicts.manifest.canonicalize import CanonicalPackage
from peru_conflicts.manifest.models import ArtifactFingerprint
from peru_conflicts.manifest.reviewed_models import (
    AdjudicationOutcome,
    ApprovalFingerprint,
    CanonicalizationReceipt,
    OwnerApprovalArtifact,
)
from peru_conflicts.paths import EXPECTED_TOP_LEVEL, DataPaths

SHA = "a" * 64
COMMIT = "b" * 40
TREE = "c" * 40
CANDIDATE_NAMES = (
    "byte_versions_candidate.jsonl",
    "corpus_manifest_candidate.jsonl",
    "coverage_report_candidate.json",
    "gap_register_candidate.jsonl",
    "source_observations_candidate.jsonl",
    "version_edges_candidate.jsonl",
)


def _approval_payload() -> dict[str, object]:
    outcomes = (
        [AdjudicationOutcome.EVIDENCE_INSUFFICIENT_RETAIN_UNRESOLVED] * 45
        + [AdjudicationOutcome.BYTES_NOT_OBSERVED_REMAIN_UNKNOWN] * 3
        + [AdjudicationOutcome.RETAIN_UNRESOLVED_OPAQUE_FILENAME] * 2
    )
    return {
        "schema_version": "0.2.0",
        "approval_id": "m1-04b-owner-adjudications-v1",
        "approved_by": "Jorge Zavala",
        "approved_at": datetime(2026, 9, 2, 6, 27, 44, tzinfo=UTC),
        "owner_approved": True,
        "protected_main": {"commit": COMMIT, "tree": TREE},
        "manifest_contract": {
            "schema_version": "0.1.1",
            "materializer_version": "m1-04a-v2",
        },
        "candidate_fingerprints": tuple(
            ArtifactFingerprint(
                artifact_role=f"candidate:{index}",
                path=name,
                bytes=1,
                sha256=SHA,
                record_count=1,
            )
            for index, name in enumerate(CANDIDATE_NAMES)
        ),
        "post_merge_materialization_receipt": {
            "path": "receipt.json",
            "bytes": 1,
            "sha256": SHA,
        },
        "review_input_fingerprints": {
            name: {"path": f"{name}.json", "bytes": 1, "sha256": SHA}
            for name in (
                "canonicalization_gate",
                "evidence_dossier",
                "m1_04b_review_spec_v011",
                "owner_decision_packet",
                "proposed_adjudications",
                "review_receipt",
            )
        },
        "approved_decisions": tuple(
            {"review_unit_id": f"review-{index:02d}", "approved_outcome": outcome}
            for index, outcome in enumerate(outcomes)
        ),
        "approved_outcome_counts": {
            AdjudicationOutcome.EVIDENCE_INSUFFICIENT_RETAIN_UNRESOLVED: 45,
            AdjudicationOutcome.BYTES_NOT_OBSERVED_REMAIN_UNKNOWN: 3,
            AdjudicationOutcome.RETAIN_UNRESOLVED_OPAQUE_FILENAME: 2,
        },
        "approved_deferred_acquisition_policy": {
            "authoritative_byte_corpus_complete": False,
            "blocks_identity_coverage_canonicalization": False,
            "count": 237,
            "future_evidence_classification": "useful_but_deferred",
            "report_numbers": tuple(range(23, 260)),
        },
        "approved_permissible_coverage_statement": (
            "Reviewed coverage accounting retains explicit limitations.",
        ),
        "prohibited_overclaims": ("Complete official PDF byte corpus.",),
        "scientific_assertions": {
            "new_report_identities_created": False,
            "new_month_mappings_created": False,
            "new_byte_identities_created": False,
            "unresolved_evidence_retained": True,
            "authoritative_byte_corpus_complete": False,
        },
    }


def _data_paths(tmp_path: Path) -> DataPaths:
    repo = tmp_path / "repo"
    root = tmp_path / "data"
    repo.mkdir(parents=True)
    root.mkdir(parents=True)
    for name in EXPECTED_TOP_LEVEL:
        (root / name).mkdir()
    return DataPaths.resolve(repo_root=repo, data_root=root)


def _fingerprint(path: str, raw: bytes, count: int = 1) -> ArtifactFingerprint:
    return ArtifactFingerprint(
        artifact_role=f"canonical_output:{path}",
        path=path,
        bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        record_count=count,
    )


def _exact_validator(expected: bytes) -> Callable[[bytes], bool]:
    return lambda raw: raw == expected


def _package() -> CanonicalPackage:
    files = {f"artifact-{index}.json": b"{}\n" for index in range(10)}
    outputs = tuple(_fingerprint(name, raw) for name, raw in sorted(files.items()))
    approval = ApprovalFingerprint(path="owner_approval.json", bytes=3, sha256=SHA)
    receipt = CanonicalizationReceipt(
        task_id="M1-04C.1",
        execution_commit=COMMIT,
        implementation_tree_sha=TREE,
        manifest_schema_version="0.2.0",
        canonical_target_relative_path="06_validation/m1_corpus_manifest/v0.2.0",
        candidate_input_artifacts=tuple(
            ArtifactFingerprint(
                artifact_role=f"candidate:{index}",
                path=f"candidate-{index}.json",
                bytes=1,
                sha256=SHA,
                record_count=1,
            )
            for index in range(6)
        ),
        review_input_artifacts=tuple(
            ApprovalFingerprint(path=f"review-{index}.json", bytes=1, sha256=SHA)
            for index in range(6)
        ),
        discovery_input_artifacts=(
            ArtifactFingerprint(
                artifact_role="discovery",
                path="discovery.jsonl",
                bytes=1,
                sha256=SHA,
                record_count=1,
            ),
        ),
        operational_input_artifacts=(
            ArtifactFingerprint(
                artifact_role="ledger",
                path="ledger.jsonl",
                bytes=1,
                sha256=SHA,
                record_count=1,
            ),
        ),
        owner_approval_artifact=approval,
        proposed_adjudications_artifact=ApprovalFingerprint(
            path="proposed.jsonl", bytes=1, sha256=SHA, record_count=50
        ),
        adjudication_records_artifact=outputs[0],
        output_artifacts=outputs,
        record_counts=tuple((item.path, 1) for item in outputs),
        unresolved_gap_counts=(("historical_month_unresolved", 21),),
        deferred_acquisition_count=237,
        byte_verified_count=10,
        authoritative_byte_corpus_complete=False,
        approved_coverage_claims=("Reviewed coverage accounting with explicit limitations.",),
        deterministic_sort_rules=("json:canonical_utf8_lf",),
        no_network_assertion=True,
        no_raw_write_assertion=True,
        write_once_no_overwrite=True,
        receipt_written_last=True,
    )
    receipt_raw = (
        json.dumps(
            receipt.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    validators = {name: _exact_validator(raw) for name, raw in files.items()}
    return CanonicalPackage(
        rendered_files=files,
        record_counts={name: 1 for name in files},
        validators=validators,
        receipt=receipt,
        receipt_bytes=receipt_raw,
    )


def _assert_written_package(package: CanonicalPackage, directory: Path) -> None:
    expected_names = set(package.rendered_files) | {canonicalize.CANONICAL_RECEIPT_NAME}
    assert {path.name for path in directory.iterdir()} == expected_names
    for name, raw in package.rendered_files.items():
        assert (directory / name).read_bytes() == raw
    receipt_raw = (directory / canonicalize.CANONICAL_RECEIPT_NAME).read_bytes()
    assert receipt_raw == package.receipt_bytes
    assert CanonicalizationReceipt.model_validate_json(receipt_raw) == package.receipt


def test_canonicalization_module_has_separate_preview_and_writer() -> None:
    assert canonicalize.CANONICAL_TARGET_RELATIVE.as_posix() == (
        "06_validation/m1_corpus_manifest/v0.2.0"
    )
    assert canonicalize.materialize_canonical_preview
    assert canonicalize.write_canonical_package


def test_fixed_target_rejects_raw_database_arbitrary_repo_existing_and_escape(
    tmp_path: Path,
) -> None:
    paths = _data_paths(tmp_path)
    expected = paths.validation / "m1_corpus_manifest" / "v0.2.0"

    assert canonicalize.require_new_canonical_target(paths, expected) == expected.resolve()
    rejected = (
        paths.raw / "manifest",
        paths.database / "m1_corpus_manifest" / "v0.2.0",
        paths.validation / "different" / "v0.2.0",
        tmp_path / "repo" / "canonical",
    )
    for candidate in rejected:
        with pytest.raises(canonicalize.CanonicalizationError):
            canonicalize.require_new_canonical_target(paths, candidate)

    expected.mkdir(parents=True)
    with pytest.raises(canonicalize.CanonicalizationError, match="already exists"):
        canonicalize.require_new_canonical_target(paths, expected)


def test_owner_approval_is_invalidated_by_changed_decisions_or_packet(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    review = tmp_path / ".cache" / "review"
    candidate.mkdir()
    review.mkdir(parents=True)
    payload = _approval_payload()

    candidate_fingerprints: list[ArtifactFingerprint] = []
    for index, name in enumerate(CANDIDATE_NAMES):
        path = candidate / name
        raw = f"candidate-{index}\n".encode()
        path.write_bytes(raw)
        candidate_fingerprints.append(
            ArtifactFingerprint(
                artifact_role=f"candidate:{index}",
                path=path.name,
                bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
                record_count=1,
            )
        )
    payload["candidate_fingerprints"] = tuple(candidate_fingerprints)
    receipt_raw = b"receipt\n"
    (candidate / "materialization_receipt.json").write_bytes(receipt_raw)
    payload["post_merge_materialization_receipt"] = {
        "path": "materialization_receipt.json",
        "bytes": len(receipt_raw),
        "sha256": hashlib.sha256(receipt_raw).hexdigest(),
    }

    decisions = cast(tuple[dict[str, object], ...], payload["approved_decisions"])
    proposed_raw = b"".join(
        json.dumps(
            {
                "review_unit_id": item["review_unit_id"],
                "proposed_outcome": cast(AdjudicationOutcome, item["approved_outcome"]).value,
                "owner_approval_required": True,
                "owner_decision": None,
                "creates_new_report_identity": False,
                "creates_new_month_mapping": False,
                "asserts_new_byte_identity": False,
                "preserves_all_source_observations": True,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
        for item in decisions
    )
    review_raw = {
        "canonicalization_gate": b"{}\n",
        "evidence_dossier": b"{}\n",
        "m1_04b_review_spec_v011": b"{}\n",
        "owner_decision_packet": (
            b'{"approved_at":null,"owner_approval_required":true,"owner_approved":false}\n'
        ),
        "proposed_adjudications": proposed_raw,
        "review_receipt": b"{}\n",
    }
    bindings = {}
    for name, raw in review_raw.items():
        suffix = ".jsonl" if name in {"evidence_dossier", "proposed_adjudications"} else ".json"
        relative = Path(".cache") / "review" / f"{name}{suffix}"
        (tmp_path / relative).write_bytes(raw)
        bindings[name] = {
            "path": relative.as_posix(),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "record_count": 50 if name == "proposed_adjudications" else 1,
        }
    payload["review_input_fingerprints"] = bindings
    approval = OwnerApprovalArtifact.model_validate(payload)

    canonicalize.verify_owner_approval_sources(
        approval, repository_root=tmp_path, candidate_dir=candidate
    )
    proposed_path = review / "proposed_adjudications.jsonl"
    proposed_path.write_bytes(proposed_raw + b"{}\n")
    with pytest.raises(canonicalize.CanonicalizationError, match="fingerprint mismatch"):
        canonicalize.verify_owner_approval_sources(
            approval, repository_root=tmp_path, candidate_dir=candidate
        )
    proposed_path.write_bytes(proposed_raw)
    packet_path = review / "owner_decision_packet.json"
    packet_path.write_bytes(b'{"owner_approved":true}\n')
    with pytest.raises(canonicalize.CanonicalizationError, match="fingerprint mismatch"):
        canonicalize.verify_owner_approval_sources(
            approval, repository_root=tmp_path, candidate_dir=candidate
        )


def test_fixed_target_rejects_symlink_or_junction_escape(tmp_path: Path) -> None:
    paths = _data_paths(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = paths.validation / "m1_corpus_manifest"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable")

    with pytest.raises(canonicalize.CanonicalizationError):
        canonicalize.require_new_canonical_target(paths, link / "v0.2.0")


def test_preview_is_byte_deterministic_and_receipt_is_written_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _package()
    first = tmp_path / ".cache" / "first"
    second = tmp_path / ".cache" / "second"
    repo = tmp_path
    write_calls: list[Path] = []
    real_write_file_fsync = cast(
        Callable[[Path, bytes], None], canonicalize.__dict__["_write_file_fsync"]
    )

    def record_write(path: Path, raw: bytes) -> None:
        write_calls.append(path)
        real_write_file_fsync(path, raw)

    monkeypatch.setattr(canonicalize, "_write_file_fsync", record_write)

    canonicalize.materialize_canonical_preview(package, output_dir=first, repository_root=repo)
    canonicalize.materialize_canonical_preview(package, output_dir=second, repository_root=repo)

    for output in (first, second):
        output_calls = [path.name for path in write_calls if path.parent == output]
        assert output_calls == [
            *sorted(package.rendered_files),
            canonicalize.CANONICAL_RECEIPT_NAME,
        ]
        assert output_calls.count(canonicalize.CANONICAL_RECEIPT_NAME) == 1
    assert {path.name: path.read_bytes() for path in first.iterdir()} == {
        path.name: path.read_bytes() for path in second.iterdir()
    }


def test_external_writer_writes_receipt_after_all_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _data_paths(tmp_path)
    package = _package()
    write_calls: list[Path] = []
    real_write_file_fsync = cast(
        Callable[[Path, bytes], None], canonicalize.__dict__["_write_file_fsync"]
    )

    def record_write(path: Path, raw: bytes) -> None:
        write_calls.append(path)
        real_write_file_fsync(path, raw)

    monkeypatch.setattr(canonicalize, "_write_file_fsync", record_write)

    target = canonicalize.write_canonical_package(package, data_paths=paths)

    package_calls = [path.name for path in write_calls]
    assert package_calls == [
        *sorted(package.rendered_files),
        canonicalize.CANONICAL_RECEIPT_NAME,
    ]
    assert package_calls.count(canonicalize.CANONICAL_RECEIPT_NAME) == 1
    _assert_written_package(package, target)


def test_external_writer_is_write_new_and_preserves_partial_evidence_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _data_paths(tmp_path)
    package = _package()

    target = canonicalize.write_canonical_package(package, data_paths=paths)
    assert target == paths.validation / "m1_corpus_manifest" / "v0.2.0"
    assert (target / "canonicalization_receipt.json").is_file()
    with pytest.raises(canonicalize.CanonicalizationError, match="already exists"):
        canonicalize.write_canonical_package(package, data_paths=paths)

    second_paths = _data_paths(tmp_path / "second")
    if os.name == "nt":
        original_rename = Path.rename

        def fail_rename(self: Path, target: Path) -> Path:
            if self.name.startswith(".m1-04c1-v020-"):
                raise OSError("simulated promotion failure")
            return original_rename(self, target)

        monkeypatch.setattr(Path, "rename", fail_rename)
    else:

        def fail_no_replace(
            source_directory: object,
            source_name: str,
            target_directory: object,
            target_name: str,
        ) -> None:
            assert source_directory is target_directory
            assert source_name.startswith(".m1-04c1-v020-")
            assert target_name == "v0.2.0"
            raise OSError("simulated promotion failure")

        monkeypatch.setattr(
            canonicalize,
            "rename_between_directories_no_replace",
            fail_no_replace,
        )
    with pytest.raises(canonicalize.CanonicalizationError, match="promotion failed"):
        canonicalize.write_canonical_package(package, data_paths=second_paths)
    package_parent = second_paths.validation / "m1_corpus_manifest"
    final_target = package_parent / "v0.2.0"
    partials = tuple(package_parent.glob(".m1-04c1-v020-*"))
    assert not final_target.exists()
    assert len(partials) == 1
    _assert_written_package(package, partials[0])
    assert not (package_parent / canonicalize.CANONICAL_LOCK_NAME).exists()
