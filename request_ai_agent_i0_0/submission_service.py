"""Persist validated Agent submissions to PostgreSQL."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from .condition_fieldsets import (
    get_active_condition_fields,
    sanitize_condition_sets,
)
from .constants import (
    SECTION_CONDITIONS,
    SECTION_REQUEST_CONTEXT,
    STATE_SCHEMA_VERSION,
)
from .database import SessionLocal
from .db_models import (
    ConditionField,
    ConditionGroup,
    ConditionInstance,
    ConditionValue,
    Request as RequestModel,
    RequestRevision,
    User,
    WorkflowEvent,
)
from .state import field_value

CARD_TYPE_TO_GROUP_CODE = {
    "operating": "OPERATING",
    "heat_exchanger": "HEAT_EXCHANGER",
    "supply_air": "SUPPLY_AIR",
    "space_environment": "SPACE_ENVIRONMENT",
}


class SubmissionError(ValueError):
    """Base error for a submission rejected before commit."""


class DuplicateSubmissionError(SubmissionError):
    """Raised when a request number has already been submitted."""


class SubmissionNotFoundError(SubmissionError):
    """Raised when the request selected for resubmission does not exist."""


class SubmissionOwnershipError(SubmissionError):
    """Raised when a different requester attempts a resubmission."""


class InvalidResubmissionStateError(SubmissionError):
    """Raised when the request cannot accept a new revision."""


class DuplicateRevisionError(SubmissionError):
    """Raised when the next revision was already submitted."""


class SubmissionMasterDataError(SubmissionError):
    """Raised when required active DB master data is missing."""


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _clean_text(value: Any) -> str:
    return str("" if value is None else value).replace("\x00", "").strip()


def _nullable_text(value: Any) -> str | None:
    text = _clean_text(value)
    return text if text else None


def _request_no(state: Mapping[str, Any]) -> str:
    metadata = _as_mapping(state.get("metadata"))
    basic_info = _as_mapping(state.get("basic_info"))

    return _clean_text(
        metadata.get("request_no")
        or field_value(basic_info.get("request_no"), "")
    )


def _schema_version(state: Mapping[str, Any]) -> str:
    metadata = _as_mapping(state.get("metadata"))
    return _clean_text(
        metadata.get("schema_version")
    ) or STATE_SCHEMA_VERSION


def _condition_metadata(card: Mapping[str, Any]) -> dict[str, Any]:
    card_type = _clean_text(card.get("type"))

    if card_type == "operating":
        return {
            "fan_rpm_mode": _clean_text(card.get("fan_rpm_mode")),
            "fans": deepcopy(
                card.get("fans")
                if isinstance(card.get("fans"), list)
                else []
            ),
        }

    if card_type == "heat_exchanger":
        return {
            "heat_exchanger_type": _clean_text(
                card.get("heat_exchanger_type")
            ),
        }

    return {}


def _condition_instance_name(
    card: Mapping[str, Any],
    group: ConditionGroup,
) -> str:
    card_type = _clean_text(card.get("type"))
    fields = _as_mapping(card.get("fields"))

    if card_type == "operating":
        return _clean_text(card.get("name")) or group.name

    if card_type == "heat_exchanger":
        return (
            _clean_text(field_value(fields.get("name"), ""))
            or group.name
        )

    return _clean_text(card.get("label")) or group.name


def _load_condition_masters(
    db: Session,
) -> tuple[
    dict[str, ConditionGroup],
    dict[tuple[int, str], ConditionField],
]:
    group_rows = db.scalars(
        select(ConditionGroup).where(
            ConditionGroup.status == "ACTIVE"
        )
    ).all()

    groups_by_code = {
        group.code: group
        for group in group_rows
    }

    required_group_codes = set(
        CARD_TYPE_TO_GROUP_CODE.values()
    )

    missing_groups = sorted(
        required_group_codes - set(groups_by_code)
    )

    if missing_groups:
        raise SubmissionMasterDataError(
            "condition groups are missing: "
            + ", ".join(missing_groups)
        )

    field_rows = db.scalars(
        select(ConditionField).where(
            ConditionField.status == "ACTIVE"
        )
    ).all()

    fields_by_group_and_code = {
        (field.condition_group_id, field.code): field
        for field in field_rows
    }

    return groups_by_code, fields_by_group_and_code


def _create_condition_rows(
    db: Session,
    *,
    state: Mapping[str, Any],
    revision_id: int,
    groups_by_code: Mapping[str, ConditionGroup],
    fields_by_group_and_code: Mapping[
        tuple[int, str],
        ConditionField,
    ],
) -> tuple[int, int]:
    request_context = _as_mapping(
        state.get(SECTION_REQUEST_CONTEXT)
    )
    conditions = _as_mapping(
        state.get(SECTION_CONDITIONS)
    )

    cards = sanitize_condition_sets(
        conditions.get("condition_sets"),
        request_context,
    )

    active_field_rows = get_active_condition_fields(state)

    active_fields_by_card: dict[
        str,
        list[Mapping[str, Any]],
    ] = defaultdict(list)

    for active_field in active_field_rows:
        if not isinstance(active_field, Mapping):
            continue

        card_id = _clean_text(active_field.get("card_id"))

        if card_id:
            active_fields_by_card[card_id].append(
                active_field
            )

    instance_count = 0
    value_count = 0

    for card_index, card in enumerate(cards, start=1):
        card_type = _clean_text(card.get("type"))
        group_code = CARD_TYPE_TO_GROUP_CODE.get(card_type)

        if not group_code:
            raise ValueError(
                f"unsupported condition card type: {card_type}"
            )

        group = groups_by_code[group_code]
        instance_key = _clean_text(card.get("id"))

        if not instance_key:
            raise ValueError(
                f"condition card id is missing: {card_type}"
            )

        instance_row = ConditionInstance(
            request_revision_id=revision_id,
            condition_group_id=group.id,
            instance_key=instance_key,
            instance_name=_condition_instance_name(
                card,
                group,
            ),
            metadata_json=_condition_metadata(card),
            sort_order=(group.sort_order * 100) + card_index,
        )

        db.add(instance_row)
        db.flush()

        instance_count += 1

        for active_field in active_fields_by_card.get(
            instance_key,
            [],
        ):
            field_code = _clean_text(
                active_field.get("field_key")
            )

            field_master = fields_by_group_and_code.get(
                (group.id, field_code)
            )

            if field_master is None:
                raise SubmissionMasterDataError(
                    "condition field master is missing: "
                    f"{group_code}.{field_code}"
                )

            values = active_field.get("values")
            values = values if isinstance(values, list) else []

            if len(values) > 1:
                raise ValueError(
                    "multiple values for one condition instance field: "
                    f"{instance_key}.{field_code}"
                )

            raw_value = (
                values[0]
                if values and isinstance(values[0], Mapping)
                else {}
            )

            raw_text = _clean_text(
                field_value(raw_value, "")
            )

            value_status = (
                _clean_text(raw_value.get("status"))
                or ("provided" if raw_text else "missing")
            )

            value_source = (
                _clean_text(raw_value.get("source"))
                or "user"
            )

            value_row = ConditionValue(
                condition_instance_id=instance_row.id,
                condition_field_id=field_master.id,
                value_text=raw_text or None,
                display_value=(
                    _nullable_text(
                        raw_value.get("display_value")
                    )
                    or raw_text
                    or None
                ),
                value_status=value_status,
                value_source=value_source,
                note=_nullable_text(raw_value.get("note")),
            )

            db.add(value_row)
            value_count += 1

    db.flush()

    return instance_count, value_count


def create_initial_submission(
    db: Session,
    *,
    state: Mapping[str, Any],
    submitted_by_user_id: int,
) -> dict[str, Any]:
    request_no = _request_no(state)

    if not request_no:
        raise ValueError("request_no is required")

    user = db.get(User, submitted_by_user_id)

    if user is None:
        raise ValueError(
            f"submitted user not found: {submitted_by_user_id}"
        )

    existing_request = db.scalar(
        select(RequestModel).where(
            RequestModel.request_no == request_no
        )
    )

    if existing_request is not None:
        raise DuplicateSubmissionError(
            f"request_no already exists: {request_no}"
        )

    groups_by_code, fields_by_group_and_code = (
        _load_condition_masters(db)
    )

    request_row = RequestModel(
        request_no=request_no,
        requester_user_id=submitted_by_user_id,
        current_status="UNDER_REVIEW",
        current_revision_no=0,
    )

    db.add(request_row)
    db.flush()

    revision_row = RequestRevision(
        request_id=request_row.id,
        revision_no=0,
        submitted_by_user_id=submitted_by_user_id,
        state_schema_version=_schema_version(state),
        snapshot_json=deepcopy(dict(state)),
    )

    db.add(revision_row)
    db.flush()

    event_row = WorkflowEvent(
        request_id=request_row.id,
        revision_id=revision_row.id,
        event_type="SUBMITTED",
        from_status=None,
        to_status="UNDER_REVIEW",
        actor_user_id=submitted_by_user_id,
        comment="최초 의뢰 제출",
    )

    db.add(event_row)

    instance_count, value_count = _create_condition_rows(
        db,
        state=state,
        revision_id=revision_row.id,
        groups_by_code=groups_by_code,
        fields_by_group_and_code=fields_by_group_and_code,
    )

    return {
        "request_id": request_row.id,
        "request_no": request_row.request_no,
        "revision_id": revision_row.id,
        "revision_no": revision_row.revision_no,
        "workflow_event_id": event_row.id,
        "condition_instance_count": instance_count,
        "condition_value_count": value_count,
        "status": request_row.current_status,
    }


def save_initial_submission(
    *,
    state: Mapping[str, Any],
    submitted_by_user_id: int,
) -> dict[str, Any]:
    with SessionLocal.begin() as db:
        return create_initial_submission(
            db,
            state=state,
            submitted_by_user_id=submitted_by_user_id,
        )


def create_revision_submission(
    db: Session,
    *,
    request_no: str,
    state: Mapping[str, Any],
    submitted_by_user_id: int,
) -> dict[str, Any]:
    normalized_request_no = _clean_text(request_no)

    if not normalized_request_no:
        raise ValueError("request_no is required")

    state_request_no = _request_no(state)

    if state_request_no != normalized_request_no:
        raise ValueError("state request_no does not match request_no")

    user = db.get(User, submitted_by_user_id)

    if user is None:
        raise ValueError(
            f"submitted user not found: {submitted_by_user_id}"
        )

    request_row = db.scalar(
        select(RequestModel)
        .where(RequestModel.request_no == normalized_request_no)
        .with_for_update()
    )

    if request_row is None:
        raise SubmissionNotFoundError(
            f"request not found: {normalized_request_no}"
        )

    if request_row.requester_user_id != submitted_by_user_id:
        raise SubmissionOwnershipError(
            "submitted user is not the request owner"
        )

    if request_row.current_status != "REVISION_REQUESTED":
        raise InvalidResubmissionStateError(
            "request status must be REVISION_REQUESTED"
        )

    current_revision_no = request_row.current_revision_no

    if current_revision_no < 0:
        raise InvalidResubmissionStateError(
            "current revision number is invalid"
        )

    current_revision_id = db.scalar(
        select(RequestRevision.id).where(
            RequestRevision.request_id == request_row.id,
            RequestRevision.revision_no == current_revision_no,
        )
    )

    if current_revision_id is None:
        raise InvalidResubmissionStateError(
            "current request revision does not exist"
        )

    next_revision_no = current_revision_no + 1
    existing_revision_id = db.scalar(
        select(RequestRevision.id).where(
            RequestRevision.request_id == request_row.id,
            RequestRevision.revision_no == next_revision_no,
        )
    )

    if existing_revision_id is not None:
        raise DuplicateRevisionError(
            "next request revision already exists"
        )

    groups_by_code, fields_by_group_and_code = (
        _load_condition_masters(db)
    )

    revision_row = RequestRevision(
        request_id=request_row.id,
        revision_no=next_revision_no,
        submitted_by_user_id=submitted_by_user_id,
        state_schema_version=_schema_version(state),
        snapshot_json=deepcopy(dict(state)),
    )

    db.add(revision_row)
    db.flush()

    instance_count, value_count = _create_condition_rows(
        db,
        state=state,
        revision_id=revision_row.id,
        groups_by_code=groups_by_code,
        fields_by_group_and_code=fields_by_group_and_code,
    )

    previous_status = request_row.current_status
    request_row.current_revision_no = next_revision_no
    request_row.current_status = "UNDER_REVIEW"

    event_row = WorkflowEvent(
        request_id=request_row.id,
        revision_id=revision_row.id,
        event_type="RESUBMITTED",
        from_status=previous_status,
        to_status="UNDER_REVIEW",
        actor_user_id=submitted_by_user_id,
        comment="보완 의뢰 재제출",
    )

    db.add(event_row)
    db.flush()

    return {
        "request_id": request_row.id,
        "request_no": request_row.request_no,
        "revision_id": revision_row.id,
        "revision_no": revision_row.revision_no,
        "workflow_event_id": event_row.id,
        "condition_instance_count": instance_count,
        "condition_value_count": value_count,
        "status": request_row.current_status,
    }


def save_revision_submission(
    *,
    request_no: str,
    state: Mapping[str, Any],
    submitted_by_user_id: int,
) -> dict[str, Any]:
    with SessionLocal.begin() as db:
        return create_revision_submission(
            db,
            request_no=request_no,
            state=state,
            submitted_by_user_id=submitted_by_user_id,
        )
