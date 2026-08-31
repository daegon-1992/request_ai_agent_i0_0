from __future__ import annotations

import importlib

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from request_ai_agent_i0_0 import create_app
from request_ai_agent_i0_0.database import Base
from request_ai_agent_i0_0.db_models import (
    Assignment,
    Request,
    RequestRevision,
    ReviewAction,
    User,
    WorkflowEvent,
)
from request_ai_agent_i0_0 import review_service
from request_ai_agent_i0_0.review_service import (
    AnalystNotFoundError,
    InvalidAnalystRoleError,
    InvalidReviewStateError,
    ReviewCommentRequiredError,
    ReviewPermissionError,
    ReviewRequestNotFoundError,
)


def _load_app_module():
    return importlib.import_module("request_ai_agent_i0_0.app")


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def review_db(monkeypatch):
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
    monkeypatch.setattr(review_service, "SessionLocal", session_factory)

    with session_factory.begin() as db:
        requester = User(
            user_code="USER001",
            name="MVP 의뢰자",
            role="REQUESTER",
        )
        manager = User(
            user_code="USER002",
            name="MVP 관리자",
            role="MANAGER",
        )
        analyst = User(
            user_code="USER003",
            name="MVP 해석담당자",
            role="ANALYST",
        )
        wrong_role = User(
            user_code="USER004",
            name="다른 의뢰자",
            role="REQUESTER",
        )
        db.add_all([requester, manager, analyst, wrong_role])
        db.flush()

        request_row = Request(
            request_no="REQ-2026-REVIEW-001",
            requester_user_id=requester.id,
            current_status="UNDER_REVIEW",
            current_revision_no=0,
        )
        db.add(request_row)
        db.flush()

        revision_row = RequestRevision(
            request_id=request_row.id,
            revision_no=0,
            submitted_by_user_id=requester.id,
            state_schema_version="request_state_v2",
            snapshot_json={"metadata": {"request_no": request_row.request_no}},
        )
        db.add(revision_row)
        db.flush()

        db.add(
            WorkflowEvent(
                request_id=request_row.id,
                revision_id=revision_row.id,
                event_type="SUBMITTED",
                from_status=None,
                to_status="UNDER_REVIEW",
                actor_user_id=requester.id,
                comment="최초 의뢰 제출",
            )
        )

        ids = {
            "request_id": request_row.id,
            "request_no": request_row.request_no,
            "revision_id": revision_row.id,
            "requester_id": requester.id,
            "manager_id": manager.id,
            "analyst_id": analyst.id,
            "wrong_role_id": wrong_role.id,
        }

    yield {"session_factory": session_factory, **ids}

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_request_revision_records_review_and_event_without_new_revision(review_db):
    result = review_service.save_revision_request(
        request_no=review_db["request_no"],
        reviewer_user_id=review_db["manager_id"],
        comment="Fan RPM 조건을 확인해 주세요.",
    )

    with review_db["session_factory"]() as db:
        request_row = db.get(Request, review_db["request_id"])
        revisions = db.scalars(
            select(RequestRevision)
            .where(RequestRevision.request_id == request_row.id)
            .order_by(RequestRevision.revision_no)
        ).all()
        action = db.scalar(
            select(ReviewAction).where(
                ReviewAction.request_id == request_row.id
            )
        )
        events = db.scalars(
            select(WorkflowEvent)
            .where(WorkflowEvent.request_id == request_row.id)
            .order_by(WorkflowEvent.id)
        ).all()

    assert result["status"] == "REVISION_REQUESTED"
    assert result["revision_no"] == 0
    assert request_row.current_status == "REVISION_REQUESTED"
    assert request_row.current_revision_no == 0
    assert len(revisions) == 1
    assert action.revision_id == review_db["revision_id"]
    assert action.reviewer_user_id == review_db["manager_id"]
    assert action.action_type == "REQUEST_REVISION"
    assert action.comment == "Fan RPM 조건을 확인해 주세요."
    assert events[-1].event_type == "SUPPLEMENT_REQUESTED"
    assert events[-1].from_status == "UNDER_REVIEW"
    assert events[-1].to_status == "REVISION_REQUESTED"


def test_review_uses_current_revision_after_resubmission(review_db):
    with review_db["session_factory"].begin() as db:
        request_row = db.get(Request, review_db["request_id"])
        rev1 = RequestRevision(
            request_id=request_row.id,
            revision_no=1,
            submitted_by_user_id=review_db["requester_id"],
            state_schema_version="request_state_v2",
            snapshot_json={"metadata": {"request_no": request_row.request_no}},
        )
        db.add(rev1)
        db.flush()
        request_row.current_revision_no = 1
        request_row.current_status = "UNDER_REVIEW"
        rev1_id = rev1.id

    result = review_service.save_revision_request(
        request_no=review_db["request_no"],
        reviewer_user_id=review_db["manager_id"],
        comment="재제출본 추가 확인이 필요합니다.",
    )

    with review_db["session_factory"]() as db:
        action = db.scalar(
            select(ReviewAction)
            .where(ReviewAction.request_id == review_db["request_id"])
            .order_by(ReviewAction.id.desc())
        )

    assert result["revision_no"] == 1
    assert result["revision_id"] == rev1_id
    assert action.revision_id == rev1_id


def test_request_revision_requires_comment(review_db):
    with pytest.raises(ReviewCommentRequiredError):
        review_service.save_revision_request(
            request_no=review_db["request_no"],
            reviewer_user_id=review_db["manager_id"],
            comment="  ",
        )

    with review_db["session_factory"]() as db:
        assert db.scalar(select(func.count(ReviewAction.id))) == 0


def test_review_rejects_missing_request_and_non_manager(review_db):
    with pytest.raises(ReviewRequestNotFoundError):
        review_service.save_revision_request(
            request_no="REQ-NOT-FOUND",
            reviewer_user_id=review_db["manager_id"],
            comment="보완 요청",
        )

    with pytest.raises(ReviewPermissionError):
        review_service.save_revision_request(
            request_no=review_db["request_no"],
            reviewer_user_id=review_db["wrong_role_id"],
            comment="보완 요청",
        )


def test_review_rejects_request_not_under_review(review_db):
    with review_db["session_factory"].begin() as db:
        db.get(Request, review_db["request_id"]).current_status = "IN_PROGRESS"

    with pytest.raises(InvalidReviewStateError):
        review_service.save_revision_request(
            request_no=review_db["request_no"],
            reviewer_user_id=review_db["manager_id"],
            comment="보완 요청",
        )

    with review_db["session_factory"]() as db:
        assert db.scalar(select(func.count(ReviewAction.id))) == 0


def test_accept_and_assign_moves_request_to_in_progress(review_db):
    result = review_service.save_accept_and_assign(
        request_no=review_db["request_no"],
        reviewer_user_id=review_db["manager_id"],
        analyst_user_code="USER003",
        comment="검토 완료",
    )

    with review_db["session_factory"]() as db:
        request_row = db.get(Request, review_db["request_id"])
        action = db.scalar(
            select(ReviewAction).where(
                ReviewAction.request_id == request_row.id
            )
        )
        assignment = db.scalar(
            select(Assignment).where(
                Assignment.request_id == request_row.id
            )
        )
        events = db.scalars(
            select(WorkflowEvent)
            .where(WorkflowEvent.request_id == request_row.id)
            .order_by(WorkflowEvent.id)
        ).all()

    assert result["status"] == "IN_PROGRESS"
    assert result["revision_no"] == 0
    assert result["analyst_user_code"] == "USER003"
    assert request_row.current_status == "IN_PROGRESS"
    assert request_row.current_revision_no == 0
    assert action.action_type == "ACCEPT"
    assert action.revision_id == review_db["revision_id"]
    assert assignment.analyst_user_id == review_db["analyst_id"]
    assert assignment.assigned_by_user_id == review_db["manager_id"]
    assert [event.event_type for event in events[-2:]] == [
        "ACCEPTED",
        "ANALYST_ASSIGNED",
    ]
    assert events[-2].from_status == "UNDER_REVIEW"
    assert events[-2].to_status == "IN_PROGRESS"
    assert events[-1].from_status == "IN_PROGRESS"
    assert events[-1].to_status == "IN_PROGRESS"


def test_accept_and_assign_uses_current_revision_after_resubmission(review_db):
    with review_db["session_factory"].begin() as db:
        request_row = db.get(Request, review_db["request_id"])
        rev1 = RequestRevision(
            request_id=request_row.id,
            revision_no=1,
            submitted_by_user_id=review_db["requester_id"],
            state_schema_version="request_state_v2",
            snapshot_json={"metadata": {"request_no": request_row.request_no}},
        )
        db.add(rev1)
        db.flush()
        request_row.current_revision_no = 1
        request_row.current_status = "UNDER_REVIEW"
        rev1_id = rev1.id

    result = review_service.save_accept_and_assign(
        request_no=review_db["request_no"],
        reviewer_user_id=review_db["manager_id"],
        analyst_user_code="USER003",
        comment="재제출본 검토 완료",
    )

    with review_db["session_factory"]() as db:
        action = db.scalar(
            select(ReviewAction).where(
                ReviewAction.request_id == review_db["request_id"]
            )
        )
        events = db.scalars(
            select(WorkflowEvent)
            .where(WorkflowEvent.request_id == review_db["request_id"])
            .order_by(WorkflowEvent.id)
        ).all()

    assert result["revision_no"] == 1
    assert result["revision_id"] == rev1_id
    assert action.revision_id == rev1_id
    assert events[-2].revision_id == rev1_id
    assert events[-1].revision_id == rev1_id


def test_second_assignment_is_rejected_by_request_state(review_db):
    review_service.save_accept_and_assign(
        request_no=review_db["request_no"],
        reviewer_user_id=review_db["manager_id"],
        analyst_user_code="USER003",
    )

    with pytest.raises(InvalidReviewStateError):
        review_service.save_accept_and_assign(
            request_no=review_db["request_no"],
            reviewer_user_id=review_db["manager_id"],
            analyst_user_code="USER003",
        )

    with review_db["session_factory"]() as db:
        assert db.scalar(select(func.count(Assignment.id))) == 1
        assert db.scalar(select(func.count(ReviewAction.id))) == 1


def test_assignment_validates_selected_analyst(review_db):
    with pytest.raises(AnalystNotFoundError):
        review_service.save_accept_and_assign(
            request_no=review_db["request_no"],
            reviewer_user_id=review_db["manager_id"],
            analyst_user_code="USER999",
        )

    with pytest.raises(InvalidAnalystRoleError):
        review_service.save_accept_and_assign(
            request_no=review_db["request_no"],
            reviewer_user_id=review_db["manager_id"],
            analyst_user_code="USER004",
        )

    with review_db["session_factory"]() as db:
        assert db.scalar(select(func.count(Assignment.id))) == 0
        assert db.get(Request, review_db["request_id"]).current_status == "UNDER_REVIEW"


def test_review_api_validates_action_comment_and_analyst(monkeypatch):
    app_module = _load_app_module()
    monkeypatch.setattr(app_module, "_reviewer_user_id", lambda: 2)
    client = create_app().test_client()

    invalid = client.post(
        "/api/requests/REQ-001/review",
        json={"action": "UNKNOWN"},
    )
    no_comment = client.post(
        "/api/requests/REQ-001/review",
        json={"action": "REQUEST_REVISION"},
    )
    no_analyst = client.post(
        "/api/requests/REQ-001/review",
        json={"action": "ACCEPT_AND_ASSIGN"},
    )

    assert invalid.status_code == 400
    assert invalid.get_json()["error"] == "invalid_review_action"
    assert no_comment.status_code == 400
    assert no_comment.get_json()["error"] == "review_comment_required"
    assert no_analyst.status_code == 400
    assert no_analyst.get_json()["error"] == "analyst_required"


def test_review_api_dispatches_revision_request(monkeypatch):
    app_module = _load_app_module()
    called = []
    monkeypatch.setattr(app_module, "_reviewer_user_id", lambda: 22)
    monkeypatch.setattr(
        app_module,
        "save_revision_request",
        lambda **kwargs: called.append(kwargs) or {
            "request_id": 1,
            "request_no": "REQ-001",
            "revision_id": 10,
            "revision_no": 0,
            "review_action_id": 20,
            "workflow_event_id": 30,
            "status": "REVISION_REQUESTED",
            "action": "REQUEST_REVISION",
        },
    )
    client = create_app().test_client()

    response = client.post(
        "/api/requests/REQ-001/review",
        json={
            "action": "REQUEST_REVISION",
            "comment": "조건 확인 필요",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "REVISION_REQUESTED"
    assert called == [
        {
            "request_no": "REQ-001",
            "reviewer_user_id": 22,
            "comment": "조건 확인 필요",
        }
    ]


def test_review_api_dispatches_accept_and_assign(monkeypatch):
    app_module = _load_app_module()
    called = []
    monkeypatch.setattr(app_module, "_reviewer_user_id", lambda: 22)
    monkeypatch.setattr(
        app_module,
        "save_accept_and_assign",
        lambda **kwargs: called.append(kwargs) or {
            "request_id": 1,
            "request_no": "REQ-001",
            "revision_id": 10,
            "revision_no": 1,
            "review_action_id": 20,
            "assignment_id": 21,
            "workflow_event_ids": [30, 31],
            "analyst_user_id": 3,
            "analyst_user_code": "USER003",
            "status": "IN_PROGRESS",
            "action": "ACCEPT_AND_ASSIGN",
        },
    )
    client = create_app().test_client()

    response = client.post(
        "/api/requests/REQ-001/review",
        json={
            "action": "ACCEPT_AND_ASSIGN",
            "analyst_user_code": "USER003",
            "comment": "검토 완료",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "IN_PROGRESS"
    assert response.get_json()["revision_no"] == 1
    assert called == [
        {
            "request_no": "REQ-001",
            "reviewer_user_id": 22,
            "analyst_user_code": "USER003",
            "comment": "검토 완료",
        }
    ]


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (ReviewRequestNotFoundError(), 404, "review_request_not_found"),
        (ReviewPermissionError(), 403, "review_forbidden"),
        (InvalidReviewStateError(), 409, "review_not_allowed"),
        (AnalystNotFoundError(), 404, "analyst_not_found"),
        (InvalidAnalystRoleError(), 400, "invalid_analyst_role"),
    ],
)
def test_review_api_maps_domain_errors(
    monkeypatch,
    error,
    expected_status,
    expected_code,
):
    app_module = _load_app_module()
    monkeypatch.setattr(app_module, "_reviewer_user_id", lambda: 22)

    def fail(**_kwargs):
        raise error

    monkeypatch.setattr(app_module, "save_revision_request", fail)
    client = create_app().test_client()

    response = client.post(
        "/api/requests/REQ-001/review",
        json={"action": "REQUEST_REVISION", "comment": "보완 필요"},
    )

    assert response.status_code == expected_status
    assert response.get_json()["error"] == expected_code
