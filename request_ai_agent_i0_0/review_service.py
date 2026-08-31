"""Persist manager review decisions and analyst assignment workflow."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .db_models import (
    Assignment,
    Request as RequestModel,
    RequestRevision,
    ReviewAction,
    User,
    WorkflowEvent,
)


class ReviewWorkflowError(ValueError):
    """Base error for a manager review workflow rejected before commit."""


class ReviewRequestNotFoundError(ReviewWorkflowError):
    """Raised when the reviewed request does not exist."""


class ReviewPermissionError(ReviewWorkflowError):
    """Raised when the acting reviewer is not a manager."""


class InvalidReviewStateError(ReviewWorkflowError):
    """Raised when the request is not currently reviewable."""


class ReviewCommentRequiredError(ReviewWorkflowError):
    """Raised when a revision request has no manager comment."""


class AnalystNotFoundError(ReviewWorkflowError):
    """Raised when the selected analyst user does not exist."""


class InvalidAnalystRoleError(ReviewWorkflowError):
    """Raised when the selected user is not an analyst."""


def _clean_text(value: Any) -> str:
    return str("" if value is None else value).replace("\x00", "").strip()


def _reviewer(db: Session, reviewer_user_id: int) -> User:
    reviewer = db.get(User, reviewer_user_id)
    if reviewer is None or reviewer.role != "MANAGER":
        raise ReviewPermissionError("reviewer must have MANAGER role")
    return reviewer


def _locked_request_and_revision(
    db: Session,
    request_no: str,
) -> tuple[RequestModel, RequestRevision]:
    normalized_request_no = _clean_text(request_no)
    if not normalized_request_no:
        raise ValueError("request_no is required")

    request_row = db.scalar(
        select(RequestModel)
        .where(RequestModel.request_no == normalized_request_no)
        .with_for_update()
    )
    if request_row is None:
        raise ReviewRequestNotFoundError(
            f"request not found: {normalized_request_no}"
        )

    if request_row.current_status != "UNDER_REVIEW":
        raise InvalidReviewStateError(
            "request status must be UNDER_REVIEW"
        )

    revision_row = db.scalar(
        select(RequestRevision).where(
            RequestRevision.request_id == request_row.id,
            RequestRevision.revision_no == request_row.current_revision_no,
        )
    )
    if revision_row is None:
        raise InvalidReviewStateError(
            "current request revision does not exist"
        )

    return request_row, revision_row


def create_revision_request(
    db: Session,
    *,
    request_no: str,
    reviewer_user_id: int,
    comment: str,
) -> dict[str, Any]:
    reviewer = _reviewer(db, reviewer_user_id)
    review_comment = _clean_text(comment)
    if not review_comment:
        raise ReviewCommentRequiredError(
            "revision request comment is required"
        )

    request_row, revision_row = _locked_request_and_revision(
        db,
        request_no,
    )
    previous_status = request_row.current_status

    review_action = ReviewAction(
        request_id=request_row.id,
        revision_id=revision_row.id,
        reviewer_user_id=reviewer.id,
        action_type="REQUEST_REVISION",
        comment=review_comment,
    )
    db.add(review_action)

    request_row.current_status = "REVISION_REQUESTED"

    event_row = WorkflowEvent(
        request_id=request_row.id,
        revision_id=revision_row.id,
        event_type="SUPPLEMENT_REQUESTED",
        from_status=previous_status,
        to_status="REVISION_REQUESTED",
        actor_user_id=reviewer.id,
        comment=review_comment,
    )
    db.add(event_row)
    db.flush()

    return {
        "request_id": request_row.id,
        "request_no": request_row.request_no,
        "revision_id": revision_row.id,
        "revision_no": revision_row.revision_no,
        "review_action_id": review_action.id,
        "workflow_event_id": event_row.id,
        "status": request_row.current_status,
        "action": "REQUEST_REVISION",
    }


def save_revision_request(
    *,
    request_no: str,
    reviewer_user_id: int,
    comment: str,
) -> dict[str, Any]:
    with SessionLocal.begin() as db:
        return create_revision_request(
            db,
            request_no=request_no,
            reviewer_user_id=reviewer_user_id,
            comment=comment,
        )


def create_accept_and_assign(
    db: Session,
    *,
    request_no: str,
    reviewer_user_id: int,
    analyst_user_code: str,
    comment: str | None = None,
) -> dict[str, Any]:
    reviewer = _reviewer(db, reviewer_user_id)
    request_row, revision_row = _locked_request_and_revision(
        db,
        request_no,
    )

    normalized_analyst_code = _clean_text(analyst_user_code)
    if not normalized_analyst_code:
        raise AnalystNotFoundError("analyst_user_code is required")

    analyst = db.scalar(
        select(User).where(User.user_code == normalized_analyst_code)
    )
    if analyst is None:
        raise AnalystNotFoundError(
            f"analyst not found: {normalized_analyst_code}"
        )
    if analyst.role != "ANALYST":
        raise InvalidAnalystRoleError(
            "assigned user must have ANALYST role"
        )

    review_comment = _clean_text(comment)
    previous_status = request_row.current_status

    review_action = ReviewAction(
        request_id=request_row.id,
        revision_id=revision_row.id,
        reviewer_user_id=reviewer.id,
        action_type="ACCEPT",
        comment=review_comment or None,
    )
    db.add(review_action)

    assignment_row = Assignment(
        request_id=request_row.id,
        analyst_user_id=analyst.id,
        assigned_by_user_id=reviewer.id,
    )
    db.add(assignment_row)

    request_row.current_status = "IN_PROGRESS"

    accepted_event = WorkflowEvent(
        request_id=request_row.id,
        revision_id=revision_row.id,
        event_type="ACCEPTED",
        from_status=previous_status,
        to_status="IN_PROGRESS",
        actor_user_id=reviewer.id,
        comment=review_comment or "해석 의뢰 접수",
    )
    assigned_event = WorkflowEvent(
        request_id=request_row.id,
        revision_id=revision_row.id,
        event_type="ANALYST_ASSIGNED",
        from_status="IN_PROGRESS",
        to_status="IN_PROGRESS",
        actor_user_id=reviewer.id,
        comment=f"담당자 배정: {analyst.name} ({analyst.user_code})",
    )
    db.add_all([accepted_event, assigned_event])
    db.flush()

    return {
        "request_id": request_row.id,
        "request_no": request_row.request_no,
        "revision_id": revision_row.id,
        "revision_no": revision_row.revision_no,
        "review_action_id": review_action.id,
        "assignment_id": assignment_row.id,
        "workflow_event_ids": [
            accepted_event.id,
            assigned_event.id,
        ],
        "analyst_user_id": analyst.id,
        "analyst_user_code": analyst.user_code,
        "status": request_row.current_status,
        "action": "ACCEPT_AND_ASSIGN",
    }


def save_accept_and_assign(
    *,
    request_no: str,
    reviewer_user_id: int,
    analyst_user_code: str,
    comment: str | None = None,
) -> dict[str, Any]:
    with SessionLocal.begin() as db:
        return create_accept_and_assign(
            db,
            request_no=request_no,
            reviewer_user_id=reviewer_user_id,
            analyst_user_code=analyst_user_code,
            comment=comment,
        )
