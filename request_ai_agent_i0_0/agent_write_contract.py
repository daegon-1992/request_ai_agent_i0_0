"""State-aware write targets for a future Agent decision step.

The contract is read-only.  It derives general and condition writability from
the existing Field Registry and Form Context, then binds those fields to the
instances that exist in the current canonical Request State.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .field_registry import get_field_registry
from .field_registry import get_geometry_products_adapter
from .form_context import build_form_context
from .product_taxonomy import find_product_taxonomy_matches
from .constants import DISABLED_ANALYSIS_TYPE_OPTIONS, ENABLED_ANALYSIS_TYPE_OPTIONS, MAX_FANS_PER_OPERATING_CONDITION
from .state import field_value


AGENT_WRITE_CONTRACT_VERSION = "agent_canonical_write_v1"

_REQUESTER_INFO_PATHS = frozenset(
    {
        "basic_info.division",
        "basic_info.department",
        "basic_info.requester_name",
        "basic_info.requester_role",
    }
)

_GEOMETRY_FIELD_DEFINITIONS: dict[str, dict[str, str]] = {
    "drawing_no": {"label": "총조립도 도면번호 (NPDM MCAD)", "value_type": "text", "unit": ""},
    "display_name": {"label": "표시 이름", "value_type": "text", "unit": ""},
    "difference_from_base": {"label": "Base 대비 변경점", "value_type": "text", "unit": ""},
}


def _clean(value: Any) -> str:
    return str("" if value is None else value).replace("\x00", "").strip()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _general_targets(state: Mapping[str, Any], form_fields: Mapping[str, Any]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for field in get_field_registry(state):
        if not field.active or not field.field_id.startswith(("basic_info.", "analysis_overview.")):
            continue
        context = form_fields.get(field.field_id)
        if context is None or context.system_generated or context.read_only:
            continue
        section = _as_mapping(state.get(field.field_id.split(".", 1)[0]))
        target = {
            "path": field.operation_path,
            "label": field.label,
            "value_type": field.value_type,
            "unit": field.unit,
            "current_value": deepcopy(field_value(section.get(field.field_key), "")),
        }
        if field.field_id in _REQUESTER_INFO_PATHS:
            target["section"] = "의뢰자 정보"
            target["semantic_scope"] = "requester_profile"
        targets.append(target)
    return targets


def _geometry_cards(state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    geometry = _as_mapping(state.get("geometry"))
    comparisons = geometry.get("comparison_products")
    return [
        card
        for card in [geometry.get("base_product"), *(comparisons if isinstance(comparisons, list) else [])]
        if isinstance(card, Mapping) and _clean(card.get("geometry_id"))
    ]


def _geometry_targets(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for card in _geometry_cards(state):
        role = _clean(card.get("role"))
        field_keys = ["drawing_no", "display_name"]
        if role == "comparison":
            field_keys.append("difference_from_base")
        targets.append(
            {
                "geometry_id": _clean(card.get("geometry_id")),
                "role": role,
                "fields": [
                    {
                        "field_key": field_key,
                        **_GEOMETRY_FIELD_DEFINITIONS[field_key],
                        "current_value": deepcopy(field_value(card.get(field_key), "")),
                    }
                    for field_key in field_keys
                ],
            }
        )
    return targets


def _product_cards_target(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    adapter = get_geometry_products_adapter()
    values = [
        deepcopy(field_value(card.get("drawing_no"), ""))
        for card in _geometry_cards(state)
        if _clean(field_value(card.get("drawing_no"), ""))
    ]
    return [
        {
            "path": adapter.transport_path,
            "label": "해석 제품",
            "value_type": "text_list",
            "current_values": values,
            "adapter": adapter.adapter_id,
            "canonical_paths": list(adapter.canonical_paths),
            "role_policy": "첫 값은 기존 Base 제품, 이후 값은 기존 비교 제품 정책을 유지",
        }
    ]


def _condition_card(state: Mapping[str, Any], card_id: str) -> Mapping[str, Any]:
    conditions = _as_mapping(state.get("conditions"))
    cards = conditions.get("condition_sets")
    if not isinstance(cards, list):
        return {}
    return next(
        (card for card in cards if isinstance(card, Mapping) and _clean(card.get("id")) == card_id),
        {},
    )


def _condition_targets(
    state: Mapping[str, Any],
    form_fields: Mapping[str, Any],
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for field in get_field_registry(state):
        if not field.field_id.startswith("conditions.") or not field.active:
            continue
        context = form_fields.get(field.field_id)
        if context is None or context.system_generated or context.read_only:
            continue
        card = _condition_card(state, field.card_id)
        if not card:
            continue
        target: dict[str, Any] = {
            "card_id": field.card_id,
            "card_type": _clean(card.get("type")),
            "field_key": field.field_key,
            "label": field.label,
            "value_type": field.value_type,
            "unit": field.unit,
            "requires_fan_id": field.field_key == "fan_rpm",
        }
        if field.field_key == "fan_rpm":
            fans = card.get("fans")
            target["fan_rpm_mode"] = _clean(card.get("fan_rpm_mode"))
            target["fans"] = [
                {
                    "fan_id": _clean(fan.get("id")),
                    "name": _clean(fan.get("name")),
                    "location": _clean(fan.get("location")),
                    "current_value": deepcopy(_as_mapping(fan.get("values")).get("fan_rpm", "")),
                }
                for fan in (fans if isinstance(fans, list) else [])
                if isinstance(fan, Mapping) and _clean(fan.get("id"))
            ]
        else:
            target["current_value"] = deepcopy(
                field_value(_as_mapping(card.get("fields")).get(field.field_key), "")
            )
        targets.append(target)
        if target["card_type"] == "operating" and field.field_key == "fan_rpm":
            location_target = deepcopy(target)
            location_target.update({"field_key": "fan_location", "label": "팬 위치", "unit": "", "requires_fan_id": True})
            location_target["fans"] = [
                {**fan, "current_value": fan["location"]}
                for fan in target["fans"]
            ]
            targets.append(location_target)
    return targets


def _condition_series_targets(condition_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for target in condition_targets:
        key = (_clean(target.get("card_type")), _clean(target.get("field_key")))
        grouped.setdefault(key, []).append(target)

    result: list[dict[str, Any]] = []
    for (card_type, field_key), targets in grouped.items():
        if not card_type or not field_key:
            continue
        current_values: list[Any] = []
        if field_key == "fan_rpm":
            if any(len(target.get("fans", [])) != 1 for target in targets):
                continue
            current_values = [deepcopy(target["fans"][0].get("current_value", "")) for target in targets]
        else:
            current_values = [deepcopy(target.get("current_value", "")) for target in targets]
        first = targets[0]
        result.append(
            {
                "card_type": card_type,
                "field_key": field_key,
                "label": _clean(first.get("label")) or field_key,
                "value_type": first.get("value_type", "text"),
                "unit": first.get("unit", ""),
                "current_values": current_values,
                "semantics": "각 values 항목은 같은 종류의 조건 카드 하나에 대응하며 카드 안의 값은 scalar",
            }
        )
    return result


def _operating_fan_targets(condition_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "card_id": target["card_id"],
            "card_type": "operating",
            "field_key": "fan_rpm",
            "label": target.get("label", "팬 회전수(RPM)"),
            "unit": target.get("unit", "RPM"),
            "current_fans": deepcopy(target.get("fans", [])),
            "fan_rpm_mode": _clean(target.get("fan_rpm_mode")),
            "semantics": "values 항목들은 한 운전 조건에 동시에 존재하는 Fan들에 각각 대응",
        }
        for target in condition_targets
        if target.get("card_type") == "operating" and target.get("field_key") == "fan_rpm"
    ]


def normalize_context_confirmation_operation(
    raw: Mapping[str, Any],
    *,
    state: Mapping[str, Any],
    source: str,
) -> dict[str, Any] | None:
    """Validate the one-shot Context operation against canonical catalogs."""

    context_state = _as_mapping(state.get("request_context"))
    if context_state.get("context_locked") is True or _clean(raw.get("op")) != "confirm_request_context":
        return None
    raw_context = raw.get("context")
    if not isinstance(raw_context, Mapping):
        return None
    analysis_type = _clean(raw_context.get("analysis_type"))
    if not analysis_type:
        return None
    if analysis_type in DISABLED_ANALYSIS_TYPE_OPTIONS or analysis_type not in ENABLED_ANALYSIS_TYPE_OPTIONS:
        return None
    taxonomy_id = _clean(raw_context.get("taxonomy_id"))
    criteria = {"taxonomy_id": taxonomy_id} if taxonomy_id else {
        "division": _clean(raw_context.get("division")),
        "product_lineup": _clean(raw_context.get("product_lineup")),
        "platform": _clean(raw_context.get("platform")),
        "chassis": None if raw_context.get("chassis") is None else _clean(raw_context.get("chassis")),
    }
    if not taxonomy_id and any(not criteria[key] for key in ("division", "product_lineup", "platform")):
        return None
    hierarchy = find_product_taxonomy_matches(criteria)
    if len(hierarchy) != 1:
        return None
    context = {
        "taxonomy_id": _clean(hierarchy[0].get("taxonomy_id")),
        "analysis_type": analysis_type,
    }
    return {
        "op": "confirm_request_context",
        "context": context,
        "label": _clean(raw.get("label")) or "의뢰 대상과 해석유형 확정",
        "confidence": "high",
        "source": source,
    }


def build_agent_write_contract(state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the writable targets that exist in the current Request State."""

    source = state if isinstance(state, Mapping) else {}
    form = build_form_context(source)
    form_fields = {field.field_id: field for field in form.fields}
    condition_targets = _condition_targets(source, form_fields)
    return {
        "version": AGENT_WRITE_CONTRACT_VERSION,
        "operations": {
            "confirm_request_context": {
                "required": ["op", "context"],
                "available": _as_mapping(source.get("request_context")).get("context_locked") is not True,
                "semantics": "taxonomy_id 또는 Division·Product Line-up·Platform·Chassis의 정확한 단일 경로와 해석유형을 검증하고 최초 한 번 확정",
            },
            "set": {
                "required": ["op", "path", "value"],
                "targets": _general_targets(source, form_fields),
            },
            "set_geometry_field": {
                "required": ["op", "geometry_id", "field_key", "value"],
                "targets": _geometry_targets(source),
            },
            "list_values": {
                "required": ["op", "path", "values"],
                "targets": _product_cards_target(source),
            },
            "set_condition_field": {
                "required": ["op", "card_id", "field_key", "value"],
                "conditional_required": {"fan_id": "field_key in [fan_rpm, fan_location]"},
                "targets": condition_targets,
            },
            "set_condition_card_series": {
                "required": ["op", "card_type", "field_key", "values"],
                "targets": _condition_series_targets(condition_targets),
            },
            "set_operating_fans": {
                "required": ["op", "card_id", "values"],
                "optional": ["locations", "fan_rpm_mode"],
                "targets": _operating_fan_targets(condition_targets),
            },
        },
        "unsupported_write_scopes": [
            "locked_request_context_change",
            "case_matrix",
            "clear_or_delete",
            "multi_field_pairing",
            "cartesian_product_generation",
        ],
    }


def normalize_instance_write_operation(
    raw: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    source: str,
) -> dict[str, Any] | None:
    """Validate and normalize one instance-aware operation against a contract."""

    op = _clean(raw.get("op"))
    operations = _as_mapping(contract.get("operations"))
    definition = _as_mapping(operations.get(op))
    targets = definition.get("targets")
    value = raw.get("value")
    if op not in {"set_geometry_field", "set_condition_field"} or not isinstance(targets, list) or not _clean(value):
        return None

    confidence = _clean(raw.get("confidence")) or "medium"
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"

    if op == "set_geometry_field":
        geometry_id = _clean(raw.get("geometry_id"))
        field_key = _clean(raw.get("field_key"))
        target = next(
            (
                item
                for item in targets
                if isinstance(item, Mapping) and _clean(item.get("geometry_id")) == geometry_id
            ),
            None,
        )
        fields = target.get("fields") if isinstance(target, Mapping) else None
        if not isinstance(fields, list) or not any(
            isinstance(field, Mapping) and _clean(field.get("field_key")) == field_key for field in fields
        ):
            return None
        path = f"geometry[geometry_id={geometry_id}].{field_key}"
        return {
            "op": op,
            "geometry_id": geometry_id,
            "field_key": field_key,
            "path": path,
            "value": value,
            "label": _clean(raw.get("label")) or path,
            "confidence": confidence,
            "source": source,
        }

    card_id = _clean(raw.get("card_id"))
    field_key = _clean(raw.get("field_key"))
    target = next(
        (
            item
            for item in targets
            if isinstance(item, Mapping)
            and _clean(item.get("card_id")) == card_id
            and _clean(item.get("field_key")) == field_key
        ),
        None,
    )
    if not isinstance(target, Mapping):
        return None
    fan_id = _clean(raw.get("fan_id"))
    if target.get("requires_fan_id") is True:
        fans = target.get("fans")
        if not fan_id or not isinstance(fans, list) or not any(
            isinstance(fan, Mapping) and _clean(fan.get("fan_id")) == fan_id for fan in fans
        ):
            return None
        path = (
            f"conditions.condition_sets[card_id={card_id}].fans[fan_id={fan_id}].location"
            if field_key == "fan_location"
            else f"conditions.condition_sets[card_id={card_id}].fans[fan_id={fan_id}].values.{field_key}"
        )
    elif fan_id:
        return None
    else:
        path = f"conditions.condition_sets[card_id={card_id}].fields.{field_key}.value"
    operation = {
        "op": op,
        "card_id": card_id,
        "field_key": field_key,
        "path": path,
        "value": value,
        "label": _clean(raw.get("label")) or path,
        "confidence": confidence,
        "source": source,
    }
    if fan_id:
        operation["fan_id"] = fan_id
    return operation


def normalize_structural_write_operation(
    raw: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    source: str,
) -> dict[str, Any] | None:
    """Validate the minimal existing-card adapters exposed to the Main Agent."""

    op = _clean(raw.get("op"))
    if op not in {"set_condition_card_series", "set_operating_fans"}:
        return None
    definition = _as_mapping(_as_mapping(contract.get("operations")).get(op))
    targets = definition.get("targets")
    values = raw.get("values")
    if not isinstance(targets, list) or not isinstance(values, list) or len(values) < 2:
        return None
    normalized_values = [_clean(value) for value in values]
    if any(not value for value in normalized_values):
        return None
    confidence = _clean(raw.get("confidence")) or "medium"
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"

    if op == "set_condition_card_series":
        card_type = _clean(raw.get("card_type"))
        field_key = _clean(raw.get("field_key"))
        target = next(
            (
                item
                for item in targets
                if isinstance(item, Mapping)
                and _clean(item.get("card_type")) == card_type
                and _clean(item.get("field_key")) == field_key
            ),
            None,
        )
        if not isinstance(target, Mapping):
            return None
        path = f"conditions.condition_sets[type={card_type}].{field_key}"
        return {
            "op": op,
            "card_type": card_type,
            "field_key": field_key,
            "path": path,
            "values": normalized_values,
            "label": _clean(raw.get("label")) or _clean(target.get("label")) or path,
            "confidence": confidence,
            "source": source,
        }

    card_id = _clean(raw.get("card_id"))
    target = next(
        (item for item in targets if isinstance(item, Mapping) and _clean(item.get("card_id")) == card_id),
        None,
    )
    if not isinstance(target, Mapping):
        return None
    if len(normalized_values) > MAX_FANS_PER_OPERATING_CONDITION:
        return None
    raw_mode = raw.get("fan_rpm_mode")
    mode_supplied = raw_mode is not None
    fan_rpm_mode = _clean(raw_mode) if mode_supplied else _clean(target.get("fan_rpm_mode"))
    if mode_supplied and fan_rpm_mode not in {"common", "individual"}:
        return None
    raw_locations = raw.get("locations")
    locations_supplied = raw_locations is not None
    if locations_supplied:
        if not isinstance(raw_locations, list) or len(raw_locations) != len(normalized_values):
            return None
        locations = [_clean(location) for location in raw_locations]
        if any(not location for location in locations) or fan_rpm_mode != "individual":
            return None
    else:
        locations = []
    if fan_rpm_mode == "common" and len(set(normalized_values)) != 1:
        return None
    path = f"conditions.condition_sets[card_id={card_id}].fans[*].values.fan_rpm"
    operation = {
        "op": op,
        "card_id": card_id,
        "field_key": "fan_rpm",
        "path": path,
        "values": normalized_values,
        "label": _clean(raw.get("label")) or _clean(target.get("label")) or path,
        "confidence": confidence,
        "source": source,
    }
    if locations_supplied:
        operation["locations"] = locations
    if mode_supplied:
        operation["fan_rpm_mode"] = fan_rpm_mode
    return operation
