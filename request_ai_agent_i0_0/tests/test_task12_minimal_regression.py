from __future__ import annotations

from copy import deepcopy
import importlib
from io import BytesIO
from zipfile import ZipFile

from request_ai_agent_i0_0 import create_app
from request_ai_agent_i0_0.condition_engine import generate_condition_axis
from request_ai_agent_i0_0.condition_fieldsets import (
    build_condition_fieldset,
    default_condition_sets,
    get_active_case_matrix_columns,
)
from request_ai_agent_i0_0.constants import SECTION_CASE_MATRIX, SECTION_CONDITIONS, SECTION_GEOMETRY, SECTION_REQUEST_CONTEXT, STATE_SCHEMA_VERSION
from request_ai_agent_i0_0.draft_pipeline import build_request_draft
from request_ai_agent_i0_0.llm_client import azure_openai_settings
from request_ai_agent_i0_0.preview_document import build_request_preview
from request_ai_agent_i0_0.review_pipeline import state_with_final_review
from request_ai_agent_i0_0.state import compose_request_title, create_initial_state, sanitize_state
from request_ai_agent_i0_0.ui import HTML_TEMPLATE
from request_ai_agent_i0_0.validator import validate_state


app_module = importlib.import_module("request_ai_agent_i0_0.app")


def _context(analysis_type: str = "이슬맺힘") -> dict[str, object]:
    return {
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


def _configured_state(analysis_type: str = "이슬맺힘") -> dict[str, object]:
    state = create_initial_state()
    state[SECTION_REQUEST_CONTEXT].update(_context(analysis_type))
    state["basic_info"].update({"division": "RAC", "department": "개발1팀", "requester_name": "테스터", "requester_role": "책임연구원"})
    state["analysis_overview"].update({
        "project_name": "T2-01B", "development_grade": "A", "npi_stage": "DV", "model_suffix": "MODEL-A",
        "request_date": "2026-08-03", "desired_completion_date": "2026-08-10",
    })
    state[SECTION_GEOMETRY]["base_product"].update({"drawing_no": "DRAW-A", "display_name": "형상 A", "display_name_custom": True})
    cards = state[SECTION_CONDITIONS]["condition_sets"]
    for card in cards:
        if card["type"] == "operating":
            card["fans"][0]["values"]["fan_rpm"] = "900"
        elif card["type"] == "heat_exchanger":
            card["fields"].update({"name": "사양 1", "fin_type": "Louver", "tube_diameter": "7", "row_count": "2", "fpi": "18"})
        elif card["type"] == "supply_air":
            card["fields"].update({"heat_exchanger_temp": "10", "heat_exchanger_rh": "70"})
        elif card["type"] == "space_environment":
            card["fields"].update({"room_temp": "25", "room_rh": "50"})
    return sanitize_state(state)


def test_title_uses_all_request_target_values_and_has_the_required_fallback():
    assert compose_request_title({SECTION_REQUEST_CONTEXT: _context()}) == "RAC / Wall Mounted / Wall Mounted / SK / 이슬맺힘"
    assert compose_request_title({SECTION_REQUEST_CONTEXT: {"business_unit": "RAC", "product_group": "벽걸이형"}}) == ""
    assert 'id="heroTitle">해석 의뢰를 시작해 주세요.</h2>' in HTML_TEMPLATE
    assert 'id="requestNoDisplay"' in HTML_TEMPLATE
    assert 'titleValues.every(Boolean) ? titleValues.join(" / ") : "해석 의뢰를 시작해 주세요."' in HTML_TEMPLATE


def test_condition_cards_remove_airflow_and_use_requested_hex_field_order():
    fieldset = build_condition_fieldset(_context())
    assert "airflow" not in str(fieldset)
    heat_card = next(card for card in default_condition_sets(_context()) if card["type"] == "heat_exchanger")
    assert list(heat_card["fields"]) == ["name", "tube_diameter", "fin_type", "row_count", "fpi"]
    assert heat_card["fields"]["name"]["value"] == "사양 1"
    assert heat_card["fields"]["name"]["source"] == "system"
    assert "°C" in str(fieldset)
    assert "운전 풍량" not in HTML_TEMPLATE
    assert "heat-exchanger-grid" in HTML_TEMPLATE
    assert '["name", "tube_diameter", "fin_type", "row_count", "fpi"]' in HTML_TEMPLATE
    assert "<h3>해석 조건 입력</h3>" not in HTML_TEMPLATE
    assert '.condition-input-screen > #section-conditions' in HTML_TEMPLATE


def test_supply_and_space_condition_fields_use_the_requested_temperature_first_order():
    cards = {card["type"]: card for card in default_condition_sets(_context())}
    assert list(cards["supply_air"]["fields"]) == ["heat_exchanger_temp", "heat_exchanger_rh"]
    assert list(cards["space_environment"]["fields"]) == ["room_temp", "room_rh"]

    fieldset_cards = {card["key"]: card for card in build_condition_fieldset(_context())["groups"]}
    assert [field["label"] for field in fieldset_cards["supply_air"]["fields"]] == ["취출 온도", "취출 상대습도"]
    assert 'supply_air: ["heat_exchanger_temp", "heat_exchanger_rh"]' in HTML_TEMPLATE
    assert 'space_environment: ["room_temp", "room_rh"]' in HTML_TEMPLATE
    assert 'previewFieldKeysFor(contextText(row.type), asObj(row.fields))' in HTML_TEMPLATE


def test_thermal_flow_excludes_humidity_from_conditions_matrix_and_screen_data():
    context = _context("열유동 해석")
    fieldset = build_condition_fieldset(context)
    fieldset_cards = {group["key"]: group for group in fieldset["groups"]}
    assert [field["key"] for field in fieldset_cards["supply_air"]["fields"] if field["active"]] == ["heat_exchanger_temp"]
    assert [field["key"] for field in fieldset_cards["space_environment"]["fields"] if field["active"]] == ["room_temp"]
    assert set(fieldset["field_keys"]).isdisjoint({"heat_exchanger_rh", "room_rh"})

    cards = {card["type"]: card for card in default_condition_sets(context)}
    assert list(cards["supply_air"]["fields"]) == ["heat_exchanger_temp"]
    assert list(cards["space_environment"]["fields"]) == ["room_temp"]
    assert [column["key"] for column in get_active_case_matrix_columns(context)] == [
        "fan", "heat_exchanger", "room_temp", "heat_exchanger_temp",
    ]

    normalized = sanitize_state(_configured_state("열유동 해석"))
    normalized_cards = normalized[SECTION_CONDITIONS]["condition_sets"]
    normalized_fields = normalized[SECTION_CONDITIONS]["fields"]
    assert "heat_exchanger_rh" not in str(normalized_cards)
    assert "room_rh" not in str(normalized_cards)
    assert {field["field_key"] for field in normalized_fields}.isdisjoint({"heat_exchanger_rh", "room_rh"})
    assert all(
        set(row["condition_values"]).isdisjoint({"heat_exchanger_rh", "room_rh"})
        for row in normalized[SECTION_CASE_MATRIX]["rows"]
    )
    assert 'filter(key => Object.prototype.hasOwnProperty.call(fields, key))' in HTML_TEMPLATE


def test_analysis_type_controls_active_cards_columns_and_clears_inactive_values():
    state = _configured_state("이슬맺힘")
    assert [column["key"] for column in get_active_case_matrix_columns(_context())] == [
        "fan", "heat_exchanger", "room_temp", "room_rh", "heat_exchanger_temp", "heat_exchanger_rh",
    ]
    assert 'const previewConditionOrder = {operating: 10, heat_exchanger: 20, space_environment: 30, supply_air: 40};' in HTML_TEMPLATE
    state[SECTION_REQUEST_CONTEXT].update(_context("일반 유동 해석"))
    changed = sanitize_state(state)
    assert {card["type"] for card in changed[SECTION_CONDITIONS]["condition_sets"]} == {"operating", "heat_exchanger"}
    assert [column["key"] for column in changed[SECTION_CASE_MATRIX]["visible_columns"]] == [
        "case_no", "geometry_id", "fan", "heat_exchanger", "remove",
    ]
    assert all(set(row["condition_values"]) <= {"fan", "heat_exchanger"} for row in changed[SECTION_CASE_MATRIX]["rows"])


def test_display_name_tracks_drawing_until_a_user_edits_it():
    state = create_initial_state()
    base = state[SECTION_GEOMETRY]["base_product"]
    base["drawing_no"] = "DRAW-A"
    first = sanitize_state(state)
    product = first[SECTION_GEOMETRY]["base_product"]
    assert product["display_name"]["value"] == "DRAW-A"
    assert product["display_name_custom"] is False

    product["drawing_no"] = "DRAW-B"
    second = sanitize_state(first)
    assert second[SECTION_GEOMETRY]["base_product"]["display_name"]["value"] == "DRAW-B"

    second[SECTION_GEOMETRY]["base_product"].update({"display_name": "사용자 표시명", "display_name_custom": True, "drawing_no": "DRAW-C"})
    third = sanitize_state(second)
    assert third[SECTION_GEOMETRY]["base_product"]["display_name"]["value"] == "사용자 표시명"
    assert third[SECTION_GEOMETRY]["base_product"]["display_name_custom"] is True
    assert 'data-product-field="description"' in HTML_TEMPLATE


def test_manual_matrix_starts_with_one_row_per_geometry_and_uses_shape_names():
    state = _configured_state()
    state[SECTION_GEOMETRY]["comparison_products"] = [
        {"geometry_id": "comparison_001", "role": "comparison", "drawing_no": "DRAW-B", "display_name": "형상 B", "display_name_custom": True, "difference_from_base": "토출부 변경"}
    ]
    matrix = sanitize_state(state)[SECTION_CASE_MATRIX]
    assert [row["visible_cells"]["geometry_id"] for row in matrix["rows"]] == ["형상 1", "형상 2"]
    assert [row["visible_cells"]["case_no"] for row in matrix["rows"]] == ["1", "2"]
    assert matrix["visible_columns"][0]["label"] == "No."
    assert matrix["visible_columns"][1]["label"] == "형상"
    assert next(column for column in matrix["visible_columns"] if column["key"] == "fan")["label"] == "운전"
    assert next(column for column in matrix["visible_columns"] if column["key"] == "heat_exchanger")["label"] == "사양"
    assert matrix["visible_columns"][-1]["label"] == "제거"
    assert [item["label"] for item in matrix["dropdown_options"]["geometry_id"]] == ["형상 1", "형상 2"]
    assert all(row["condition_values"] == {
        "fan": "operating_1",
        "heat_exchanger": "heat_exchanger_1",
        "heat_exchanger_temp": "10",
        "heat_exchanger_rh": "70",
        "room_temp": "25",
        "room_rh": "50",
    } for row in matrix["rows"])


def test_heat_exchanger_specs_flow_to_case_matrix_by_row_order():
    state = _configured_state()
    first = next(card for card in state[SECTION_CONDITIONS]["condition_sets"] if card["type"] == "heat_exchanger")
    second = {**first, "id": "heat_exchanger_2", "is_default": False, "fields": dict(first["fields"])}
    second["fields"]["name"] = "사용자가 보낸 구분명"
    state[SECTION_CONDITIONS]["condition_sets"].append(second)

    normalized = sanitize_state(state)
    heat_exchangers = [card for card in normalized[SECTION_CONDITIONS]["condition_sets"] if card["type"] == "heat_exchanger"]
    matrix = normalized[SECTION_CASE_MATRIX]

    assert [card["fields"]["name"]["value"] for card in heat_exchangers] == ["사양 1", "사양 2"]
    assert matrix["dropdown_options"]["heat_exchanger"] == [
        {"value": "heat_exchanger_1", "label": "사양 1"},
        {"value": "heat_exchanger_2", "label": "사양 2"},
    ]


def test_operating_fan_names_flow_to_case_matrix_by_row_order():
    state = _configured_state()
    first = next(card for card in state[SECTION_CONDITIONS]["condition_sets"] if card["type"] == "operating")
    second = {**first, "id": "operating_2", "is_default": False, "fans": [{"id": "fan_1", "name": "", "running": True, "values": {"fan_rpm": "1200"}}]}
    second["name"] = "사용자가 보낸 구분명"
    state[SECTION_CONDITIONS]["condition_sets"].append(second)

    normalized = sanitize_state(state)
    operating = [card for card in normalized[SECTION_CONDITIONS]["condition_sets"] if card["type"] == "operating"]
    matrix = normalized[SECTION_CASE_MATRIX]

    assert [card["name"] for card in operating] == ["운전 1", "운전 2"]
    assert matrix["dropdown_options"]["fan"] == [
        {"value": "operating_1", "label": "운전 1"},
        {"value": "operating_2", "label": "운전 2"},
    ]


def test_case_matrix_migrates_legacy_labels_and_keeps_card_identity_when_order_changes():
    state = _configured_state()
    state["metadata"]["schema_version"] = "request_state_v1"
    first = next(card for card in state[SECTION_CONDITIONS]["condition_sets"] if card["type"] == "operating")
    second = deepcopy(first)
    second.update({"id": "operating_opaqueabc", "is_default": False})
    second["fans"][0]["values"]["fan_rpm"] = "1200"
    state[SECTION_CONDITIONS]["condition_sets"].append(second)
    state[SECTION_CASE_MATRIX]["rows"][0]["condition_values"]["fan"] = "운전 2"

    migrated = sanitize_state(state)
    assert migrated["metadata"]["schema_version"] == STATE_SCHEMA_VERSION == "request_state_v2"
    assert migrated[SECTION_CASE_MATRIX]["rows"][0]["condition_values"]["fan"] == "operating_opaqueabc"
    assert migrated[SECTION_CASE_MATRIX]["rows"][0]["visible_cells"]["fan"] == "운전 2"
    assert "operating_opaqueabc" not in str(build_request_preview(migrated)["case_matrix"]["rows"])

    cards = migrated[SECTION_CONDITIONS]["condition_sets"]
    operating = [card for card in cards if card["type"] == "operating"]
    others = [card for card in cards if card["type"] != "operating"]
    migrated[SECTION_CONDITIONS]["condition_sets"] = [operating[1], operating[0], *others]
    reordered = sanitize_state(migrated)

    assert reordered[SECTION_CASE_MATRIX]["rows"][0]["condition_values"]["fan"] == "operating_opaqueabc"
    assert reordered[SECTION_CASE_MATRIX]["rows"][0]["visible_cells"]["fan"] == "운전 1"


def test_case_matrix_clears_only_the_deleted_card_reference():
    state = _configured_state()
    first = next(card for card in state[SECTION_CONDITIONS]["condition_sets"] if card["type"] == "operating")
    second = deepcopy(first)
    second.update({"id": "operating_opaqueabc", "is_default": False})
    state[SECTION_CONDITIONS]["condition_sets"].append(second)
    state[SECTION_CASE_MATRIX]["rows"][0]["condition_values"]["fan"] = "operating_opaqueabc"
    normalized = sanitize_state(state)

    normalized[SECTION_CONDITIONS]["condition_sets"] = [
        card for card in normalized[SECTION_CONDITIONS]["condition_sets"] if card["id"] != "operating_opaqueabc"
    ]
    after_delete = sanitize_state(normalized)

    assert "fan" not in after_delete[SECTION_CASE_MATRIX]["rows"][0]["condition_values"]


def test_removed_condition_rows_disappear_from_every_case_matrix_option_list():
    state = _configured_state()
    extra_values = {
        "operating": {"fan_rpm": "1200"},
        "heat_exchanger": {"tube_diameter": "9", "fin_type": "Slit", "row_count": "3", "fpi": "20"},
        "space_environment": {"room_temp": "30", "room_rh": "60"},
        "supply_air": {"heat_exchanger_temp": "15", "heat_exchanger_rh": "80"},
    }
    for card_type, values in extra_values.items():
        base = next(card for card in state[SECTION_CONDITIONS]["condition_sets"] if card["type"] == card_type)
        extra = deepcopy(base)
        extra.update({"id": f"{card_type}_2", "is_default": False})
        if card_type == "operating":
            extra["fans"][0]["values"]["fan_rpm"] = values["fan_rpm"]
        else:
            extra["fields"].update(values)
        state[SECTION_CONDITIONS]["condition_sets"].append(extra)

    with_extras = sanitize_state(state)
    assert [item["value"] for item in with_extras[SECTION_CASE_MATRIX]["dropdown_options"]["fan"]] == ["operating_1", "operating_2"]
    assert [item["value"] for item in with_extras[SECTION_CASE_MATRIX]["dropdown_options"]["heat_exchanger"]] == ["heat_exchanger_1", "heat_exchanger_2"]
    assert [item["value"] for item in with_extras[SECTION_CASE_MATRIX]["dropdown_options"]["room_temp"]] == ["25", "30"]
    assert [item["value"] for item in with_extras[SECTION_CASE_MATRIX]["dropdown_options"]["room_rh"]] == ["50", "60"]
    assert [item["value"] for item in with_extras[SECTION_CASE_MATRIX]["dropdown_options"]["heat_exchanger_temp"]] == ["10", "15"]
    assert [item["value"] for item in with_extras[SECTION_CASE_MATRIX]["dropdown_options"]["heat_exchanger_rh"]] == ["70", "80"]

    with_extras[SECTION_CONDITIONS]["condition_sets"] = [
        card for card in with_extras[SECTION_CONDITIONS]["condition_sets"] if card["is_default"] is True
    ]
    after_removal = sanitize_state(with_extras)

    assert after_removal[SECTION_CASE_MATRIX]["dropdown_options"]["fan"] == [{"value": "operating_1", "label": "운전 1"}]
    assert after_removal[SECTION_CASE_MATRIX]["dropdown_options"]["heat_exchanger"] == [{"value": "heat_exchanger_1", "label": "사양 1"}]
    assert [item["value"] for item in after_removal[SECTION_CASE_MATRIX]["dropdown_options"]["room_temp"]] == ["25"]
    assert [item["value"] for item in after_removal[SECTION_CASE_MATRIX]["dropdown_options"]["room_rh"]] == ["50"]
    assert [item["value"] for item in after_removal[SECTION_CASE_MATRIX]["dropdown_options"]["heat_exchanger_temp"]] == ["10"]
    assert [item["value"] for item in after_removal[SECTION_CASE_MATRIX]["dropdown_options"]["heat_exchanger_rh"]] == ["70"]


def test_multiple_rpms_in_one_fan_row_remain_one_case_in_full_preview():
    state = _configured_state()
    operating = next(card for card in state[SECTION_CONDITIONS]["condition_sets"] if card["type"] == "operating")
    operating["fans"] = [
        {"id": "fan_1", "name": "", "location": "상", "running": True, "values": {"fan_rpm": "900"}},
        {"id": "fan_2", "name": "", "location": "중", "running": True, "values": {"fan_rpm": "1100"}},
        {"id": "fan_3", "name": "", "location": "하", "running": True, "values": {"fan_rpm": "1200"}},
    ]
    operating["fan_rpm_mode"] = "individual"

    normalized = sanitize_state(state)
    operating = next(card for card in normalized[SECTION_CONDITIONS]["condition_sets"] if card["type"] == "operating")
    axis = generate_condition_axis(normalized)
    preview = build_request_preview(normalized)
    fan_item = next(
        item
        for item in next(section for section in preview["sections"] if section["key"] == "conditions")["items"]
        if item["label"].startswith("운전 1")
    )

    assert operating["fan_count"] == 3
    assert operating["fan_rpms"] == ["900", "1100", "1200"]
    assert len(normalized[SECTION_CASE_MATRIX]["rows"]) == 1
    assert len(preview["case_matrix"]["rows"]) == 1
    assert fan_item["value"] == "상 900 / 중 1100 / 하 1200"
    assert "operating_1.fan_rpm" in axis["common_conditions"]
    assert "operating_1.fan_rpm" not in axis["variable_conditions"]
    assert len(axis["condition_variants"]) == 1


def test_matrix_clears_invalid_manual_selections_and_adds_new_geometry_rows_only_once():
    state = _configured_state()
    matrix = state[SECTION_CASE_MATRIX]
    row = matrix["rows"][0]
    row["auto_geometry_id"] = ""
    row["geometry_id"] = "missing"
    row["condition_values"] = {"fan": "bad", "heat_exchanger": "사양 1"}
    normalized = sanitize_state(state)
    row = normalized[SECTION_CASE_MATRIX]["rows"][0]
    assert row["geometry_id"] == ""
    assert row["condition_values"] == {"heat_exchanger": "heat_exchanger_1"}

    normalized[SECTION_GEOMETRY]["comparison_products"] = [
        {"geometry_id": "comparison_001", "role": "comparison", "drawing_no": "DRAW-B", "display_name": "형상 B", "display_name_custom": True, "difference_from_base": "토출부 변경"}
    ]
    with_new_product = sanitize_state(normalized)
    assert len(with_new_product[SECTION_CASE_MATRIX]["rows"]) == 2
    assert len(sanitize_state(with_new_product)[SECTION_CASE_MATRIX]["rows"]) == 2


def test_condition_combination_state_and_validation_are_removed_in_favor_of_manual_rows():
    state = _configured_state()
    assert "combinations" not in state[SECTION_CONDITIONS]
    assert "condition_combinations" not in str(validate_state(state))
    assert "condition_combinations" not in HTML_TEMPLATE
    assert "조건조합" not in HTML_TEMPLATE


def test_validator_requires_current_manual_matrix_dropdown_choices():
    state = _configured_state()
    row = state[SECTION_CASE_MATRIX]["rows"][0]
    row["condition_values"] = {
        "fan": "운전 1",
        "heat_exchanger": "사양 1",
        "heat_exchanger_temp": "10",
        "heat_exchanger_rh": "70",
        "room_temp": "25",
        "room_rh": "50",
    }
    valid = validate_state(sanitize_state(state))
    assert not [item for item in valid["blocking"] if item["section"] == SECTION_CASE_MATRIX]

    row["auto_geometry_id"] = ""
    row["condition_values"]["fan"] = "not-current"
    invalid = validate_state(sanitize_state(state))
    assert any(item["code"] == "case_matrix.fan.missing" for item in invalid["blocking"])


def test_validator_blocks_duplicate_complete_manual_cases():
    state = _configured_state()
    original = state[SECTION_CASE_MATRIX]["rows"][0]
    state[SECTION_CASE_MATRIX]["rows"].append({
        **original,
        "case_id": "case_duplicate",
        "auto_geometry_id": "",
        "condition_values": dict(original["condition_values"]),
    })

    validation = validate_state(sanitize_state(state))

    duplicate = next(item for item in validation["blocking"] if item["code"] == "case_matrix.duplicate")
    assert duplicate["case_no"] == 2
    assert duplicate["duplicate_of_case_no"] == 1


def test_manual_matrix_rows_are_used_by_preview_draft_and_review():
    state = _configured_state()
    state["analysis_overview"].update({
        "request_description": "결로가 반복되어 원인 검토가 필요함",
        "additional_result_request": "결로 발생 원인과 개선 방향 확인",
        "decision_use": "설계 검토",
    })
    for row in state[SECTION_CASE_MATRIX]["rows"]:
        row["condition_values"] = {
            "fan": "운전 1",
            "heat_exchanger": "사양 1",
            "heat_exchanger_temp": "10",
            "heat_exchanger_rh": "70",
            "room_temp": "25",
            "room_rh": "50",
        }
    state = sanitize_state(state)

    preview = build_request_preview(state)
    assert len(preview["case_matrix"]["rows"]) == 1
    assert "final_cases" not in preview["case_matrix"]

    draft = build_request_draft(state)
    assert draft["status"] == "ready"
    assert draft["document"]["case_matrix_summary"]["case_count"] == 1
    assert "final_cases" not in draft["document"]["case_matrix_summary"]

    reviewed = state_with_final_review(state)
    final_payload = reviewed["review"]["final_review"]["final_payload"]
    assert final_payload is not None
    assert len(final_payload["case_matrix"]["rows"]) == 1
    assert "final_cases" not in final_payload["case_matrix"]

    app = create_app()
    client = app.test_client()
    refreshed = client.post("/api/preview", json={"state": state})
    assert refreshed.status_code == 200
    assert len(refreshed.get_json()["case_matrix"]["rows"]) == 1


def test_ui_uses_agent_heading_and_manual_case_controls_without_summary_or_regeneration():
    assert '<strong class="stage-assist-title">Agent</strong>' in HTML_TEMPLATE
    assert '<strong class="stage-assist-title">Summary</strong>' not in HTML_TEMPLATE
    assert 'data-action="add-case">Case 추가</button>' in HTML_TEMPLATE
    assert 'data-action="remove-case"' in HTML_TEMPLATE
    assert 'data-case-field="geometry_id"' in HTML_TEMPLATE
    assert "regenerate-case-matrix" not in HTML_TEMPLATE
    assert "data-case-include" not in HTML_TEMPLATE
    assert 'id="contextChangeBtn" type="button" hidden>의뢰대상 변경</button>' in HTML_TEMPLATE


def test_case_matrix_lists_shape_operation_and_specification_inputs_above_the_table():
    summary = HTML_TEMPLATE.split("function caseSourceReferenceHtml()", 1)[1].split("function caseTableHtml()", 1)[0]

    assert "아래 입력값을 확인하고 Case별 형상·운전·사양을 선택해 주세요." in summary
    assert "listHtml(options.geometry_id" in summary
    assert "listHtml(options.fan" in summary
    assert "listHtml(options.heat_exchanger" in summary
    assert 'class="case-source-category"' not in summary
    assert 'class="case-source-name"' in summary
    assert 'class="case-source-details"' in summary
    assert "case-source-grid" not in summary
    assert "case-source-group" not in summary
    assert '도면번호: ${productText(product, "drawing_no") || "-"} · 설명: ${description}' in summary
    assert '팬 개수: ${display.count} · 회전수(RPM): ${display.text}' in summary
    assert 'HEX type: ${type}' in summary
    assert '$("caseMatrix").innerHTML = `${caseSourceReferenceHtml()}${caseTableHtml()}`;' in HTML_TEMPLATE


def test_bootstrap_exposes_four_progress_stages_and_current_manual_matrix():
    app = create_app()
    payload = app.test_client().get("/api/bootstrap").get_json()
    assert payload["stage_progress"]["order"] == ["analysis_overview", "geometry", "conditions", "case_matrix"]
    assert payload["case_matrix"]["matrix_type"] == "manual_mapping"
    assert "condition_combinations" not in payload["stage_progress"]["stages"]


def test_new_request_resets_only_the_current_agent_state():
    app = create_app()
    client = app.test_client()
    state = _configured_state()
    state["metadata"]["chat_history"] = [{"role": "user", "content": "기존 의뢰", "html": ""}]
    saved = client.post("/api/input/save", json={"state": state})
    assert saved.status_code == 200

    response = client.post("/api/request/new")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["state_changed"] is True
    assert payload["state"][SECTION_REQUEST_CONTEXT]["context_locked"] is False
    assert payload["state"][SECTION_REQUEST_CONTEXT]["analysis_type"] == ""
    assert payload["state"][SECTION_CASE_MATRIX]["rows"] == []
    assert payload["state"]["metadata"]["chat_history"] == []


def test_demo_clients_do_not_share_server_state_or_recent_request_api():
    app = create_app()
    first_client = app.test_client()
    second_client = app.test_client()
    first_state = _configured_state()
    first_state["analysis_overview"]["project_name"] = "First browser only"

    saved = first_client.post("/api/input/save", json={"state": first_state})
    assert saved.status_code == 200
    assert saved.get_json()["state"]["analysis_overview"]["project_name"]["value"] == "First browser only"

    second_bootstrap = second_client.get("/api/bootstrap")
    assert second_bootstrap.status_code == 200
    assert second_bootstrap.get_json()["state"]["analysis_overview"]["project_name"]["value"] == ""
    assert second_client.get("/api/recent").status_code == 404
    assert second_client.post("/api/recent/load", json={"id": "any"}).status_code == 404


def test_azure_llm_can_be_explicitly_disabled(monkeypatch):
    monkeypatch.setenv("REQUEST_AGENT_LLM_ENABLED", "false")
    assert azure_openai_settings().enabled is False


def _main_chat_runtime(monkeypatch, decision):
    monkeypatch.setattr(app_module, "decide_agent_action", lambda _context, _contract: decision)
    app = create_app()
    client = app.test_client()
    created = client.post("/api/request/versioned", json={"state": _configured_state()}).get_json()
    conversation = client.post("/api/conversations", json={"request_id": created["request_id"]}).get_json()
    return app, client, created["request_id"], conversation["conversation_id"]


def test_chat_does_not_fallback_to_rules_when_llm_is_unavailable(monkeypatch):
    app, client, request_id, conversation_id = _main_chat_runtime(
        monkeypatch,
        {"action": "answer", "reply": "unused", "operations": [], "active_field_id": None},
    )
    monkeypatch.setattr(app_module, "decide_agent_action", lambda *_args: (_ for _ in ()).throw(RuntimeError("offline")))
    before = app.extensions["request_state_store"].read(request_id)

    response = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "열교환기 사양의 의미는 무엇인가요?", "mode": "auto"},
    )

    assert response.status_code == 503
    assert response.get_json()["assistant"] == "LLM이 정상 작동하지 않습니다."
    assert app.extensions["request_state_store"].read(request_id) == before


def test_chat_uses_agent_decision_operations_without_rule_based_value_parsing(monkeypatch):
    decision = {
        "action": "propose",
        "reply": "기준 형상의 도면번호를 A100으로 변경하는 내용을 제안합니다.",
        "operations": [
            {"op": "set_geometry_field", "geometry_id": "base_001", "field_key": "drawing_no", "value": "A100"}
        ],
        "active_field_id": None,
    }
    app, client, request_id, conversation_id = _main_chat_runtime(monkeypatch, decision)
    before = app.extensions["request_state_store"].read(request_id)

    proposed = client.post("/api/chat/send", json={"conversation_id": conversation_id, "message": "기준 형상은 A100으로 입력해줘."})
    proposal = proposed.get_json()["proposal"]

    assert proposed.status_code == 200
    assert proposal["status"] == "pending"
    assert app.extensions["request_state_store"].read(request_id) == before

    approved = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal["proposal_id"], "decision": "approve"},
    )
    assert approved.get_json()["status"] == "approved"
    assert app.extensions["request_state_store"].read(request_id).state[SECTION_GEOMETRY]["base_product"]["drawing_no"]["value"] == "A100"


def test_invalid_llm_operation_is_not_proposed_or_applied(monkeypatch):
    decision = {
        "action": "propose",
        "reply": "unsafe",
        "operations": [{"op": "set", "path": "metadata.request_no", "value": "unsafe"}],
        "active_field_id": None,
    }
    app, client, request_id, conversation_id = _main_chat_runtime(monkeypatch, decision)
    before = app.extensions["request_state_store"].read(request_id)

    response = client.post("/api/chat/send", json={"conversation_id": conversation_id, "message": "unsafe"})

    assert response.status_code == 503
    assert response.get_json()["assistant"] == "LLM이 정상 작동하지 않습니다."
    assert app.extensions["proposal_service"].proposal_count() == 0
    assert app.extensions["request_state_store"].read(request_id) == before


def test_current_value_answer_reads_server_state_without_rag_or_mutation(monkeypatch):
    decision = {"action": "answer", "reply": "현재 도면번호는 DRAW-A입니다.", "operations": [], "active_field_id": None}
    app, client, request_id, conversation_id = _main_chat_runtime(monkeypatch, decision)
    monkeypatch.setattr(app_module, "run_rag_qa", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not use RAG")))
    before = app.extensions["request_state_store"].read(request_id)

    response = client.post("/api/chat/send", json={"conversation_id": conversation_id, "message": "현재 도면번호는?"})
    payload = response.get_json()

    assert payload["action"] == "answer"
    assert payload["assistant"] == "현재 도면번호는 DRAW-A입니다."
    assert "qa" not in payload
    assert app.extensions["request_state_store"].read(request_id) == before


def test_main_chat_rag_question_stays_single_answer_without_rag_payload(monkeypatch):
    decision = {"action": "answer", "reply": "현재는 사내 문서 근거를 조회하지 않습니다.", "operations": [], "active_field_id": None}
    app, client, request_id, conversation_id = _main_chat_runtime(monkeypatch, decision)
    monkeypatch.setattr(app_module, "run_rag_qa", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Main Chat RAG is off")))
    before = app.extensions["request_state_store"].read(request_id)

    response = client.post("/api/chat/send", json={"conversation_id": conversation_id, "message": "SOP 근거를 찾아줘", "mode": "rag"})
    payload = response.get_json()

    assert payload["action"] == "answer"
    assert "qa" not in payload
    assert app.extensions["request_state_store"].read(request_id) == before


def test_direct_rag_endpoint_keeps_disabled_and_failed_paths_read_only(monkeypatch):
    app = create_app()
    client = app.test_client()
    disabled_state = _configured_state()
    monkeypatch.setattr(app_module, "run_rag_qa", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("disabled RAG must not run")))

    disabled = client.post("/api/rag/qa", json={"question": "RAG question", "state": disabled_state})
    disabled_payload = disabled.get_json()
    assert disabled.status_code == 200
    assert disabled_payload["qa"]["question_type"] == "rag_disabled"
    assert disabled_payload["state_changed"] is False

    enabled_state = _configured_state()
    enabled_state["metadata"]["rag_enabled"] = True
    monkeypatch.setattr(app_module, "run_rag_qa", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("search unavailable")))
    failed = client.post("/api/rag/qa", json={"question": "RAG question", "state": enabled_state})
    failed_payload = failed.get_json()
    assert failed.status_code == 200
    assert failed_payload["qa"]["question_type"] == "rag_error"
    assert failed_payload["qa"]["read_only"] is True
    assert failed_payload["state_changed"] is False


def test_word_export_keeps_using_the_rendered_preview_payload():
    app = create_app()
    response = app.test_client().post(
        "/api/export/word",
        json={"state": _configured_state(), "sections": [{"title": "Case Matrix", "blocks": [{"type": "table", "caption": "Case Matrix", "headers": ["No.", "형상"], "rows": [["1", "형상 A"]]}]}]},
    )
    assert response.status_code == 200
    with ZipFile(BytesIO(response.data)) as document:
        xml = document.read("word/document.xml").decode("utf-8")
    assert "Case Matrix" in xml
    assert "형상 A" in xml
