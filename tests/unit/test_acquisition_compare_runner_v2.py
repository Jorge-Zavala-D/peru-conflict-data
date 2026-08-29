"""Deterministic compare-only orchestration with synthetic bytes and storage."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest

from peru_conflicts.acquisition.authorization import compute_data_root_identity_sha256
from peru_conflicts.acquisition.compare_runner import (
    BoundProtectedSources,
    CleanupPending,
    CompareOnlyRunner,
    CompareTarget,
    LocalSourceMismatch,
    verify_all_local_sources,
)
from peru_conflicts.acquisition.engine import (
    DownloadedObject,
    LandingHtmlEvidence,
    TemporaryCleanupPending,
)
from peru_conflicts.acquisition.models import SafeResponseHeaders
from peru_conflicts.acquisition.models_v2 import (
    DurableAttemptFinishedV2,
    DurableAttemptStartedV2,
    DurableComparisonV2,
    DurableIssueV2,
    DurableRunTerminalV2,
    DurableSourceRehashV2,
    StorageNamespaceMarkerV2,
)
from peru_conflicts.acquisition.persistent_ledger import (
    LedgerRecordConflict,
    ManifestLedgerStore,
    validate_durable_ledger_graph,
)

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
NONCE = "a" * 64
HOST_SHA = "b" * 64


def _targets(tmp_path: Path) -> tuple[CompareTarget, ...]:
    source_root = tmp_path / "source"
    source_root.mkdir()
    targets: list[CompareTarget] = []
    for report in range(260, 270):
        content = b"%PDF-" + bytes((report - 259,)) * 1_100
        source = source_root / f"report-{report}.pdf"
        source.write_bytes(content)
        targets.append(
            CompareTarget(
                report_number=report,
                landing_url=f"https://www.defensoria.gob.pe/documentos/reporte-{report}/",
                direct_download_url=(
                    f"https://www.defensoria.gob.pe/wp-content/uploads/report-{report}.pdf"
                ),
                protected_source_path=source,
                expected_byte_count=len(content),
                expected_sha256=hashlib.sha256(content).hexdigest(),
                association_status=(
                    "unresolved_opaque_filename" if report in {261, 263} else "visibly_associated"
                ),
            )
        )
    return tuple(targets)


def _rooted_targets(tmp_path: Path) -> tuple[Path, tuple[CompareTarget, ...]]:
    root = tmp_path / "bound-data"
    targets: list[CompareTarget] = []
    for report in range(260, 270):
        year = "2025" if report <= 262 else "2026"
        content = b"%PDF-" + bytes((report - 259,)) * 1_100
        source = root / "01_raw" / "reports" / year / f"report-{report}.pdf"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(content)
        targets.append(
            CompareTarget(
                report_number=report,
                landing_url=f"https://www.defensoria.gob.pe/documentos/reporte-{report}/",
                direct_download_url=(
                    f"https://www.defensoria.gob.pe/wp-content/uploads/report-{report}.pdf"
                ),
                protected_source_path=source,
                expected_byte_count=len(content),
                expected_sha256=hashlib.sha256(content).hexdigest(),
                association_status=(
                    "unresolved_opaque_filename" if report in {261, 263} else "visibly_associated"
                ),
            )
        )
    return root, tuple(targets)


def test_protected_sources_are_hashed_through_retained_parent_leases(tmp_path: Path) -> None:
    root, targets = _rooted_targets(tmp_path)
    with BoundProtectedSources.open(data_root=root, targets=targets) as sources:
        verify_all_local_sources(targets, source_fingerprinter=sources.fingerprint)
        for target in targets:
            assert sources.fingerprint(target) == (
                target.expected_byte_count,
                target.expected_sha256,
            )


def test_protected_source_intermediate_symlink_is_rejected(tmp_path: Path) -> None:
    root, targets = _rooted_targets(tmp_path)
    reports = root / "01_raw" / "reports"
    outside = tmp_path / "outside-reports"
    reports.rename(outside)
    try:
        reports.symlink_to(outside, target_is_directory=True)
    except OSError:
        outside.rename(reports)
        pytest.skip("directory symlinks are unavailable on this host")

    with pytest.raises(LocalSourceMismatch, match="parent"):
        BoundProtectedSources.open(data_root=root, targets=targets)


def test_protected_source_hardlink_alias_is_rejected(tmp_path: Path) -> None:
    root, targets = _rooted_targets(tmp_path)
    alias = tmp_path / "protected-source-alias.pdf"
    alias.hardlink_to(targets[0].protected_source_path)

    with pytest.raises(LocalSourceMismatch, match="parent binding"):
        BoundProtectedSources.open(data_root=root, targets=targets)


def _store(tmp_path: Path) -> ManifestLedgerStore:
    data_root = tmp_path / "data"
    (data_root / "01_raw" / "manifests").mkdir(parents=True, exist_ok=True)
    identity = compute_data_root_identity_sha256(
        data_root,
        marker_nonce_sha256=NONCE,
        execution_host_identity_sha256=HOST_SHA,
    )
    return ManifestLedgerStore.open(
        data_root=data_root,
        marker=StorageNamespaceMarkerV2(
            schema_version="0.2.0",
            namespace_id="namespace-1",
            owner_nonce_sha256=NONCE,
        ),
        expected_data_root_identity_sha256=identity,
        execution_host_identity_sha256=HOST_SHA,
        expected_execution_tree_sha256=NONCE,
        expected_authorization_artifact_sha256=NONCE,
        authorization_id="authorization-1",
        run_id="run-1",
        plan_id="plan-1",
        recorded_at=NOW,
    )


@dataclass
class FakeClient:
    targets: dict[int, CompareTarget]
    temp_root: Path
    collision_report: int | None = None
    missing_landing_report: int | None = None
    ambiguous_landing_report: int | None = None
    interrupt_pdf_report: int | None = None
    internal_cleanup_pending_report: int | None = None
    cleanup_failures_remaining: int = 0
    ledger: ManifestLedgerStore | None = None

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.current_report: int | None = None
        self.last_completed_attempt_id: str | None = None
        self.downloaded: dict[int, tuple[DownloadedObject, str]] = {}

    def set_report_context(self, report_number: int) -> None:
        self.current_report = report_number

    def _durable_attempt(
        self,
        *,
        report_number: int,
        request_kind: Literal["robots", "landing_html", "pdf"],
        url: str,
        body: bytes | None,
        outcome: Literal[
            "success",
            "redirect",
            "rejected",
            "retryable_failure",
            "interrupted",
        ] = "success",
    ) -> str:
        assert self.ledger is not None
        ordinal = self.ledger.consumed_attempts + 1
        attempt_id = f"attempt-{ordinal:04d}"
        self.ledger.append(
            DurableAttemptStartedV2(
                schema_version="0.2.0",
                record_type="attempt_started",
                record_id=f"{attempt_id}-start",
                authorization_id=self.ledger.authorization_id,
                run_id=self.ledger.run_id,
                plan_id=self.ledger.plan_id,
                sequence=self.ledger.next_sequence,
                previous_record_sha256=self.ledger.ledger_head_sha256,
                recorded_at=NOW,
                attempt_id=attempt_id,
                attempt_ordinal=ordinal,
                report_number=report_number,
                request_kind=request_kind,
                source_url_sha256=hashlib.sha256(url.encode()).hexdigest(),
                normalized_url=url,
                wire_target="/synthetic-reviewed-target",
                reserved_bytes=(50_000_000 if request_kind == "pdf" else 2_000_000),
            )
        )
        success = outcome == "success"
        self.ledger.append(
            DurableAttemptFinishedV2(
                schema_version="0.2.0",
                record_type="attempt_finished",
                record_id=f"{attempt_id}-finish",
                authorization_id=self.ledger.authorization_id,
                run_id=self.ledger.run_id,
                plan_id=self.ledger.plan_id,
                sequence=self.ledger.next_sequence,
                previous_record_sha256=self.ledger.ledger_head_sha256,
                recorded_at=NOW,
                attempt_id=attempt_id,
                attempt_ordinal=ordinal,
                outcome=outcome,
                status_code=200 if success else None,
                accepted_bytes=len(body or b"") if success else 0,
                body_sha256=hashlib.sha256(body or b"").hexdigest() if success else None,
                error_code=None if success else "synthetic_interruption",
                response_headers=(
                    SafeResponseHeaders(content_type_original="application/pdf")
                    if success
                    else None
                ),
            )
        )
        return attempt_id

    def fetch_landing_html(
        self, url: str, *, run_id: str, report_number: int
    ) -> LandingHtmlEvidence:
        del run_id
        assert self.current_report == report_number
        assert url == self.targets[report_number].landing_url
        self.calls.append(("landing", report_number))
        direct = self.targets[report_number].direct_download_url
        if self.missing_landing_report == report_number:
            body = b"<article><p>Sin enlace de descarga.</p></article>"
        elif self.ambiguous_landing_report == report_number:
            body = (
                f'<article><div><a href="{direct}">Descargar</a>'
                '<a href="https://www.defensoria.gob.pe/wp-content/uploads/'
                f'reporte-{report_number}-revisado.pdf">Otra descarga</a></div>'
                f"<h2>Reporte de Conflictos Sociales N. {report_number}</h2></article>"
            ).encode()
        else:
            body = (
                f"<article><h1>Reporte de Conflictos Sociales N.° {report_number}</h1>"
                f'<a href="{direct}">Descargar reporte</a></article>'
            ).encode()
        self.last_completed_attempt_id = self._durable_attempt(
            report_number=report_number,
            request_kind="landing_html",
            url=url,
            body=body,
        )
        return LandingHtmlEvidence(
            body=body,
            byte_count=len(body),
            sha256=hashlib.sha256(body).hexdigest(),
            final_url=url,
        )

    def fetch_pdf(self, url: str, *, run_id: str, report_number: int) -> DownloadedObject:
        del run_id
        assert self.current_report == report_number
        assert url == self.targets[report_number].direct_download_url
        self.calls.append(("pdf", report_number))
        if self.internal_cleanup_pending_report == report_number:
            raise TemporaryCleanupPending(report_number)
        if self.interrupt_pdf_report == report_number:
            self.last_completed_attempt_id = self._durable_attempt(
                report_number=report_number,
                request_kind="pdf",
                url=url,
                body=None,
                outcome="interrupted",
            )
            raise KeyboardInterrupt
        content = self.targets[report_number].protected_source_path.read_bytes()
        if self.collision_report == report_number:
            content += b"different"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        path = self.temp_root / f"report-{report_number}.pdf"
        path.write_bytes(content)
        self.last_completed_attempt_id = self._durable_attempt(
            report_number=report_number,
            request_kind="pdf",
            url=url,
            body=content,
        )
        downloaded = DownloadedObject(
            path=path,
            byte_count=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            final_url=url,
        )
        self.downloaded[report_number] = (downloaded, self.last_completed_attempt_id)
        return downloaded

    def cleanup_downloaded(
        self,
        downloaded: DownloadedObject,
        *,
        run_id: str,
        report_number: int,
        related_attempt_id: str,
    ) -> None:
        del run_id
        assert related_attempt_id.startswith("attempt-")
        assert downloaded.path.name == f"report-{report_number}.pdf"
        if self.cleanup_failures_remaining:
            self.cleanup_failures_remaining -= 1
            raise OSError("synthetic cleanup failure")
        downloaded.path.unlink()
        self.downloaded.pop(report_number, None)

    def recover_downloaded(self, report_number: int) -> tuple[DownloadedObject, str] | None:
        return self.downloaded.get(report_number)


def test_ten_equal_reports_complete_in_exact_order_without_duplicate_raw_files(
    tmp_path: Path,
) -> None:
    targets = _targets(tmp_path)
    client = FakeClient({target.report_number: target for target in targets}, tmp_path / "temp")
    with _store(tmp_path) as store:
        client.ledger = store
        result = CompareOnlyRunner(
            targets=targets,
            ledger=store,
            client=client,
            run_id="run-1",
            execution_tree_sha256=NONCE,
            execution_host_identity_sha256=HOST_SHA,
            utc_clock=lambda: NOW,
        ).run()

        assert result == "completed"
        assert client.calls == [
            item for report in range(260, 270) for item in (("landing", report), ("pdf", report))
        ]
        terminal = store.records[-1]
        assert isinstance(terminal, DurableRunTerminalV2)
        assert terminal.terminal_status == "completed"
        comparisons = [r for r in store.records if isinstance(r, DurableComparisonV2)]
        assert [record.report_number for record in comparisons] == list(range(260, 270))
        assert all(record.relationship == "identical_bytes" for record in comparisons)
        assert list((tmp_path / "temp").glob("*.pdf")) == []


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("drop_pre_network", "completed terminal"),
        ("wrong_observed_hash", "completed terminal"),
    ),
)
def test_completed_graph_requires_every_matching_source_rehash_phase(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    targets = _targets(tmp_path)
    client = FakeClient({target.report_number: target for target in targets}, tmp_path / "temp")
    with _store(tmp_path) as store:
        client.ledger = store
        result = CompareOnlyRunner(
            targets=targets,
            ledger=store,
            client=client,
            run_id="run-1",
            execution_tree_sha256=NONCE,
            execution_host_identity_sha256=HOST_SHA,
            utc_clock=lambda: NOW,
        ).run()
        assert result == "completed"
        records = list(store.records)

    if mutation == "drop_pre_network":
        records = [
            record
            for record in records
            if not (
                isinstance(record, DurableSourceRehashV2)
                and record.report_number == 260
                and record.phase == "pre_network"
            )
        ]
    else:
        index = next(
            position
            for position, record in enumerate(records)
            if isinstance(record, DurableSourceRehashV2)
            and record.report_number == 260
            and record.phase == "comparison_before"
        )
        records[index] = records[index].model_copy(update={"observed_sha256": "c" * 64})

    with pytest.raises(LedgerRecordConflict, match=message):
        validate_durable_ledger_graph(records)


def test_first_collision_stops_later_reports_and_removes_temporary_bytes(tmp_path: Path) -> None:
    targets = _targets(tmp_path)
    client = FakeClient(
        {target.report_number: target for target in targets},
        tmp_path / "temp",
        collision_report=262,
    )
    with _store(tmp_path) as store:
        client.ledger = store
        result = CompareOnlyRunner(
            targets=targets,
            ledger=store,
            client=client,
            run_id="run-1",
            execution_tree_sha256=NONCE,
            execution_host_identity_sha256=HOST_SHA,
            utc_clock=lambda: NOW,
        ).run()

        assert result == "stop_for_review"
        assert ("landing", 263) not in client.calls
        collision = next(
            record
            for record in store.records
            if isinstance(record, DurableComparisonV2) and record.report_number == 262
        )
        assert collision.relationship == "different_bytes_association_unresolved"
        assert collision.disposition == "stop_for_review"
        assert any(
            isinstance(record, DurableIssueV2) and record.classification == "AMBIGUITY"
            for record in store.records
        )
        assert list((tmp_path / "temp").glob("*.pdf")) == []


def test_cleanup_failure_leaves_active_run_then_restart_cleans_and_completes(
    tmp_path: Path,
) -> None:
    targets = _targets(tmp_path)
    client = FakeClient(
        {target.report_number: target for target in targets},
        tmp_path / "temp",
        cleanup_failures_remaining=1,
    )
    with _store(tmp_path) as store:
        client.ledger = store
        with pytest.raises(CleanupPending):
            CompareOnlyRunner(
                targets=targets,
                ledger=store,
                client=client,
                run_id="run-1",
                execution_tree_sha256=NONCE,
                execution_host_identity_sha256=HOST_SHA,
                utc_clock=lambda: NOW,
            ).run()
        assert not any(isinstance(record, DurableRunTerminalV2) for record in store.records)
        assert list((tmp_path / "temp").glob("*.pdf"))

    with _store(tmp_path) as resumed:
        client.ledger = resumed
        result = CompareOnlyRunner(
            targets=targets,
            ledger=resumed,
            client=client,
            run_id="run-1",
            execution_tree_sha256=NONCE,
            execution_host_identity_sha256=HOST_SHA,
            utc_clock=lambda: NOW,
        ).run()
        assert result == "completed"
        assert not list((tmp_path / "temp").glob("*.pdf"))


def test_engine_internal_cleanup_pending_cannot_terminalize_the_authorization(
    tmp_path: Path,
) -> None:
    targets = _targets(tmp_path)
    client = FakeClient(
        {target.report_number: target for target in targets},
        tmp_path / "temp",
        internal_cleanup_pending_report=260,
    )
    with _store(tmp_path) as store:
        client.ledger = store
        with pytest.raises(CleanupPending):
            CompareOnlyRunner(
                targets=targets,
                ledger=store,
                client=client,
                run_id="run-1",
                execution_tree_sha256=NONCE,
                execution_host_identity_sha256=HOST_SHA,
                utc_clock=lambda: NOW,
            ).run()

        assert not any(isinstance(record, DurableRunTerminalV2) for record in store.records)
        assert any(
            isinstance(record, DurableIssueV2)
            and record.classification == "INFRASTRUCTURE_FAILURE"
            and record.reason_code == "temporary_cleanup_pending"
            and record.report_number == 260
            for record in store.records
        )


def test_missing_landing_evidence_prevents_pdf_request_and_stops_for_review(
    tmp_path: Path,
) -> None:
    targets = _targets(tmp_path)
    client = FakeClient(
        {target.report_number: target for target in targets},
        tmp_path / "temp",
        missing_landing_report=260,
    )
    with _store(tmp_path) as store:
        client.ledger = store
        result = CompareOnlyRunner(
            targets=targets,
            ledger=store,
            client=client,
            run_id="run-1",
            execution_tree_sha256=NONCE,
            execution_host_identity_sha256=HOST_SHA,
            utc_clock=lambda: NOW,
        ).run()
        assert result == "stop_for_review"
        assert client.calls == [("landing", 260)]


def test_ambiguous_landing_evidence_prevents_pdf_request_and_stops_for_review(
    tmp_path: Path,
) -> None:
    targets = _targets(tmp_path)
    client = FakeClient(
        {target.report_number: target for target in targets},
        tmp_path / "temp",
        ambiguous_landing_report=260,
    )
    with _store(tmp_path) as store:
        client.ledger = store
        result = CompareOnlyRunner(
            targets=targets,
            ledger=store,
            client=client,
            run_id="run-1",
            execution_tree_sha256=NONCE,
            execution_host_identity_sha256=HOST_SHA,
            utc_clock=lambda: NOW,
        ).run()
        assert result == "stop_for_review"
        assert client.calls == [("landing", 260)]
        assert any(
            isinstance(record, DurableIssueV2)
            and record.classification == "AMBIGUITY"
            and record.reason_code == "competing_landing_pdf_candidate"
            for record in store.records
        )


def test_all_local_sources_are_verified_before_client_factory_or_manifest_write(
    tmp_path: Path,
) -> None:
    targets = list(_targets(tmp_path))
    targets[-1] = replace(targets[-1], expected_sha256="0" * 64)
    calls: list[str] = []

    with pytest.raises(LocalSourceMismatch):
        CompareOnlyRunner.preflight_then_open(
            targets=tuple(targets),
            store_factory=lambda: calls.append("store") or _store(tmp_path),
            client_factory=lambda store: (
                calls.append("client") or FakeClient({}, tmp_path, ledger=store)
            ),
            run_id="run-1",
            execution_tree_sha256=NONCE,
            execution_host_identity_sha256=HOST_SHA,
            utc_clock=lambda: NOW,
        )
    assert calls == []
    assert not (tmp_path / "data").exists()


def test_compare_runner_has_no_raw_publication_dependency() -> None:
    source = Path("src/peru_conflicts/acquisition/compare_runner.py").read_text(encoding="utf-8")
    assert "stage_copy_and_publish_no_replace" not in source
    assert "acquisition.storage" not in source


def test_same_run_resume_skips_completed_report_and_durable_landing(tmp_path: Path) -> None:
    targets = _targets(tmp_path)
    first = FakeClient(
        {target.report_number: target for target in targets},
        tmp_path / "temp",
        interrupt_pdf_report=261,
    )
    with _store(tmp_path) as store:
        first.ledger = store
        with pytest.raises(KeyboardInterrupt):
            CompareOnlyRunner(
                targets=targets,
                ledger=store,
                client=first,
                run_id="run-1",
                execution_tree_sha256=NONCE,
                execution_host_identity_sha256=HOST_SHA,
                utc_clock=lambda: NOW,
            ).run()
    assert first.calls == [("landing", 260), ("pdf", 260), ("landing", 261), ("pdf", 261)]

    resumed = FakeClient(
        {target.report_number: target for target in targets},
        tmp_path / "temp",
    )
    with _store(tmp_path) as store:
        resumed.ledger = store
        result = CompareOnlyRunner(
            targets=targets,
            ledger=store,
            client=resumed,
            run_id="run-1",
            execution_tree_sha256=NONCE,
            execution_host_identity_sha256=HOST_SHA,
            utc_clock=lambda: NOW,
        ).run()

    assert result == "completed"
    assert resumed.calls[0] == ("pdf", 261)
    assert ("landing", 260) not in resumed.calls
    assert ("pdf", 260) not in resumed.calls
    assert ("landing", 261) not in resumed.calls
