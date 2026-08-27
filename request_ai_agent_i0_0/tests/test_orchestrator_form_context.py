from copy import deepcopy

import pytest

import request_ai_agent_i0_0.form_context as form_context_module
from request_ai_agent_i0_0.condition_fieldsets import make_condition_card
from request_ai_agent_i0_0.field_registry import get_field_registry
from request_ai_agent_i0_0.form_context import ANALYSIS_TYPE_CONTEXT, build_form_context
from request_ai_agent_i0_0.heat_exchanger_catalog import HeatExchangerCatalogError
from request_ai_agent_i0_0.state import create_initial_state


ANALYSIS_TYPE_FIELD_EXAMPLES = {
    "풍량": (
        "예: 그릴 형상 변경 후 풍량 저하가 우려되어 검토가 필요합니다.",
        "예: 기존 제품과 변경 제품의 풍량 차이를 확인하고 싶습니다.",
    ),
    "기류 패턴": (
        "예: 토출 기류가 한쪽 방향으로 편중되어 유동 상태 확인이 필요합니다.",
        "예: 기류 분포와 편중 영역을 기존안과 변경안에서 비교하고 싶습니다.",
    ),
    "이슬맺힘": (
        "예: 토출부 주변에 이슬맺힘이 반복되어 발생 현상 검토가 필요합니다.",
        "예: 이슬맺힘 발생 영역과 개선안별 차이를 확인하고 싶습니다.",
    ),
    "열교환기 유속 프로파일": (
        "예: 열교환기 전면의 유속 편차가 우려되어 분포 확인이 필요합니다.",
        "예: 열교환기 전면의 위치별 유속 분포와 편차를 확인하고 싶습니다.",
    ),
}


def _locked_state(analysis_type="이슬맺힘"):
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
            "analysis_type": analysis_type,
            "context_locked": True,
        }
    )
    return state


def _by_id(context):
    return {field.field_id: field for field in context.fields}


def _set_card_field(card, field_key, value):
    card["fields"][field_key].update(
        {
            "value": value,
            "display_value": value,
            "status": "provided" if value else "missing",
        }
    )


def test_form_context_has_complete_minimum_metadata_and_excludes_internal_registry_fields():
    context = build_form_context(_locked_state())
    fields = _by_id(context)

    assert context.form_id == "analysis_request"
    assert context.title == "해석의뢰서"
    assert context.to_dict()["analysis_type_context"]["selected_type"] == "이슬맺힘"
    assert "request_context.division" in fields
    assert "request_context.product_lineup" in fields
    assert "request_context.chassis" in fields
    assert "analysis_overview.request_description" in fields
    assert "geometry.base_product.drawing_no" in fields
    assert "conditions.operating_1.fan_rpm" in fields
    assert "request_context.context_locked" not in fields
    assert "request_context.condition_fieldset_snapshot" not in fields
    for field in context.fields:
        payload = field.to_dict()
        expected_keys = {
            "field_id", "screen", "section", "label", "description",
            "example", "required", "unit", "system_generated", "read_only",
        }
        if field.allowed_values:
            expected_keys.update({"allowed_values", "allow_custom_input"})
        elif field.allow_custom_input:
            expected_keys.add("allow_custom_input")
        assert set(payload) == expected_keys
        assert all(payload[key] for key in ("field_id", "screen", "section", "label", "description"))
        assert isinstance(payload["example"], str)
        assert isinstance(payload["required"], bool)
        assert isinstance(payload["unit"], str)
        assert isinstance(payload["system_generated"], bool)
        assert isinstance(payload["read_only"], bool)


def test_llm_facing_screen_names_use_navigation_labels_without_internal_ids():
    fields = _by_id(build_form_context(_locked_state()))

    assert ANALYSIS_TYPE_CONTEXT["screen"] == "01 의뢰 대상·시작"
    assert all("SCREEN-" not in field.screen for field in fields.values())
    assert fields["request_context.division"].screen == "01 의뢰 대상·시작"
    assert fields["analysis_overview.project_name"].screen == "02 요청 내용"
    assert fields["geometry.base_product.drawing_no"].screen == "03 해석 제품"
    assert fields["conditions.operating_1.fan_rpm"].screen == "04 해석 조건"


def test_choice_fields_reuse_dropdown_options_for_llm_context():
    fields = _by_id(build_form_context(_locked_state()))

    project_name = fields["analysis_overview.project_name"].to_dict()
    assert project_name["allowed_values"] == ["미정"]
    assert project_name["allow_custom_input"] is True

    development_grade = fields["analysis_overview.development_grade"].to_dict()
    assert development_grade["allowed_values"] == ["A", "B", "Ca", "Cb", "Cc", "선행", "미정"]
    assert development_grade["allow_custom_input"] is True

    npi_stage = fields["analysis_overview.npi_stage"].to_dict()
    assert npi_stage["allowed_values"] == ["CP", "DV", "PV", "MP", "미정"]
    assert npi_stage["allow_custom_input"] is True

    model_suffix = fields["analysis_overview.model_suffix"].to_dict()
    assert model_suffix["allowed_values"] == ["미정"]
    assert model_suffix["allow_custom_input"] is True


def test_form_context_reuses_registry_requirement_units_and_existing_guidance():
    state = _locked_state()
    context = _by_id(build_form_context(state))
    registry = {field.field_id: field for field in get_field_registry(state)}

    request_description = context["analysis_overview.request_description"]
    assert request_description.label == registry[request_description.field_id].label
    assert request_description.required == registry[request_description.field_id].required is True
    assert request_description.description == "이번 해석을 의뢰하게 된 문제, 현상, 설계 변경 또는 검토 배경을 작성합니다."
    assert request_description.example == ANALYSIS_TYPE_FIELD_EXAMPLES["이슬맺힘"][0]

    additional_request = context["analysis_overview.additional_result_request"]
    assert additional_request.description == "이번 해석 결과를 통해 확인하거나 비교하고 싶은 내용을 작성합니다."
    assert additional_request.example == ANALYSIS_TYPE_FIELD_EXAMPLES["이슬맺힘"][1]

    fan = context["conditions.operating_1.fan_rpm"]
    assert fan.required == registry[fan.field_id].required
    assert fan.unit == registry[fan.field_id].unit == "RPM"
    assert fan.example == "예: 780"
    assert fan.description == "해당 Fan의 회전수 조건입니다. 해당 운전 조건에서 적용할 회전수를 입력합니다."


def test_form_context_uses_current_active_fieldset_without_mutating_state():
    state = _locked_state("풍량")
    before = deepcopy(state)

    fields = _by_id(build_form_context(state))

    assert state == before
    assert "conditions.space_environment_1.room_temp" not in fields
    assert "conditions.supply_air_1.heat_exchanger_temp" not in fields
    assert "conditions.space_environment_1.room_rh" not in fields
    assert "conditions.supply_air_1.heat_exchanger_rh" not in fields
    assert fields["geometry.comparison_products[].difference_from_base"].required is True
    assert fields["geometry.comparison_products[].difference_from_base"].section == "총 조립 형상"


def test_geometry_form_context_describes_total_assembly_and_existing_difference():
    fields = _by_id(build_form_context(_locked_state()))

    base = fields["geometry.base_product.drawing_no"]
    comparison = fields["geometry.comparison_products[].drawing_no"]
    difference = fields["geometry.comparison_products[].difference_from_base"]
    assert base.screen == comparison.screen == difference.screen == "03 해석 제품"
    assert base.section == comparison.section == difference.section == "총 조립 형상"
    assert base.label == comparison.label == "총조립도 도면번호 (NPDM MCAD)"
    assert difference.label == "Base 대비 변경점"
    assert "총 조립 형상" in base.description
    assert "각각 다른 도면번호" in base.description
    assert "임시 도면번호" in base.description
    assert "총 조립 형상" in comparison.description
    assert "각각 다른 도면번호" in comparison.description
    assert "임시 도면번호" in comparison.description
    assert "이미 반영된" in difference.description
    assert "형상·조립 상태 차이" in difference.description
    assert base.example == "예: AJT000123 또는 TEMP-BASE-01"
    assert comparison.example == "예: AJT000234 또는 TEMP-COMP-01"
    assert difference.example == "예: 베인 각도 30° 적용, Fan 위치 상향 20 mm"


@pytest.mark.parametrize(
    "analysis_type",
    ["기류 패턴"],
)
def test_temperature_fields_expose_value_or_none_fieldset_metadata(analysis_type):
    fields = _by_id(build_form_context(_locked_state(analysis_type)))

    for field_id in (
        "conditions.space_environment_1.room_temp",
        "conditions.supply_air_1.heat_exchanger_temp",
    ):
        assert fields[field_id].allowed_values == ("없음",)
        assert fields[field_id].allow_custom_input is True
        assert fields[field_id].required is True


@pytest.mark.parametrize("analysis_type", ["풍량", "열교환기 유속 프로파일"])
def test_non_temperature_analysis_types_omit_temperature_fields(analysis_type):
    fields = _by_id(build_form_context(_locked_state(analysis_type)))

    assert "conditions.space_environment_1.room_temp" not in fields
    assert "conditions.supply_air_1.heat_exchanger_temp" not in fields


def test_dew_temperature_fields_do_not_expose_value_or_none_metadata():
    fields = _by_id(build_form_context(_locked_state("이슬맺힘")))

    for field_id in (
        "conditions.space_environment_1.room_temp",
        "conditions.supply_air_1.heat_exchanger_temp",
    ):
        assert fields[field_id].allowed_values == ()
        assert fields[field_id].allow_custom_input is False


def test_unselected_analysis_type_exposes_the_full_catalog_without_defaulting_form_context_to_dew():
    state = create_initial_state()
    before = deepcopy(state)

    context = build_form_context(state)
    fields = _by_id(context)
    semantic = context.analysis_type_context

    assert state == before
    assert semantic["selected_type"] == ""
    assert semantic["selected_option"] is None
    assert semantic["selected_type_supported"] is False
    assert semantic["options"] == ANALYSIS_TYPE_CONTEXT["options"]
    assert semantic["selectable_options"] == ["풍량", "기류 패턴", "이슬맺힘", "열교환기 유속 프로파일"]
    assert not any(field_id.startswith("conditions.") for field_id in fields)
    assert fields["analysis_overview.request_description"].example == "예: 설계 변경 후 성능 저하 현상이 발생하여 원인 검토가 필요합니다."
    assert fields["analysis_overview.additional_result_request"].example == "예: 기존안과 변경안의 결과 차이와 개선 효과를 확인하고 싶습니다."


@pytest.mark.parametrize(
    "analysis_type",
    ["풍량", "기류 패턴", "이슬맺힘", "열교환기 유속 프로파일"],
)
def test_available_analysis_type_overlays_semantics_and_request_examples(analysis_type):
    context = build_form_context(_locked_state(analysis_type))
    fields = _by_id(context)
    semantic = context.analysis_type_context
    expected = ANALYSIS_TYPE_CONTEXT["options"][analysis_type]

    assert semantic["selected_type"] == analysis_type
    assert semantic["selected_type_supported"] is True
    assert semantic["selected_option"] == expected
    assert set(("description", "what_can_be_checked", "suitable_when", "example_request", "distinction")) <= set(expected)
    assert fields["analysis_overview.request_description"].example == ANALYSIS_TYPE_FIELD_EXAMPLES[analysis_type][0]
    assert fields["analysis_overview.additional_result_request"].example == ANALYSIS_TYPE_FIELD_EXAMPLES[analysis_type][1]
    assert any(field_id.startswith("conditions.") for field_id in fields)


def test_planned_types_remain_semantically_visible_but_not_selectable_or_supported_form_flows():
    planned = {
        name: option
        for name, option in ANALYSIS_TYPE_CONTEXT["options"].items()
        if option["availability"] == "planned"
    }
    assert set(planned) == {"기류도달거리", "PDB", "실사용 해석", "집진해석(먼지거동)", "PCB발열", "다상유동"}
    assert all(option["selectable"] is False for option in planned.values())

    context = build_form_context(_locked_state("PDB"))
    fields = _by_id(context)
    semantic = context.analysis_type_context

    assert semantic["selected_type"] == "PDB"
    assert semantic["selected_type_supported"] is False
    assert semantic["selected_option"] == {
        "availability": "planned",
        "selectable": False,
        "description": "세부 업무 정의가 아직 Context에 등록되지 않은 개발 예정 해석유형입니다.",
        "agent_behavior": "PDB의 의미를 임의로 해석하거나 설명하지 않습니다. 현재 지원하지 않는 해석유형임을 안내합니다.",
    }
    assert "PDB" not in semantic["selectable_options"]
    assert not any(field_id.startswith("conditions.") for field_id in fields)


@pytest.mark.parametrize("analysis_type", ["풍량", "이슬맺힘"])
def test_system_generated_heat_exchanger_names_are_read_only_but_user_condition_fields_are_not(analysis_type):
    state = _locked_state(analysis_type)
    state["conditions"]["condition_sets"].append(make_condition_card("heat_exchanger", 2))

    fields = _by_id(build_form_context(state))

    for field_id in (
        "conditions.heat_exchanger_1.name",
        "conditions.heat_exchanger_2.name",
    ):
        assert fields[field_id].system_generated is True
        assert fields[field_id].read_only is True

    fan = fields["conditions.operating_1.fan_rpm"]
    assert fan.system_generated is False
    assert fan.read_only is False


def test_heat_exchanger_catalog_values_follow_card_type_and_other_entered_fields():
    state = _locked_state()
    card = next(card for card in state["conditions"]["condition_sets"] if card["type"] == "heat_exchanger")
    _set_card_field(card, "tube_diameter", "5PI")
    _set_card_field(card, "fin_type", "Slit(Half)")
    _set_card_field(card, "row_count", "2R")

    fields = _by_id(build_form_context(state))
    fpi = fields["conditions.heat_exchanger_1.fpi"]
    assert fpi.allowed_values == ("20", "21", "22")
    assert fpi.allow_custom_input is True

    card["heat_exchanger_type"] = "Micro-Channel"
    _set_card_field(card, "tube_diameter", "W16")
    _set_card_field(card, "fin_type", "Flat")
    _set_card_field(card, "row_count", "2")
    _set_card_field(card, "fpi", "75")

    micro_fields = _by_id(build_form_context(state))
    fin_type = micro_fields["conditions.heat_exchanger_1.fin_type"]
    assert fin_type.allowed_values == ("Flat",)
    assert fin_type.read_only is True
    assert fin_type.allow_custom_input is False
    assert micro_fields["conditions.heat_exchanger_1.fpi"].allowed_values == ("75",)
    assert micro_fields["conditions.heat_exchanger_1.fpi"].allow_custom_input is True


def test_heat_exchanger_form_context_remains_custom_writable_when_catalog_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        form_context_module,
        "load_heat_exchanger_catalog",
        lambda: (_ for _ in ()).throw(HeatExchangerCatalogError("unavailable")),
    )

    fields = _by_id(build_form_context(_locked_state()))
    for field_key in ("tube_diameter", "fin_type", "row_count", "fpi"):
        field = fields[f"conditions.heat_exchanger_1.{field_key}"]
        assert field.allowed_values == ()
        assert field.allow_custom_input is True
        assert field.read_only is False
        assert "allowed_values" not in field.to_dict()
