from request_ai_agent_i0_0.agent_decision import proposal_changes
from request_ai_agent_i0_0.chat_patch import apply_patch_operations
from request_ai_agent_i0_0.state import create_initial_state, sanitize_state


def _state():
    state = create_initial_state()
    state["request_context"].update(
        {
            "business_unit": "RAC",
            "product_group": "벽걸이",
            "platform": "SK",
            "analysis_type": "열교환기 유속 프로파일",
            "context_locked": True,
        }
    )
    return sanitize_state(state)


def test_product_list_proposal_is_split_by_canonical_geometry():
    current = _state()
    proposed = apply_patch_operations(
        current,
        [{"op": "list_values", "path": "geometry.products", "values": ["AJT123123", "T-123123"]}],
    )

    assert proposal_changes(current, proposed) == [
        {
            "label": "형상 1 · 총조립도 도면번호 (NPDM MCAD)",
            "current_value": "",
            "new_value": "AJT123123",
        },
        {
            "label": "형상 2 · 총조립도 도면번호 (NPDM MCAD)",
            "current_value": "",
            "new_value": "T-123123",
        },
    ]


def test_condition_series_proposal_is_split_by_canonical_cards():
    current = _state()
    proposed = apply_patch_operations(
        current,
        [
            {
                "op": "set_condition_card_series",
                "card_type": "operating",
                "field_key": "fan_rpm",
                "values": ["1500", "1800"],
            }
        ],
    )

    assert proposal_changes(current, proposed) == [
        {"label": "운전 1 · 팬 회전수(RPM)", "current_value": "", "new_value": "1500"},
        {"label": "운전 2 · 팬 회전수(RPM)", "current_value": "", "new_value": "1800"},
    ]


def test_single_field_proposal_keeps_existing_display():
    current = _state()
    proposed = apply_patch_operations(
        current,
        [{"op": "set", "path": "analysis_overview.project_name", "value": "PROJECT-X"}],
    )

    assert proposal_changes(current, proposed) == [
        {"label": "프로젝트명(PMS)", "current_value": "", "new_value": "PROJECT-X"}
    ]
