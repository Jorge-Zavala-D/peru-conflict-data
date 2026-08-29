"""Fail-closed production composition for a future authorized live comparison."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from peru_conflicts.acquisition.attempt_transport import DurableAttemptTransport
from peru_conflicts.acquisition.authorization import (
    ExecutionTreeMismatch,
    ReviewedNetworkAuthorizationV2,
    compute_data_root_identity_sha256,
    compute_execution_host_identity_sha256,
    read_reviewed_git_blob,
    require_live_compare_platform,
    verify_execution_tree,
)
from peru_conflicts.acquisition.compare_runner import (
    BoundProtectedSources,
    CompareOnlyRunner,
    CompareTarget,
    verify_all_local_sources,
)
from peru_conflicts.acquisition.engine import (
    AcquisitionClient,
    DownloadedObject,
    LandingHtmlEvidence,
    StreamingTransport,
)
from peru_conflicts.acquisition.models_v2 import (
    DurableIssueV2,
    DurableRunTerminalV2,
    ExecutionTreeManifestV2,
    NetworkAuthorizationArtifactV2,
)
from peru_conflicts.acquisition.persistent_ledger import ManifestLedgerStore
from peru_conflicts.acquisition.plan import LoadedPilotPlan, validate_reviewed_loaded_plan
from peru_conflicts.acquisition.policy import seal_validated_v2_network_grant
from peru_conflicts.acquisition.temp_recovery import (
    RecoveredDownload,
    TemporaryRecoveryManager,
    deterministic_temp_token,
)
from peru_conflicts.acquisition.transport import (
    StandardLibraryStreamingTransport,
    validate_network_environment,
)
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.paths import DataPaths

EXECUTION_TREE_MANIFEST_RELATIVE_PATH = (
    "config/acquisition_authorizations/execution_tree_manifest_v2.json"
)
FUTURE_AUTHORIZATION_ARTIFACT_RELATIVE_PATH = (
    "config/acquisition_authorizations/m1_03b2_reports_260_269_authorization_v1.json"
)
EXECUTION_TREE_EXTERNAL_TRUST_ANCHORS = tuple(
    sorted(
        {
            FUTURE_AUTHORIZATION_ARTIFACT_RELATIVE_PATH,
            "config/acquisition_authorizations/reviewed_registry_v2.json",
            "config/acquisition_authorizations/reviewed_registry_v2.sha256",
            EXECUTION_TREE_MANIFEST_RELATIVE_PATH,
        }
    )
)
EXECUTION_TREE_REQUIRED_PATHS = tuple(
    sorted(
        (
            "config/acquisition_pilots/m1_03_reports_260_269_v2.yaml",
            "docs/source_integrity_receipt_m1_03b1.md",
            "pyproject.toml",
            "scripts/acquire_official_sources.py",
            "src/peru_conflicts/__init__.py",
            "src/peru_conflicts/acquisition/__init__.py",
            "src/peru_conflicts/acquisition/attempt_transport.py",
            "src/peru_conflicts/acquisition/authorization.py",
            "src/peru_conflicts/acquisition/cli.py",
            "src/peru_conflicts/acquisition/compare_runner.py",
            "src/peru_conflicts/acquisition/engine.py",
            "src/peru_conflicts/acquisition/fs_safety.py",
            "src/peru_conflicts/acquisition/landing.py",
            "src/peru_conflicts/acquisition/ledger.py",
            "src/peru_conflicts/acquisition/live_compare.py",
            "src/peru_conflicts/acquisition/models.py",
            "src/peru_conflicts/acquisition/models_v2.py",
            "src/peru_conflicts/acquisition/persistent_ledger.py",
            "src/peru_conflicts/acquisition/plan.py",
            "src/peru_conflicts/acquisition/policy.py",
            "src/peru_conflicts/acquisition/preflight.py",
            "src/peru_conflicts/acquisition/storage.py",
            "src/peru_conflicts/acquisition/temp_recovery.py",
            "src/peru_conflicts/acquisition/transport.py",
            "src/peru_conflicts/discovery/pilot.py",
            "src/peru_conflicts/discovery/policy.py",
            "src/peru_conflicts/discovery/settings.py",
            "src/peru_conflicts/hashing.py",
            "src/peru_conflicts/models/__init__.py",
            "src/peru_conflicts/models/common.py",
            "src/peru_conflicts/paths.py",
            "uv.lock",
        )
    )
)
MAX_TOTAL_ATTEMPTS = 60
MAX_TOTAL_ACCEPTED_BYTES = 500_000_000


class LiveComparisonPreflightError(RuntimeError):
    """A reviewed local prerequisite differs before transport construction."""


GitBlobReader = Callable[[str, str], bytes]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def default_git_blob_reader(repo_root: Path) -> GitBlobReader:
    def read(commit: str, relative_path: str) -> bytes:
        try:
            return read_reviewed_git_blob(repo_root, commit, relative_path)
        except (OSError, ExecutionTreeMismatch) as error:
            raise LiveComparisonPreflightError(
                "protected source receipt Git blob is unavailable"
            ) from error

    return read


def verify_protected_source_receipt(
    *,
    repo_root: Path,
    relative_path: str,
    expected_git_commit: str,
    expected_sha256: str,
    git_blob_reader: GitBlobReader | None = None,
) -> None:
    """Require the working receipt and its pinned commit blob to be byte-identical."""

    repository = repo_root.resolve(strict=True)
    candidate = repo_root / relative_path
    try:
        resolved = candidate.resolve(strict=True)
        working_bytes = candidate.read_bytes()
    except OSError as error:
        raise LiveComparisonPreflightError(
            "protected source receipt working-tree bytes are unavailable"
        ) from error
    if not resolved.is_relative_to(repository) or not candidate.is_file():
        raise LiveComparisonPreflightError(
            "protected source receipt working-tree path escapes the repository"
        )
    if _sha256_bytes(working_bytes) != expected_sha256:
        raise LiveComparisonPreflightError("protected source receipt working-tree SHA-256 differs")
    reader = git_blob_reader or default_git_blob_reader(repo_root)
    committed_bytes = reader(expected_git_commit, relative_path)
    if _sha256_bytes(committed_bytes) != expected_sha256:
        raise LiveComparisonPreflightError("protected source receipt Git blob SHA-256 differs")
    if committed_bytes != working_bytes:
        raise LiveComparisonPreflightError(
            "protected source receipt working-tree and Git blob bytes differ"
        )


def derive_run_id(authorization_id: str) -> str:
    """Derive one path-safe deterministic run identity from the one-shot grant."""

    digest = hashlib.sha256(authorization_id.encode("utf-8")).hexdigest()
    return f"m103b-{digest[:32]}"


def build_compare_targets(
    loaded_plan: LoadedPilotPlan,
    *,
    data_root: Path,
) -> tuple[CompareTarget, ...]:
    """Translate the byte-pinned plan without resolving source uncertainty away."""

    plan = validate_reviewed_loaded_plan(loaded_plan)
    targets: list[CompareTarget] = []
    for target in plan.targets:
        association_status = (
            "visibly_associated"
            if target.association_status == "visibly_associated"
            else "unresolved_opaque_filename"
        )
        if target.report_number in {261, 263}:
            if target.association_status != "unresolved_association" or set(
                target.uncertainty_codes
            ) != {"opaque_filename", "unresolved_association"}:
                raise LiveComparisonPreflightError(
                    "opaque report associations no longer preserve reviewed uncertainty"
                )
        elif target.association_status != "visibly_associated":
            raise LiveComparisonPreflightError(
                "only reports 261 and 263 may retain an unresolved association"
            )
        targets.append(
            CompareTarget(
                report_number=target.report_number,
                landing_url=target.landing_page_url,
                direct_download_url=target.direct_download_url,
                protected_source_path=data_root / target.existing_local_relative_path,
                expected_byte_count=target.existing_local_byte_count,
                expected_sha256=target.existing_local_sha256,
                association_status=association_status,
            )
        )
    return tuple(targets)


def _load_execution_tree_manifest(
    repo_root: Path,
    authorization: NetworkAuthorizationArtifactV2,
    *,
    protected_main_sha: str,
) -> ExecutionTreeManifestV2:
    path = repo_root / EXECUTION_TREE_MANIFEST_RELATIVE_PATH
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise LiveComparisonPreflightError(
            "reviewed execution-tree manifest is unavailable"
        ) from error
    if _sha256_bytes(raw) != authorization.execution_tree_manifest_sha256:
        raise LiveComparisonPreflightError("execution-tree manifest SHA-256 differs")
    try:
        manifest = ExecutionTreeManifestV2.model_validate_json(raw)
    except ValidationError as error:
        raise LiveComparisonPreflightError(
            "execution-tree manifest is structurally invalid"
        ) from error
    if manifest.execution_tree_sha256 != authorization.execution_tree_sha256:
        raise LiveComparisonPreflightError("execution-tree content hash differs")
    validate_execution_manifest_paths(manifest)
    required_paths = tuple(entry.path for entry in manifest.entries)
    if set(EXECUTION_TREE_EXTERNAL_TRUST_ANCHORS).intersection(required_paths):
        raise LiveComparisonPreflightError(
            "execution-tree manifest cannot include circular external trust anchors"
        )
    try:
        verify_execution_tree(
            repo_root=repo_root,
            expected_git_commit=authorization.execution_git_commit,
            expected_manifest=manifest,
            required_paths=required_paths,
            external_trust_anchors=EXECUTION_TREE_EXTERNAL_TRUST_ANCHORS,
            protected_main_sha=protected_main_sha,
        )
    except ExecutionTreeMismatch as error:
        raise LiveComparisonPreflightError("reviewed execution tree differs") from error
    return manifest


def validate_execution_manifest_paths(manifest: ExecutionTreeManifestV2) -> None:
    """Reject incomplete or widened runtime manifests before Git verification."""

    observed = tuple(entry.path for entry in manifest.entries)
    if observed != EXECUTION_TREE_REQUIRED_PATHS:
        raise LiveComparisonPreflightError(
            "execution-tree manifest is not the exact closed runtime input set"
        )


def _require_bound_directory(path: Path, *, description: str) -> None:
    try:
        details = path.lstat()
    except OSError as error:
        raise LiveComparisonPreflightError(f"{description} is unavailable") from error
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if (
        not stat.S_ISDIR(details.st_mode)
        or path.is_symlink()
        or (reparse and getattr(details, "st_file_attributes", 0) & reparse)
    ):
        raise LiveComparisonPreflightError(f"{description} is not a direct directory")


def _validate_authorization_binding(
    loaded_plan: LoadedPilotPlan,
    authorization: NetworkAuthorizationArtifactV2,
) -> None:
    plan = validate_reviewed_loaded_plan(loaded_plan)
    limits_sha256 = _sha256_bytes(canonical_json_bytes(plan.limits.model_dump(mode="json")))
    if (
        authorization.plan_id != plan.plan_id
        or authorization.plan_file_sha256 != loaded_plan.file_sha256
        or authorization.plan_semantic_sha256 != loaded_plan.semantic_sha256
        or authorization.ordered_target_set_sha256 != loaded_plan.target_set_sha256
        or authorization.plan_limits_sha256 != limits_sha256
    ):
        raise LiveComparisonPreflightError("authorization does not bind the exact reviewed plan")


@dataclass(slots=True)
class _ProductionCompareClient:
    engine: AcquisitionClient
    attempts: DurableAttemptTransport
    recovered: dict[int, RecoveredDownload]

    @property
    def last_completed_attempt_id(self) -> str | None:
        return self.attempts.last_completed_attempt_id

    def set_report_context(self, report_number: int) -> None:
        self.attempts.set_report_context(report_number)

    def fetch_landing_html(
        self, url: str, *, run_id: str, report_number: int
    ) -> LandingHtmlEvidence:
        return self.engine.fetch_landing_html(
            url,
            run_id=run_id,
            report_number=report_number,
        )

    def fetch_pdf(self, url: str, *, run_id: str, report_number: int) -> DownloadedObject:
        return self.engine.fetch_pdf(url, run_id=run_id, report_number=report_number)

    def cleanup_downloaded(
        self,
        downloaded: DownloadedObject,
        *,
        run_id: str,
        report_number: int,
        related_attempt_id: str,
    ) -> None:
        self.engine.cleanup_downloaded(
            downloaded,
            run_id=run_id,
            report_number=report_number,
            related_attempt_id=related_attempt_id,
        )

    def recover_downloaded(self, report_number: int) -> tuple[DownloadedObject, str] | None:
        recovered = self.recovered.pop(report_number, None)
        if recovered is None:
            return None
        return recovered.downloaded, recovered.attempt_id


def _system_temp_root() -> Path:
    return Path(tempfile.gettempdir()) / "peru-conflict-data" / "m1-03-pilot-260-269"


def _object_token_factory(
    authorization_id: str,
    consumed_attempts: int,
) -> Callable[[int, int], str]:
    def token(report_number: int, local_attempt_number: int) -> str:
        ordinal = consumed_attempts + local_attempt_number
        return deterministic_temp_token(
            authorization_id,
            report_number=report_number,
            attempt_ordinal=ordinal,
        )

    return token


def execute_live_compare(
    *,
    loaded_plan: LoadedPilotPlan,
    authorization: ReviewedNetworkAuthorizationV2,
    repo_root: Path,
    data_root: Path,
) -> str:
    """Execute only after a future fixed registry admits one exact owner grant."""

    require_live_compare_platform()
    reviewed = ReviewedNetworkAuthorizationV2.require(authorization)
    artifact = reviewed.artifact
    _validate_authorization_binding(loaded_plan, artifact)
    manifest = _load_execution_tree_manifest(
        repo_root,
        artifact,
        protected_main_sha=reviewed.protected_main_sha,
    )
    verify_protected_source_receipt(
        repo_root=repo_root,
        relative_path=artifact.protected_source_receipt_path,
        expected_git_commit=artifact.protected_source_receipt_git_commit,
        expected_sha256=artifact.protected_source_receipt_sha256,
    )
    paths = DataPaths.resolve(repo_root=repo_root, data_root=data_root)
    _require_bound_directory(paths.raw, description="protected raw root")
    manifests = paths.raw / "manifests"
    _require_bound_directory(manifests, description="operational manifest directory")
    if os.path.lexists(paths.raw / ".staging"):
        raise LiveComparisonPreflightError(
            "compare-only execution forbids a real raw staging directory"
        )

    execution_host_sha256 = compute_execution_host_identity_sha256()
    if execution_host_sha256 != artifact.execution_host_identity_sha256:
        raise LiveComparisonPreflightError("execution host identity differs")
    data_root_sha256 = compute_data_root_identity_sha256(
        paths.root,
        marker_nonce_sha256=artifact.storage_namespace_marker.owner_nonce_sha256,
        execution_host_identity_sha256=execution_host_sha256,
    )
    if data_root_sha256 != artifact.data_root_identity_sha256:
        raise LiveComparisonPreflightError("data-root identity differs")

    targets = build_compare_targets(loaded_plan, data_root=paths.root)
    with BoundProtectedSources.open(data_root=paths.root, targets=targets) as sources:
        verify_all_local_sources(targets, source_fingerprinter=sources.fingerprint)
        validate_network_environment()
        run_id = derive_run_id(artifact.authorization_id)
        recorded_at = datetime.now(UTC)

        with ManifestLedgerStore.open(
            data_root=paths.root,
            marker=artifact.storage_namespace_marker,
            expected_data_root_identity_sha256=artifact.data_root_identity_sha256,
            execution_host_identity_sha256=execution_host_sha256,
            expected_execution_tree_sha256=manifest.execution_tree_sha256,
            expected_authorization_artifact_sha256=reviewed.artifact_sha256,
            authorization_id=artifact.authorization_id,
            run_id=run_id,
            plan_id=artifact.plan_id,
            recorded_at=recorded_at,
        ) as ledger:
            reconciled_attempts = ledger.reconcile_unfinished_attempts(recorded_at=recorded_at)
            recovered = TemporaryRecoveryManager(
                system_temp_root=_system_temp_root(),
                run_id=run_id,
                authorization_id=artifact.authorization_id,
                ledger=ledger,
            ).reconcile()
            crash_outcome_unknown = bool(reconciled_attempts) or any(
                isinstance(record, DurableIssueV2)
                and record.reason_code == "attempt_outcome_unknown_after_process_crash"
                for record in ledger.records
            )
            if crash_outcome_unknown:
                ledger.append(
                    DurableRunTerminalV2(
                        schema_version="0.2.0",
                        record_type="run_terminal",
                        record_id="run-terminal",
                        authorization_id=ledger.authorization_id,
                        run_id=ledger.run_id,
                        plan_id=ledger.plan_id,
                        sequence=ledger.next_sequence,
                        previous_record_sha256=ledger.ledger_head_sha256,
                        recorded_at=datetime.now(UTC),
                        terminal_status="stop_for_review",
                        reason_code="attempt_outcome_unknown_after_process_crash",
                    )
                )
                return "stop_for_review"
            remaining_attempts = MAX_TOTAL_ATTEMPTS - ledger.consumed_attempts
            remaining_bytes = MAX_TOTAL_ACCEPTED_BYTES - ledger.reserved_bytes
            if remaining_attempts < 1 or remaining_bytes < 1:
                raise LiveComparisonPreflightError(
                    "durable request or accepted-byte budget is exhausted"
                )

            direct_transport = StandardLibraryStreamingTransport(
                approved_hosts=frozenset(artifact.approved_hosts)
            )
            durable_transport = DurableAttemptTransport(
                transport=direct_transport,
                ledger=ledger,
                approved_hosts=frozenset(artifact.approved_hosts),
                reviewed_landing_urls={
                    target.report_number: target.landing_url for target in targets
                },
                reviewed_pdf_urls={
                    target.report_number: target.direct_download_url for target in targets
                },
            )
            transport_for_grant = cast(StreamingTransport, durable_transport)
            grant = seal_validated_v2_network_grant(
                loaded_plan,
                artifact,
                transport_for_grant,
            )
            engine = AcquisitionClient(
                grant=grant,
                system_temp_root=_system_temp_root(),
                attempt_limit=remaining_attempts,
                total_byte_limit=remaining_bytes,
                object_name_token_factory=_object_token_factory(
                    artifact.authorization_id,
                    ledger.consumed_attempts,
                ),
            )
            client = _ProductionCompareClient(
                engine=engine,
                attempts=durable_transport,
                recovered=recovered,
            )
            return CompareOnlyRunner(
                targets=targets,
                ledger=ledger,
                client=client,
                run_id=run_id,
                execution_tree_sha256=manifest.execution_tree_sha256,
                execution_host_identity_sha256=execution_host_sha256,
                source_fingerprinter=sources.fingerprint,
            ).run()
