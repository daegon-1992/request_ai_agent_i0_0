from __future__ import annotations

from request_ai_agent_i0_0 import create_app
from request_ai_agent_i0_0.product_taxonomy import (
    build_product_taxonomy_payload,
    find_product_taxonomy_matches,
    product_taxonomy_answer,
)
from request_ai_agent_i0_0.state import create_initial_state, normalize_request_context
from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def _path_tuple(item):
    return tuple(item[key] for key in ("division", "product_lineup", "platform", "chassis"))


def test_taxonomy_applies_the_approved_lineup_platform_chassis_policy():
    payload = build_product_taxonomy_payload()
    paths = payload["paths"]
    tuples = [_path_tuple(item) for item in paths]

    assert payload["taxonomy_version"] == "2026-08-23"
    assert payload["row_count"] == 251
    assert payload["variant_count"] == 72
    assert payload["division_counts"] == {"Air Care": 23, "Chiller": 2, "RAC": 43, "SAC": 183}
    assert payload["division_rules"] == {
        "Air Care": {"platform_selection_mode": "derived_from_product_lineup"},
        "Chiller": {"platform_selection_mode": "catalog"},
        "RAC": {"platform_selection_mode": "derived_from_product_lineup"},
        "SAC": {"platform_selection_mode": "catalog"},
    }
    assert [item["label"] for item in payload["divisions"]] == ["SAC", "RAC", "Air Care", "Chiller"]
    assert len(tuples) == len(set(tuples))
    assert not any(item["division"] == "ESS" for item in paths)
    assert not any(
        item["division"] == "SAC" and item["product_lineup"].casefold() in {"etc", "networkcontrol", "platform"}
        for item in paths
    )


def test_taxonomy_applies_accessory_na_and_chassis_exceptions():
    payload = build_product_taxonomy_payload()
    tuples = {_path_tuple(item) for item in payload["paths"]}

    assert not any(item["chassis"] == "Accessory" for item in payload["paths"])
    assert ("SAC", "Applied", "Ventilation", None) not in tuples
    assert ("SAC", "Heating", "Water heater", None) not in tuples
    assert ("SAC", "Multi V", "Multi V Water", None) not in tuples
    assert ("Chiller", "Screw", "Air Cooled", None) in tuples
    assert ("Chiller", "Screw", "Water Cooled", None) in tuples
    assert ("SAC", "Multi V", "Duct(Multi V)", "NA") in tuples
    assert ("SAC", "Single CAC", "Duct(Single CAC)", "NA") in tuples
    assert ("SAC", "Applied", "DOAS", "DD(RTU)") in tuples
    assert ("SAC", "Multi V", "AHU", "10RT") in tuples
    assert ("SAC", "Single CAC", "CST(Single CAC)", "BG GGBD") in tuples
    assert ("SAC", "Single CAC", "CST(Single CAC)", "BR GGBD") in tuples


def test_rac_and_air_care_variants_are_management_only_children():
    payload = build_product_taxonomy_payload()
    target = next(item for item in payload["paths"] if _path_tuple(item) == ("RAC", "Wall Mounted", "Wall Mounted", "SK"))

    assert [variant["label"] for variant in target["variants"]] == ["Artcool", "E", "R", "Semi R"]
    assert all(variant["label"] != "NA" for item in payload["paths"] for variant in item["variants"])
    assert sum(len(item["variants"]) for item in payload["paths"] if item["division"] == "RAC") == 60
    assert sum(len(item["variants"]) for item in payload["paths"] if item["division"] == "Air Care") == 12


def test_taxonomy_lookup_accepts_air_care_alias_and_null_chassis():
    air_care = find_product_taxonomy_matches(
        {"division": "Aircare", "product_lineup": "Air Circulator", "platform": "Air Circulator", "chassis": "Aero Tower"}
    )
    chiller = find_product_taxonomy_matches(
        {"division": "Chiller", "product_lineup": "Screw", "platform": "Air Cooled", "chassis": None}
    )

    assert len(air_care) == 1 and air_care[0]["division"] == "Air Care"
    assert len(chiller) == 1 and chiller[0]["chassis"] is None


def test_zero_result_guides_the_user_to_the_request_manager():
    answer = product_taxonomy_answer({"platform": "NEW-PLATFORM"}, [])

    assert "등록된 목록에서만 선택" in answer
    assert "해석의뢰관리자에게 분류 추가를 요청" in answer


def test_taxonomy_api_and_context_confirmation_use_new_contract():
    app = create_app()
    client = app.test_client()
    payload = client.get("/api/product-taxonomy").get_json()
    target = next(item for item in payload["paths"] if _path_tuple(item) == ("RAC", "Wall Mounted", "Wall Mounted", "SK"))

    response = client.post(
        "/api/request-context/confirm",
        json={"state": create_initial_state(), "request_context": {"taxonomy_id": target["taxonomy_id"], "analysis_type": "풍량"}},
    )

    assert response.status_code == 200
    context = response.get_json()["state"]["request_context"]
    assert context["taxonomy_id"] == target["taxonomy_id"]
    assert (context["division"], context["product_lineup"], context["platform"], context["chassis"]) == (
        "RAC", "Wall Mounted", "Wall Mounted", "SK"
    )
    assert context["context_locked"] is True


def test_null_chassis_is_valid_and_old_or_tampered_context_is_rejected():
    app = create_app()
    client = app.test_client()
    paths = client.get("/api/product-taxonomy").get_json()["paths"]
    chiller = next(item for item in paths if _path_tuple(item) == ("Chiller", "Screw", "Air Cooled", None))
    rac = next(item for item in paths if _path_tuple(item) == ("RAC", "Wall Mounted", "Wall Mounted", "SK"))

    valid = client.post(
        "/api/request-context/confirm",
        json={"state": create_initial_state(), "request_context": {"taxonomy_id": chiller["taxonomy_id"], "analysis_type": "풍량"}},
    )
    legacy = client.post(
        "/api/request-context/confirm",
        json={"state": create_initial_state(), "request_context": {"division": "RAC", "level1": "Wall Mounted", "level2": "SK", "analysis_type": "풍량"}},
    )
    tampered = client.post(
        "/api/request-context/confirm",
        json={"state": create_initial_state(), "request_context": {"taxonomy_id": rac["taxonomy_id"], "platform": "Window", "analysis_type": "풍량"}},
    )

    assert valid.status_code == 200 and valid.get_json()["state"]["request_context"]["chassis"] is None
    assert legacy.status_code == 400
    assert tampered.status_code == 400


def test_old_taxonomy_state_is_reset_instead_of_migrated():
    context = normalize_request_context(
        {"taxonomy_id": "PTX-OLD", "taxonomy_version": "2026-08-12", "division": "RAC", "analysis_type": "풍량", "context_locked": True}
    )

    assert context["taxonomy_id"] == ""
    assert context["product_lineup"] == ""
    assert context["chassis"] is None
    assert context["context_locked"] is False


def test_taxonomy_ui_has_five_catalog_only_selection_levels():
    for control_id in ("quickDivisionSelect", "quickProductLineupSelect", "quickPlatformSelect", "quickChassisSelect"):
        assert f'id="{control_id}"' in HTML_TEMPLATE
    screen = HTML_TEMPLATE.split('<section class="screen-group" data-screen="SCREEN-01"', 1)[1].split(
        '<section class="screen-group request-content-screen" data-screen="SCREEN-02"', 1
    )[0]
    assert "Product Line-up 선택" in screen and "Platform 선택" in screen and "Chassis 선택" in screen
    assert "직접 입력" not in screen and ">미정<" not in screen
    assert 'platformSelectionMode(context.division) === "derived_from_product_lineup"' in HTML_TEMPLATE
    assert 'const platformDisabled = !context.product_lineup || platformDerived;' in HTML_TEMPLATE
    assert 'const chassisAutoNull = chassisRows.length === 1 && chassisRows[0] === NULL_CHASSIS_VALUE;' in HTML_TEMPLATE
    assert 'const NULL_CHASSIS_VALUE = "__null_chassis__";' in HTML_TEMPLATE
