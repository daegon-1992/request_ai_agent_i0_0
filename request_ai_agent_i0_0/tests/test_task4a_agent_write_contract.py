from copy import deepcopy

import pytest

from request_ai_agent_i0_0.agent_decision import proposal_changes, writable_active_field_ids
from request_ai_agent_i0_0.agent_write_contract import (
    build_agent_write_contract,
    normalize_instance_write_operation,
    normalize_structural_write_operation,
)
from request_ai_agent_i0_0.chat_patch import apply_patch_operations
from request_ai_agent_i0_0.condition_fieldsets import default_condition_sets, make_condition_card
from request_ai_agent_i0_0.proposal_store import ProposalService, ProposalValidationError
from request_ai_agent_i0_0.request_state_store import RequestStateStore
from request_ai_agent_i0_0.state import create_initial_state
from request_ai_agent_i0_0.validator import state_with_validation, validate_state


def _configured_state():
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
    state["analysis_overview"]["project_name"] = "Before"
    state["geometry"].update(
        {
            "base_product": {
                "geometry_id": "base_001",
                "role": "base",
                "drawing_no": "DRAW-A",
                "display_name": "기준 형상",
                "display_name_custom": True,
            },
            "comparison_products": [
                {
                    "geometry_id": "comparison_001",
                    "role": "comparison",
                    "drawing_no": "DRAW-B",
                    "display_name": "비교 형상",
                    "display_name_custom": True,
                    "difference_from_base": "기존 차이",
                }
            ],
        }
    )

    cards = default_condition_sets(state["request_context"])
    operating_1 = next(card for card in cards if card["type"] == "operating")
    operating_1["fans"] = [
        {"id": "fan_1", "name": "Main", "location": "좌", "running": True, "values": {"fan_rpm": "650"}},
        {"id": "fan_2", "name": "Aux", "location": "우", "running": True, "values": {"fan_rpm": "800"}},
    ]
    operating_2 = make_condition_card("operating", 2)
    operating_2["fans"][0]["values"]["fan_rpm"] = "750"

    heat_exchanger_1 = next(card for card in cards if card["type"] == "heat_exchanger")
    heat_exchanger_1["fields"]["fpi"]["value"] = "16"
    heat_exchanger_2 = make_condition_card("heat_exchanger", 2)
    heat_exchanger_2["fields"]["tube_diameter"]["value"] = "7.5"

    state["conditions"]["condition_sets"] = [
        operating_1,
        operating_2,
        heat_exchanger_1,
        heat_exchanger_2,
        *(card for card in cards if card["type"] not in {"operating", "heat_exchanger"}),
    ]
    return state


def _service():
    requests = RequestStateStore(state_with_validation)
    service = ProposalService(requests)
    created = requests.create(_configured_state())
    return requests, service, created


def _card(state, card_id):
    return next(card for card in state["conditions"]["condition_sets"] if card["id"] == card_id)


def _fan(state, card_id, fan_id):
    return next(fan for fan in _card(state, card_id)["fans"] if fan["id"] == fan_id)


def test_contract_exposes_only_current_writable_general_geometry_and_condition_targets():
    _requests, _service_instance, created = _service()
    contract = build_agent_write_contract(created.state)

    general_paths = {target["path"] for target in contract["operations"]["set"]["targets"]}
    geometry_operation = contract["operations"]["set_geometry_field"]
    geometry = {
        target["geometry_id"]: {field["field_key"] for field in target["fields"]}
        for target in geometry_operation["targets"]
    }
    conditions = {
        (target["card_id"], target["field_key"]): target
        for target in contract["operations"]["set_condition_field"]["targets"]
    }

    assert "analysis_overview.project_name" in general_paths
    requester_targets = {
        target["path"]: target
        for target in contract["operations"]["set"]["targets"]
        if target["path"].startswith("basic_info.")
    }
    assert set(requester_targets) == {
        "basic_info.division",
        "basic_info.department",
        "basic_info.requester_name",
        "basic_info.requester_role",
    }
    assert all(target["section"] == "의뢰자 정보" for target in requester_targets.values())
    assert all(target["semantic_scope"] == "requester_profile" for target in requester_targets.values())
    assert not any(path.startswith("request_context.") for path in general_paths)
    assert "basic_info.request_no" not in general_paths
    assert geometry_operation["required"] == ["op", "geometry_id", "field_key", "value"]
    assert geometry["base_001"] == {"drawing_no", "display_name"}
    assert geometry["comparison_001"] == {"drawing_no", "display_name", "difference_from_base"}
    drawing_fields = [
        field
        for target in geometry_operation["targets"]
        for field in target["fields"]
        if field["field_key"] == "drawing_no"
    ]
    assert drawing_fields
    assert all(field["label"] == "총조립도 도면번호 (NPDM MCAD)" for field in drawing_fields)
    assert all(set(field) == {"field_key", "label", "value_type", "unit", "current_value"} for field in drawing_fields)
    assert ("heat_exchanger_2", "fpi") in conditions
    assert ("heat_exchanger_2", "name") not in conditions
    assert [fan["fan_id"] for fan in conditions[("operating_1", "fan_rpm")]["fans"]] == ["fan_1", "fan_2"]


def test_multiple_general_and_instance_operations_share_one_proposal_and_apply_exact_targets():
    requests, service, created = _service()
    before = requests.read(created.request_id)
    before_case_geometry = [row["geometry_id"] for row in before.state["case_matrix"]["rows"]]
    before_validation = validate_state(before.state)
    operations = [
        {"op": "set", "path": "analysis_overview.project_name", "value": "After"},
        {"op": "set_condition_field", "card_id": "operating_1", "field_key": "fan_rpm", "fan_id": "fan_1", "value": "700"},
        {"op": "set_condition_field", "card_id": "operating_2", "field_key": "fan_rpm", "fan_id": "fan_1", "value": "900"},
        {"op": "set_condition_field", "card_id": "heat_exchanger_2", "field_key": "fpi", "value": "18"},
        {"op": "set_geometry_field", "geometry_id": "comparison_001", "field_key": "difference_from_base", "value": "토출 베인 각도 변경"},
    ]

    assert any(issue["code"] == "conditions.heat_exchanger_2.fpi.required_missing" for issue in before_validation["blocking"])
    proposal = service.create_proposal(created.request_id, operations, source="agent_write_contract")

    assert proposal.status == "pending"
    assert len(proposal.operations) == len(operations)
    assert service.proposal_count() == 1
    assert requests.read(created.request_id) == before

    approved = service.approve_proposal(proposal.proposal_id)
    latest = requests.read(created.request_id)

    assert approved.status == "approved"
    assert latest.version == created.version + 1
    assert latest.state["analysis_overview"]["project_name"]["value"] == "After"
    assert _fan(latest.state, "operating_1", "fan_1")["values"]["fan_rpm"] == "700"
    assert _fan(latest.state, "operating_2", "fan_1")["values"]["fan_rpm"] == "900"
    assert _fan(latest.state, "operating_1", "fan_2")["values"]["fan_rpm"] == "800"
    assert _card(latest.state, "heat_exchanger_1")["fields"]["fpi"]["value"] == "16"
    assert _card(latest.state, "heat_exchanger_2")["fields"]["fpi"]["value"] == "18"
    assert _card(latest.state, "heat_exchanger_2")["fields"]["tube_diameter"]["value"] == "7.5"
    assert _card(latest.state, "heat_exchanger_2")["fields"]["name"]["source"] == "system"

    comparison = latest.state["geometry"]["comparison_products"][0]
    assert comparison["geometry_id"] == "comparison_001"
    assert comparison["drawing_no"]["value"] == "DRAW-B"
    assert comparison["display_name"]["value"] == "비교 형상"
    assert comparison["difference_from_base"]["value"] == "토출 베인 각도 변경"
    assert latest.state["geometry"]["base_product"] == before.state["geometry"]["base_product"]
    assert [row["geometry_id"] for row in latest.state["case_matrix"]["rows"]] == before_case_geometry

    derived = next(field for field in latest.state["conditions"]["fields"] if field["key"] == "operating_2.fan_rpm")
    assert derived["fan_configuration"]["fan_rpms"] == ["900"]
    assert latest.state["review"]["validator"] == validate_state(latest.state)
    assert not any(
        issue["code"] == "conditions.heat_exchanger_2.fpi.required_missing"
        for issue in latest.state["review"]["validator"]["blocking"]
    )


@pytest.mark.parametrize(
    "operation",
    [
        {"op": "set_condition_field", "card_id": "missing", "field_key": "fpi", "value": "18"},
        {"op": "set_geometry_field", "geometry_id": "missing", "field_key": "drawing_no", "value": "X"},
        {"op": "set_condition_field", "card_id": "space_environment_1", "field_key": "room_rh", "value": "50"},
        {"op": "set_condition_field", "card_id": "heat_exchanger_2", "field_key": "name", "value": "임의 사양"},
        {"op": "set_condition_field", "card_id": "operating_2", "field_key": "fan_rpm", "fan_id": "missing", "value": "900"},
    ],
)
def test_invalid_instance_target_rejects_the_whole_proposal(operation):
    requests, service, created = _service()
    before = requests.read(created.request_id)

    with pytest.raises(ProposalValidationError):
        service.create_proposal(
            created.request_id,
            [
                {"op": "set", "path": "analysis_overview.project_name", "value": "must not be selected"},
                operation,
            ],
            source="agent_write_contract",
        )

    assert service.proposal_count() == 0
    assert requests.read(created.request_id) == before


def test_canonical_noop_does_not_create_pending_proposal():
    requests, service, created = _service()
    before = requests.read(created.request_id)

    with pytest.raises(ProposalValidationError, match="do not change canonical"):
        service.create_proposal(
            created.request_id,
            [{"op": "set", "path": "analysis_overview.project_name", "value": "Before"}],
            source="agent_write_contract",
        )

    assert service.proposal_count() == 0
    assert requests.read(created.request_id) == before


def test_operating_fan_write_supports_legacy_values_locations_modes_and_the_shared_limit():
    state = _configured_state()
    contract = build_agent_write_contract(state)
    assert contract["operations"]["set_operating_fans"]["optional"] == ["locations", "fan_rpm_mode"]

    values_only = normalize_structural_write_operation(
        {"op": "set_operating_fans", "card_id": "operating_1", "values": ["1000", "700"]},
        contract=contract,
        source="agent",
    )
    ten_fans = normalize_structural_write_operation(
        {"op": "set_operating_fans", "card_id": "operating_1", "values": [str(600 + index) for index in range(10)]},
        contract=contract,
        source="agent",
    )
    eleven_fans = normalize_structural_write_operation(
        {"op": "set_operating_fans", "card_id": "operating_1", "values": [str(600 + index) for index in range(11)]},
        contract=contract,
        source="agent",
    )
    individual = normalize_structural_write_operation(
        {
            "op": "set_operating_fans",
            "card_id": "operating_1",
            "values": ["1000", "700", "640"],
            "locations": ["상", "중", "하"],
            "fan_rpm_mode": "individual",
        },
        contract=contract,
        source="agent",
    )
    common = normalize_structural_write_operation(
        {
            "op": "set_operating_fans",
            "card_id": "operating_1",
            "values": ["1600", "1600", "1600"],
            "fan_rpm_mode": "common",
        },
        contract=contract,
        source="agent",
    )

    assert values_only is not None and "fan_rpm_mode" not in values_only
    assert ten_fans is not None
    assert eleven_fans is None
    assert individual is not None and individual["locations"] == ["상", "중", "하"]
    assert common is not None
    assert normalize_structural_write_operation(
        {
            "op": "set_operating_fans",
            "card_id": "operating_1",
            "values": ["1600", "1500"],
            "fan_rpm_mode": "common",
        },
        contract=contract,
        source="agent",
    ) is None

    updated = apply_patch_operations(state, [individual])
    card = _card(updated, "operating_1")
    assert card["id"] == "operating_1"
    assert card["fan_rpm_mode"] == "individual"
    assert [fan["location"] for fan in card["fans"]] == ["상", "중", "하"]
    assert [fan["values"]["fan_rpm"] for fan in card["fans"]] == ["1000", "700", "640"]

    defended = apply_patch_operations(
        state,
        [{"op": "set_operating_fans", "card_id": "operating_1", "values": [str(index) for index in range(11)]}],
    )
    assert _card(defended, "operating_1")["fans"] == _card(state, "operating_1")["fans"]


def test_individual_fan_location_is_writable_applies_only_to_location_and_has_a_user_label():
    state = state_with_validation(_configured_state())
    _card(state, "operating_1")["fan_rpm_mode"] = "individual"
    contract = build_agent_write_contract(state)
    operation = normalize_instance_write_operation(
        {
            "op": "set_condition_field",
            "card_id": "operating_1",
            "fan_id": "fan_1",
            "field_key": "fan_location",
            "value": "상",
        },
        contract=contract,
        source="agent",
    )

    assert operation is not None
    assert operation["path"] == "conditions.condition_sets[card_id=operating_1].fans[fan_id=fan_1].location"
    assert "conditions.operating_1.fan_location" in writable_active_field_ids(
        {"form_context": {"fields": []}},
        contract,
    )

    updated = apply_patch_operations(state, [operation])
    assert _fan(updated, "operating_1", "fan_1")["location"] == "상"
    assert _fan(updated, "operating_1", "fan_1")["values"]["fan_rpm"] == "650"
    assert _fan(updated, "operating_1", "fan_2") == _fan(state, "operating_1", "fan_2")
    assert len(_card(updated, "operating_1")["fans"]) == len(_card(state, "operating_1")["fans"])
    assert _card(updated, "operating_1")["id"] == _card(state, "operating_1")["id"]
    changes = proposal_changes(state, updated)
    assert changes == [{"label": "운전 1 · 첫 번째 팬 위치", "current_value": "좌", "new_value": "상"}]
    assert "operating_1" not in changes[0]["label"] and "fan_1" not in changes[0]["label"]
