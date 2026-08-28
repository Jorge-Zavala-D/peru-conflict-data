from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from peru_conflicts.discovery.receipts import (
    CorpusCompletenessStatus,
    LandingTraversalCounts,
    RateLimitHeader,
    ReconnaissanceSummary,
    RequestAttemptReceipt,
    RequestKind,
    RequestOutcome,
    SelectedHttpHeaders,
    StopClass,
    SurfaceStopReason,
    SurfaceTraversalReceipt,
)

STARTED_AT = datetime(2026, 8, 27, 18, 0, 0, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 8, 27, 18, 0, 1, tzinfo=UTC)
URL = "https://www.defensoria.gob.pe/?s=Reporte+Mensual+de+Conflictos+Sociales"
BODY = b"<html><body>fuente oficial</body></html>"


def _successful_receipt() -> RequestAttemptReceipt:
    return RequestAttemptReceipt(
        schema_version="0.3.0",
        receipt_id="request-attempt-1",
        observation_id="observation-1",
        request_kind=RequestKind.HTML,
        attempt_number=1,
        redirect_index=0,
        requested_url=URL,
        requested_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        outcome=RequestOutcome.SUCCESS,
        status_code=200,
        response_url=URL,
        selected_headers=SelectedHttpHeaders(
            content_type_original="text/html; charset=UTF-8",
            content_length_original=str(len(BODY)),
            etag_original='"source-version"',
            last_modified_original="Thu, 27 Aug 2026 17:59:00 GMT",
            retry_after_original=None,
            rate_limit_headers=(RateLimitHeader(name="X-RateLimit-Remaining", value="42"),),
        ),
        body_read=True,
        body_byte_count=len(BODY),
        body_sha256=hashlib.sha256(BODY).hexdigest(),
    )


def test_request_attempt_preserves_selected_headers_body_bytes_and_hash() -> None:
    receipt = _successful_receipt()

    assert receipt.schema_version == "0.3.0"
    assert receipt.requested_at == STARTED_AT
    assert receipt.completed_at == COMPLETED_AT
    assert receipt.selected_headers.content_type_original == "text/html; charset=UTF-8"
    assert receipt.selected_headers.rate_limit_headers[0].name == "X-RateLimit-Remaining"
    assert receipt.body_byte_count == len(BODY)
    assert receipt.body_sha256 == hashlib.sha256(BODY).hexdigest()


def test_only_recognized_rate_limit_headers_can_be_retained() -> None:
    with pytest.raises(ValidationError, match="rate-limit"):
        RateLimitHeader(name="Set-Cookie", value="session=secret")


@pytest.mark.parametrize(
    "update",
    [
        {"body_read": False},
        {"body_byte_count": None},
        {"body_sha256": None},
    ],
)
def test_body_hash_count_and_read_flag_must_close_together(update: dict[str, object]) -> None:
    payload = _successful_receipt().model_dump()
    payload.update(update)

    with pytest.raises(ValidationError, match="body"):
        RequestAttemptReceipt.model_validate(payload)


def test_unlisted_content_type_cannot_claim_a_read_body() -> None:
    payload = _successful_receipt().model_dump()
    payload["selected_headers"] = {
        **_successful_receipt().selected_headers.model_dump(),
        "content_type_original": "application/x-unlisted-binary",
    }

    with pytest.raises(ValidationError, match="content type"):
        RequestAttemptReceipt.model_validate(payload)


def test_transport_error_requires_error_evidence_and_no_http_or_body_claim() -> None:
    with pytest.raises(ValidationError, match="transport error"):
        RequestAttemptReceipt(
            schema_version="0.3.0",
            receipt_id="request-attempt-failed",
            observation_id="observation-1",
            request_kind=RequestKind.HTML,
            attempt_number=1,
            redirect_index=0,
            requested_url=URL,
            requested_at=STARTED_AT,
            completed_at=COMPLETED_AT,
            outcome=RequestOutcome.TRANSPORT_ERROR,
            status_code=503,
            response_url=None,
            selected_headers=SelectedHttpHeaders(),
            body_read=False,
            body_byte_count=None,
            body_sha256=None,
            error_type=None,
        )


def test_completion_timestamp_cannot_precede_request_timestamp() -> None:
    payload = _successful_receipt().model_dump()
    payload["completed_at"] = datetime(2026, 8, 27, 17, 59, 59, tzinfo=UTC)

    with pytest.raises(ValidationError, match="completed_at"):
        RequestAttemptReceipt.model_validate(payload)


def test_reconnaissance_summary_never_claims_corpus_completeness() -> None:
    traversal = SurfaceTraversalReceipt(
        start_url=URL,
        pages_visited=9,
        seen_urls=(URL,),
        stop_reason=SurfaceStopReason.NO_NEXT_LINK,
        stop_class=StopClass.LOCAL_TERMINAL,
        reached_local_terminal=True,
        pagination_contract_verified=True,
        pagination_exhausted=True,
    )
    summary = ReconnaissanceSummary(
        schema_version="0.3.0",
        run_id="m1-02-1-test-run",
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        start_urls=(URL,),
        pages_visited=9,
        records_written=34,
        request_attempt_count=10,
        surface_traversals=(traversal,),
        errors=(),
        landing_pages=LandingTraversalCounts(
            discovered=10,
            selected=0,
            fetched=0,
            failed=0,
            skipped=10,
            cap_reached=True,
        ),
        all_surfaces_reached_local_terminal=True,
        corpus_completeness_status=CorpusCompletenessStatus.NOT_ASSESSED,
        boundary="HTML/robots only; no PDF or binary body retrieval; no raw writes",
    )

    dumped = summary.model_dump(mode="json")
    assert dumped["corpus_completeness_status"] == "not_assessed"
    assert "complete" not in dumped
    assert dumped["surface_traversals"][0]["pagination_exhausted"] is True


def test_repeated_url_is_never_a_local_terminal_or_pagination_exhaustion() -> None:
    with pytest.raises(ValidationError, match="repeated URL"):
        SurfaceTraversalReceipt(
            start_url=URL,
            pages_visited=2,
            seen_urls=(URL,),
            stop_reason=SurfaceStopReason.REPEATED_URL,
            stop_class=StopClass.SAFETY_STOP,
            reached_local_terminal=True,
            pagination_contract_verified=True,
            pagination_exhausted=True,
        )


@pytest.mark.parametrize(
    ("outcome", "status", "body_read", "body_complete", "message"),
    [
        (RequestOutcome.SUCCESS, 404, True, True, "success outcome requires"),
        (RequestOutcome.REDIRECT, 200, False, False, "redirect outcome requires"),
        (RequestOutcome.TRANSIENT_HTTP, 404, False, False, "transient outcome requires"),
        (RequestOutcome.HTTP_ERROR, 200, False, False, "HTTP-error outcome requires"),
        (
            RequestOutcome.REJECTED_CONTENT_TYPE,
            404,
            False,
            False,
            "content-type rejection requires",
        ),
        (
            RequestOutcome.REJECTED_BODY_SIGNATURE,
            200,
            False,
            False,
            "signature rejection requires",
        ),
        (
            RequestOutcome.REJECTED_REDIRECT,
            200,
            False,
            False,
            "rejected redirect requires",
        ),
    ],
)
def test_request_outcome_status_and_body_matrix_is_fail_closed(
    outcome: RequestOutcome,
    status: int,
    body_read: bool,
    body_complete: bool,
    message: str,
) -> None:
    payload = _successful_receipt().model_dump()
    payload.update(
        {
            "outcome": outcome,
            "status_code": status,
            "body_read": body_read,
            "body_complete": body_complete,
            "body_byte_count": len(BODY) if body_read else None,
            "body_sha256": hashlib.sha256(BODY).hexdigest() if body_read else None,
        }
    )

    with pytest.raises(ValidationError, match=message):
        RequestAttemptReceipt.model_validate(payload)


def test_redirect_receipt_requires_location_and_preserves_normalized_target() -> None:
    payload = _successful_receipt().model_dump()
    payload.update(
        {
            "outcome": RequestOutcome.REDIRECT,
            "status_code": 302,
            "body_read": False,
            "body_complete": False,
            "body_byte_count": None,
            "body_sha256": None,
            "redirect_target_url": "https://www.defensoria.gob.pe/page/2/",
            "selected_headers": {
                **_successful_receipt().selected_headers.model_dump(),
                "location_original": "/page/2/",
            },
        }
    )
    receipt = RequestAttemptReceipt.model_validate(payload)
    assert receipt.redirect_target_url == "https://www.defensoria.gob.pe/page/2/"

    payload["selected_headers"]["location_original"] = None
    with pytest.raises(ValidationError, match="Location"):
        RequestAttemptReceipt.model_validate(payload)
