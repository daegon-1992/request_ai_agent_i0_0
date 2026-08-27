from copy import deepcopy

import pytest

from request_ai_agent_i0_0.agent_context import build_agent_context
from request_ai_agent_i0_0.condition_fieldsets import make_condition_card
from request_ai_agent_i0_0.constants import SUBMISSION_CONTACT
from request_ai_agent_i0_0.conversation_store import ConversationSnapshot
from request_ai_agent_i0_0.request_state_store import RequestStateSnapshot
from request_ai_agent_i0_0.state import create_initial_state, sanitize_complete_product
from request_ai_agent_i0_0.validator import validate_state


def _snapshots(*, context_locked=True):
    state = create_initial_state()
    state["request_context"].update(
        {
            "taxonomy_id": "PTX-ADA7A057CA62",
            "taxonomy_version": "2026-08-23",
            "division": "RAC",
            "product_lineup": "Wall Mounted",
            "platform": "Wall Mounted",
            "chassis": "SK",
            "display_path": "RAC > Wall Mounted > Wall Mounted > SK",
            "analysis_type": "풍량",
            "operation_mode": "standard",
            "context_locked": context_locked,
            "condition_fieldset_key": "derived_key",
            "condition_fieldset_snapshot": [{"derived": True}],
        }
    )
    state["geometry"]["comparison_products"] = [
        sanitize_complete_product(
            {
                "geometry_id": "comparison_001",
                "drawing_no": "DRAW-B",
                "difference_from_base": "토출부 변경",
            },
            role="comparison",
            index=1,
        )
    ]
    state["conditions"]["condition_sets"] = [
        make_condition_card("operating", 1),
        make_condition_card("operating", 2),
        make_condition_card("heat_exchanger", 1),
        make_condition_card("heat_exchanger", 2),
    ]
    state["case_matrix"]["rows"] = [
        {
            "case_id": "case_001",
            "geometry_id": "base_001",
            "auto_geometry_id": "base_001",
            "condition_values": {"fan": "운전 1", "heat_exchanger": "사양 1"},
            "visible_cells": {"geometry_id": "형상 1"},
        }
    ]
    state["metadata"]["chat_history"] = [{"role": "user", "content": "합치지 마세요"}]
    state["review"]["validator"] = {
        "summary": {"blocking_count": 999},
        "blocking": [{"code": "stale"}],
        "warning": [],
    }

    request = RequestStateSnapshot(request_id="request_a", version=7, state=state)
    conversation = ConversationSnapshot(
        conversation_id="conversation_a",
        request_id="request_a",
        workflow_status="awaiting_answer",
        pending_proposal_id="proposal_a",
        question_history=["과거 질문"],
        paused=False,
        summary="internal summary",
        version=4,
        status="active",
        recent_turns=[
            {"role": "assistant", "content": "Fan 회전수를 알려주세요."},
            {"role": "user", "content": "780 RPM"},
        ],
        active_field_id="conditions.operating_1.fan_rpm",
    )
    return conversation, request


def test_builds_detached_common_agent_context_from_current_snapshots():
    conversation, request = _snapshots()
    conversation_before = deepcopy(conversation)
    request_before = deepcopy(request)

    context = build_agent_context("비교 형상도 추가할게요.", conversation, request)

    assert set(context) == {
        "current_message",
        "conversation",
        "workflow",
        "request_state",
        "instance_context",
        "active_question",
        "form_context",
        "validation",
        "submission_process",
        "request_deferred_input",
    }
    assert context["request_deferred_input"] == {"facts": [], "ready": []}
    assert context["current_message"] == "비교 형상도 추가할게요."
    assert context["conversation"] == {
        "recent_turns": conversation.recent_turns,
        "active_field_id": "conditions.operating_1.fan_rpm",
        "pending_write_candidates": [],
    }
    assert context["current_message"] not in context["conversation"]["recent_turns"]
    assert context["workflow"] == {
        "workflow_status": "awaiting_answer",
        "has_pending_proposal": True,
    }

    projected = context["request_state"]
    assert projected["request_context"] == {
        "taxonomy_id": "PTX-ADA7A057CA62",
        "taxonomy_version": "2026-08-23",
        "division": "RAC",
        "product_lineup": "Wall Mounted",
        "platform": "Wall Mounted",
        "chassis": "SK",
        "display_path": "RAC > Wall Mounted > Wall Mounted > SK",
        "analysis_type": "풍량",
        "operation_mode": "standard",
        "context_locked": True,
    }
    assert projected["basic_info"] == request.state["basic_info"]
    assert projected["analysis_overview"] == request.state["analysis_overview"]
    assert projected["geometry"] == {
        "base_product": request.state["geometry"]["base_product"],
        "comparison_products": request.state["geometry"]["comparison_products"],
    }
    assert projected["conditions"] == {
        "mode": request.state["conditions"]["mode"],
        "condition_sets": request.state["conditions"]["condition_sets"],
    }
    assert projected["case_matrix"] == {
        "rows": [
            {
                "case_id": "case_001",
                "geometry_id": "base_001",
                "condition_values": {"fan": "운전 1", "heat_exchanger": "사양 1"},
            }
        ]
    }

    assert context["instance_context"] == {
        "geometry": {"Base 제품": "base_001", "비교 제품": "comparison_001"},
        "operating_conditions": {"첫 번째 운전 조건": "operating_1", "두 번째 운전 조건": "operating_2"},
        "heat_exchangers": {"첫 번째 열교환기 사양": "heat_exchanger_1", "두 번째 열교환기 사양": "heat_exchanger_2"},
        "space_environments": {},
        "supply_air_conditions": {},
    }
    assert context["active_question"] == {
        "active_field_id": "conditions.operating_1.fan_rpm",
        "parent_group": "운전 조건",
        "parent_group_key": "operating",
        "field_key": "fan_rpm",
        "field_label": "운전 1 팬 회전수(RPM)",
        "object_index": 1,
        "object_count": 2,
        "simultaneous_components": {
            "kind": "fans",
            "count": 1,
            "items": request.state["conditions"]["condition_sets"][0]["fans"],
        },
    }
    assert context["form_context"]["form_id"] == "analysis_request"

    current_validation = validate_state(request.state)
    assert context["validation"] == {
        "summary": current_validation["summary"],
        "blocking": current_validation["blocking"],
        "warning": current_validation["warning"],
    }
    assert context["submission_process"] == {
        "required_input_complete": current_validation["summary"]["can_submit"],
        "required_input_status_meaning": "필수 입력 충족 여부이며 실제 제출 완료 여부가 아님",
        "next_action": None,
        "remaining_steps": [
            {"key": "case_matrix_review", "action": "Case Matrix 확인"},
            {"key": "full_preview_review", "action": "전체 확인 화면에서 의뢰서 미리보기 검토"},
            {"key": "word_generation", "action": "의뢰서 생성(Word)"},
            {"key": "email_submission", "action": "생성한 Word 파일 이메일 제출"},
        ],
        "submission": {
            "method": "email",
            "direct_screen_submission_available": False,
            "recipient": SUBMISSION_CONTACT,
        },
    }
    assert context["validation"]["summary"] != request.state["review"]["validator"]["summary"]

    assert "metadata" not in projected
    assert "review" not in projected
    assert "legacy_internal" not in projected
    assert "axis" not in projected["geometry"]
    assert "axis" not in projected["conditions"]
    assert "visible_cells" not in projected["case_matrix"]["rows"][0]
    assert "auto_geometry_id" not in projected["case_matrix"]["rows"][0]
    for excluded in ("condition_fieldset_key", "condition_fieldset_snapshot"):
        assert excluded not in projected["request_context"]

    context["conversation"]["recent_turns"][0]["content"] = "forged"
    context["request_state"]["basic_info"].clear()
    context["request_state"]["conditions"]["condition_sets"][0]["id"] = "forged"
    context["form_context"]["fields"].clear()
    context["validation"]["blocking"].clear()
    assert conversation == conversation_before
    assert request == request_before


@pytest.mark.parametrize("context_locked", [False, True])
def test_request_context_preserves_canonical_lock_state_and_excludes_fieldset_derivatives(context_locked):
    conversation, request = _snapshots(context_locked=context_locked)

    projected = build_agent_context("message", conversation, request)["request_state"]["request_context"]

    assert projected["context_locked"] is context_locked
    assert "condition_fieldset_key" not in projected
    assert "condition_fieldset_snapshot" not in projected


def test_rejects_snapshots_linked_to_different_requests():
    conversation, request = _snapshots()
    mismatched = RequestStateSnapshot(request_id="request_b", version=request.version, state=request.state)

    with pytest.raises(ValueError, match="different request_ids"):
        build_agent_context("message", conversation, mismatched)
