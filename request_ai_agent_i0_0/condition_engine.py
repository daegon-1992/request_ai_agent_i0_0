"""Condition axis generation for request assistant state."""

from __future__ import annotations

from copy import deepcopy
from itertools import product
from typing import Any, Mapping

from .condition_fields import (
    boundary_binding_record,
    clean_text,
    condition_field_ref,
    condition_value_refs,
)
from .condition_fieldsets import get_active_condition_fields
from .constants import (
    FIELD_STATUS_MISSING,
    FIELD_STATUS_PROVIDED,
    SECTION_CONDITIONS,
)
from .state import sanitize_state


ConditionPayload = dict[str, Any]


def _conditions_section(source: Mapping[str, Any]) -> Mapping[str, Any]:
    conditions = source.get(SECTION_CONDITIONS)
    if isinstance(conditions, Mapping):
        return conditions
    return source


def _field_label_for_variant(value_ref: Mapping[str, Any]) -> str:
    field_label = clean_text(value_ref.get("field_label")) or clean_text(value_ref.get("field_key"))
    value_label = clean_text(value_ref.get("label"))
    return f"{field_label}={value_label}" if value_label else field_label


def _make_variant(index: int, combo: tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
    values = {str(value_ref["field_key"]): dict(value_ref) for value_ref in combo}
    if combo:
        label = " / ".join(_field_label_for_variant(value_ref) for value_ref in combo)
    else:
        label = "Common conditions"
    return {
        "condition_id": f"cond_{index:03d}",
        "condition_label": label,
        "variable_values": values,
        "variable_value_refs": [dict(value_ref) for value_ref in combo],
    }


def split_condition_fields(source: Mapping[str, Any]) -> dict[str, Any]:
    """Split provided condition values into common and variable groups."""

    conditions = _conditions_section(source)
    state = source if isinstance(source.get(SECTION_CONDITIONS), Mapping) else {SECTION_CONDITIONS: conditions}
    fields = get_active_condition_fields(state)

    common_conditions: dict[str, Any] = {}
    variable_conditions: dict[str, Any] = {}
    missing_required_fields: list[dict[str, str]] = []
    boundary_bindings: list[dict[str, Any]] = []
    normalized_fields: list[dict[str, Any]] = []

    for field in fields:
        if not isinstance(field, Mapping):
            continue
        field_ref = condition_field_ref(field)
        value_refs = condition_value_refs(field)
        binding = boundary_binding_record(field)
        if value_refs and binding is not None:
            boundary_bindings.append(binding)

        normalized = {
            **field_ref,
            "values": value_refs,
            "value_count": len(value_refs),
            "role": "missing",
        }
        if len(value_refs) == 1:
            normalized["role"] = "common"
            common_conditions[field_ref["field_key"]] = {
                **field_ref,
                "value": value_refs[0],
                "values": value_refs,
                "value_count": 1,
            }
        elif len(value_refs) >= 2:
            normalized["role"] = "variable"
            variable_conditions[field_ref["field_key"]] = {
                **field_ref,
                "values": value_refs,
                "value_count": len(value_refs),
            }
        elif field_ref["required"]:
            missing_required_fields.append(
                {
                    "field_key": field_ref["field_key"],
                    "field_label": field_ref["field_label"],
                }
            )
        normalized_fields.append(normalized)

    return {
        "fields": normalized_fields,
        "common_conditions": common_conditions,
        "variable_conditions": variable_conditions,
        "boundary_bindings": boundary_bindings,
        "missing_required_fields": missing_required_fields,
    }


def generate_condition_axis(source: Mapping[str, Any], *, combination_strategy: str = "cartesian") -> ConditionPayload:
    """Return a condition-axis payload based on provided field values."""

    split = split_condition_fields(source)
    common_conditions = split["common_conditions"]
    variable_conditions = split["variable_conditions"]
    warnings: list[dict[str, str]] = []

    for item in split["missing_required_fields"]:
        warnings.append(
            {
                "code": "condition.required_missing",
                "field_key": item["field_key"],
                "message": f"Required condition field is missing: {item['field_label']}",
            }
        )

    for item in split["boundary_bindings"]:
        warnings.append(
            {
                "code": "condition.boundary_binding_pending",
                "field_key": item["field_key"],
                "message": "Boundary-like condition needs geometry-linked or condition-linked classification.",
            }
        )

    variable_value_groups = [
        list(condition["values"])
        for condition in variable_conditions.values()
        if isinstance(condition.get("values"), list) and condition.get("values")
    ]

    variants: list[dict[str, Any]] = []
    if variable_value_groups:
        for combo in product(*variable_value_groups):
            variants.append(_make_variant(len(variants) + 1, tuple(combo)))
    elif common_conditions:
        variants.append(_make_variant(1, tuple()))

    provided_value_count = sum(field.get("value_count", 0) for field in split["fields"])

    return {
        "axis_type": "condition",
        "generation_status": FIELD_STATUS_PROVIDED if variants else FIELD_STATUS_MISSING,
        "combination_strategy": combination_strategy,
        "common_conditions": common_conditions,
        "variable_conditions": variable_conditions,
        "condition_variants": variants,
        "boundary_bindings": split["boundary_bindings"],
        "source_inputs": {
            "provided_field_count": sum(1 for field in split["fields"] if field.get("value_count", 0) > 0),
            "provided_value_count": provided_value_count,
            "common_field_count": len(common_conditions),
            "variable_field_count": len(variable_conditions),
        },
        "warnings": warnings,
    }


def state_with_condition_axis(raw_state: Mapping[str, Any]) -> dict[str, Any]:
    """Return a sanitized state copy with condition axis payload populated."""

    state = sanitize_state(deepcopy(raw_state))
    axis = generate_condition_axis(state)
    conditions = state[SECTION_CONDITIONS]
    conditions["common_conditions"] = deepcopy(axis["common_conditions"])
    conditions["variable_conditions"] = deepcopy(axis["variable_conditions"])
    conditions["axis"] = {
        "axis_type": axis["axis_type"],
        "generation_status": axis["generation_status"],
        "combination_strategy": axis["combination_strategy"],
        "condition_variants": deepcopy(axis["condition_variants"]),
        "boundary_bindings": deepcopy(axis["boundary_bindings"]),
        "source_inputs": deepcopy(axis["source_inputs"]),
        "warnings": deepcopy(axis["warnings"]),
    }
    return state


def state_with_active_submission_conditions(raw_state: Mapping[str, Any]) -> dict[str, Any]:
    """Copy state for submission with only provided active condition values."""

    state = sanitize_state(deepcopy(raw_state))
    conditions = state[SECTION_CONDITIONS]
    active_fields = get_active_condition_fields(state)
    provided_fields = [field for field in active_fields if condition_value_refs(field)]
    provided_keys = {clean_text(field.get("key")) for field in provided_fields}
    provided_keys.discard("")

    conditions["fields"] = deepcopy(provided_fields)
    raw_values = conditions.get("condition_values")
    conditions["condition_values"] = {
        key: deepcopy(value)
        for key, value in raw_values.items()
        if key in provided_keys
    } if isinstance(raw_values, Mapping) else {}
    if "heat_exchanger_spec" not in provided_keys:
        conditions.pop("hex_spec", None)
    conditions["condition_options"] = {}

    axis = generate_condition_axis(state)
    conditions["common_conditions"] = deepcopy(axis["common_conditions"])
    conditions["variable_conditions"] = deepcopy(axis["variable_conditions"])
    conditions["axis"] = {
        "axis_type": axis["axis_type"],
        "generation_status": axis["generation_status"],
        "combination_strategy": axis["combination_strategy"],
        "condition_variants": deepcopy(axis["condition_variants"]),
        "boundary_bindings": deepcopy(axis["boundary_bindings"]),
        "source_inputs": deepcopy(axis["source_inputs"]),
        "warnings": deepcopy(axis["warnings"]),
    }

    input_structure = conditions.get("input_structure")
    if isinstance(input_structure, Mapping):
        groups: list[dict[str, Any]] = []
        raw_groups = input_structure.get("groups")
        for group in raw_groups if isinstance(raw_groups, list) else []:
            if not isinstance(group, Mapping):
                continue
            fields = [
                deepcopy(field)
                for field in group.get("fields", [])
                if isinstance(field, Mapping) and clean_text(field.get("key")) in provided_keys
            ]
            if fields:
                groups.append({**deepcopy(dict(group)), "fields": fields})
        conditions["input_structure"] = {**deepcopy(dict(input_structure)), "groups": groups}
    return state
