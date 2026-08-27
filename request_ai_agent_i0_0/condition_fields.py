"""Condition field normalization helpers."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .constants import FIELD_STATUS_PROVIDED
from .schema import CONDITION_FIELD_SPECS, FieldSpec
from .state import field_value


BINDING_CONDITION_LINKED = "condition-linked"
BINDING_GEOMETRY_LINKED = "geometry-linked"
BINDING_UNCLASSIFIED_BOUNDARY = "unclassified-boundary"

BOUNDARY_BINDING_OPTIONS = (
    BINDING_GEOMETRY_LINKED,
    BINDING_CONDITION_LINKED,
)

BOUNDARY_FIELD_KEYS = frozenset({"vane_or_louver", "filter_state"})
BOUNDARY_KEY_HINTS = ("vane", "louver", "filter", "flap")


def clean_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def slug(value: Any, fallback: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", clean_text(value))
    return token.strip("_") or fallback


def field_catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": spec.key,
            "label": spec.label,
            "required": spec.required,
            "value_type": spec.value_type,
            "unit": spec.unit,
            "binding": spec.binding or BINDING_CONDITION_LINKED,
            "legacy_key": spec.legacy_key,
            "is_boundary": is_boundary_field(spec),
        }
        for spec in CONDITION_FIELD_SPECS
    ]


def is_boundary_field(field: Mapping[str, Any] | FieldSpec | str) -> bool:
    if isinstance(field, str):
        key = clean_text(field)
        binding = ""
    elif isinstance(field, FieldSpec):
        key = clean_text(field.key)
        binding = clean_text(field.binding)
    else:
        key = clean_text(field.get("key"))
        binding = clean_text(field.get("binding"))

    key_token = key.lower()
    return (
        binding == BINDING_UNCLASSIFIED_BOUNDARY
        or key in BOUNDARY_FIELD_KEYS
        or any(hint in key_token for hint in BOUNDARY_KEY_HINTS)
    )


def condition_field_ref(field: Mapping[str, Any]) -> dict[str, Any]:
    key = clean_text(field.get("key"))
    return {
        "field_key": key,
        "field_label": clean_text(field.get("label")) or key,
        "required": bool(field.get("required", False)),
        "value_type": clean_text(field.get("value_type")) or "text",
        "unit": clean_text(field.get("unit")),
        "binding": clean_text(field.get("binding")) or BINDING_CONDITION_LINKED,
        "legacy_key": clean_text(field.get("legacy_key")),
        "is_boundary": is_boundary_field(field),
    }


def _value_label(value: Any, unit: str) -> str:
    label = clean_text(value)
    if not label or not unit:
        return label
    if unit.lower() in label.lower():
        return label
    return f"{label} {unit}"


def condition_value_refs(field: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(field.get("values"), list):
        return []
    if is_boundary_field(field) and field.get("active") is False:
        return []

    field_ref = condition_field_ref(field)
    refs: list[dict[str, Any]] = []
    for index, row in enumerate(field.get("values", []), start=1):
        if not isinstance(row, Mapping):
            continue
        if row.get("status") != FIELD_STATUS_PROVIDED:
            continue
        value = field_value(row)
        raw_label = clean_text(value)
        if not raw_label:
            continue
        value_id = slug(row.get("id"), f"{field_ref['field_key']}_value_{index}")
        refs.append(
            {
                **field_ref,
                "value_id": value_id,
                "value": value,
                "raw_label": raw_label,
                "label": _value_label(value, field_ref["unit"]),
                "source": clean_text(row.get("source")),
                "note": clean_text(row.get("note")),
            }
        )
    return refs


def boundary_binding_record(field: Mapping[str, Any]) -> dict[str, Any] | None:
    if not is_boundary_field(field):
        return None

    field_ref = condition_field_ref(field)
    return {
        "field_key": field_ref["field_key"],
        "field_label": field_ref["field_label"],
        "current_binding": field_ref["binding"],
        "normalized_axis_binding": None,
        "classification_status": "pending",
        "allowed_bindings": list(BOUNDARY_BINDING_OPTIONS),
        "llm_decision": None,
        "reason": "",
    }
