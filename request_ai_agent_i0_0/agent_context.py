"""Read-only assembly of the common LLM-facing Agent Context."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping

from .conversation_store import ConversationSnapshot
from .condition_fieldsets import sanitize_condition_sets
from .constants import SUBMISSION_CONTACT
from .form_context import build_form_context
from .request_state_store import RequestStateSnapshot
from .validator import validate_state


_REQUEST_CONTEXT_USER_KEYS = (
    "taxonomy_id",
    "taxonomy_version",
    "division",
    "product_lineup",
    "platform",
    "chassis",
    "display_path",
    "analysis_type",
    "operation_mode",
    "context_locked",
)

_GEOMETRY_ACTIVE_FIELD_RE = re.compile(
    r"^geometry\.(base_product|comparison_products\[(\d+)\])\.([A-Za-z0-9_]+)$"
)

_CONDITION_GROUP_LABELS = {
    "operating": "운전 조건",
    "heat_exchanger": "열교환기 사양",
    "space_environment": "공간 환경 조건",
    "supply_air": "취출 공기 조건",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _project_request_context(state: Mapping[str, Any]) -> dict[str, Any]:
    request_context = _mapping(state.get("request_context"))
    return {
        key: deepcopy(request_context[key])
        for key in _REQUEST_CONTEXT_USER_KEYS
        if key in request_context
    }


def _project_case_rows(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    case_matrix = _mapping(state.get("case_matrix"))
    rows = case_matrix.get("rows")
    if not isinstance(rows, list):
        return []

    canonical_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        canonical_rows.append(
            {
                key: deepcopy(row[key])
                for key in ("case_id", "geometry_id", "condition_values")
                if key in row
            }
        )
    return canonical_rows


def _project_request_state(state: Mapping[str, Any]) -> dict[str, Any]:
    geometry = _mapping(state.get("geometry"))
    conditions = _mapping(state.get("conditions"))
    return {
        "request_context": _project_request_context(state),
        "basic_info": deepcopy(dict(_mapping(state.get("basic_info")))),
        "analysis_overview": deepcopy(dict(_mapping(state.get("analysis_overview")))),
        "geometry": {
            "base_product": deepcopy(geometry.get("base_product", {})),
            "comparison_products": deepcopy(geometry.get("comparison_products", [])),
        },
        "conditions": {
            "mode": deepcopy(conditions.get("mode")),
            "condition_sets": _active_condition_sets(state),
        },
        "case_matrix": {"rows": _project_case_rows(state)},
    }


def _active_condition_sets(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    conditions = _mapping(state.get("conditions"))
    return sanitize_condition_sets(conditions.get("condition_sets"), state)


def _build_submission_process(validation: Mapping[str, Any]) -> dict[str, Any]:
    required_input_complete = _mapping(validation.get("summary")).get("can_submit") is True
    steps = [
        {"key": "case_matrix_review", "action": "Case Matrix 확인"},
        {"key": "full_preview_review", "action": "전체 확인 화면에서 의뢰서 미리보기 검토"},
        {"key": "word_generation", "action": "의뢰서 생성(Word)"},
        {"key": "email_submission", "action": "생성한 Word 파일 이메일 제출"},
    ]
    return {
        "required_input_complete": required_input_complete,
        "required_input_status_meaning": "필수 입력 충족 여부이며 실제 제출 완료 여부가 아님",
        "next_action": deepcopy(steps[0]) if required_input_complete else None,
        "remaining_steps": steps,
        "submission": {
            "method": "email",
            "direct_screen_submission_available": False,
            "recipient": deepcopy(SUBMISSION_CONTACT),
        },
    }


def _ordinal(index: int) -> str:
    return {1: "첫 번째", 2: "두 번째", 3: "세 번째"}.get(index, f"{index}번째")


def _geometry_reference(role: str, comparison_index: int = 0) -> str:
    if role == "base":
        return "Base 제품"
    return "비교 제품" if comparison_index <= 1 else f"{_ordinal(comparison_index)} 비교 제품"


def _build_instance_context(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    geometry = _mapping(state.get("geometry"))
    products = [
        geometry.get("base_product"),
        *(geometry.get("comparison_products") if isinstance(geometry.get("comparison_products"), list) else []),
    ]
    geometry_references: dict[str, Any] = {}
    comparison_index = 0
    for product in products:
        if not isinstance(product, Mapping) or not product.get("geometry_id"):
            continue
        role = str(product.get("role") or "").strip()
        if role == "comparison":
            comparison_index += 1
        geometry_references[_geometry_reference(role, comparison_index)] = deepcopy(product["geometry_id"])

    cards = _active_condition_sets(state)
    condition_references: dict[str, dict[str, Any]] = {
        "operating_conditions": {},
        "heat_exchangers": {},
        "space_environments": {},
        "supply_air_conditions": {},
    }
    context_keys = {
        "operating": "operating_conditions",
        "heat_exchanger": "heat_exchangers",
        "space_environment": "space_environments",
        "supply_air": "supply_air_conditions",
    }
    type_counts = {
        card_type: sum(
            1
            for card in cards
            if isinstance(card, Mapping) and str(card.get("type") or "").strip() == card_type
        )
        for card_type in context_keys
    }
    for card in cards:
        if not isinstance(card, Mapping) or not card.get("id"):
            continue
        card_type = str(card.get("type") or "").strip()
        context_key = context_keys.get(card_type)
        if not context_key:
            continue
        references = condition_references[context_key]
        index = len(references) + 1
        label = _CONDITION_GROUP_LABELS[card_type]
        if type_counts[card_type] > 1:
            label = f"{_ordinal(index)} {label}"
        references[label] = deepcopy(card["id"])

    return {
        "geometry": geometry_references,
        **condition_references,
    }


def _build_active_question_context(
    state: Mapping[str, Any],
    active_field_id: Any,
    form_context: Mapping[str, Any],
) -> dict[str, Any] | None:
    active_id = str(active_field_id or "").strip()
    if not active_id:
        return None
    fields = form_context.get("fields") if isinstance(form_context.get("fields"), list) else []

    geometry_match = _GEOMETRY_ACTIVE_FIELD_RE.fullmatch(active_id)
    if geometry_match is not None:
        collection, raw_index, field_key = geometry_match.groups()
        form_id = active_id if collection == "base_product" else f"geometry.comparison_products[].{field_key}"
        field = next((item for item in fields if isinstance(item, Mapping) and item.get("field_id") == form_id), {})
        return {
            "active_field_id": active_id,
            "parent_group": "해석 제품",
            "parent_group_key": "geometry",
            "field_key": field_key,
            "field_label": deepcopy(field.get("label", field_key)),
            "object_role": "Base 제품" if collection == "base_product" else _geometry_reference("comparison", int(raw_index) + 1),
        }

    if active_id.startswith("conditions."):
        parts = active_id.split(".")
        if len(parts) != 3:
            return None
        _section, card_id, field_key = parts
        card_list = _active_condition_sets(state)
        card = next(
            (item for item in card_list if isinstance(item, Mapping) and str(item.get("id") or "").strip() == card_id),
            None,
        )
        if not isinstance(card, Mapping):
            return None
        card_type = str(card.get("type") or "").strip()
        same_type = [item for item in card_list if isinstance(item, Mapping) and item.get("type") == card_type]
        object_index = next((index for index, item in enumerate(same_type, 1) if item is card), 1)
        field = next((item for item in fields if isinstance(item, Mapping) and item.get("field_id") == active_id), {})
        payload: dict[str, Any] = {
            "active_field_id": active_id,
            "parent_group": _CONDITION_GROUP_LABELS.get(card_type, card_type),
            "parent_group_key": card_type,
            "field_key": field_key,
            "field_label": deepcopy(field.get("label", field_key)),
            "object_index": object_index,
            "object_count": len(same_type),
        }
        if card_type == "operating":
            fans = card.get("fans") if isinstance(card.get("fans"), list) else []
            payload["simultaneous_components"] = {
                "kind": "fans",
                "count": len(fans),
                "items": deepcopy(fans),
            }
        return payload
    return None


def build_agent_context(
    current_message: Any,
    conversation_snapshot: ConversationSnapshot,
    request_snapshot: RequestStateSnapshot,
    *,
    has_pending_proposal: bool | None = None,
    deferred_input: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one detached Agent Context from caller-supplied snapshots only."""

    if conversation_snapshot.request_id != request_snapshot.request_id:
        raise ValueError("conversation and request snapshots reference different request_ids")

    state = request_snapshot.state
    validation = validate_state(state)
    form_context = build_form_context(state).to_dict()
    return {
        "current_message": deepcopy(current_message),
        "conversation": {
            "recent_turns": deepcopy(conversation_snapshot.recent_turns),
            "active_field_id": deepcopy(conversation_snapshot.active_field_id),
            "pending_write_candidates": deepcopy(conversation_snapshot.pending_write_candidates),
        },
        "request_deferred_input": deepcopy(dict(deferred_input)) if isinstance(deferred_input, Mapping) else {
            "facts": [],
            "ready": [],
        },
        "workflow": {
            "workflow_status": deepcopy(conversation_snapshot.workflow_status),
            "has_pending_proposal": (
                conversation_snapshot.pending_proposal_id is not None
                if has_pending_proposal is None
                else bool(has_pending_proposal)
            ),
        },
        "request_state": _project_request_state(state),
        "instance_context": _build_instance_context(state),
        "active_question": _build_active_question_context(
            state,
            conversation_snapshot.active_field_id,
            form_context,
        ),
        "form_context": form_context,
        "validation": {
            "summary": deepcopy(validation.get("summary", {})),
            "blocking": deepcopy(validation.get("blocking", [])),
            "warning": deepcopy(validation.get("warning", [])),
        },
        "submission_process": _build_submission_process(validation),
    }
