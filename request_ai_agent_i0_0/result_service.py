"""Persist analyst results and requester completion workflow."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .db_models import Assignment, Request as RequestModel, RequestRevision, Result, User, WorkflowEvent


class ResultWorkflowError(ValueError):
    """Base error for a result workflow action rejected before commit."""


class ResultRequestNotFoundError(ResultWorkflowError):
    """Raised when the result target request does not exist."""


class ResultUserNotFoundError(ResultWorkflowError):
    """Raised when an actor user code does not exist."""


class ResultPermissionError(ResultWorkflowError):
    """Raised when the actor role does not allow the requested action."""


class InvalidResultStateError(ResultWorkflowError):
    """Raised when the request is not in the required result workflow state."""


class ResultSummaryRequiredError(ResultWorkflowError):
    """Raised when the analyst does not provide a result summary."""


class AssignedAnalystMismatchError(ResultWorkflowError):
    """Raised when the actor is not the current assigned analyst."""


def _clean_text(value: Any) -> str:
    return str("" if value is None else value).replace("\x00", "").strip()


def _locked_request_and_revision(
    db: Session,
    request_no: str,
    *,
    expected_status: str,
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
        raise ResultRequestNotFoundError(f"request not found: {normalized_request_no}")
    if request_row.current_status != expected_status:
        raise InvalidResultStateError(f"request status must be {expected_status}")

    revision_row = db.scalar(
        select(RequestRevision).where(
            RequestRevision.request_id == request_row.id,
            RequestRevision.revision_no == request_row.current_revision_no,
        )
    )
    if revision_row is None:
        raise InvalidResultStateError("current request revision does not exist")
    return request_row, revision_row


def _user_by_code(db: Session, user_code: str) -> User:
    normalized = _clean_text(user_code)
    if not normalized:
        raise ValueError("user_code is required")
    user = db.scalar(select(User).where(User.user_code == normalized))
    if user is None:
        raise ResultUserNotFoundError(f"user not found: {normalized}")
    return user


def create_result(
    db: Session,
    *,
    request_no: str,
    analyst_user_code: str,
    result_summary: str,
) -> dict[str, Any]:
    analyst = _user_by_code(db, analyst_user_code)
    if analyst.role != "ANALYST":
        raise ResultPermissionError("result registration requires ANALYST role")

    summary = _clean_text(result_summary)
    if not summary:
        raise ResultSummaryRequiredError("result summary is required")

    request_row, revision_row = _locked_request_and_revision(
        db,
        request_no,
        expected_status="IN_PROGRESS",
    )

    assignment = db.scalar(
        select(Assignment)
        .where(
            Assignment.request_id == request_row.id,
            Assignment.analyst_user_id == analyst.id,
        )
        .order_by(Assignment.id.desc())
    )
    if assignment is None:
        raise AssignedAnalystMismatchError("analyst is not assigned to this request")

    existing_result = db.scalar(
        select(Result).where(
            Result.request_id == request_row.id,
            Result.revision_id == revision_row.id,
        )
    )
    if existing_result is not None:
        raise InvalidResultStateError("result already exists for current revision")

    result_row = Result(
        request_id=request_row.id,
        revision_id=revision_row.id,
        analyst_user_id=analyst.id,
        result_summary=summary,
    )
    db.add(result_row)

    previous_status = request_row.current_status
    request_row.current_status = "RESULT_REVIEW"

    event_row = WorkflowEvent(
        request_id=request_row.id,
        revision_id=revision_row.id,
        event_type="RESULT_REGISTERED",
        from_status=previous_status,
        to_status="RESULT_REVIEW",
        actor_user_id=analyst.id,
        comment="해석 결과 등록",
    )
    db.add(event_row)
    db.flush()

    return {
        "request_id": request_row.id,
        "request_no": request_row.request_no,
        "revision_id": revision_row.id,
        "revision_no": revision_row.revision_no,
        "result_id": result_row.id,
        "workflow_event_id": event_row.id,
        "analyst_user_id": analyst.id,
        "analyst_user_code": analyst.user_code,
        "status": request_row.current_status,
    }


def save_result(
    *,
    request_no: str,
    analyst_user_code: str,
    result_summary: str,
) -> dict[str, Any]:
    with SessionLocal.begin() as db:
        return create_result(
            db,
            request_no=request_no,
            analyst_user_code=analyst_user_code,
            result_summary=result_summary,
        )


def complete_request(
    db: Session,
    *,
    request_no: str,
    requester_user_code: str,
    comment: str | None = None,
) -> dict[str, Any]:
    requester = _user_by_code(db, requester_user_code)
    if requester.role != "REQUESTER":
        raise ResultPermissionError("request completion requires REQUESTER role")

    request_row, revision_row = _locked_request_and_revision(
        db,
        request_no,
        expected_status="RESULT_REVIEW",
    )
    if request_row.requester_user_id != requester.id:
        raise ResultPermissionError("requester is not the request owner")

    result_row = db.scalar(
        select(Result).where(
            Result.request_id == request_row.id,
            Result.revision_id == revision_row.id,
        )
    )
    if result_row is None:
        raise InvalidResultStateError("current revision has no registered result")

    previous_status = request_row.current_status
    request_row.current_status = "COMPLETED"
    event_row = WorkflowEvent(
        request_id=request_row.id,
        revision_id=revision_row.id,
        event_type="REQUESTER_CONFIRMED",
        from_status=previous_status,
        to_status="COMPLETED",
        actor_user_id=requester.id,
        comment=_clean_text(comment) or "해석 결과 확인 및 완료",
    )
    db.add(event_row)
    db.flush()

    return {
        "request_id": request_row.id,
        "request_no": request_row.request_no,
        "revision_id": revision_row.id,
        "revision_no": revision_row.revision_no,
        "result_id": result_row.id,
        "workflow_event_id": event_row.id,
        "requester_user_id": requester.id,
        "status": request_row.current_status,
    }


def save_completion(
    *,
    request_no: str,
    requester_user_code: str,
    comment: str | None = None,
) -> dict[str, Any]:
    with SessionLocal.begin() as db:
        return complete_request(
            db,
            request_no=request_no,
            requester_user_code=requester_user_code,
            comment=comment,
        )
