from copy import deepcopy

import pytest

from request_ai_agent_i0_0.agent_next_question import plan_next_question
from request_ai_agent_i0_0.condition_fieldsets import default_condition_sets, make_condition_card
from request_ai_agent_i0_0.request_state_store import RequestStateSnapshot
from request_ai_agent_i0_0.state import create_initial_state, make_field, sanitize_complete_product, sanitize_state
from request_ai_agent_i0_0.validator import validate_state


def _complete_state(analysis_type="풍량"):
    state = create_initial_state()
    state["request_context"].update(
        {
            "business_unit": "RAC",
            "product_group": "벽걸이",
            "platform": "SK",
            "analysis_type": analysis_type,
            "context_locked": True,
        }
    )
    values = {
        "project_name": "T2-01B",
        "development_grade": "A",
        "npi_stage": "DV",
        "model_suffix": "MODEL-A",
        "desired_completion_date": "2026-08-25",
        "request_description": "설계 변경 검토",
        "additional_result_request": "기존안과 변경안 비교",
    }
    for key, value in values.items():
        state["analysis_overview"][key] = value
    state["geometry"]["base_product"]["drawing_no"] = "DRAW-A"

    cards = default_condition_sets(state["request_context"])
    for card in cards:
        if card["type"] == "operating":
            card["fans"][0]["values"]["fan_rpm"] = "700"
            continue
        for key, field in card["fields"].items():
            if key != "name":
                field["value"] = "1"
    state["conditions"]["condition_sets"] = cards
    state = sanitize_state(state)
    assert validate_state(state)["summary"]["can_submit"] is True
    return state


def _snapshot(state):
    return RequestStateSnapshot(request_id="request_5a", version=7, state=state)


def _card(state, card_id):
    return next(card for card in state["conditions"]["condition_sets"] if card["id"] == card_id)


def test_general_field_uses_fresh_validator_and_is_read_only():
    state = _complete_state()
    state["analysis_overview"]["project_name"] = make_field("")
    state["review"]["validator"] = {"summary": {"can_submit": True}, "blocking": []}
    snapshot = _snapshot(state)
    before = deepcopy(snapshot)

    result = plan_next_question(snapshot)

    assert result == {
        "kind": "field_question",
        "message": "프로젝트명(PMS)를 입력해 주세요. 예: 26년향 하이드로타워 대용량 가습공청기",
        "active_field_id": "analysis_overview.project_name",
        "blocking_code": "analysis_overview.project_name.required_missing",
    }
    result["message"] = "changed"
    assert snapshot == before


def test_geometry_uses_the_exact_comparison_instance_and_contract_field():
    state = _complete_state()
    state["geometry"]["comparison_products"] = [
        sanitize_complete_product(
            {
                "geometry_id": "comparison_001",
                "drawing_no": "",
                "difference_from_base": "",
            },
            role="comparison",
            index=1,
        )
    ]

    drawing_question = plan_next_question(_snapshot(state))
    assert drawing_question["active_field_id"] == "geometry.comparison_products[0].drawing_no"
    assert drawing_question["blocking_code"] == "geometry.product.drawing_no.required_missing"
    assert drawing_question["message"].startswith("비교 제품의 총조립도 도면번호 (NPDM MCAD)를 입력해 주세요.")

    state["geometry"]["comparison_products"][0]["drawing_no"] = make_field("DRAW-B")
    difference_question = plan_next_question(_snapshot(state))
    assert difference_question["active_field_id"] == "geometry.comparison_products[0].difference_from_base"
    assert difference_question["message"].startswith("비교 제품의 Base 대비 변경점을 입력해 주세요.")


def test_first_geometry_is_called_base_product():
    state = _complete_state()
    state["geometry"]["base_product"]["drawing_no"] = make_field("")

    result = plan_next_question(_snapshot(state))

    assert result["active_field_id"] == "geometry.base_product.drawing_no"
    assert result["message"].startswith("Base 제품의 총조립도 도면번호 (NPDM MCAD)를 입력해 주세요.")
    assert "기준 제품" not in result["message"]


def test_geometry_fallback_uses_screen_name(monkeypatch):
    state = _complete_state()
    validation = {
        "blocking": [
            {
                "severity": "blocking",
                "code": "geometry.synthetic_check",
                "section": "geometry",
                "path": "geometry.synthetic_check",
                "field_label": "형상 확인",
                "message": "synthetic fallback check",
            }
        ],
        "warning": [],
        "info": [],
        "summary": {"can_submit": False},
    }
    monkeypatch.setattr("request_ai_agent_i0_0.agent_next_question.validate_state", lambda _state: validation)

    result = plan_next_question(_snapshot(state))

    assert result == {
        "kind": "ui_guidance",
        "message": "해석 제품 화면에서 형상 확인 항목을 확인해 주세요.",
        "active_field_id": None,
        "blocking_code": "geometry.synthetic_check",
    }


def test_repeated_condition_instances_and_missing_fan_are_not_merged():
    state = _complete_state()
    operating_2 = make_condition_card("operating", 2)
    operating_2["fans"] = [
        {"id": "fan_1", "name": "", "location": "좌", "running": True, "values": {"fan_rpm": "800"}},
        {"id": "fan_2", "name": "", "location": "우", "running": True, "values": {"fan_rpm": ""}},
    ]
    state["conditions"]["condition_sets"].append(operating_2)
    state = sanitize_state(state)

    result = plan_next_question(_snapshot(state))

    assert result["active_field_id"] == "conditions.operating_2.fan_rpm"
    assert result["blocking_code"] == "conditions.operating_2.fan_rpm.required_missing"
    assert result["message"].startswith(
        "먼저 운전 조건을 확인하겠습니다. 두 번째 운전 조건의 두 번째 팬의 회전수(RPM) (위치: 우)를 알려주세요."
    )


@pytest.mark.parametrize(
    ("location", "rpm", "active_field_id", "question_text"),
    [
        ("", "1000", "conditions.operating_1.fan_location", "첫 번째 팬의 위치를 알려주세요."),
        ("상", "", "conditions.operating_1.fan_rpm", "첫 번째 팬의 회전수(RPM) (위치: 상)을 알려주세요."),
        ("", "", "conditions.operating_1.fan_location", "첫 번째 팬의 위치를 알려주세요."),
    ],
)
def test_individual_fan_question_asks_location_before_rpm(location, rpm, active_field_id, question_text):
    state = _complete_state()
    operating = _card(state, "operating_1")
    operating["fan_rpm_mode"] = "individual"
    operating["fans"] = [
        {"id": "fan_1", "name": "", "location": location, "running": True, "values": {"fan_rpm": rpm}},
        {"id": "fan_2", "name": "", "location": "하", "running": True, "values": {"fan_rpm": "700"}},
    ]
    state = sanitize_state(state)

    result = plan_next_question(_snapshot(state))

    assert result["active_field_id"] == active_field_id
    assert result["blocking_code"] == "conditions.operating_1.fan_rpm.required_missing"
    assert result["message"].startswith(f"먼저 운전 조건을 확인하겠습니다. {question_text}")
    assert "fan_1" not in result["message"] and "operating_1" not in result["message"]


def test_repeated_heat_exchanger_uses_the_second_instance():
    state = _complete_state()
    heat_exchanger_2 = make_condition_card("heat_exchanger", 2)
    for key, field in heat_exchanger_2["fields"].items():
        if key not in {"name", "fpi"}:
            field["value"] = "2"
    state["conditions"]["condition_sets"].append(heat_exchanger_2)
    state = sanitize_state(state)

    result = plan_next_question(_snapshot(state))

    assert result["active_field_id"] == "conditions.heat_exchanger_2.fpi"
    assert result["blocking_code"] == "conditions.heat_exchanger_2.fpi.required_missing"
    assert result["message"].startswith(
        "이제는 열교환기 사양 정보가 필요합니다. 두 번째 열교환기 사양의 FPI를 알려주세요."
    )


def test_condition_group_transition_is_not_repeated_for_follow_up_field():
    state = _complete_state()
    heat_exchanger = _card(state, "heat_exchanger_1")
    heat_exchanger["fields"]["fin_type"] = make_field("")
    heat_exchanger["fields"]["row_count"] = make_field("")

    first = plan_next_question(
        _snapshot(state),
        previous_active_field_id="conditions.operating_1.fan_rpm",
    )
    assert first["message"].startswith("이제는 열교환기 사양 정보가 필요합니다.")

    second = plan_next_question(
        _snapshot(state),
        previous_active_field_id="conditions.heat_exchanger_1.tube_diameter",
    )
    assert second["message"].startswith("Fin type을 알려주세요.")
    assert "열교환기 사양 정보가 필요합니다" not in second["message"]


@pytest.mark.parametrize(
    ("analysis_type", "card_id", "field_key", "expected"),
    [
        ("풍량", "operating_1", "fan_rpm", "먼저 운전 조건을 확인하겠습니다. 팬 회전수(RPM)를 알려주세요."),
        ("풍량", "heat_exchanger_1", "tube_diameter", "이제는 열교환기 사양 정보가 필요합니다. 관 직경을 알려주세요."),
        ("기류 패턴", "space_environment_1", "room_temp", "온도 조건에 따라 해석 결과가 달라질 수 있으므로, 확인된 온도 조건이 있다면 입력해 주세요. 별도 온도 조건이 없는 경우에만 ‘없음’을 선택해 주세요."),
        ("기류 패턴", "supply_air_1", "heat_exchanger_temp", "온도 조건에 따라 해석 결과가 달라질 수 있으므로, 확인된 온도 조건이 있다면 입력해 주세요. 별도 온도 조건이 없는 경우에만 ‘없음’을 선택해 주세요."),
    ],
)
def test_first_question_in_each_condition_group_uses_business_wording(analysis_type, card_id, field_key, expected):
    state = _complete_state(analysis_type)
    card = _card(state, card_id)
    if field_key == "fan_rpm":
        card["fans"][0]["values"][field_key] = ""
    else:
        card["fields"][field_key] = make_field("")

    result = plan_next_question(_snapshot(state))

    assert result["message"].startswith(expected)
    for internal_name in (
        "operating_1",
        "heat_exchanger_1",
        "space_environment_1",
        "supply_air_1",
        "운전 1의",
        "사양 1의",
    ):
        assert internal_name not in result["message"]


@pytest.mark.parametrize(
    "analysis_type",
    ["기류 패턴"],
)
def test_temperature_question_uses_final_guidance_for_supported_analysis_types(analysis_type):
    state = _complete_state(analysis_type)
    _card(state, "space_environment_1")["fields"]["room_temp"] = make_field("")

    result = plan_next_question(_snapshot(state))

    assert result["message"] == (
        "온도 조건에 따라 해석 결과가 달라질 수 있으므로, "
        "확인된 온도 조건이 있다면 입력해 주세요. "
        "별도 온도 조건이 없는 경우에만 ‘없음’을 선택해 주세요."
    )


@pytest.mark.parametrize(
    ("field_key", "code"),
    [
        ("heat_exchanger_1.name", "conditions.heat_exchanger_1.name.required_missing"),
        ("space_environment_1.room_rh", "conditions.space_environment_1.room_rh.required_missing"),
    ],
)
def test_system_generated_read_only_and_inactive_fields_are_not_questions(monkeypatch, field_key, code):
    state = _complete_state()
    validation = {
        "blocking": [
            {
                "severity": "blocking",
                "code": code,
                "section": "conditions",
                "path": f"conditions.fields.{field_key}.values",
                "field_key": field_key,
                "message": "synthetic exclusion check",
            }
        ],
        "warning": [],
        "info": [],
        "summary": {"can_submit": False},
    }
    monkeypatch.setattr("request_ai_agent_i0_0.agent_next_question.validate_state", lambda _state: validation)

    result = plan_next_question(_snapshot(state))

    assert result["kind"] == "ui_guidance"
    assert result["active_field_id"] is None
    assert result["blocking_code"] == code


def test_request_context_and_case_matrix_blockers_return_ui_guidance():
    request_context_state = _complete_state()
    request_context_state["request_context"]["context_locked"] = False
    request_context_result = plan_next_question(_snapshot(request_context_state))
    assert request_context_result == {
        "kind": "ui_guidance",
        "message": "의뢰 대상과 해석유형을 화면에서 확정해 주세요.",
        "active_field_id": None,
        "blocking_code": "request_context.not_locked",
    }

    case_state = _complete_state()
    case_state["case_matrix"]["rows"][0]["geometry_id"] = "missing_geometry"
    case_result = plan_next_question(_snapshot(case_state))
    assert case_result == {
        "kind": "ui_guidance",
        "message": "Case Matrix에서 실제 해석할 Case와 조건 매핑을 확인해 주세요.",
        "active_field_id": None,
        "blocking_code": "case_matrix.geometry_missing",
    }


def test_complete_comes_only_from_current_validator_summary():
    state = _complete_state()

    result = plan_next_question(_snapshot(state))

    assert result == {
        "kind": "complete",
        "message": "필수 입력이 완료되었습니다. 다음으로 Case Matrix에서 실제 해석할 Case와 조건 매핑을 확인해 주세요.",
        "active_field_id": None,
        "blocking_code": None,
    }
    assert "제출 가능" not in result["message"]
