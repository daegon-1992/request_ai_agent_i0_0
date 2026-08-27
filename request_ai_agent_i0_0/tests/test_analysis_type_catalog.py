from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.condition_fieldsets import (
    build_condition_fieldset,
    default_condition_sets,
    sanitize_condition_sets,
)
from request_ai_agent_i0_0.constants import (
    ANALYSIS_TYPE_OPTIONS,
    DISABLED_ANALYSIS_TYPE_OPTIONS,
    ENABLED_ANALYSIS_TYPE_OPTIONS,
)
from request_ai_agent_i0_0.state import create_initial_state, sanitize_state
from request_ai_agent_i0_0.ui import HTML_TEMPLATE


EXPECTED_ANALYSIS_TYPES = (
    "풍량",
    "기류 패턴",
    "이슬맺힘",
    "열교환기 유속 프로파일",
    "기류도달거리",
    "PDB",
    "실사용 해석",
    "집진해석(먼지거동)",
    "PCB발열",
    "다상유동",
)


def test_analysis_type_catalog_replaces_removed_flow_types():
    assert "일반 유동 해석" not in ANALYSIS_TYPE_OPTIONS
    assert "열유동 해석" not in ANALYSIS_TYPE_OPTIONS
    assert ANALYSIS_TYPE_OPTIONS == EXPECTED_ANALYSIS_TYPES
    assert "기류 패턴" in ENABLED_ANALYSIS_TYPE_OPTIONS
    assert "풍량" in ENABLED_ANALYSIS_TYPE_OPTIONS
    assert set(DISABLED_ANALYSIS_TYPE_OPTIONS) == set(EXPECTED_ANALYSIS_TYPES) - {
        "풍량",
        "기류 패턴",
        "이슬맺힘",
        "열교환기 유속 프로파일",
    }


def test_first_screen_analysis_types_follow_catalog_order():
    expected = '["풍량","기류 패턴","이슬맺힘","열교환기 유속 프로파일","기류도달거리","PDB","실사용 해석","집진해석(먼지거동)","PCB발열","다상유동"]'
    assert f"const prepAnalysisTypes = {expected}" in HTML_TEMPLATE


def test_analysis_types_use_their_matching_condition_policy():
    general = build_condition_fieldset({"analysis_type": "일반 유동 해석"})
    thermal = build_condition_fieldset({"analysis_type": "열유동 해석"})
    airflow_pattern = build_condition_fieldset({"analysis_type": "기류 패턴"})
    air_volume = build_condition_fieldset({"analysis_type": "풍량"})
    hex_profile = build_condition_fieldset({"analysis_type": "열교환기 유속 프로파일"})

    assert airflow_pattern["field_keys"] == thermal["field_keys"]
    assert air_volume["field_keys"] == general["field_keys"]
    assert hex_profile["field_keys"] == general["field_keys"]


def test_air_volume_and_hex_profile_exclude_room_and_supply_temperature_conditions():
    for analysis_type in ("풍량", "열교환기 유속 프로파일"):
        fieldset = build_condition_fieldset({"analysis_type": analysis_type})
        assert set(fieldset["field_keys"]).isdisjoint(
            {"room_temp", "room_rh", "heat_exchanger_temp", "heat_exchanger_rh"}
        )
        assert {card["type"] for card in default_condition_sets({"analysis_type": analysis_type})} == {
            "operating",
            "heat_exchanger",
        }


def test_airflow_pattern_keeps_temperature_without_humidity():
    fieldset = build_condition_fieldset({"analysis_type": "기류 패턴"})
    assert {"room_temp", "heat_exchanger_temp"} <= set(fieldset["field_keys"])
    assert set(fieldset["field_keys"]).isdisjoint({"room_rh", "heat_exchanger_rh"})


def test_saved_air_volume_request_refreshes_old_temperature_policy():
    state = create_initial_state()
    state["request_context"].update(
        {
            "analysis_type": "풍량",
            "condition_fieldset_snapshot": build_condition_fieldset({"analysis_type": "기류 패턴"})["groups"],
        }
    )
    state["conditions"]["condition_sets"] = default_condition_sets({"analysis_type": "기류 패턴"})

    cleaned = sanitize_state(state)

    active_groups = {
        group["key"]
        for group in cleaned["request_context"]["condition_fieldset_snapshot"]
        if group["active"]
    }
    assert active_groups == {"operating", "heat_exchanger"}
    assert {card["type"] for card in cleaned["conditions"]["condition_sets"]} == active_groups


def test_temperature_value_or_none_policy_is_fieldset_metadata_for_temperature_types_only():
    fieldset = build_condition_fieldset({"analysis_type": "기류 패턴"})
    fields = {
        field["key"]: field
        for group in fieldset["groups"]
        for field in group["fields"]
    }
    for field_key in ("room_temp", "heat_exchanger_temp"):
        assert fields[field_key]["allowed_values"] == ["없음"]
        assert fields[field_key]["allow_custom_input"] is True

    dew_fields = {
        field["key"]: field
        for group in build_condition_fieldset({"analysis_type": "이슬맺힘"})["groups"]
        for field in group["fields"]
    }
    for field_key in ("room_temp", "heat_exchanger_temp"):
        assert "allowed_values" not in dew_fields[field_key]
        assert "allow_custom_input" not in dew_fields[field_key]

    for analysis_type in ("풍량", "열교환기 유속 프로파일"):
        fields = {
            field["key"]: field
            for group in build_condition_fieldset({"analysis_type": analysis_type})["groups"]
            for field in group["fields"]
        }
        for field_key in ("room_temp", "heat_exchanger_temp"):
            assert fields[field_key]["active"] is False
            assert "allowed_values" not in fields[field_key]
            assert "allow_custom_input" not in fields[field_key]


def test_temperature_inputs_offer_direct_entry_or_none_and_store_none_as_provided():
    assert "temperatureAnalysisTypes" not in HTML_TEMPLATE
    assert "temperatureFieldKeys" not in HTML_TEMPLATE
    assert "fieldsetInputMetadata" in HTML_TEMPLATE
    assert 'asArray(metadata.allowed_values).map(contextText).includes("없음")' in HTML_TEMPLATE
    assert 'data-undecided-value="없음"' in HTML_TEMPLATE
    assert '>직접 입력</button><button class="undecided-combobox-option"' in HTML_TEMPLATE
    assert '>없음</button>' in HTML_TEMPLATE
    assert 'wireUndecidedComboboxes($("conditionFields"));' in HTML_TEMPLATE
    assert HTML_TEMPLATE.count("온도 조건에 따라 해석 결과가 달라질 수 있으므로, 확인된 온도 조건이 있다면 입력해 주세요.") == 1
    assert HTML_TEMPLATE.count("별도 온도 조건이 없는 경우에만 ‘없음’을 선택해 주세요.") == 1
    assert '입력해 주세요.")}<br>${esc("별도 온도 조건이' in HTML_TEMPLATE
    guidance_css = HTML_TEMPLATE.split(
        ".workspace-shell .condition-input-screen .condition-temperature-guidance{", 1
    )[1].split("}", 1)[0]
    assert "margin:-10px 0 0" in guidance_css
    assert "color:#55585B" in guidance_css
    assert "font-size:13px" in guidance_css
    assert "font-weight:400" in guidance_css
    assert "line-height:1.55" in guidance_css
    render_order = HTML_TEMPLATE.rsplit('$("conditionFields").innerHTML = ', 1)[1].split(";", 1)[0]
    assert render_order.index("condition-primary-grid") < render_order.index("condition-environment-grid")
    assert render_order.index("condition-environment-grid") < render_order.index("temperatureGuidance")

    context = {"analysis_type": "기류 패턴"}
    cards = default_condition_sets(context)
    for card in cards:
        if card["type"] == "space_environment":
            card["fields"]["room_temp"] = "없음"
        elif card["type"] == "supply_air":
            card["fields"]["heat_exchanger_temp"] = "없음"
    cleaned = sanitize_condition_sets(cards, context)
    temperatures = {
        key: value
        for card in cleaned
        for key, value in card["fields"].items()
        if key in {"room_temp", "heat_exchanger_temp"}
    }
    assert temperatures["room_temp"]["value"] == "없음"
    assert temperatures["room_temp"]["status"] == "provided"
    assert temperatures["heat_exchanger_temp"]["value"] == "없음"
    assert temperatures["heat_exchanger_temp"]["status"] == "provided"


def test_temperature_none_menu_is_not_clipped_by_environment_cards():
    assert '.condition-card-type-space_environment,.condition-card-type-supply_air{overflow:visible}' in HTML_TEMPLATE
    assert (
        '.condition-card-type-space_environment:focus-within,'
        '.condition-card-type-supply_air:focus-within{position:relative;z-index:45}'
        in HTML_TEMPLATE
    )
    assert '.workspace-shell .condition-input-screen > #section-conditions{' in HTML_TEMPLATE
    section_style = HTML_TEMPLATE.split(
        '.workspace-shell .condition-input-screen > #section-conditions{', 1
    )[1].split('}', 1)[0]
    assert 'overflow:visible' in section_style


def test_scheduled_analysis_types_are_disabled_and_labeled_in_both_selectors():
    assert 'const disabledAnalysisTypes = ["기류도달거리","PDB","실사용 해석","집진해석(먼지거동)","PCB발열","다상유동"]' in HTML_TEMPLATE
    assert 'disabledAnalysisTypeReason, " (예정)", true' in HTML_TEMPLATE
    assert 'disabledAnalysisTypes, " (예정)", disabledAnalysisTypeLockPrefix' in HTML_TEMPLATE


def test_scheduled_analysis_types_reuse_the_disabled_step_lock_icon():
    lock_svg = '<svg viewBox="0 0 16 16"><rect x="3" y="7" width="10" height="7" rx="1.5"></rect><path d="M5 7V5a3 3 0 0 1 6 0v2"></path></svg>'
    assert f'<span class="screen-map-lock" aria-hidden="true">{lock_svg}</span>' in HTML_TEMPLATE
    assert f'<span class="prep-choice-lock" aria-hidden="true">{lock_svg}</span>' in HTML_TEMPLATE
    assert '.prep-choice-lock svg{width:12px;height:12px;fill:none;stroke:currentColor;' in HTML_TEMPLATE
    assert r'const disabledAnalysisTypeLockPrefix = "\u{1F512}\uFE0E ";' in HTML_TEMPLATE
    assert '${disabledPrefix}${displayValue}${disabledSuffix}' in HTML_TEMPLATE


def test_api_accepts_active_types_and_rejects_scheduled_or_removed_types():
    client = create_app().test_client()

    for analysis_type in ("기류 패턴", "풍량"):
        response = client.post("/api/analysis-type/select", json={"analysis_type": analysis_type, "state": {}})
        assert response.status_code == 200
        assert response.get_json()["state"]["request_context"]["analysis_type"] == analysis_type

    scheduled = client.post("/api/analysis-type/select", json={"analysis_type": "PCB발열", "state": {}})
    assert scheduled.status_code == 400
    assert "예정" in scheduled.get_json()["message"]

    for analysis_type in ("일반 유동 해석", "열유동 해석"):
        response = client.post("/api/analysis-type/select", json={"analysis_type": analysis_type, "state": {}})
        assert response.status_code == 400
        assert response.get_json()["message"] == "지원하지 않는 해석유형입니다."
