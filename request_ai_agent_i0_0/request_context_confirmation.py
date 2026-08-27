"""Shared request-context confirmation used by the UI and Main Agent."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping
from uuid import uuid4

from .condition_fieldsets import build_condition_fieldset
from .constants import (
    DISABLED_ANALYSIS_TYPE_OPTIONS,
    ENABLED_ANALYSIS_TYPE_OPTIONS,
    SECTION_BASIC_INFO,
    SECTION_REQUEST_CONTEXT,
    VALUE_SOURCE_SYSTEM,
)
from .product_taxonomy import find_product_taxonomy_matches, load_product_taxonomy, taxonomy_path_by_id
from .state import apply_analysis_overview_defaults, field_value, generate_request_no, make_field
from .validator import state_with_validation


def _clean(value: Any) -> str:
    return str("" if value is None else value).replace("\x00", "").strip()


def _request_no(state: Mapping[str, Any]) -> str:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), Mapping) else {}
    basic = state.get(SECTION_BASIC_INFO) if isinstance(state.get(SECTION_BASIC_INFO), Mapping) else {}
    return str(metadata.get("request_no") or field_value(basic.get("request_no"), "") or "")


def _assign_request_no(state: dict[str, Any]) -> dict[str, Any]:
    if _request_no(state):
        return state
    request_no = generate_request_no(sequence=int(uuid4().hex[:8], 16) % 999_999_999 + 1)
    metadata = dict(state.get("metadata") if isinstance(state.get("metadata"), Mapping) else {})
    metadata["request_no"] = request_no
    metadata["request_no_generated"] = True
    state["metadata"] = metadata
    basic = dict(state.get(SECTION_BASIC_INFO) if isinstance(state.get(SECTION_BASIC_INFO), Mapping) else {})
    basic["request_no"] = make_field(request_no, source=VALUE_SOURCE_SYSTEM)
    state[SECTION_BASIC_INFO] = basic
    return state


def confirm_request_context_state(
    raw_state: Mapping[str, Any],
    raw_context: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate, lock, and materialize the canonical Context fieldset once."""

    state = state_with_validation(raw_state)
    current_context = dict(
        state.get(SECTION_REQUEST_CONTEXT)
        if isinstance(state.get(SECTION_REQUEST_CONTEXT), Mapping)
        else {}
    )
    if current_context.get("context_locked") is True:
        raise ValueError("request_context_already_locked")
    for key in ("taxonomy_id", "division", "product_lineup", "platform", "analysis_type", "operation_mode"):
        value = _clean(raw_context.get(key))
        if value:
            current_context[key] = value
    if "chassis" in raw_context:
        current_context["chassis"] = None if raw_context.get("chassis") is None else _clean(raw_context.get("chassis"))
    missing = [key for key in ("analysis_type",) if not _clean(current_context.get(key))]
    if missing:
        raise ValueError("missing_context:" + ",".join(missing))
    taxonomy_path = taxonomy_path_by_id(current_context.get("taxonomy_id"))
    if taxonomy_path is None:
        criteria = {
            "division": _clean(current_context.get("division")),
            "product_lineup": _clean(current_context.get("product_lineup")),
            "platform": _clean(current_context.get("platform")),
            "chassis": current_context.get("chassis"),
        }
        if any(not criteria[key] for key in ("division", "product_lineup", "platform")):
            raise ValueError("missing_context:taxonomy_id")
        matches = find_product_taxonomy_matches(criteria)
        taxonomy_path = matches[0] if len(matches) == 1 else None
    if taxonomy_path is None:
        raise ValueError("invalid_taxonomy_id:" + _clean(current_context.get("taxonomy_id")))
    for key in ("division", "product_lineup", "platform"):
        supplied = _clean(raw_context.get(key))
        if supplied and supplied.casefold() != _clean(taxonomy_path.get(key)).casefold():
            raise ValueError("invalid_taxonomy_id:" + _clean(current_context.get("taxonomy_id")))
    if "chassis" in raw_context:
        supplied_chassis = raw_context.get("chassis")
        canonical_chassis = taxonomy_path.get("chassis")
        chassis_matches = (
            supplied_chassis is None and canonical_chassis is None
        ) or (
            supplied_chassis is not None
            and canonical_chassis is not None
            and _clean(supplied_chassis).casefold() == _clean(canonical_chassis).casefold()
        )
        if not chassis_matches:
            raise ValueError("invalid_taxonomy_id:" + _clean(current_context.get("taxonomy_id")))
    current_context.update(
        {
            "taxonomy_id": _clean(taxonomy_path.get("taxonomy_id")),
            "taxonomy_version": _clean(load_product_taxonomy().get("taxonomy_version")),
            "division": _clean(taxonomy_path.get("division")),
            "product_lineup": _clean(taxonomy_path.get("product_lineup")),
            "platform": _clean(taxonomy_path.get("platform")),
            "chassis": taxonomy_path.get("chassis") if taxonomy_path.get("chassis") is None else _clean(taxonomy_path.get("chassis")),
            "display_path": _clean(taxonomy_path.get("display_path")),
        }
    )
    analysis_type = _clean(current_context.get("analysis_type"))
    if analysis_type in DISABLED_ANALYSIS_TYPE_OPTIONS:
        raise ValueError("disabled_analysis_type:" + analysis_type)
    if analysis_type not in ENABLED_ANALYSIS_TYPE_OPTIONS:
        raise ValueError("unsupported_analysis_type:" + analysis_type)

    fieldset = build_condition_fieldset(current_context)
    current_context["analysis_type"] = _clean(fieldset.get("analysis_type")) or analysis_type
    current_context["operation_mode"] = _clean(fieldset.get("operation_mode"))
    current_context["condition_fieldset_key"] = _clean(fieldset.get("key"))
    groups = fieldset.get("groups")
    current_context["condition_fieldset_snapshot"] = deepcopy(groups if isinstance(groups, list) else [])
    current_context["context_locked"] = True
    state[SECTION_REQUEST_CONTEXT] = current_context
    state = apply_analysis_overview_defaults(state)
    state = _assign_request_no(state)
    return state_with_validation(state), fieldset
