from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from request_ai_agent_i0_0.database import Base
from request_ai_agent_i0_0.db_models import Assignment, Request, RequestRevision, Result, User, WorkflowEvent
from request_ai_agent_i0_0 import result_service
from request_ai_agent_i0_0.result_service import (
    AssignedAnalystMismatchError,
    InvalidResultStateError,
    ResultPermissionError,
    ResultRequestNotFoundError,
    ResultSummaryRequiredError,
    ResultUserNotFoundError,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def result_db(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(result_service, "SessionLocal", session_factory)

    with session_factory.begin() as db:
        requester = User(user_code="USER001", name="MVP 의뢰자", role="REQUESTER")
        manager = User(user_code="USER002", name="MVP 관리자", role="MANAGER")
        analyst = User(user_code="USER003", name="MVP 해석담당자", role="ANALYST")
        wrong_role = User(user_code="USER004", name="다른 사용자", role="MANAGER")
        unassigned_analyst = User(user_code="USER005", name="미배정 해석담당자", role="ANALYST")
        db.add_all([requester, manager, analyst, wrong_role, unassigned_analyst])
        db.flush()

        request_row = Request(
            request_no="REQ-2026-RESULT-001",
            requester_user_id=requester.id,
            current_status="IN_PROGRESS",
            current_revision_no=0,
        )
        db.add(request_row)
        db.flush()
        revision = RequestRevision(
            request_id=request_row.id,
            revision_no=0,
            submitted_by_user_id=requester.id,
            state_schema_version="request_state_v2",
            snapshot_json={"metadata": {"request_no": request_row.request_no}},
        )
        db.add(revision)
        db.flush()
        assignment = Assignment(
            request_id=request_row.id,
            analyst_user_id=analyst.id,
            assigned_by_user_id=manager.id,
        )
        db.add(assignment)
        db.flush()
        db.add(
            WorkflowEvent(
                request_id=request_row.id,
                revision_id=revision.id,
                event_type="ANALYST_ASSIGNED",
                from_status="UNDER_REVIEW",
                to_status="IN_PROGRESS",
                actor_user_id=manager.id,
                comment="담당자 배정",
            )
        )
        ids = {
            "request_id": request_row.id,
            "request_no": request_row.request_no,
            "revision_id": revision.id,
            "requester_id": requester.id,
            "manager_id": manager.id,
            "analyst_id": analyst.id,
            "wrong_role_id": wrong_role.id,
            "unassigned_analyst_id": unassigned_analyst.id,
        }
    yield {"session_factory": session_factory, **ids}
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_register_result_moves_request_to_result_review_and_records_event(result_db):
    result = result_service.save_result(
        request_no=result_db["request_no"],
        analyst_user_code="USER003",
        result_summary="해석 결과에서 기준 대비 유속 편차가 확인되었습니다.",
    )
    with result_db["session_factory"]() as db:
        request_row = db.get(Request, result_db["request_id"])
        result_row = db.get(Result, result["result_id"])
        event = db.get(WorkflowEvent, result["workflow_event_id"])
    assert result["revision_no"] == 0
    assert result["status"] == "RESULT_REVIEW"
    assert request_row.current_status == "RESULT_REVIEW"
    assert result_row.revision_id == result_db["revision_id"]
    assert result_row.analyst_user_id == result_db["analyst_id"]
    assert result_row.result_summary.startswith("해석 결과에서")
    assert event.event_type == "RESULT_REGISTERED"
    assert event.from_status == "IN_PROGRESS"
    assert event.to_status == "RESULT_REVIEW"


def test_register_result_uses_current_revision(result_db):
    with result_db["session_factory"].begin() as db:
        request_row = db.get(Request, result_db["request_id"])
        rev1 = RequestRevision(
            request_id=request_row.id,
            revision_no=1,
            submitted_by_user_id=result_db["requester_id"],
            state_schema_version="request_state_v2",
            snapshot_json={"metadata": {"request_no": request_row.request_no}},
        )
        db.add(rev1)
        db.flush()
        request_row.current_revision_no = 1
        revision_id = rev1.id
    result = result_service.save_result(
        request_no=result_db["request_no"],
        analyst_user_code="USER003",
        result_summary="Rev.1 해석 결과",
    )
    with result_db["session_factory"]() as db:
        row = db.get(Result, result["result_id"])
    assert result["revision_no"] == 1
    assert row.revision_id == revision_id


def test_register_result_requires_assigned_analyst(result_db):
    with pytest.raises(AssignedAnalystMismatchError):
        result_service.save_result(
            request_no=result_db["request_no"],
            analyst_user_code="USER005",
            result_summary="결과",
        )


def test_register_result_rejects_non_analyst(result_db):
    with pytest.raises(ResultPermissionError):
        result_service.save_result(
            request_no=result_db["request_no"],
            analyst_user_code="USER002",
            result_summary="결과",
        )


def test_register_result_requires_summary(result_db):
    with pytest.raises(ResultSummaryRequiredError):
        result_service.save_result(
            request_no=result_db["request_no"],
            analyst_user_code="USER003",
            result_summary="  ",
        )
    with result_db["session_factory"]() as db:
        assert db.scalar(select(func.count(Result.id))) == 0


def test_register_result_requires_in_progress_state(result_db):
    with result_db["session_factory"].begin() as db:
        db.get(Request, result_db["request_id"]).current_status = "RESULT_REVIEW"
    with pytest.raises(InvalidResultStateError):
        result_service.save_result(
            request_no=result_db["request_no"],
            analyst_user_code="USER003",
            result_summary="결과",
        )


def test_register_result_prevents_duplicate_for_current_revision(result_db):
    result_service.save_result(
        request_no=result_db["request_no"],
        analyst_user_code="USER003",
        result_summary="최초 결과",
    )
    with pytest.raises(InvalidResultStateError):
        result_service.save_result(
            request_no=result_db["request_no"],
            analyst_user_code="USER003",
            result_summary="중복 결과",
        )
    with result_db["session_factory"]() as db:
        assert db.scalar(select(func.count(Result.id))) == 1


def test_register_result_unknown_user_is_distinct_from_request_not_found(result_db):
    with pytest.raises(ResultUserNotFoundError):
        result_service.save_result(
            request_no=result_db["request_no"],
            analyst_user_code="USER999",
            result_summary="결과",
        )


def test_register_result_request_not_found(result_db):
    with pytest.raises(ResultRequestNotFoundError):
        result_service.save_result(
            request_no="REQ-NOT-FOUND",
            analyst_user_code="USER003",
            result_summary="결과",
        )


def test_complete_request_moves_to_completed_and_records_event(result_db):
    result_service.save_result(
        request_no=result_db["request_no"],
        analyst_user_code="USER003",
        result_summary="최종 결과",
    )
    completion = result_service.save_completion(
        request_no=result_db["request_no"],
        requester_user_code="USER001",
        comment="결과 확인했습니다.",
    )
    with result_db["session_factory"]() as db:
        request_row = db.get(Request, result_db["request_id"])
        event = db.get(WorkflowEvent, completion["workflow_event_id"])
    assert completion["status"] == "COMPLETED"
    assert request_row.current_status == "COMPLETED"
    assert event.event_type == "REQUESTER_CONFIRMED"
    assert event.from_status == "RESULT_REVIEW"
    assert event.to_status == "COMPLETED"
    assert event.comment == "결과 확인했습니다."


def test_complete_request_requires_owner(result_db):
    result_service.save_result(
        request_no=result_db["request_no"],
        analyst_user_code="USER003",
        result_summary="최종 결과",
    )
    with pytest.raises(ResultPermissionError):
        result_service.save_completion(
            request_no=result_db["request_no"],
            requester_user_code="USER004",
        )


def test_complete_request_requires_result_review_state(result_db):
    with pytest.raises(InvalidResultStateError):
        result_service.save_completion(
            request_no=result_db["request_no"],
            requester_user_code="USER001",
        )


def test_complete_request_requires_registered_result(result_db):
    with result_db["session_factory"].begin() as db:
        db.get(Request, result_db["request_id"]).current_status = "RESULT_REVIEW"
    with pytest.raises(InvalidResultStateError):
        result_service.save_completion(
            request_no=result_db["request_no"],
            requester_user_code="USER001",
        )


def test_complete_request_cannot_be_repeated(result_db):
    result_service.save_result(
        request_no=result_db["request_no"],
        analyst_user_code="USER003",
        result_summary="최종 결과",
    )
    result_service.save_completion(
        request_no=result_db["request_no"],
        requester_user_code="USER001",
    )
    with pytest.raises(InvalidResultStateError):
        result_service.save_completion(
            request_no=result_db["request_no"],
            requester_user_code="USER001",
        )
