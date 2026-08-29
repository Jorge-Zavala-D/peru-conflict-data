"""Acquisition v0.2 contracts for separately authorized live comparison."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from peru_conflicts.acquisition.models import SafeResponseHeaders
from peru_conflicts.acquisition.models_v2 import (
    AuthorizationCapabilitiesV2,
    AuthorizationRegistryV2,
    DurableAttemptFinishedV2,
    DurableAttemptStartedV2,
    DurableLedgerRecordV2,
    DurableRunTerminalV2,
    ExecutionTreeEntryV2,
    ExecutionTreeManifestV2,
    NetworkAuthorizationArtifactV2,
    RedirectPolicyV2,
    StorageNamespaceMarkerV2,
    authorization_registry_core_sha256,
    marker_bytes,
)
from peru_conflicts.hashing import canonical_json_bytes

SHA = "a" * 64
OTHER_SHA = "b" * 64
COMMIT = "c" * 40
NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def _marker() -> StorageNamespaceMarkerV2:
    return StorageNamespaceMarkerV2(
        schema_version="0.2.0",
        namespace_id="m1-03b-reports-260-269",
        owner_nonce_sha256=SHA,
    )


def _artifact_payload() -> dict[str, object]:
    marker = _marker()
    return {
        "schema_version": "0.2.0",
        "authorization_id": "m1-03b2-example",
        "authorization_status": "authorized",
        "scope": "m1_03b_reports_260_269_compare_only",
        "plan_id": "m1-03-reports-260-269-v2",
        "plan_file_sha256": SHA,
        "plan_semantic_sha256": SHA,
        "ordered_target_set_sha256": SHA,
        "plan_limits_sha256": SHA,
        "protected_source_receipt_path": "docs/source_integrity_receipt_m1_03b1.md",
        "protected_source_receipt_git_commit": COMMIT,
        "protected_source_receipt_sha256": SHA,
        "execution_git_commit": COMMIT,
        "execution_tree_manifest_sha256": SHA,
        "execution_tree_sha256": SHA,
        "dependency_records": tuple(
            {
                "distribution": distribution,
                "record_path": f"{distribution}-1.0.dist-info/RECORD",
                "record_sha256": SHA,
            }
            for distribution in (
                "annotated-types",
                "pydantic",
                "pydantic-core",
                "pyyaml",
                "typing-extensions",
                "typing-inspection",
            )
        ),
        "approved_report_numbers": tuple(range(260, 270)),
        "approved_hosts": ("defensoria.gob.pe", "www.defensoria.gob.pe"),
        "capabilities": AuthorizationCapabilitiesV2(
            external_network_comparison=True,
            operational_ledger_writes=True,
            raw_staging=False,
            raw_promotion=False,
            historical_full_corpus_expansion=False,
        ),
        "redirect_policy": RedirectPolicyV2(
            max_hops=5,
            path_policy="canonical_wire_equivalent_only",
            approved_host_aliases=("defensoria.gob.pe", "www.defensoria.gob.pe"),
            require_https=True,
            default_port_only=True,
            allow_query=False,
        ),
        "storage_namespace_marker": marker,
        "storage_namespace_marker_sha256": hashlib.sha256(marker_bytes(marker)).hexdigest(),
        "data_root_identity_sha256": SHA,
        "execution_host_identity_sha256": SHA,
        "approved_by": "Jorge Zavala",
        "approved_at": NOW,
        "reuse_policy": "one_shot_same_run_resume_only",
    }


def test_authorization_contract_is_exactly_scoped_and_marker_is_self_consistent() -> None:
    artifact = NetworkAuthorizationArtifactV2.model_validate(_artifact_payload())

    assert artifact.approved_report_numbers == tuple(range(260, 270))
    assert artifact.capabilities.raw_staging is False
    assert artifact.capabilities.raw_promotion is False
    assert artifact.redirect_policy.allow_query is False

    for field, replacement in (
        ("approved_report_numbers", tuple(range(259, 270))),
        ("approved_hosts", ("defensoria.gob.pe", "mirror.example")),
        ("protected_source_receipt_path", "docs/source_integrity_receipt_m1_02_2.md"),
        ("storage_namespace_marker_sha256", OTHER_SHA),
        ("reuse_policy", "unlimited"),
    ):
        payload = _artifact_payload()
        payload[field] = replacement
        with pytest.raises(ValidationError):
            NetworkAuthorizationArtifactV2.model_validate(payload)


def test_authorization_rejects_widened_capabilities_and_naive_timestamp() -> None:
    for capability in (
        "raw_staging",
        "raw_promotion",
        "historical_full_corpus_expansion",
    ):
        payload = _artifact_payload()
        capability_model = payload["capabilities"]
        assert isinstance(capability_model, AuthorizationCapabilitiesV2)
        capabilities = capability_model.model_dump()
        capabilities[capability] = True
        payload["capabilities"] = capabilities
        with pytest.raises(ValidationError):
            NetworkAuthorizationArtifactV2.model_validate(payload)

    payload = _artifact_payload()
    payload["approved_at"] = datetime(2026, 8, 29, 12, 0)
    with pytest.raises(ValidationError):
        NetworkAuthorizationArtifactV2.model_validate(payload)


def test_registry_core_includes_execution_commit_and_is_deterministic() -> None:
    first = NetworkAuthorizationArtifactV2.model_validate(_artifact_payload())
    changed = first.model_copy(update={"execution_git_commit": "d" * 40})

    assert authorization_registry_core_sha256(first) != authorization_registry_core_sha256(changed)
    assert authorization_registry_core_sha256(first) != SHA
    empty = AuthorizationRegistryV2(schema_version="0.2.0", grants=())
    assert empty.grants == ()


def test_execution_tree_manifest_is_sorted_unique_and_hash_bound() -> None:
    entries = (
        ExecutionTreeEntryV2(path="pyproject.toml", sha256=SHA, byte_count=10),
        ExecutionTreeEntryV2(
            path="src/peru_conflicts/acquisition/cli.py",
            sha256=OTHER_SHA,
            byte_count=20,
        ),
    )
    manifest = ExecutionTreeManifestV2.from_entries(entries)

    assert manifest.entries == entries
    assert manifest.execution_tree_sha256 != SHA

    with pytest.raises(ValidationError):
        ExecutionTreeManifestV2.from_entries(tuple(reversed(entries)))
    with pytest.raises(ValidationError):
        ExecutionTreeManifestV2.from_entries((entries[0], entries[0]))


def test_hash_chained_attempt_records_keep_missing_zero_and_terminal_distinct() -> None:
    started = DurableAttemptStartedV2(
        schema_version="0.2.0",
        record_type="attempt_started",
        record_id="attempt-1-start",
        authorization_id="authorization-1",
        run_id="run-1",
        plan_id="plan-1",
        sequence=1,
        previous_record_sha256=None,
        recorded_at=NOW,
        attempt_id="attempt-1",
        attempt_ordinal=1,
        report_number=260,
        request_kind="landing_html",
        source_url_sha256=SHA,
        normalized_url="https://www.defensoria.gob.pe/documentos/example/",
        wire_target="/documentos/example/",
        reserved_bytes=2_000_000,
        continued_from_attempt_id=None,
        continuation_reason=None,
    )
    finished = DurableAttemptFinishedV2(
        schema_version="0.2.0",
        record_type="attempt_finished",
        record_id="attempt-1-finish",
        authorization_id="authorization-1",
        run_id="run-1",
        plan_id="plan-1",
        sequence=2,
        previous_record_sha256=SHA,
        recorded_at=NOW,
        attempt_id="attempt-1",
        attempt_ordinal=1,
        outcome="success",
        status_code=200,
        accepted_bytes=0,
        body_sha256=OTHER_SHA,
        error_code=None,
        response_headers=SafeResponseHeaders(content_type_original="text/html"),
    )
    terminal = DurableRunTerminalV2(
        schema_version="0.2.0",
        record_type="run_terminal",
        record_id="terminal-1",
        authorization_id="authorization-1",
        run_id="run-1",
        plan_id="plan-1",
        sequence=3,
        previous_record_sha256=OTHER_SHA,
        recorded_at=NOW,
        terminal_status="abandoned",
        reason_code="synthetic_stop",
    )

    adapter: TypeAdapter[DurableLedgerRecordV2] = TypeAdapter(DurableLedgerRecordV2)
    assert adapter.validate_json(canonical_json_bytes(started.model_dump(mode="json"))) == started
    assert adapter.validate_json(canonical_json_bytes(finished.model_dump(mode="json"))) == finished
    assert adapter.validate_json(canonical_json_bytes(terminal.model_dump(mode="json"))) == terminal
    assert finished.accepted_bytes == 0
    assert finished.error_code is None

    with pytest.raises(ValidationError):
        DurableAttemptStartedV2.model_validate(
            {**started.model_dump(mode="json"), "sequence": 1, "previous_record_sha256": SHA}
        )
