from copy import deepcopy
from unittest.mock import patch

from request_ai_agent_i0_0.chat_patch import apply_patch_operations
from request_ai_agent_i0_0.condition_fieldsets import get_active_condition_fields
from request_ai_agent_i0_0.field_registry import get_field_registry, get_geometry_products_adapter
from request_ai_agent_i0_0.state import create_initial_state
from request_ai_agent_i0_0.validator import validate_state


def _locked_state(analysis_type="이슬맺힘"):
    state = create_initial_state()
    state["request_context"].update(
        {
            "business_unit": "RAC",
            "product_group": "wall",
            "platform": "SK",
            "analysis_type": analysis_type,
            "context_locked": True,
        }
    )
    return state


def test_registry_omits_condition_fields_until_analysis_type_is_selected():
    state = create_initial_state()
    before = deepcopy(state)

    registry = get_field_registry(state)

    assert any(item.field_id == "analysis_overview.request_description" for item in registry)
    assert not any(item.field_id.startswith("conditions.") for item in registry)
    assert state == before


def test_registry_keeps_existing_active_conditions_for_air_volume_and_dew():
    for analysis_type in ("풍량", "이슬맺힘"):
        state = _locked_state(analysis_type)
        expected = [f"conditions.{field['key']}" for field in get_active_condition_fields(state)]
        actual = [
            item.field_id
            for item in get_field_registry(state)
            if item.field_id.startswith("conditions.")
        ]

        assert actual == expected


def test_registry_matches_existing_general_and_active_condition_bindings_without_mutation():
    state = _locked_state()
    before = deepcopy(state)

    registry = {item.field_id: item for item in get_field_registry(state)}
    active = {f"conditions.{field['key']}": field for field in get_active_condition_fields(state)}
    validation = validate_state(state)

    general = registry["analysis_overview.request_description"]
    assert general.canonical_path == "analysis_overview.request_description"
    assert general.required is True
    assert general.validation_binding == "validator._validate_required_field_section"
    assert any(issue["code"] == "analysis_overview.request_description.required_missing" for issue in validation["blocking"])

    conditional = registry["conditions.space_environment_1.room_temp"]
    source = active[conditional.field_id]
    assert conditional.active is source["active"] is True
    assert conditional.required is source["required"] is True
    assert conditional.canonical_path == "conditions.condition_sets[card_id=space_environment_1].fields.room_temp.value"
    assert conditional.operation_path == "conditions.fields.room_temp.values"
    assert any(issue["code"] == "conditions.space_environment_1.room_temp.required_missing" for issue in validation["blocking"])
    assert state == before


def test_registry_exposes_existing_conditional_required_validation_contract_by_mocking_fieldset_result():
    state = _locked_state()
    mocked = [
        {
            "key": "alternate_1.room_temp",
            "field_key": "room_temp",
            "card_id": "alternate_1",
            "label": "Alternate room temperature",
            "unit": "degC",
            "active": True,
            "required": True,
            "required_level": "conditional_required",
            "conditional_group": "room_environment",
            "values": [{"value": "", "status": "missing"}],
        }
    ]
    with patch("request_ai_agent_i0_0.field_registry.get_active_condition_fields", return_value=mocked), patch(
        "request_ai_agent_i0_0.validator.get_active_condition_fields", return_value=mocked
    ):
        dto = next(item for item in get_field_registry(state) if item.field_id == "conditions.alternate_1.room_temp")
        validation = validate_state(state)

    assert dto.required_level == "conditional_required"
    assert dto.priority == "blocking_conditional_group"
    assert dto.dependencies == ("conditions.conditional_group.room_environment",)
    assert any(issue["code"] == "conditions.room_environment.conditional_required_missing" for issue in validation["blocking"])


def test_registry_write_reference_still_uses_existing_normalizer_and_validator():
    state = _locked_state()
    state["request_context"]["analysis_type"] = "일반 유동 해석"
    before = deepcopy(state)
    registry = {item.field_id: item for item in get_field_registry(state)}
    dto = registry["analysis_overview.request_description"]
    adapter = get_geometry_products_adapter()

    assert state == before
    assert adapter.transport_path == "geometry.products"
    assert adapter.state_path is None
    assert adapter.canonical_paths == ("geometry.base_product.drawing_no", "geometry.comparison_products[].drawing_no")

    result = apply_patch_operations(
        state,
        [
            {"op": "set", "path": dto.operation_path, "value": "Registry write"},
            # This stale, inactive-card field may be supplied by a Registry
            # consumer, but only the existing normalizer decides its fate.
            {"op": "condition_values", "field_key": "room_temp", "values": ["25"]},
        ],
    )

    assert state == before
    assert result["analysis_overview"]["request_description"]["value"] == "Registry write"
    assert all(card["type"] != "space_environment" for card in result["conditions"]["condition_sets"])
    assert result["review"]["submission"]["can_submit"] is False
    assert result["metadata"]["issue_registry"]
    assert result["review"]["submission"]["blocking_reasons"] == [
        issue["code"] for issue in result["review"]["validator"]["blocking"]
    ]
