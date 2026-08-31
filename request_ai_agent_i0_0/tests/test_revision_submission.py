from __future__ import annotations

from copy import deepcopy
import importlib

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from request_ai_agent_i0_0 import create_app
from request_ai_agent_i0_0.condition_fieldsets import (
    get_active_condition_fields,
    sanitize_condition_sets,
)
from request_ai_agent_i0_0.database import Base
from request_ai_agent_i0_0.db_models import (
    ConditionField,
    ConditionGroup,
    ConditionInstance,
    ConditionValue,
    Request,
    RequestRevision,
    User,
    WorkflowEvent,
)
from request_ai_agent_i0_0.state import create_initial_state
from request_ai_agent_i0_0 import submission_service
from request_ai_agent_i0_0.submission_service import (
    CARD_TYPE_TO_GROUP_CODE,
    DuplicateRevisionError,
    InvalidResubmissionStateError,
    SubmissionMasterDataError,
    SubmissionNotFoundError,
    SubmissionOwnershipError,
)


app_module = importlib.import_module("request_ai_agent_i0_0.app")


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _submission_state(request_no: str) -> dict[str, object]:
    state = create_initial_state()
    state["metadata"]["request_no"] = request_no
    state["review"]["validator"] = {
        "summary": {"can_submit": True},
        "blocking": [],
        "warning": [],
    }
    return state


def _changed_revision_state(state: dict[str, object]) -> dict[str, object]:
    changed = deepcopy(state)
    changed["metadata"]["revision_test_marker"] = "rev1"
    cards = changed["conditions"]["condition_sets"]

    for card in cards:
        fields = card.get("fields", {})
        if not fields:
            continue
        field = next(iter(fields.values()))
        field["value"] = "REV1_CHANGED_VALUE"
        field["display_value"] = "REV1_CHANGED_VALUE"
        field["status"] = "provided"
        field["source"] = "user"
        break

    return changed


@pytest.fixture
def revision_db(monkeypatch):
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
    monkeypatch.setattr(
        submission_service,
        "SessionLocal",
        session_factory,
    )

    request_no = "REQ-2026-REVISION-001"
    state = _submission_state(request_no)

    with session_factory.begin() as db:
        requester = User(
            user_code="USER001",
            name="MVP 의뢰자",
            role="REQUESTER",
        )
        other_requester = User(
            user_code="USER004",
            name="다른 의뢰자",
            role="REQUESTER",
        )
        db.add_all([requester, other_requester])
        db.flush()

        groups_by_type = {}
        for sort_order, (card_type, group_code) in enumerate(
            CARD_TYPE_TO_GROUP_CODE.items(),
            start=1,
        ):
            group = ConditionGroup(
                code=group_code,
                name=group_code,
                description=None,
                status="ACTIVE",
                sort_order=sort_order * 10,
            )
            db.add(group)
            groups_by_type[card_type] = group
        db.flush()

        cards = sanitize_condition_sets(
            state["conditions"]["condition_sets"],
            state["request_context"],
        )
        card_type_by_id = {
            card["id"]: card["type"]
            for card in cards
        }
        field_keys = set()

        for sort_order, active_field in enumerate(
            get_active_condition_fields(state),
            start=1,
        ):
            card_type = card_type_by_id[active_field["card_id"]]
            group = groups_by_type[card_type]
            field_code = active_field["field_key"]
            unique_key = (group.id, field_code)

            if unique_key in field_keys:
                continue

            field_keys.add(unique_key)
            db.add(
                ConditionField(
                    condition_group_id=group.id,
                    code=field_code,
                    name=active_field.get("label") or field_code,
                    value_type="TEXT",
                    unit=None,
                    status="ACTIVE",
                    sort_order=sort_order * 10,
                )
            )

        db.flush()
        initial_result = submission_service.create_initial_submission(
            db,
            state=state,
            submitted_by_user_id=requester.id,
        )
        requester_id = requester.id
        other_requester_id = other_requester.id

    yield {
        "engine": engine,
        "session_factory": session_factory,
        "request_no": request_no,
        "state": state,
        "initial_result": initial_result,
        "requester_id": requester_id,
        "other_requester_id": other_requester_id,
    }

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_initial_submission_enters_under_review_and_records_submitted_event(
    revision_db,
):
    with revision_db["session_factory"]() as db:
        request_row = db.scalar(
            select(Request).where(
                Request.request_no == revision_db["request_no"]
            )
        )
        events = db.scalars(
            select(WorkflowEvent)
            .where(WorkflowEvent.request_id == request_row.id)
            .order_by(WorkflowEvent.id)
        ).all()

    assert revision_db["initial_result"]["status"] == "UNDER_REVIEW"
    assert request_row.current_revision_no == 0
    assert request_row.current_status == "UNDER_REVIEW"
    assert len(events) == 1
    assert events[0].event_type == "SUBMITTED"
    assert events[0].from_status is None
    assert events[0].to_status == "UNDER_REVIEW"


def _mark_revision_requested(revision_db) -> None:
    with revision_db["session_factory"].begin() as db:
        request_row = db.scalar(
            select(Request).where(
                Request.request_no == revision_db["request_no"]
            )
        )
        request_row.current_status = "REVISION_REQUESTED"


def test_revision_submission_preserves_rev0_and_creates_rev1(revision_db):
    _mark_revision_requested(revision_db)
    changed_state = _changed_revision_state(revision_db["state"])

    result = submission_service.save_revision_submission(
        request_no=revision_db["request_no"],
        state=changed_state,
        submitted_by_user_id=revision_db["requester_id"],
    )

    assert result["revision_no"] == 1
    assert result["status"] == "UNDER_REVIEW"
    assert result["condition_instance_count"] > 0
    assert result["condition_value_count"] > 0

    with revision_db["session_factory"]() as db:
        request_row = db.scalar(
            select(Request).where(
                Request.request_no == revision_db["request_no"]
            )
        )
        revisions = db.scalars(
            select(RequestRevision)
            .where(RequestRevision.request_id == request_row.id)
            .order_by(RequestRevision.revision_no)
        ).all()
        events = db.scalars(
            select(WorkflowEvent)
            .where(WorkflowEvent.request_id == request_row.id)
            .order_by(WorkflowEvent.id)
        ).all()
        rev0_instance_count = db.scalar(
            select(func.count(ConditionInstance.id)).where(
                ConditionInstance.request_revision_id == revisions[0].id
            )
        )
        rev1_instance_count = db.scalar(
            select(func.count(ConditionInstance.id)).where(
                ConditionInstance.request_revision_id == revisions[1].id
            )
        )
        rev0_value_count = db.scalar(
            select(func.count(ConditionValue.id))
            .join(ConditionInstance)
            .where(
                ConditionInstance.request_revision_id == revisions[0].id
            )
        )
        rev1_value_count = db.scalar(
            select(func.count(ConditionValue.id))
            .join(ConditionInstance)
            .where(
                ConditionInstance.request_revision_id == revisions[1].id
            )
        )

    assert request_row.current_revision_no == 1
    assert request_row.current_status == "UNDER_REVIEW"
    assert [revision.revision_no for revision in revisions] == [0, 1]
    assert "revision_test_marker" not in revisions[0].snapshot_json["metadata"]
    assert revisions[1].snapshot_json["metadata"]["revision_test_marker"] == "rev1"
    assert rev0_instance_count == rev1_instance_count
    assert rev0_value_count == rev1_value_count
    assert events[-1].revision_id == revisions[1].id
    assert events[-1].event_type == "RESUBMITTED"
    assert events[-1].from_status == "REVISION_REQUESTED"
    assert events[-1].to_status == "UNDER_REVIEW"


def test_revision_submission_rejects_invalid_state_owner_and_repeat(
    revision_db,
):
    changed_state = _changed_revision_state(revision_db["state"])

    with pytest.raises(InvalidResubmissionStateError):
        submission_service.save_revision_submission(
            request_no=revision_db["request_no"],
            state=changed_state,
            submitted_by_user_id=revision_db["requester_id"],
        )

    _mark_revision_requested(revision_db)

    with pytest.raises(SubmissionOwnershipError):
        submission_service.save_revision_submission(
            request_no=revision_db["request_no"],
            state=changed_state,
            submitted_by_user_id=revision_db["other_requester_id"],
        )

    submission_service.save_revision_submission(
        request_no=revision_db["request_no"],
        state=changed_state,
        submitted_by_user_id=revision_db["requester_id"],
    )

    with pytest.raises(InvalidResubmissionStateError):
        submission_service.save_revision_submission(
            request_no=revision_db["request_no"],
            state=changed_state,
            submitted_by_user_id=revision_db["requester_id"],
        )

    with revision_db["session_factory"]() as db:
        request_row = db.scalar(
            select(Request).where(
                Request.request_no == revision_db["request_no"]
            )
        )
        revision_count = db.scalar(
            select(func.count(RequestRevision.id)).where(
                RequestRevision.request_id == request_row.id
            )
        )

    assert revision_count == 2


def test_revision_submission_rolls_back_partial_revision_and_conditions(
    revision_db,
):
    _mark_revision_requested(revision_db)
    changed_state = _changed_revision_state(revision_db["state"])

    with revision_db["session_factory"].begin() as db:
        field_row = db.scalar(select(ConditionField).limit(1))
        db.delete(field_row)

    with pytest.raises(SubmissionMasterDataError):
        submission_service.save_revision_submission(
            request_no=revision_db["request_no"],
            state=changed_state,
            submitted_by_user_id=revision_db["requester_id"],
        )

    with revision_db["session_factory"]() as db:
        request_row = db.scalar(
            select(Request).where(
                Request.request_no == revision_db["request_no"]
            )
        )
        revision_count = db.scalar(
            select(func.count(RequestRevision.id)).where(
                RequestRevision.request_id == request_row.id
            )
        )
        instance_count = db.scalar(
            select(func.count(ConditionInstance.id))
        )
        initial_instance_count = revision_db["initial_result"][
            "condition_instance_count"
        ]

    assert request_row.current_revision_no == 0
    assert request_row.current_status == "REVISION_REQUESTED"
    assert revision_count == 1
    assert instance_count == initial_instance_count


def test_revision_submission_rejects_missing_request_and_request_mismatch(
    revision_db,
):
    changed_state = _changed_revision_state(revision_db["state"])

    with pytest.raises(ValueError, match="does not match"):
        submission_service.save_revision_submission(
            request_no="REQ-DIFFERENT",
            state=changed_state,
            submitted_by_user_id=revision_db["requester_id"],
        )

    changed_state["metadata"]["request_no"] = "REQ-NOT-FOUND"

    with pytest.raises(SubmissionNotFoundError):
        submission_service.save_revision_submission(
            request_no="REQ-NOT-FOUND",
            state=changed_state,
            submitted_by_user_id=revision_db["requester_id"],
        )


def test_resubmit_api_requires_consent_and_matching_request(monkeypatch):
    state = _submission_state("REQ-2026-REVISION-API")
    monkeypatch.setattr(
        app_module,
        "state_with_validation",
        lambda _state: deepcopy(state),
    )
    called = []
    monkeypatch.setattr(
        app_module,
        "save_revision_submission",
        lambda **kwargs: called.append(kwargs),
    )
    client = create_app().test_client()

    without_consent = client.post(
        "/api/requests/REQ-2026-REVISION-API/resubmit",
        json={"state": state},
    )
    mismatch = client.post(
        "/api/requests/REQ-DIFFERENT/resubmit",
        json={"state": state, "submission_consent": True},
    )

    assert without_consent.status_code == 400
    assert without_consent.get_json()["error"] == "resubmission_consent_required"
    assert mismatch.status_code == 400
    assert mismatch.get_json()["error"] == "resubmission_request_mismatch"
    assert called == []


def test_resubmit_api_rejects_blocking_validation_without_db_write(
    monkeypatch,
):
    request_no = "REQ-2026-REVISION-API"
    state = _submission_state(request_no)
    state["review"]["validator"] = {
        "summary": {"can_submit": False},
        "blocking": [
            {
                "code": "conditions.missing",
                "message": "보완 조건이 필요합니다.",
            }
        ],
        "warning": [],
    }
    monkeypatch.setattr(
        app_module,
        "state_with_validation",
        lambda _state: deepcopy(state),
    )
    monkeypatch.setattr(
        app_module,
        "save_revision_submission",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("blocked resubmission must not write")
        ),
    )

    response = create_app().test_client().post(
        f"/api/requests/{request_no}/resubmit",
        json={"state": state, "submission_consent": True},
    )

    assert response.status_code == 422
    assert response.get_json()["error"] == "resubmission_validation_failed"
    assert response.get_json()["state_changed"] is False


def test_resubmit_api_persists_consent_and_returns_rev1(monkeypatch):
    request_no = "REQ-2026-REVISION-API"
    state = _submission_state(request_no)
    captured = {}

    monkeypatch.setattr(
        app_module,
        "state_with_validation",
        lambda _state: deepcopy(state),
    )
    monkeypatch.setattr(app_module, "_submission_user_id", lambda: 7)

    def save_submission(**kwargs):
        captured.update(kwargs)
        return {
            "request_id": 11,
            "request_no": request_no,
            "revision_id": 22,
            "revision_no": 1,
            "workflow_event_id": 33,
            "condition_instance_count": 4,
            "condition_value_count": 10,
            "status": "UNDER_REVIEW",
        }

    monkeypatch.setattr(
        app_module,
        "save_revision_submission",
        save_submission,
    )

    response = create_app().test_client().post(
        f"/api/requests/{request_no}/resubmit",
        json={"state": state, "submission_consent": True},
    )

    assert response.status_code == 200
    payload = response.get_json()
    consent = captured["state"]["metadata"]["submission_consent"]
    assert captured["request_no"] == request_no
    assert captured["submitted_by_user_id"] == 7
    assert consent["accepted"] is True
    assert consent["submitted_by_user_id"] == 7
    assert payload["submission_result"]["revision_no"] == 1
    assert payload["submission"]["status"] == "UNDER_REVIEW"
    assert payload["state_changed"] is True


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (
            SubmissionNotFoundError("missing"),
            404,
            "resubmission_request_not_found",
        ),
        (
            SubmissionOwnershipError("forbidden"),
            403,
            "resubmission_forbidden",
        ),
        (
            DuplicateRevisionError("duplicate"),
            409,
            "duplicate_resubmission",
        ),
        (
            InvalidResubmissionStateError("state"),
            409,
            "resubmission_not_allowed",
        ),
    ],
)
def test_resubmit_api_maps_domain_errors(
    monkeypatch,
    error,
    expected_status,
    expected_code,
):
    request_no = "REQ-2026-REVISION-API"
    state = _submission_state(request_no)
    monkeypatch.setattr(
        app_module,
        "state_with_validation",
        lambda _state: deepcopy(state),
    )
    monkeypatch.setattr(app_module, "_submission_user_id", lambda: 7)
    monkeypatch.setattr(
        app_module,
        "save_revision_submission",
        lambda **_kwargs: (_ for _ in ()).throw(error),
    )

    response = create_app().test_client().post(
        f"/api/requests/{request_no}/resubmit",
        json={"state": state, "submission_consent": True},
    )

    assert response.status_code == expected_status
    assert response.get_json()["error"] == expected_code
    assert response.get_json()["state_changed"] is False
