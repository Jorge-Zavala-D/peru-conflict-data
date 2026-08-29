"""The future live command exists but cannot cross the empty B.1 registry."""

from __future__ import annotations

import hashlib
import os
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from peru_conflicts.acquisition.authorization import (
    AuthorizationNotReviewed,
    LiveComparePlatformUnsupported,
)
from peru_conflicts.acquisition.models_v2 import (
    AuthorizationCapabilitiesV2,
    DependencyRecordPinV2,
    NetworkAuthorizationArtifactV2,
    RedirectPolicyV2,
    StorageNamespaceMarkerV2,
    marker_bytes,
)
from peru_conflicts.acquisition.plan import REVIEWED_V2_PLAN_FILE_SHA256
from peru_conflicts.hashing import canonical_json_bytes


@pytest.mark.skipif(os.name != "nt", reason="registry path follows Windows live gate")
def test_live_compare_fails_at_empty_registry_before_any_side_effect_factory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from peru_conflicts.acquisition import cli

    plan = tmp_path / "plan.yaml"
    authorization = tmp_path / "authorization.json"
    plan.write_text("not consulted by synthetic loader\n", encoding="utf-8")
    authorization.write_text("{}\n", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setenv("CONFLICT_DATA_ROOT", str(tmp_path / "data"))

    def load_plan(*args: object, **kwargs: object) -> object:
        del args, kwargs
        return object()

    monkeypatch.setattr(cli, "load_reviewed_pilot_plan", load_plan)

    def reject(*args: object, **kwargs: object) -> object:
        del args, kwargs
        calls.append("authorization")
        raise AuthorizationNotReviewed("no M1-03B.2 grant exists")

    monkeypatch.setattr(cli, "load_reviewed_network_authorization", reject)

    def execute(*args: object, **kwargs: object) -> None:
        del args, kwargs
        calls.append("execute")

    monkeypatch.setattr(cli, "execute_live_compare", execute)

    with pytest.raises(AuthorizationNotReviewed, match=r"no M1-03B\.2"):
        cli.main(
            (
                "--mode",
                "live-compare",
                "--plan",
                str(plan),
                "--require-plan-sha256",
                "a" * 64,
                "--authorization",
                str(authorization),
                "--require-authorization-sha256",
                "b" * 64,
            )
        )
    assert calls == ["authorization"]
    assert not (tmp_path / "data").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX application live boundary")
def test_posix_live_compare_fails_before_plan_authorization_or_data_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from peru_conflicts.acquisition import cli

    calls: list[str] = []
    data_root = tmp_path / "data-root-must-not-exist"
    monkeypatch.setenv("CONFLICT_DATA_ROOT", str(data_root))

    def record_plan(*args: object, **kwargs: object) -> None:
        del args, kwargs
        calls.append("plan")

    def record_authorization(*args: object, **kwargs: object) -> None:
        del args, kwargs
        calls.append("authorization")

    def record_execute(*args: object, **kwargs: object) -> None:
        del args, kwargs
        calls.append("execute")

    monkeypatch.setattr(cli, "load_reviewed_pilot_plan", record_plan)
    monkeypatch.setattr(cli, "load_reviewed_network_authorization", record_authorization)
    monkeypatch.setattr(cli, "execute_live_compare", record_execute)

    with pytest.raises(LiveComparePlatformUnsupported):
        cli.main(
            (
                "--mode",
                "live-compare",
                "--require-plan-sha256",
                "a" * 64,
                "--authorization",
                str(tmp_path / "authorization-must-not-be-read.json"),
                "--require-authorization-sha256",
                "b" * 64,
            )
        )

    assert calls == []
    assert not data_root.exists()


@pytest.mark.skipif(os.name != "nt", reason="registry path follows Windows live gate")
def test_real_empty_registry_blocks_valid_artifact_before_dns_or_data_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from peru_conflicts.acquisition import cli

    marker = StorageNamespaceMarkerV2(
        schema_version="0.2.0",
        namespace_id="blocked-integration",
        owner_nonce_sha256="a" * 64,
    )
    artifact = NetworkAuthorizationArtifactV2(
        schema_version="0.2.0",
        authorization_id="blocked-integration",
        authorization_status="authorized",
        scope="m1_03b_reports_260_269_compare_only",
        plan_id="m1-03-reports-260-269-v2",
        plan_file_sha256=REVIEWED_V2_PLAN_FILE_SHA256,
        plan_semantic_sha256="a" * 64,
        ordered_target_set_sha256="b" * 64,
        plan_limits_sha256="c" * 64,
        protected_source_receipt_path="docs/source_integrity_receipt_m1_03b1.md",
        protected_source_receipt_git_commit="d" * 40,
        protected_source_receipt_sha256="e" * 64,
        execution_git_commit="f" * 40,
        execution_tree_manifest_sha256="1" * 64,
        execution_tree_sha256="2" * 64,
        dependency_records=tuple(
            DependencyRecordPinV2(
                distribution=distribution,
                record_path=f"{distribution}-1.0.dist-info/RECORD",
                record_sha256="5" * 64,
            )
            for distribution in (
                "annotated-types",
                "pydantic",
                "pydantic-core",
                "pyyaml",
                "typing-extensions",
                "typing-inspection",
            )
        ),
        approved_report_numbers=tuple(range(260, 270)),
        approved_hosts=("defensoria.gob.pe", "www.defensoria.gob.pe"),
        capabilities=AuthorizationCapabilitiesV2(
            external_network_comparison=True,
            operational_ledger_writes=True,
            raw_staging=False,
            raw_promotion=False,
            historical_full_corpus_expansion=False,
        ),
        redirect_policy=RedirectPolicyV2(
            max_hops=5,
            path_policy="canonical_wire_equivalent_only",
            approved_host_aliases=("defensoria.gob.pe", "www.defensoria.gob.pe"),
            require_https=True,
            default_port_only=True,
            allow_query=False,
        ),
        storage_namespace_marker=marker,
        storage_namespace_marker_sha256=hashlib.sha256(marker_bytes(marker)).hexdigest(),
        data_root_identity_sha256="3" * 64,
        execution_host_identity_sha256="4" * 64,
        approved_by="Jorge Zavala",
        approved_at=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        reuse_policy="one_shot_same_run_resume_only",
    )
    raw = canonical_json_bytes(artifact.model_dump(mode="json")) + b"\n"
    authorization = tmp_path / "authorization.json"
    authorization.write_bytes(raw)
    monkeypatch.setattr(
        "peru_conflicts.acquisition.authorization.PRODUCTION_AUTHORIZATION_PATH",
        authorization,
    )
    data_root = tmp_path / "must-not-be-created"
    monkeypatch.setenv("CONFLICT_DATA_ROOT", str(data_root))

    def deny_network(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("network boundary crossed")

    monkeypatch.setattr(socket, "getaddrinfo", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)
    with pytest.raises(AuthorizationNotReviewed):
        cli.main(
            (
                "--mode",
                "live-compare",
                "--require-plan-sha256",
                REVIEWED_V2_PLAN_FILE_SHA256,
                "--authorization",
                str(authorization),
                "--require-authorization-sha256",
                hashlib.sha256(raw).hexdigest(),
            )
        )
    assert not data_root.exists()


@pytest.mark.parametrize(
    "forbidden",
    (
        ("--host", "example.org"),
        ("--url", "https://example.org/file.pdf"),
        ("--reports", "1-269"),
        ("--destination", "elsewhere"),
        ("--force",),
        ("--authorize",),
        ("--skip-robots",),
        ("--insecure",),
        ("--promote",),
        ("--output", "somewhere.json"),
        ("--output=somewhere.json",),
        ("--out", "somewhere.json"),
    ),
)
def test_live_cli_has_no_scope_or_security_escape_hatch(forbidden: tuple[str, ...]) -> None:
    from peru_conflicts.acquisition import cli

    with pytest.raises(SystemExit):
        cli.main(("--mode", "live-compare", *forbidden))
