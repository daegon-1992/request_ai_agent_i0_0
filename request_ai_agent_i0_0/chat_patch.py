"""Proposal operation validation and approved patch application helpers.

Natural-language intent and value extraction belongs to the LLM client.  This
module deliberately does not parse user messages: it only validates the
structured operations returned by the LLM and applies an approved operation
set to a state copy.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping
from uuid import uuid4

from .agent_write_contract import (
    build_agent_write_contract,
    normalize_context_confirmation_operation,
    normalize_instance_write_operation,
    normalize_structural_write_operation,
)
from .constants import MAX_FANS_PER_OPERATING_CONDITION, SECTION_CASE_MATRIX, SECTION_CONDITIONS
from .condition_fieldsets import new_condition_card_id
from .schema import CONDITION_FIELD_SPECS
from .state import field_value, sanitize_state
from .request_context_confirmation import confirm_request_context_state
from .validator import state_with_validation


PatchOperation = dict[str, Any]
PatchProposal = dict[str, Any]

_SET_ALLOWED_PATHS = {
    "basic_info.request_no",
    "basic_info.division",
    "basic_info.department",
    "basic_info.requester_name",
    "basic_info.requester_role",
    "analysis_overview.project_name",
    "analysis_overview.development_grade",
    "analysis_overview.npi_stage",
    "analysis_overview.model_suffix",
    "analysis_overview.request_date",
    "analysis_overview.desired_completion_date",
    "analysis_overview.request_description",
    "analysis_overview.decision_use",
    "analysis_overview.additional_result_request",
    "geometry.has_changed_part",
    "geometry.changed_from_part",
}
_LIST_ALLOWED_PATHS = {"geometry.products", "geometry.parts"}
_LEGACY_PRODUCT_LIST_PATH = "geometry.products"
_CANONICAL_PRODUCT_ADAPTER = "geometry_products_to_complete_product_cards"


def _clean(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _dedupe(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean(value)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _listify_values(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [_clean(value)] if _clean(value) else []


def _with_value_metadata(operation: PatchOperation) -> PatchOperation:
    op = dict(operation)
    if op.get("op") in {"list_values", "condition_values"}:
        values = [_clean(item) for item in _listify_values(op.get("values")) if _clean(item)]
        if len(values) > 1:
            op["value_count"] = len(values)
            op["interpretation_note"] = f"{len(values)}개 값으로 LLM이 제안했습니다"
    return op


def _merge_duplicate_ops(operations: Iterable[Mapping[str, Any]]) -> list[PatchOperation]:
    out: list[PatchOperation] = []
    seen: set[tuple[str, ...]] = set()
    for raw in operations:
        if not isinstance(raw, Mapping):
            continue
        op = dict(raw)
        key = (
            _clean(op.get("op")),
            _clean(op.get("path")),
            _clean(op.get("field_key")),
            _clean(op.get("card_type")),
            _clean(op.get("geometry_id")),
            _clean(op.get("card_id")),
            _clean(op.get("fan_id")),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(_with_value_metadata(op))
    return out


def sanitize_external_operations(
    operations: Iterable[Mapping[str, Any]],
    *,
    source: str,
    state: Mapping[str, Any] | None = None,
) -> list[PatchOperation]:
    """Keep only structurally allowed LLM operations; do not infer values."""

    out: list[PatchOperation] = []
    condition_keys = {spec.key for spec in CONDITION_FIELD_SPECS}
    write_contract: dict[str, Any] | None = None
    for raw in operations:
        if not isinstance(raw, Mapping):
            continue
        op = _clean(raw.get("op"))
        path = _clean(raw.get("path"))
        label = _clean(raw.get("label")) or path
        confidence = _clean(raw.get("confidence")) or "medium"
        if confidence not in {"low", "medium", "high"}:
            confidence = "medium"
        merge_strategy = _clean(raw.get("merge_strategy")) or "replace"
        if merge_strategy not in {"replace", "append"}:
            merge_strategy = "replace"
        if op == "set" and path in _SET_ALLOWED_PATHS:
            value = raw.get("value")
            if _clean(value):
                out.append(
                    {
                        "op": "set",
                        "path": path,
                        "value": value,
                        "label": label,
                        "confidence": confidence,
                        "source": source,
                    }
                )
        elif op == "confirm_request_context" and isinstance(state, Mapping):
            normalized = normalize_context_confirmation_operation(raw, state=state, source=source)
            if normalized is not None:
                out.append(normalized)
        elif op == "list_values" and path in _LIST_ALLOWED_PATHS:
            values = _dedupe(_listify_values(raw.get("values")))
            if values:
                operation = {
                    "op": "list_values",
                    "path": path,
                    "values": values,
                    "merge_strategy": merge_strategy,
                    "label": label,
                    "confidence": confidence,
                    "source": source,
                }
                if path == _LEGACY_PRODUCT_LIST_PATH:
                    # The LLM-facing path remains stable, but the state has no
                    # ``geometry.products`` field.  Apply this through the
                    # canonical complete-product cards instead of retaining a
                    # legacy field that renderers and the Case Matrix ignore.
                    operation["adapter"] = _CANONICAL_PRODUCT_ADAPTER
                    operation["canonical_paths"] = [
                        "geometry.base_product.drawing_no",
                        "geometry.comparison_products[].drawing_no",
                    ]
                out.append(operation)
        elif op == "condition_values":
            field_key = _clean(raw.get("field_key"))
            values = _dedupe(_listify_values(raw.get("values")))
            if field_key in condition_keys and values:
                out.append(
                    {
                        "op": "condition_values",
                        "field_key": field_key,
                        "path": f"conditions.fields.{field_key}.values",
                        "values": values,
                        "merge_strategy": merge_strategy,
                        "label": label,
                        "confidence": confidence,
                        "source": source,
                    }
                )
        elif op in {"set_geometry_field", "set_condition_field"} and isinstance(state, Mapping):
            if write_contract is None:
                write_contract = build_agent_write_contract(state)
            normalized = normalize_instance_write_operation(raw, contract=write_contract, source=source)
            if normalized is not None:
                out.append(normalized)
        elif op in {"set_condition_card_series", "set_operating_fans"} and isinstance(state, Mapping):
            if write_contract is None:
                write_contract = build_agent_write_contract(state)
            normalized = normalize_structural_write_operation(raw, contract=write_contract, source=source)
            if normalized is not None:
                out.append(normalized)
    return _merge_duplicate_ops(out)


def _proposal_summary(operations: Iterable[Mapping[str, Any]]) -> str:
    lines: list[str] = []
    for operation in operations:
        label = _clean(operation.get("label")) or _clean(operation.get("path"))
        values = operation.get("values")
        value = ", ".join(_clean(item) for item in values) if isinstance(values, list) else _clean(operation.get("value"))
        if label and value:
            lines.append(f"{label}: {value}")
    return " / ".join(lines) or "LLM이 적용할 명시적 입력값을 제안하지 않았습니다."


def proposal_from_operations(
    message: str,
    operations: Iterable[Mapping[str, Any]],
    *,
    source: str,
    summary: str = "",
    warnings: Iterable[Any] | None = None,
    questions: Iterable[Any] | None = None,
    state: Mapping[str, Any] | None = None,
) -> PatchProposal:
    normalized = sanitize_external_operations(operations, source=source, state=state)
    question_list = [_clean(item) for item in questions or [] if _clean(item)]
    warning_list = [_clean(item) for item in warnings or [] if _clean(item)]
    status = "pending" if normalized else "needs_clarification" if question_list else "noop"
    proposal: PatchProposal = {
        "proposal_id": f"patch_{uuid4().hex[:10]}",
        "status": status,
        "intent": "patch" if normalized else "question" if question_list else "noop",
        "message": _clean(message),
        "operations": normalized,
        "summary": _clean(summary) or _proposal_summary(normalized),
        "warnings": _dedupe(warning_list),
        "questions": question_list,
        "state_changed": False,
        "read_only": True,
        "extraction_source": source,
    }
    if isinstance(state, Mapping):
        metadata = state.get("metadata")
        proposal["base_schema_version"] = _clean(metadata.get("schema_version")) if isinstance(metadata, Mapping) else ""
    return proposal


def _set_field(raw_state: dict[str, Any], path: str, value: Any) -> None:
    section_key, field_key = path.split(".", 1)
    section = dict(raw_state.get(section_key, {})) if isinstance(raw_state.get(section_key), Mapping) else {}
    section[field_key] = value
    raw_state[section_key] = section


def _current_row_values(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return []
    return [
        _clean(field_value(row, "") if isinstance(row, Mapping) else row)
        for row in rows
        if _clean(field_value(row, "") if isinstance(row, Mapping) else row)
    ]


def _set_list_values(raw_state: dict[str, Any], path: str, values: list[Any], *, merge_strategy: str) -> None:
    if path == _LEGACY_PRODUCT_LIST_PATH:
        _set_canonical_geometry_products(raw_state, values, merge_strategy=merge_strategy)
        return
    section_key, list_key = path.split(".", 1)
    section = dict(raw_state.get(section_key, {})) if isinstance(raw_state.get(section_key), Mapping) else {}
    cleaned = _dedupe(values)
    if merge_strategy == "append":
        cleaned = _dedupe(_current_row_values(section.get(list_key)) + cleaned)
    section[list_key] = cleaned
    raw_state[section_key] = section


def _canonical_product_values(geometry: Mapping[str, Any]) -> list[str]:
    base_product = geometry.get("base_product")
    comparisons = geometry.get("comparison_products")
    products = [base_product, *(comparisons if isinstance(comparisons, list) else [])]
    return _dedupe(
        field_value(product.get("drawing_no"), "")
        for product in products
        if isinstance(product, Mapping)
    )


def _set_canonical_geometry_products(
    raw_state: dict[str, Any],
    values: list[Any],
    *,
    merge_strategy: str,
) -> None:
    """Adapt the LLM list DTO to canonical base/comparison product cards."""

    geometry = dict(raw_state.get("geometry", {})) if isinstance(raw_state.get("geometry"), Mapping) else {}
    product_values = _dedupe(values)
    if merge_strategy == "append":
        product_values = _dedupe(_canonical_product_values(geometry) + product_values)
    if not product_values:
        return

    geometry["base_product"] = {
        "geometry_id": "base_001",
        "role": "base",
        "drawing_no": product_values[0],
    }
    geometry["comparison_products"] = [
        {
            "geometry_id": f"comparison_{index:03d}",
            "role": "comparison",
            "drawing_no": drawing_no,
        }
        for index, drawing_no in enumerate(product_values[1:], start=1)
    ]
    raw_state["geometry"] = geometry


def _set_condition_values(raw_state: dict[str, Any], field_key: str, values: list[Any], *, merge_strategy: str) -> None:
    conditions = dict(raw_state.get(SECTION_CONDITIONS, {})) if isinstance(raw_state.get(SECTION_CONDITIONS), Mapping) else {}
    fields = conditions.get("fields") if isinstance(conditions.get("fields"), list) else []
    updated: list[Any] = []
    handled = False
    for item in fields:
        if not isinstance(item, Mapping) or _clean(item.get("key")) != field_key:
            updated.append(item)
            continue
        next_item = dict(item)
        next_values = _dedupe(values)
        if merge_strategy == "append":
            next_values = _dedupe(_current_row_values(next_item.get("values")) + next_values)
        next_item["values"] = next_values
        updated.append(next_item)
        handled = True
    if not handled:
        spec = next((item for item in CONDITION_FIELD_SPECS if item.key == field_key), None)
        updated.append(
            {
                "key": field_key,
                "label": spec.label if spec else field_key,
                "required": bool(spec.required) if spec else False,
                "value_type": spec.value_type if spec else "text",
                "unit": spec.unit if spec else "",
                "binding": spec.binding if spec else "condition-linked",
                "legacy_key": spec.legacy_key if spec else "",
                "values": _dedupe(values),
            }
        )
    conditions["fields"] = updated
    raw_state[SECTION_CONDITIONS] = conditions


def _set_geometry_field(raw_state: dict[str, Any], geometry_id: str, field_key: str, value: Any) -> None:
    geometry = dict(raw_state.get("geometry", {})) if isinstance(raw_state.get("geometry"), Mapping) else {}
    base = geometry.get("base_product")
    if isinstance(base, Mapping) and _clean(base.get("geometry_id")) == geometry_id:
        next_base = dict(base)
        next_base[field_key] = value
        if field_key == "display_name":
            next_base["display_name_custom"] = True
        geometry["base_product"] = next_base
    else:
        comparisons = geometry.get("comparison_products")
        updated: list[Any] = []
        for card in comparisons if isinstance(comparisons, list) else []:
            if not isinstance(card, Mapping) or _clean(card.get("geometry_id")) != geometry_id:
                updated.append(card)
                continue
            next_card = dict(card)
            next_card[field_key] = value
            if field_key == "display_name":
                next_card["display_name_custom"] = True
            updated.append(next_card)
        geometry["comparison_products"] = updated
    raw_state["geometry"] = geometry


def _set_condition_field(
    raw_state: dict[str, Any],
    card_id: str,
    field_key: str,
    value: Any,
    *,
    fan_id: str = "",
) -> None:
    conditions = dict(raw_state.get(SECTION_CONDITIONS, {})) if isinstance(raw_state.get(SECTION_CONDITIONS), Mapping) else {}
    cards = conditions.get("condition_sets")
    updated_cards: list[Any] = []
    for card in cards if isinstance(cards, list) else []:
        if not isinstance(card, Mapping) or _clean(card.get("id")) != card_id:
            updated_cards.append(card)
            continue
        next_card = dict(card)
        if fan_id:
            fans = card.get("fans")
            updated_fans: list[Any] = []
            for fan in fans if isinstance(fans, list) else []:
                if not isinstance(fan, Mapping) or _clean(fan.get("id")) != fan_id:
                    updated_fans.append(fan)
                    continue
                next_fan = dict(fan)
                if field_key == "fan_location":
                    next_fan["location"] = value
                else:
                    fan_values = dict(fan.get("values", {})) if isinstance(fan.get("values"), Mapping) else {}
                    fan_values[field_key] = value
                    next_fan["values"] = fan_values
                updated_fans.append(next_fan)
            next_card["fans"] = updated_fans
        else:
            fields = dict(card.get("fields", {})) if isinstance(card.get("fields"), Mapping) else {}
            current = fields.get(field_key)
            next_field = dict(current) if isinstance(current, Mapping) else {}
            next_field.update({"value": value, "display_value": value, "source": "user"})
            fields[field_key] = next_field
            next_card["fields"] = fields
        updated_cards.append(next_card)
    conditions["condition_sets"] = updated_cards
    raw_state[SECTION_CONDITIONS] = conditions


def _set_condition_card_series(
    raw_state: dict[str, Any],
    card_type: str,
    field_key: str,
    values: list[Any],
) -> None:
    """Distribute scalar alternatives over existing canonical condition cards."""

    conditions = dict(raw_state.get(SECTION_CONDITIONS, {})) if isinstance(raw_state.get(SECTION_CONDITIONS), Mapping) else {}
    cards = conditions.get("condition_sets")
    card_list = list(cards) if isinstance(cards, list) else []
    existing = [card for card in card_list if isinstance(card, Mapping) and _clean(card.get("type")) == card_type]
    if not existing:
        return

    replacements: list[dict[str, Any]] = []
    allocated_ids = {
        _clean(card.get("id"))
        for card in card_list
        if isinstance(card, Mapping) and _clean(card.get("id"))
    }
    for index, value in enumerate(values, 1):
        source = existing[index - 1] if index <= len(existing) else existing[0]
        card = deepcopy(dict(source))
        if index > len(existing):
            card_id = new_condition_card_id(card_type)
            while card_id in allocated_ids:
                card_id = new_condition_card_id(card_type)
            allocated_ids.add(card_id)
            card["id"] = card_id
        card["is_default"] = index == 1
        if card_type == "operating":
            fans = card.get("fans") if isinstance(card.get("fans"), list) else []
            if len(fans) != 1:
                return
            fan = deepcopy(dict(fans[0])) if isinstance(fans[0], Mapping) else {}
            fan.update({"id": "fan_1", "running": True})
            fan_values = dict(fan.get("values", {})) if isinstance(fan.get("values"), Mapping) else {}
            fan_values["fan_rpm"] = value
            fan["values"] = fan_values
            card["fans"] = [fan]
            card["name"] = f"운전 {index}"
        else:
            fields = dict(card.get("fields", {})) if isinstance(card.get("fields"), Mapping) else {}
            current = fields.get(field_key)
            field = dict(current) if isinstance(current, Mapping) else {}
            field.update({"value": value, "display_value": value, "status": "provided", "source": "user"})
            fields[field_key] = field
            card["fields"] = fields
        replacements.append(card)

    updated: list[Any] = []
    inserted = False
    for card in card_list:
        if isinstance(card, Mapping) and _clean(card.get("type")) == card_type:
            if not inserted:
                updated.extend(replacements)
                inserted = True
            continue
        updated.append(card)
    conditions["condition_sets"] = updated
    raw_state[SECTION_CONDITIONS] = conditions


def _set_operating_fans(
    raw_state: dict[str, Any],
    card_id: str,
    values: list[Any],
    *,
    locations: Any = None,
    fan_rpm_mode: Any = None,
) -> None:
    conditions = dict(raw_state.get(SECTION_CONDITIONS, {})) if isinstance(raw_state.get(SECTION_CONDITIONS), Mapping) else {}
    cards = conditions.get("condition_sets")
    cleaned_values = [_clean(value) for value in values]
    if not 2 <= len(cleaned_values) <= MAX_FANS_PER_OPERATING_CONDITION or any(not value for value in cleaned_values):
        return
    updated: list[Any] = []
    for raw_card in cards if isinstance(cards, list) else []:
        if not isinstance(raw_card, Mapping) or _clean(raw_card.get("id")) != card_id or _clean(raw_card.get("type")) != "operating":
            updated.append(raw_card)
            continue
        card = dict(raw_card)
        existing = card.get("fans") if isinstance(card.get("fans"), list) else []
        mode_supplied = fan_rpm_mode is not None
        mode = _clean(fan_rpm_mode) if mode_supplied else _clean(card.get("fan_rpm_mode"))
        if mode_supplied and mode not in {"common", "individual"}:
            return
        locations_supplied = locations is not None
        if locations_supplied:
            if not isinstance(locations, list) or len(locations) != len(cleaned_values):
                return
            cleaned_locations = [_clean(location) for location in locations]
            if any(not location for location in cleaned_locations) or mode != "individual":
                return
        else:
            cleaned_locations = []
        if mode == "common" and len(set(cleaned_values)) != 1:
            return
        fans: list[dict[str, Any]] = []
        for index, value in enumerate(cleaned_values, 1):
            source = existing[index - 1] if index <= len(existing) and isinstance(existing[index - 1], Mapping) else {}
            fan = deepcopy(dict(source))
            fan.update({"id": f"fan_{index}", "running": True})
            if locations_supplied:
                fan["location"] = cleaned_locations[index - 1]
            fan_values = dict(fan.get("values", {})) if isinstance(fan.get("values"), Mapping) else {}
            fan_values["fan_rpm"] = value
            fan["values"] = fan_values
            fans.append(fan)
        card["fans"] = fans
        if mode_supplied:
            card["fan_rpm_mode"] = mode
        updated.append(card)
    conditions["condition_sets"] = updated
    raw_state[SECTION_CONDITIONS] = conditions


def apply_patch_operations(raw_state: Mapping[str, Any], operations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Apply approved, already-sanitized operations to a copy and normalize it."""

    raw = deepcopy(dict(raw_state or {}))
    for operation in operations:
        if not isinstance(operation, Mapping):
            continue
        op = _clean(operation.get("op"))
        path = _clean(operation.get("path"))
        if op == "set" and path in _SET_ALLOWED_PATHS:
            _set_field(raw, path, operation.get("value"))
        elif op == "confirm_request_context":
            context = operation.get("context")
            if isinstance(context, Mapping):
                raw, _fieldset = confirm_request_context_state(raw, context)
        elif op == "list_values" and path in _LIST_ALLOWED_PATHS:
            _set_list_values(raw, path, _listify_values(operation.get("values")), merge_strategy=_clean(operation.get("merge_strategy")) or "replace")
        elif op == "condition_values":
            field_key = _clean(operation.get("field_key"))
            if field_key:
                _set_condition_values(raw, field_key, _listify_values(operation.get("values")), merge_strategy=_clean(operation.get("merge_strategy")) or "replace")
        elif op == "set_geometry_field":
            _set_geometry_field(
                raw,
                _clean(operation.get("geometry_id")),
                _clean(operation.get("field_key")),
                operation.get("value"),
            )
        elif op == "set_condition_field":
            _set_condition_field(
                raw,
                _clean(operation.get("card_id")),
                _clean(operation.get("field_key")),
                operation.get("value"),
                fan_id=_clean(operation.get("fan_id")),
            )
        elif op == "set_condition_card_series":
            _set_condition_card_series(
                raw,
                _clean(operation.get("card_type")),
                _clean(operation.get("field_key")),
                _listify_values(operation.get("values")),
            )
        elif op == "set_operating_fans":
            _set_operating_fans(
                raw,
                _clean(operation.get("card_id")),
                _listify_values(operation.get("values")),
                locations=operation.get("locations"),
                fan_rpm_mode=operation.get("fan_rpm_mode"),
            )
    return state_with_validation(sanitize_state(raw))


def preview_patch(raw_state: Mapping[str, Any], proposal: Mapping[str, Any]) -> dict[str, Any]:
    operations = proposal.get("operations") if isinstance(proposal, Mapping) else []
    if not isinstance(operations, list) or not operations:
        return state_with_validation(raw_state if isinstance(raw_state, Mapping) else {})
    return apply_patch_operations(raw_state, operations)
