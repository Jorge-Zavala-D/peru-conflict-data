"""Durable attempt claims precede every synthetic transport call."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from peru_conflicts.acquisition.attempt_transport import DurableAttemptTransport
from peru_conflicts.acquisition.authorization import compute_data_root_identity_sha256
from peru_conflicts.acquisition.models_v2 import (
    DurableAttemptFinishedV2,
    DurableAttemptStartedV2,
    DurableRunOpenedV2,
    StorageNamespaceMarkerV2,
)
from peru_conflicts.acquisition.persistent_ledger import ManifestLedgerStore
from peru_conflicts.acquisition.policy import SealedTransportPolicyError

HOSTS = frozenset(("defensoria.gob.pe", "www.defensoria.gob.pe"))
SHA = "a" * 64
HOST_SHA = "b" * 64
NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
LANDING = "https://www.defensoria.gob.pe/documentos/reporte-260/"
PDF = "https://www.defensoria.gob.pe/wp-content/uploads/reporte-260.pdf"


@dataclass
class Response:
    status_code: int
    headers: Mapping[str, str]
    chunks: list[bytes]
    closed: bool = False

    def iter_bytes(self) -> Iterable[bytes]:
        while self.chunks:
            yield self.chunks.pop(0)

    def close(self) -> None:
        self.closed = True


class Transport:
    follows_redirects = False

    def __init__(self, store: ManifestLedgerStore, response: Response) -> None:
        self.store = store
        self.response = response
        self.calls = 0

    def request(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: int,
    ) -> Response:
        del url, headers, timeout_seconds
        self.calls += 1
        assert isinstance(self.store.records[-1], DurableAttemptStartedV2)
        return self.response


def _store(tmp_path: Path) -> ManifestLedgerStore:
    root = tmp_path / "data"
    (root / "01_raw" / "manifests").mkdir(parents=True)
    identity = compute_data_root_identity_sha256(
        root,
        marker_nonce_sha256=SHA,
        execution_host_identity_sha256=HOST_SHA,
    )
    store = ManifestLedgerStore.open(
        data_root=root,
        marker=StorageNamespaceMarkerV2(
            schema_version="0.2.0",
            namespace_id="namespace-1",
            owner_nonce_sha256=SHA,
        ),
        expected_data_root_identity_sha256=identity,
        execution_host_identity_sha256=HOST_SHA,
        expected_execution_tree_sha256=SHA,
        expected_authorization_artifact_sha256=SHA,
        authorization_id="authorization-1",
        run_id="run-1",
        plan_id="plan-1",
        recorded_at=NOW,
    )
    store.append(
        DurableRunOpenedV2(
            schema_version="0.2.0",
            record_type="run_opened",
            record_id="run-opened",
            authorization_id="authorization-1",
            run_id="run-1",
            plan_id="plan-1",
            sequence=store.next_sequence,
            previous_record_sha256=store.ledger_head_sha256,
            recorded_at=NOW,
            authorization_artifact_sha256=SHA,
            execution_tree_sha256=SHA,
            data_root_identity_sha256=store.data_root_identity_sha256,
            execution_host_identity_sha256=HOST_SHA,
        )
    )
    return store


def test_attempt_start_is_fsynced_before_transport_and_finish_requires_engine_acceptance(
    tmp_path: Path,
) -> None:
    with _store(tmp_path) as store:
        response = Response(
            status_code=200,
            headers={"Content-Type": "text/html"},
            chunks=[b"<html>", b"</html>"],
        )
        underlying = Transport(store, response)
        transport = DurableAttemptTransport(
            transport=underlying,
            ledger=store,
            approved_hosts=HOSTS,
            reviewed_landing_urls={260: LANDING},
            reviewed_pdf_urls={260: PDF},
            utc_clock=lambda: NOW,
        )
        transport.set_report_context(260)
        wrapped = transport.request(
            LANDING,
            headers={"Accept": "text/html, application/xhtml+xml"},
            timeout_seconds=30,
        )
        assert underlying.calls == 1
        assert isinstance(store.records[-1], DurableAttemptStartedV2)
        assert b"".join(wrapped.iter_bytes()) == b"<html></html>"
        assert isinstance(store.records[-1], DurableAttemptStartedV2)
        wrapped.mark_accepted()
        assert isinstance(store.records[-1], DurableAttemptFinishedV2)
        assert store.records[-1].accepted_bytes == 13
        assert store.records[-1].response_headers is not None
        assert store.records[-1].response_headers.content_type_original == "text/html"
        wrapped.close()
        assert response.closed is True


def test_transport_exception_leaves_a_finished_failure_and_consumes_attempt(
    tmp_path: Path,
) -> None:
    class Failing:
        follows_redirects = False

        def request(self, *args: object, **kwargs: object) -> Response:
            del args, kwargs
            raise OSError("secret-bearing operating-system detail")

    with _store(tmp_path) as store:
        transport = DurableAttemptTransport(
            transport=Failing(),
            ledger=store,
            approved_hosts=HOSTS,
            reviewed_landing_urls={260: LANDING},
            reviewed_pdf_urls={260: PDF},
            utc_clock=lambda: NOW,
        )
        transport.set_report_context(260)
        with pytest.raises(OSError):
            transport.request(LANDING, headers={"Accept": "text/html"}, timeout_seconds=30)
        assert store.consumed_attempts == 1
        assert isinstance(store.records[-1], DurableAttemptFinishedV2)
        assert store.records[-1].error_code == "transport_OSError"


def test_unconsumed_response_close_records_rejection_without_body_hash(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        response = Response(status_code=302, headers={"Location": PDF}, chunks=[])
        underlying = Transport(store, response)
        transport = DurableAttemptTransport(
            transport=underlying,
            ledger=store,
            approved_hosts=HOSTS,
            reviewed_landing_urls={260: LANDING},
            reviewed_pdf_urls={260: PDF},
            utc_clock=lambda: NOW,
        )
        transport.set_report_context(260)
        wrapped = transport.request(LANDING, headers={"Accept": "text/html"}, timeout_seconds=30)
        wrapped.close()
        finished = store.records[-1]
        assert isinstance(finished, DurableAttemptFinishedV2)
        assert finished.outcome == "redirect"
        assert finished.body_sha256 is None


def test_fully_consumed_but_unaccepted_body_is_not_durable_success(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        response = Response(
            status_code=200,
            headers={"Content-Type": "text/html", "Content-Length": "99"},
            chunks=[b"short"],
        )
        transport = DurableAttemptTransport(
            transport=Transport(store, response),
            ledger=store,
            approved_hosts=HOSTS,
            reviewed_landing_urls={260: LANDING},
            reviewed_pdf_urls={260: PDF},
            utc_clock=lambda: NOW,
        )
        transport.set_report_context(260)
        wrapped = transport.request(LANDING, headers={"Accept": "text/html"}, timeout_seconds=30)
        assert b"".join(wrapped.iter_bytes()) == b"short"
        wrapped.close()
        finished = store.records[-1]
        assert isinstance(finished, DurableAttemptFinishedV2)
        assert finished.outcome == "rejected"
        assert finished.error_code == "body_not_accepted"
        assert finished.body_sha256 is None


def test_engine_cannot_accept_body_before_stream_reaches_eof(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        response = Response(
            status_code=200,
            headers={"Content-Type": "text/html"},
            chunks=[b"body"],
        )
        transport = DurableAttemptTransport(
            transport=Transport(store, response),
            ledger=store,
            approved_hosts=HOSTS,
            reviewed_landing_urls={260: LANDING},
            reviewed_pdf_urls={260: PDF},
            utc_clock=lambda: NOW,
        )
        transport.set_report_context(260)
        wrapped = transport.request(LANDING, headers={"Accept": "text/html"}, timeout_seconds=30)
        with pytest.raises(SealedTransportPolicyError, match="fully consumed"):
            wrapped.mark_accepted()
        wrapped.close()


def test_path_changing_redirect_request_is_rejected_before_attempt_or_transport(
    tmp_path: Path,
) -> None:
    with _store(tmp_path) as store:
        response = Response(status_code=200, headers={}, chunks=[])
        underlying = Transport(store, response)
        transport = DurableAttemptTransport(
            transport=underlying,
            ledger=store,
            approved_hosts=HOSTS,
            reviewed_landing_urls={260: LANDING},
            reviewed_pdf_urls={260: PDF},
            utc_clock=lambda: NOW,
        )
        transport.set_report_context(260)
        before = store.consumed_attempts
        with pytest.raises(SealedTransportPolicyError):
            transport.request(
                "https://www.defensoria.gob.pe/documentos/different/",
                headers={"Accept": "text/html"},
                timeout_seconds=30,
            )
        assert store.consumed_attempts == before
        assert underlying.calls == 0


def test_redirect_attempt_is_explicitly_linked_to_the_following_request(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        underlying = Transport(
            store,
            Response(
                status_code=302,
                headers={"Location": "https://defensoria.gob.pe/documentos/reporte-260/"},
                chunks=[],
            ),
        )
        transport = DurableAttemptTransport(
            transport=underlying,
            ledger=store,
            approved_hosts=HOSTS,
            reviewed_landing_urls={260: LANDING},
            reviewed_pdf_urls={260: PDF},
            utc_clock=lambda: NOW,
        )
        transport.set_report_context(260)
        redirected = transport.request(
            LANDING,
            headers={"Accept": "text/html"},
            timeout_seconds=30,
        )
        redirected.close()

        underlying.response = Response(
            status_code=200,
            headers={"Content-Type": "text/html"},
            chunks=[b"ok"],
        )
        followed = transport.request(
            "https://defensoria.gob.pe/documentos/reporte-260/",
            headers={"Accept": "text/html"},
            timeout_seconds=30,
        )
        start = store.records[-1]
        assert isinstance(start, DurableAttemptStartedV2)
        assert start.continued_from_attempt_id == "attempt-0001"
        assert start.continuation_reason == "redirect"
        assert b"".join(followed.iter_bytes()) == b"ok"
        followed.mark_accepted()


def test_pdf_attempt_reserves_full_ceiling_until_finished(tmp_path: Path) -> None:
    pdf_bytes = b"%PDF-" + b"x" * 1_020
    with _store(tmp_path) as store:
        response = Response(
            status_code=200,
            headers={"Content-Type": "application/pdf"},
            chunks=[pdf_bytes],
        )
        underlying = Transport(store, response)
        transport = DurableAttemptTransport(
            transport=underlying,
            ledger=store,
            approved_hosts=HOSTS,
            reviewed_landing_urls={260: LANDING},
            reviewed_pdf_urls={260: PDF},
            utc_clock=lambda: NOW,
        )
        transport.set_report_context(260)
        wrapped = transport.request(PDF, headers={"Accept": "application/pdf"}, timeout_seconds=30)
        assert store.reserved_bytes == 50_000_000
        assert hashlib.sha256(b"".join(wrapped.iter_bytes())).digest()
        wrapped.mark_accepted()
        assert store.reserved_bytes == len(pdf_bytes)
