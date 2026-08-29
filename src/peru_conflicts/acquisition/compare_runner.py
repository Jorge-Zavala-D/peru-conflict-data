"""Deterministic compare-only orchestration; no raw publication dependency."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Literal, Protocol, Self

from peru_conflicts.acquisition.engine import (
    AcquisitionEngineError,
    DownloadedObject,
    LandingHtmlEvidence,
    TemporaryCleanupPending,
)
from peru_conflicts.acquisition.fs_safety import DirectoryLease, DirectoryLeaseError
from peru_conflicts.acquisition.landing import (
    LandingAssociationAmbiguous,
    LandingAssociationMissing,
    verify_landing_association,
)
from peru_conflicts.acquisition.models_v2 import (
    DurableByteObjectV2,
    DurableCleanupV2,
    DurableComparisonV2,
    DurableIssueV2,
    DurableLandingAssociationV2,
    DurableRunOpenedV2,
    DurableRunTerminalV2,
    DurableSourceRehashV2,
)
from peru_conflicts.acquisition.persistent_ledger import ManifestLedgerStore
from peru_conflicts.acquisition.policy import AcquisitionPolicyError
from peru_conflicts.hashing import sha256_file

APPROVED_HOSTS = frozenset(("defensoria.gob.pe", "www.defensoria.gob.pe"))


class CompareRunnerError(RuntimeError):
    """The compare-only run cannot truthfully continue."""


class LocalSourceMismatch(CompareRunnerError):
    """A protected source differs from the reviewed byte baseline."""


class CleanupPending(CompareRunnerError):
    """Run-owned temporary bytes remain and must be reconciled before terminal state."""

    def __init__(self, report_number: int) -> None:
        super().__init__(f"temporary cleanup remains pending for report {report_number}")
        self.report_number = report_number


@dataclass(frozen=True, slots=True)
class CompareTarget:
    """One exact report/source/official-URL comparison target."""

    report_number: int
    landing_url: str
    direct_download_url: str
    protected_source_path: Path
    expected_byte_count: int
    expected_sha256: str
    association_status: Literal["visibly_associated", "unresolved_opaque_filename"]


SourceFingerprinter = Callable[[CompareTarget], tuple[int, str]]


@dataclass(frozen=True, slots=True)
class _BoundProtectedSource:
    target_path: Path
    parent: DirectoryLease
    child_name: str
    source: BinaryIO
    identity: tuple[int, int]


@dataclass(slots=True)
class BoundProtectedSources(AbstractContextManager["BoundProtectedSources"]):
    """Retain handle-relative bindings for every protected benchmark source."""

    data_root: Path
    _stack: ExitStack
    _sources: dict[int, _BoundProtectedSource]
    _closed: bool = False

    @classmethod
    def open(
        cls,
        *,
        data_root: Path,
        targets: Sequence[CompareTarget],
    ) -> Self:
        root_path = Path(os.path.abspath(data_root))
        stack = ExitStack()
        try:
            root = stack.enter_context(DirectoryLease.acquire(root_path))
            raw = stack.enter_context(root.acquire_child("01_raw"))
            reports = stack.enter_context(raw.acquire_child("reports"))
            years: dict[str, DirectoryLease] = {}
            sources: dict[int, _BoundProtectedSource] = {}
            for target in targets:
                target_path = Path(os.path.abspath(target.protected_source_path))
                try:
                    relative = target_path.relative_to(root_path)
                except ValueError as error:
                    raise LocalSourceMismatch(
                        "protected source path is outside the bound data root"
                    ) from error
                if (
                    len(relative.parts) != 4
                    or relative.parts[0:2] != ("01_raw", "reports")
                    or len(relative.parts[2]) != 4
                    or not relative.parts[2].isdigit()
                    or target.report_number in sources
                ):
                    raise LocalSourceMismatch(
                        "protected source path does not match the reviewed reports layout"
                    )
                year, child_name = relative.parts[2:4]
                parent = years.get(year)
                if parent is None:
                    parent = stack.enter_context(reports.acquire_child(year))
                    years[year] = parent
                source = stack.enter_context(parent.open_child_read(child_name))
                details = os.fstat(source.fileno())
                if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
                    raise LocalSourceMismatch("protected source is not an unaliased regular file")
                sources[target.report_number] = _BoundProtectedSource(
                    target_path=target_path,
                    parent=parent,
                    child_name=child_name,
                    source=source,
                    identity=(details.st_dev, details.st_ino),
                )
            root.require_bound()
            raw.require_bound()
            reports.require_bound()
            return cls(data_root=root_path, _stack=stack, _sources=sources)
        except (DirectoryLeaseError, OSError) as error:
            stack.close()
            raise LocalSourceMismatch("protected source parent binding failed") from error
        except BaseException:
            stack.close()
            raise

    def __enter__(self) -> Self:
        if self._closed:
            raise LocalSourceMismatch("protected source bindings are already closed")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stack.close()

    def fingerprint(self, target: CompareTarget) -> tuple[int, str]:
        """Hash one retained source and prove its path still names that object."""

        if self._closed:
            raise LocalSourceMismatch("protected source bindings are closed")
        bound = self._sources.get(target.report_number)
        if (
            bound is None
            or Path(os.path.abspath(target.protected_source_path)) != bound.target_path
        ):
            raise LocalSourceMismatch("protected source is outside the retained target set")
        try:
            bound.parent.require_bound()
            before = os.fstat(bound.source.fileno())
            named_before = bound.parent.child_lstat(bound.child_name)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or (before.st_dev, before.st_ino) != bound.identity
                or (named_before.st_dev, named_before.st_ino) != bound.identity
                or named_before.st_nlink != 1
            ):
                raise LocalSourceMismatch("protected source binding changed")
            bound.source.seek(0)
            digest = hashlib.sha256()
            while chunk := bound.source.read(1024 * 1024):
                digest.update(chunk)
            after = os.fstat(bound.source.fileno())
            named_after = bound.parent.child_lstat(bound.child_name)
            if (
                (after.st_dev, after.st_ino) != bound.identity
                or (named_after.st_dev, named_after.st_ino) != bound.identity
                or after.st_nlink != 1
                or named_after.st_nlink != 1
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
            ):
                raise LocalSourceMismatch("protected source changed while it was hashed")
            bound.parent.require_bound()
            return int(after.st_size), digest.hexdigest()
        except DirectoryLeaseError as error:
            raise LocalSourceMismatch("protected source parent binding changed") from error


class CompareFetchClient(Protocol):
    @property
    def last_completed_attempt_id(self) -> str | None: ...

    def set_report_context(self, report_number: int) -> None: ...

    def fetch_landing_html(
        self, url: str, *, run_id: str, report_number: int
    ) -> LandingHtmlEvidence: ...

    def fetch_pdf(self, url: str, *, run_id: str, report_number: int) -> DownloadedObject: ...

    def cleanup_downloaded(
        self,
        downloaded: DownloadedObject,
        *,
        run_id: str,
        report_number: int,
        related_attempt_id: str,
    ) -> None: ...

    def recover_downloaded(self, report_number: int) -> tuple[DownloadedObject, str] | None: ...


def _stable_source_fingerprint(path: Path) -> tuple[int, str]:
    logical = Path(os.path.abspath(path))
    if logical.is_symlink():
        raise LocalSourceMismatch("protected source cannot be a symlink or reparse point")
    try:
        before = logical.lstat()
    except OSError as error:
        raise LocalSourceMismatch("protected source is unavailable") from error
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if (
        not stat.S_ISREG(before.st_mode)
        or (reparse and getattr(before, "st_file_attributes", 0) & reparse)
        or before.st_nlink != 1
    ):
        raise LocalSourceMismatch("protected source is not an unaliased regular file")
    observed_sha = sha256_file(logical)
    after = logical.lstat()
    if (before.st_dev, before.st_ino, before.st_size) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
    ) or before.st_mtime_ns != after.st_mtime_ns:
        raise LocalSourceMismatch("protected source changed while it was hashed")
    return int(after.st_size), observed_sha


def _target_path_fingerprint(target: CompareTarget) -> tuple[int, str]:
    return _stable_source_fingerprint(target.protected_source_path)


def verify_all_local_sources(
    targets: Sequence[CompareTarget],
    *,
    source_fingerprinter: SourceFingerprinter | None = None,
) -> None:
    """Rehash all ten sources before any manifest or transport factory is called."""

    if tuple(target.report_number for target in targets) != tuple(range(260, 270)):
        raise LocalSourceMismatch("comparison targets must be exactly reports 260 through 269")
    fingerprint: SourceFingerprinter = source_fingerprinter or _target_path_fingerprint
    for target in targets:
        size, observed_sha = fingerprint(target)
        if size != target.expected_byte_count or observed_sha != target.expected_sha256:
            raise LocalSourceMismatch(
                f"protected source fingerprint mismatch for report {target.report_number}"
            )


class CompareOnlyRunner:
    """Run one bounded comparison through an already-open, authorization-bound ledger."""

    def __init__(
        self,
        *,
        targets: Sequence[CompareTarget],
        ledger: ManifestLedgerStore,
        client: CompareFetchClient,
        run_id: str,
        execution_tree_sha256: str,
        execution_host_identity_sha256: str,
        source_fingerprinter: SourceFingerprinter | None = None,
        utc_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if tuple(target.report_number for target in targets) != tuple(range(260, 270)):
            raise ValueError("runner target scope must be exactly reports 260 through 269")
        if run_id != ledger.run_id:
            raise ValueError("runner and durable ledger run IDs differ")
        self.targets = tuple(targets)
        self.ledger = ledger
        self.client = client
        self.run_id = run_id
        self.execution_tree_sha256 = execution_tree_sha256
        self.execution_host_identity_sha256 = execution_host_identity_sha256
        self.source_fingerprinter: SourceFingerprinter = (
            source_fingerprinter or _target_path_fingerprint
        )
        self.utc_clock = utc_clock

    @classmethod
    def preflight_then_open(
        cls,
        *,
        targets: Sequence[CompareTarget],
        store_factory: Callable[[], ManifestLedgerStore],
        client_factory: Callable[[ManifestLedgerStore], CompareFetchClient],
        run_id: str,
        execution_tree_sha256: str,
        execution_host_identity_sha256: str,
        source_fingerprinter: SourceFingerprinter | None = None,
        utc_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> str:
        """Prove all protected sources before creating storage or network-capable clients."""

        verify_all_local_sources(targets, source_fingerprinter=source_fingerprinter)
        with store_factory() as store:
            client = client_factory(store)
            return cls(
                targets=targets,
                ledger=store,
                client=client,
                run_id=run_id,
                execution_tree_sha256=execution_tree_sha256,
                execution_host_identity_sha256=execution_host_identity_sha256,
                source_fingerprinter=source_fingerprinter,
                utc_clock=utc_clock,
            ).run()

    def _has_record(self, record_id: str) -> bool:
        return any(
            getattr(record, "record_id", None) == record_id for record in self.ledger.records
        )

    def _report_record(self, record_type: str, report_number: int) -> object | None:
        matches = tuple(
            record
            for record in self.ledger.records
            if getattr(record, "record_type", None) == record_type
            and getattr(record, "report_number", None) == report_number
        )
        if len(matches) > 1:
            raise CompareRunnerError(
                f"durable state has multiple {record_type} records for one report"
            )
        return matches[0] if matches else None

    def _append_run_opened(self) -> None:
        existing = next(
            (
                record
                for record in self.ledger.records
                if getattr(record, "record_id", None) == "run-opened"
            ),
            None,
        )
        if isinstance(existing, DurableRunOpenedV2):
            if (
                existing.execution_tree_sha256 != self.execution_tree_sha256
                or existing.data_root_identity_sha256 != self.ledger.data_root_identity_sha256
                or existing.execution_host_identity_sha256 != self.execution_host_identity_sha256
            ):
                raise CompareRunnerError("run-opened execution identity differs")
            return
        self.ledger.append(
            DurableRunOpenedV2(
                schema_version="0.2.0",
                record_type="run_opened",
                record_id="run-opened",
                authorization_id=self.ledger.authorization_id,
                run_id=self.run_id,
                plan_id=self.ledger.plan_id,
                sequence=self.ledger.next_sequence,
                previous_record_sha256=self.ledger.ledger_head_sha256,
                recorded_at=self.utc_clock(),
                authorization_artifact_sha256=self.ledger.authorization_artifact_sha256,
                execution_tree_sha256=self.execution_tree_sha256,
                data_root_identity_sha256=self.ledger.data_root_identity_sha256,
                execution_host_identity_sha256=self.execution_host_identity_sha256,
            )
        )

    def _append_source_rehash(
        self,
        target: CompareTarget,
        *,
        phase: Literal["pre_network", "comparison_before", "comparison_after", "terminal"],
        observed_sha256: str,
    ) -> None:
        record_id = f"source-rehash-{phase}-{target.report_number}"
        if self._has_record(record_id):
            return
        self.ledger.append(
            DurableSourceRehashV2(
                schema_version="0.2.0",
                record_type="source_rehash",
                record_id=record_id,
                authorization_id=self.ledger.authorization_id,
                run_id=self.run_id,
                plan_id=self.ledger.plan_id,
                sequence=self.ledger.next_sequence,
                previous_record_sha256=self.ledger.ledger_head_sha256,
                recorded_at=self.utc_clock(),
                report_number=target.report_number,
                expected_sha256=target.expected_sha256,
                observed_sha256=observed_sha256,
                phase=phase,
            )
        )

    def _append_issue(
        self,
        *,
        report_number: int | None,
        classification: Literal[
            "PARSER_ERROR",
            "MISSING_EVIDENCE",
            "AMBIGUITY",
            "SOURCE_INCONSISTENCY",
            "POLICY_VIOLATION",
            "INFRASTRUCTURE_FAILURE",
        ],
        reason_code: str,
        evidence_sha256: str | None = None,
    ) -> None:
        suffix = "run" if report_number is None else str(report_number)
        record_id = f"issue-{classification.casefold()}-{reason_code}-{suffix}"
        if self._has_record(record_id):
            return
        self.ledger.append(
            DurableIssueV2(
                schema_version="0.2.0",
                record_type="issue",
                record_id=record_id,
                authorization_id=self.ledger.authorization_id,
                run_id=self.run_id,
                plan_id=self.ledger.plan_id,
                sequence=self.ledger.next_sequence,
                previous_record_sha256=self.ledger.ledger_head_sha256,
                recorded_at=self.utc_clock(),
                report_number=report_number,
                classification=classification,
                reason_code=reason_code,
                evidence_sha256=evidence_sha256,
            )
        )

    def _terminal(
        self,
        status: Literal["completed", "abandoned", "stop_for_review"],
        reason: str,
    ) -> str:
        self.ledger.append(
            DurableRunTerminalV2(
                schema_version="0.2.0",
                record_type="run_terminal",
                record_id="run-terminal",
                authorization_id=self.ledger.authorization_id,
                run_id=self.run_id,
                plan_id=self.ledger.plan_id,
                sequence=self.ledger.next_sequence,
                previous_record_sha256=self.ledger.ledger_head_sha256,
                recorded_at=self.utc_clock(),
                terminal_status=status,
                reason_code=reason,
            )
        )
        return status

    def _pre_network_hashes(self) -> None:
        for target in self.targets:
            size, observed = self.source_fingerprinter(target)
            if size != target.expected_byte_count or observed != target.expected_sha256:
                raise LocalSourceMismatch(
                    f"protected source mismatch before network for report {target.report_number}"
                )
            self._append_source_rehash(target, phase="pre_network", observed_sha256=observed)

    def _landing(self, target: CompareTarget) -> bool:
        landing = self.client.fetch_landing_html(
            target.landing_url,
            run_id=self.run_id,
            report_number=target.report_number,
        )
        try:
            evidence = verify_landing_association(
                landing.body,
                landing_url=target.landing_url,
                reviewed_direct_url=target.direct_download_url,
                approved_hosts=APPROVED_HOSTS,
                report_number=target.report_number,
                association_status=target.association_status,
            )
        except LandingAssociationMissing:
            self._append_issue(
                report_number=target.report_number,
                classification="MISSING_EVIDENCE",
                reason_code="reviewed_direct_link_absent",
                evidence_sha256=landing.sha256,
            )
            return False
        except LandingAssociationAmbiguous:
            self._append_issue(
                report_number=target.report_number,
                classification="AMBIGUITY",
                reason_code="competing_landing_pdf_candidate",
                evidence_sha256=landing.sha256,
            )
            return False
        attempt_id = self.client.last_completed_attempt_id
        if attempt_id is None:
            raise CompareRunnerError("landing evidence lacks a durable source attempt")
        self.ledger.append(
            DurableLandingAssociationV2(
                schema_version="0.2.0",
                record_type="landing_association",
                record_id=f"landing-association-{target.report_number}",
                authorization_id=self.ledger.authorization_id,
                run_id=self.run_id,
                plan_id=self.ledger.plan_id,
                sequence=self.ledger.next_sequence,
                previous_record_sha256=self.ledger.ledger_head_sha256,
                recorded_at=self.utc_clock(),
                report_number=target.report_number,
                landing_attempt_id=attempt_id,
                landing_body_sha256=evidence.landing_body_sha256,
                landing_body_bytes=evidence.landing_body_bytes,
                excerpt_sha256=evidence.excerpt_sha256,
                source_span_text=evidence.source_span_text,
                character_start=evidence.character_start,
                character_end=evidence.character_end,
                byte_start=evidence.byte_start,
                byte_end=evidence.byte_end,
                parser_version=evidence.parser_version,
                reviewed_href_original=evidence.reviewed_href_original,
                reviewed_url_normalized=evidence.reviewed_url_normalized,
                reviewed_wire_target=evidence.reviewed_wire_target,
                candidate_url_sha256s=evidence.candidate_url_sha256s,
                identity_association_status=target.association_status,
            )
        )
        return True

    def _append_cleanup(
        self,
        target: CompareTarget,
        *,
        attempt_id: str,
        downloaded: DownloadedObject | None,
    ) -> None:
        if self._report_record("cleanup", target.report_number) is not None:
            return
        cleanup_status: Literal["removed", "already_absent"] = "already_absent"
        if downloaded is not None:
            try:
                self.client.cleanup_downloaded(
                    downloaded,
                    run_id=self.run_id,
                    report_number=target.report_number,
                    related_attempt_id=attempt_id,
                )
            except BaseException as error:
                raise CleanupPending(target.report_number) from error
            if downloaded.path.exists():
                raise CleanupPending(target.report_number)
            cleanup_status = "removed"
        self.ledger.append(
            DurableCleanupV2(
                schema_version="0.2.0",
                record_type="cleanup",
                record_id=f"cleanup-{target.report_number}",
                authorization_id=self.ledger.authorization_id,
                run_id=self.run_id,
                plan_id=self.ledger.plan_id,
                sequence=self.ledger.next_sequence,
                previous_record_sha256=self.ledger.ledger_head_sha256,
                recorded_at=self.utc_clock(),
                report_number=target.report_number,
                attempt_id=attempt_id,
                cleanup_status=cleanup_status,
            )
        )

    def _compare_observation(
        self,
        target: CompareTarget,
        *,
        attempt_id: str,
        observed_sha256: str,
        observed_bytes: int,
    ) -> Literal["identical", "different", "failed"]:
        result: Literal["identical", "different", "failed"] = "failed"
        before_size, before_sha = self.source_fingerprinter(target)
        self._append_source_rehash(
            target,
            phase="comparison_before",
            observed_sha256=before_sha,
        )
        after_size, after_sha = self.source_fingerprinter(target)
        self._append_source_rehash(
            target,
            phase="comparison_after",
            observed_sha256=after_sha,
        )
        if (
            before_size != target.expected_byte_count
            or after_size != target.expected_byte_count
            or before_sha != target.expected_sha256
            or after_sha != target.expected_sha256
        ):
            self._append_issue(
                report_number=target.report_number,
                classification="POLICY_VIOLATION",
                reason_code="protected_source_changed_during_comparison",
            )
            return "failed"
        identical = observed_sha256 == target.expected_sha256
        self.ledger.append(
            DurableComparisonV2(
                schema_version="0.2.0",
                record_type="comparison",
                record_id=f"comparison-{target.report_number}",
                authorization_id=self.ledger.authorization_id,
                run_id=self.run_id,
                plan_id=self.ledger.plan_id,
                sequence=self.ledger.next_sequence,
                previous_record_sha256=self.ledger.ledger_head_sha256,
                recorded_at=self.utc_clock(),
                report_number=target.report_number,
                source_attempt_id=attempt_id,
                observed_sha256=observed_sha256,
                observed_bytes=observed_bytes,
                expected_source_sha256=target.expected_sha256,
                source_sha256_before=before_sha,
                source_sha256_after=after_sha,
                relationship=(
                    "identical_bytes" if identical else "different_bytes_association_unresolved"
                ),
                disposition=("identical_no_duplicate" if identical else "stop_for_review"),
            )
        )
        result = "identical" if identical else "different"
        return result

    def _compare_pdf(self, target: CompareTarget) -> Literal["identical", "different", "failed"]:
        prior_byte = self._report_record("byte_object", target.report_number)
        recovered = self.client.recover_downloaded(target.report_number)
        downloaded: DownloadedObject | None
        if isinstance(prior_byte, DurableByteObjectV2):
            attempt_id = prior_byte.source_attempt_id
            downloaded = recovered[0] if recovered is not None else None
            if recovered is not None and recovered[1] != attempt_id:
                raise CompareRunnerError("recovered object and durable byte object disagree")
            observed_sha256 = prior_byte.observed_sha256
            observed_bytes = prior_byte.observed_bytes
        else:
            if recovered is None:
                downloaded = self.client.fetch_pdf(
                    target.direct_download_url,
                    run_id=self.run_id,
                    report_number=target.report_number,
                )
                attempt_id = self.client.last_completed_attempt_id
                if attempt_id is None:
                    raise CompareRunnerError("PDF object lacks a durable source attempt")
            else:
                downloaded, attempt_id = recovered
            observed_sha256 = downloaded.sha256
            observed_bytes = downloaded.byte_count
            self.ledger.append(
                DurableByteObjectV2(
                    schema_version="0.2.0",
                    record_type="byte_object",
                    record_id=f"byte-object-{target.report_number}-{observed_sha256}",
                    authorization_id=self.ledger.authorization_id,
                    run_id=self.run_id,
                    plan_id=self.ledger.plan_id,
                    sequence=self.ledger.next_sequence,
                    previous_record_sha256=self.ledger.ledger_head_sha256,
                    recorded_at=self.utc_clock(),
                    report_number=target.report_number,
                    source_attempt_id=attempt_id,
                    observed_sha256=observed_sha256,
                    observed_bytes=observed_bytes,
                )
            )
        try:
            return self._compare_observation(
                target,
                attempt_id=attempt_id,
                observed_sha256=observed_sha256,
                observed_bytes=observed_bytes,
            )
        finally:
            self._append_cleanup(
                target,
                attempt_id=attempt_id,
                downloaded=downloaded,
            )

    def run(self) -> str:
        """Execute exact ordered comparison and derive terminal truth from records."""

        verify_all_local_sources(
            self.targets,
            source_fingerprinter=self.source_fingerprinter,
        )
        self._append_run_opened()
        self._pre_network_hashes()
        try:
            for target in self.targets:
                self.client.set_report_context(target.report_number)
                prior_comparison = self._report_record("comparison", target.report_number)
                if isinstance(prior_comparison, DurableComparisonV2):
                    prior_cleanup = self._report_record("cleanup", target.report_number)
                    if prior_cleanup is None:
                        recovered = self.client.recover_downloaded(target.report_number)
                        self._append_cleanup(
                            target,
                            attempt_id=prior_comparison.source_attempt_id,
                            downloaded=recovered[0] if recovered is not None else None,
                        )
                    if prior_comparison.relationship != "identical_bytes":
                        self._append_issue(
                            report_number=target.report_number,
                            classification="AMBIGUITY",
                            reason_code="remote_bytes_differ_association_unresolved",
                        )
                        return self._terminal("stop_for_review", "remote_bytes_differ")
                    continue
                prior_landing = self._report_record("landing_association", target.report_number)
                if prior_landing is None and not self._landing(target):
                    return self._terminal("stop_for_review", "landing_evidence_not_unique")
                comparison = self._compare_pdf(target)
                if comparison == "different":
                    self._append_issue(
                        report_number=target.report_number,
                        classification="AMBIGUITY",
                        reason_code="remote_bytes_differ_association_unresolved",
                    )
                    return self._terminal("stop_for_review", "remote_bytes_differ")
                if comparison == "failed":
                    return self._terminal("abandoned", "protected_source_changed")
            for target in self.targets:
                size, observed = self.source_fingerprinter(target)
                if size != target.expected_byte_count or observed != target.expected_sha256:
                    raise LocalSourceMismatch("terminal protected-source rehash differs")
                self._append_source_rehash(target, phase="terminal", observed_sha256=observed)
            comparisons = tuple(
                record for record in self.ledger.records if isinstance(record, DurableComparisonV2)
            )
            cleanups = tuple(
                record
                for record in self.ledger.records
                if getattr(record, "record_type", None) == "cleanup"
            )
            if (
                tuple(record.report_number for record in comparisons) != tuple(range(260, 270))
                or any(record.relationship != "identical_bytes" for record in comparisons)
                or len(cleanups) != 10
            ):
                raise CompareRunnerError("durable graph is incomplete; completion is forbidden")
            return self._terminal("completed", "all_ten_remote_bytes_identical")
        except (LandingAssociationMissing, LandingAssociationAmbiguous):
            raise
        except LocalSourceMismatch:
            self._append_issue(
                report_number=None,
                classification="POLICY_VIOLATION",
                reason_code="protected_source_mismatch",
            )
            return self._terminal("abandoned", "protected_source_mismatch")
        except CleanupPending as error:
            self._append_issue(
                report_number=error.report_number,
                classification="INFRASTRUCTURE_FAILURE",
                reason_code="temporary_cleanup_pending",
            )
            raise
        except TemporaryCleanupPending as error:
            self._append_issue(
                report_number=error.report_number,
                classification="INFRASTRUCTURE_FAILURE",
                reason_code="temporary_cleanup_pending",
            )
            raise CleanupPending(error.report_number) from error
        except CompareRunnerError:
            self._append_issue(
                report_number=None,
                classification="INFRASTRUCTURE_FAILURE",
                reason_code="compare_runner_failure",
            )
            return self._terminal("abandoned", "compare_runner_failure")
        except (AcquisitionEngineError, AcquisitionPolicyError):
            self._append_issue(
                report_number=None,
                classification="POLICY_VIOLATION",
                reason_code="bounded_acquisition_failure",
            )
            return self._terminal("abandoned", "bounded_acquisition_failure")
