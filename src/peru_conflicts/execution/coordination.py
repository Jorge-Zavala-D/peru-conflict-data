"""Private coordinator execution contracts; never distribute these to annotators."""

from collections.abc import Mapping
from typing import Literal, Self

from pydantic import Field, model_validator

from peru_conflicts.benchmark.models import PartitionRole
from peru_conflicts.models.common import Sha256, StrictModel

from .packages import PackageManifest


class EligibilityAttestation(StrictModel):
    """Future private coordinator assertion, not proof of authorship or launch authority."""

    role: Literal["annotator-a", "annotator-b"]
    private_person_token: str = Field(min_length=1)
    distinct_human_confirmed: bool
    machine_answers_seen: bool
    parser_predictions_seen: bool
    machine_prefill_seen: bool
    other_submission_seen: bool
    partition_labels_received: bool


def verify_eligibility(a: EligibilityAttestation, b: EligibilityAttestation) -> None:
    if (a.role, b.role) != ("annotator-a", "annotator-b") or (
        a.private_person_token == b.private_person_token
    ):
        raise ValueError("A/B must represent distinct privately attested humans")
    for person in (a, b):
        if not person.distinct_human_confirmed or any(
            (
                person.machine_answers_seen,
                person.parser_predictions_seen,
                person.machine_prefill_seen,
                person.other_submission_seen,
                person.partition_labels_received,
            )
        ):
            raise ValueError("human is not eligible for blind annotation")


class SubmissionRoute(StrictModel):
    report_number: int = Field(ge=260, le=269)
    partition_role: PartitionRole
    sealed: bool
    development_visible: Literal[False] = False

    @model_validator(mode="after")
    def preserve_sealing(self) -> Self:
        if self.partition_role is PartitionRole.HELD_OUT_EVALUATION and not self.sealed:
            raise ValueError("held-out labels must remain coordinator-only sealed")
        return self


class CoordinatorContext(StrictModel):
    kind: Literal["COORDINATOR_ONLY_NOT_FOR_ANNOTATORS"] = "COORDINATOR_ONLY_NOT_FOR_ANNOTATORS"
    package_id: Sha256
    role: Literal["annotator-a", "annotator-b"]
    routes: tuple[SubmissionRoute, ...]
    submission_root: Literal["submissions/annotator-a", "submissions/annotator-b"]
    comparison_root: Literal["coordinator/comparisons"] = "coordinator/comparisons"
    annotation_launch_approved: Literal[False] = False


def build_context(
    package: PackageManifest, partitions: Mapping[int, PartitionRole]
) -> CoordinatorContext:
    if set(partitions) != {m.report_number for m in package.references}:
        raise ValueError("coordinator source assignment differs from neutral package")
    return CoordinatorContext(
        package_id=package.package_id,
        role=package.role,
        submission_root="submissions/annotator-a"
        if package.role == "annotator-a"
        else "submissions/annotator-b",
        routes=tuple(
            SubmissionRoute(
                report_number=number,
                partition_role=partition,
                sealed=partition is PartitionRole.HELD_OUT_EVALUATION,
            )
            for number, partition in sorted(partitions.items())
        ),
    )


def verify_context(context: CoordinatorContext, package: PackageManifest) -> None:
    expected = build_context(package, {r.report_number: r.partition_role for r in context.routes})
    if context != expected:
        raise ValueError("coordinator package/role/routing identity changed")
