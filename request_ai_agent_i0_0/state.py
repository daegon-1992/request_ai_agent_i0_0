"""State creation and normalization for the request assistant."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
import os
import re
from typing import Any, Iterable, Mapping

from .constants import (
    ANALYSIS_TYPE_ALIASES,
    ANALYSIS_TYPE_OPTIONS,
    DEFAULT_RAG_SCOPE,
    DEFAULT_REQUEST_NO_PREFIX,
    DEMO_CONDITION_MODE,
    DEMO_REQUEST_NO_PREFIX,
    ENABLED_ANALYSIS_TYPE_OPTIONS,
    FIELD_STATUS_MISSING,
    FIELD_STATUS_NONE,
    FIELD_STATUS_PROVIDED,
    FIELD_STATUS_SKIPPED,
    FIELD_STATUS_UNKNOWN,
    FIELD_STATUSES,
    NONE_TOKENS,
    SECTION_ANALYSIS_OVERVIEW,
    SECTION_BASIC_INFO,
    SECTION_CASE_MATRIX,
    SECTION_CONDITIONS,
    SECTION_GEOMETRY,
    SECTION_LEGACY_INTERNAL,
    SECTION_METADATA,
    SECTION_REQUEST_CONTEXT,
    SECTION_REVIEW,
    SKIPPED_TOKENS,
    STATE_SCHEMA_VERSION,
    UNKNOWN_TOKENS,
    VALUE_SOURCE_LEGACY_INTERNAL,
    VALUE_SOURCE_SYSTEM,
    VALUE_SOURCE_USER,
)
from .condition_fieldsets import (
    build_condition_fieldset,
    build_condition_input_structure,
    default_condition_sets,
    get_active_case_matrix_columns,
    get_active_condition_fields,
    sanitize_condition_sets,
)
from .product_taxonomy import load_product_taxonomy, taxonomy_path_by_id
from .schema import ANALYSIS_OVERVIEW_SPECS, BASIC_INFO_SPECS, CONDITION_FIELD_SPECS, FieldSpec


Field = dict[str, Any]
State = dict[str, Any]

TITLE_MAX_CHARS = 64
HEX_SPEC_DEFAULTS = {
    "fin_type": "WIDE LOUVER PLUS",
    "tube_diameter": "7PI",
    "row_count": "3R",
    "fpi": "14FPI",
}

DECISION_USE_CODES = (
    "problem_analysis",
    "design_review",
    "performance_validation",
    "other",
    "undecided",
)
DECISION_USE_LEGACY_CODES = {
    "design_selection": "design_review",
    "change_applicability": "design_review",
    "root_cause": "problem_analysis",
    "improvement_direction": "problem_analysis",
    "phenomenon_review": "problem_analysis",
    "performance_requirement": "performance_validation",
    "other": "other",
    "undecided": "undecided",
}
DECISION_USE_DISPLAY = {
    "problem_analysis": "문제·현상 분석",
    "design_review": "설계·변경 검토",
    "performance_validation": "성능·시험 검증",
    "other": "기타",
    "undecided": "아직 결정하지 못함",
}


REQUEST_CONTEXT_KEYS = (
    "taxonomy_id",
    "taxonomy_version",
    "division",
    "product_lineup",
    "platform",
    "chassis",
    "display_path",
    "analysis_type",
    "operation_mode",
    "context_locked",
    "condition_fieldset_key",
    "condition_fieldset_snapshot",
)

LEGACY_CONDITION_VALUE_MIGRATION_CANDIDATES = {
    "fan_rpm": (
        "conditions.fields[fan_rpm]",
        "conditions.fan_rpm",
        "analysis_overview.fan_rpm",
        "metadata.fan_rpm",
        "fanRpm",
    ),
    "room_temp": (
        "conditions.fields[room_temp]",
        "conditions.room_temp",
        "analysis_overview.room_temp",
        "metadata.room_temp",
        "roomTemp",
    ),
    "room_rh": (
        "conditions.fields[room_rh]",
        "conditions.room_rh",
        "analysis_overview.room_rh",
        "metadata.room_rh",
        "roomRH",
    ),
}

LEGACY_CONDITION_KEY_ALIASES = {
    "fanrpm": "fan_rpm",
    "fan_rpm": "fan_rpm",
    "heatexchangerspec": "heat_exchanger_spec",
    "heat_exchanger_spec": "heat_exchanger_spec",
    "roomtemp": "room_temp",
    "room_temp": "room_temp",
    "roomrh": "room_rh",
    "room_rh": "room_rh",
    "heatexchangertemp": "heat_exchanger_temp",
    "heat_exchanger_temp": "heat_exchanger_temp",
    "hex_temp": "heat_exchanger_temp",
    "heatexchangerrh": "heat_exchanger_rh",
    "heat_exchanger_rh": "heat_exchanger_rh",
    "hex_rh": "heat_exchanger_rh",
}

LEGACY_PRODUCT_VALUE_KEYS = (
    "product_modeling_no",
    "product_modeling_number",
    "productModelingNo",
    "productModelingNumber",
    "product",
)

LEGACY_BASE_PART_VALUE_KEYS = (
    "changed_from_part",
    "changedFromPart",
    "changed_part_modeling_no",
    "changedPartModelingNo",
    "base_part",
    "basePart",
    "base_modeling_no",
    "baseModelingNo",
)


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _slug(value: Any, fallback: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", _clean_text(value))
    return token.strip("_") or fallback


def _condition_key_alias(key: Any) -> str:
    clean_key = _clean_text(key)
    if not clean_key:
        return ""
    compact = _token(clean_key)
    return LEGACY_CONDITION_KEY_ALIASES.get(compact, clean_key)


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = _clean_text(os.getenv(name))
    if not raw:
        return default
    return raw.lower() not in {"0", "false", "no", "off"}


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    token = _clean_text(value).lower()
    if not token:
        return default
    if token in {"0", "false", "no", "off", "unchecked"}:
        return False
    if token in {"1", "true", "yes", "on", "checked"}:
        return True
    return default


def _sanitize_chat_history(raw: Any, *, limit: int = 200) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        role = _clean_text(item.get("role"))
        if role not in {"user", "assistant"}:
            role = "assistant"
        content = _clean_text(item.get("content"))
        html = _clean_text(item.get("html"))
        if not content and not html:
            continue
        rows.append({"role": role, "content": content, "html": html})
    return rows[-limit:]


def _request_prefix() -> str:
    configured = _clean_text(os.getenv("REQUEST_AGENT_REQUEST_NO_PREFIX"))
    if configured:
        return configured
    return DEMO_REQUEST_NO_PREFIX if _env_flag("REQUEST_AGENT_DEMO_MODE", default=False) else DEFAULT_REQUEST_NO_PREFIX


def generate_request_no(today: date | None = None, *, sequence: int = 1) -> str:
    """Return a deterministic daily request number for new local requests."""

    current = today or date.today()
    return f"{_request_prefix()}-{current:%Y%m%d}-{max(1, int(sequence)):03d}"


def _request_no_from_raw(raw_state: Mapping[str, Any]) -> str:
    metadata = raw_state.get(SECTION_METADATA) if isinstance(raw_state.get(SECTION_METADATA), Mapping) else {}
    basic = raw_state.get(SECTION_BASIC_INFO) if isinstance(raw_state.get(SECTION_BASIC_INFO), Mapping) else {}
    candidates = [
        _clean_text(_as_value(metadata.get("request_no"))) if isinstance(metadata, Mapping) else "",
        _clean_text(_as_value(basic.get("request_no"))) if isinstance(basic, Mapping) else "",
        _clean_text(_as_value(raw_state.get("request_no"))),
    ]
    return next((item for item in candidates if item), "")


def _as_value(value: Any) -> Any:
    if isinstance(value, Mapping) and "value" in value:
        return value.get("value")
    return value


def _token(value: Any) -> str:
    return _clean_text(value).lower().replace(" ", "")


def _normalize_analysis_type_text(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    if text in ANALYSIS_TYPE_OPTIONS:
        return text
    if text in ANALYSIS_TYPE_ALIASES:
        return ANALYSIS_TYPE_ALIASES[text]
    compact = _token(text)
    for alias, canonical in ANALYSIS_TYPE_ALIASES.items():
        if _token(alias) == compact:
            return canonical
    return text


def _normalize_analysis_type_field(field: Any) -> Field:
    normalized = _normalize_analysis_type_text(_as_value(field))
    if not isinstance(field, Mapping):
        return sanitize_field(normalized or field)
    next_field = dict(field)
    if normalized:
        next_field["value"] = normalized
        next_field["display_value"] = normalized
    return sanitize_field(next_field)


def _field_source(field: Any) -> str:
    if not isinstance(field, Mapping):
        return ""
    return _clean_text(field.get("source"))


def _date_from_text(value: Any) -> date | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def compose_request_title(raw_state: Mapping[str, Any], fallback: str = "") -> str:
    request_context = raw_state.get(SECTION_REQUEST_CONTEXT) if isinstance(raw_state.get(SECTION_REQUEST_CONTEXT), Mapping) else {}
    parts = [
        _clean_text(request_context.get("division")),
        _clean_text(request_context.get("product_lineup")),
        _clean_text(request_context.get("platform")),
        "null" if request_context.get("chassis") is None and request_context.get("taxonomy_id") else _clean_text(request_context.get("chassis")),
        _clean_text(request_context.get("analysis_type")),
    ]
    if all(parts):
        return " / ".join(parts)[:TITLE_MAX_CHARS]
    return _clean_text(fallback)[:TITLE_MAX_CHARS]


def apply_analysis_overview_defaults(raw_state: Mapping[str, Any]) -> State:
    state = dict(raw_state or {})
    overview = dict(state.get(SECTION_ANALYSIS_OVERVIEW) if isinstance(state.get(SECTION_ANALYSIS_OVERVIEW), Mapping) else {})
    today_text = date.today().isoformat()
    request_date_field = sanitize_field(
        overview.get("request_date"),
        default=make_field(today_text, source=VALUE_SOURCE_SYSTEM),
    )
    if request_date_field.get("status") != FIELD_STATUS_PROVIDED:
        request_date_field = make_field(today_text, source=VALUE_SOURCE_SYSTEM)
    overview["request_date"] = request_date_field
    state[SECTION_ANALYSIS_OVERVIEW] = overview
    return state


def normalize_decision_use_field(raw: Any, *, default: Field | None = None) -> Field:
    """Preserve Field Value metadata while migrating decision_use to its catalog."""

    raw_field = raw if isinstance(raw, Mapping) else {}
    value = raw_field.get("value", raw)
    value_map = value if isinstance(value, Mapping) else {}
    source = _clean_text(raw_field.get("source")) or ("legacy" if not isinstance(raw, Mapping) else VALUE_SOURCE_USER)
    note = _clean_text(raw_field.get("note"))
    primary_code = _clean_text(value_map.get("primary_code"))
    custom_text = _clean_text(value_map.get("custom_text"))

    if not primary_code:
        legacy_text = "" if isinstance(value, Mapping) else _clean_text(value)
        mapped = DECISION_USE_LEGACY_CODES.get(legacy_text, legacy_text if legacy_text in DECISION_USE_CODES else "")
        primary_code = mapped or ("other" if legacy_text else "")
        if primary_code == "other" and legacy_text:
            custom_text = legacy_text
            source = "legacy" if not _clean_text(raw_field.get("source")) else source
    if primary_code not in DECISION_USE_CODES:
        custom_text = custom_text or primary_code
        primary_code = "other" if custom_text else ""
        source = "legacy" if not _clean_text(raw_field.get("source")) else source

    custom_text = custom_text if primary_code == "other" else ""
    is_selected = bool(primary_code)
    status = FIELD_STATUS_PROVIDED if is_selected else FIELD_STATUS_MISSING
    validity = "invalid" if not is_selected or (primary_code == "other" and not custom_text) else ("unverified" if primary_code == "undecided" else "valid")
    confirmation_status = _clean_text(raw_field.get("confirmation_status"))
    if confirmation_status not in {"not_required", "pending", "confirmed"}:
        confirmation_status = "not_required"
    display_value = DECISION_USE_DISPLAY.get(primary_code, "")
    if primary_code == "other" and custom_text:
        display_value = f"{display_value}: {custom_text}"
    return {
        "value": {"primary_code": primary_code, "custom_text": custom_text or None},
        "display_value": display_value,
        "status": status,
        "source": source,
        "validity": validity,
        "confirmation_status": confirmation_status,
        "note": note,
    }


def decision_use_is_complete(field: Any) -> bool:
    normalized = normalize_decision_use_field(field)
    value = normalized["value"]
    primary_code = value["primary_code"]
    return primary_code in {"problem_analysis", "design_review", "performance_validation"} or (
        primary_code == "other" and bool(value["custom_text"])
    )


def infer_field_status(value: Any) -> str:
    if value is None:
        return FIELD_STATUS_MISSING
    if isinstance(value, str):
        stripped = _clean_text(value)
        if not stripped:
            return FIELD_STATUS_MISSING
        compact = _token(stripped)
        unknown = {_token(item) for item in UNKNOWN_TOKENS}
        none_values = {_token(item) for item in NONE_TOKENS}
        skipped = {_token(item) for item in SKIPPED_TOKENS}
        if compact in unknown:
            return FIELD_STATUS_UNKNOWN
        if compact in none_values:
            return FIELD_STATUS_NONE
        if compact in skipped:
            return FIELD_STATUS_SKIPPED
        return FIELD_STATUS_PROVIDED
    if isinstance(value, (list, tuple, set, dict)):
        return FIELD_STATUS_PROVIDED if len(value) > 0 else FIELD_STATUS_MISSING
    return FIELD_STATUS_PROVIDED


def normalize_status(status: Any, value: Any) -> str:
    token = _clean_text(status).lower().replace("-", "_")
    if token not in FIELD_STATUSES:
        return infer_field_status(value)
    if token == FIELD_STATUS_PROVIDED and infer_field_status(value) == FIELD_STATUS_MISSING:
        return FIELD_STATUS_MISSING
    return token


def _canonical_value(value: Any, status: str) -> Any:
    if status == FIELD_STATUS_MISSING:
        return ""
    if status in {FIELD_STATUS_UNKNOWN, FIELD_STATUS_NONE, FIELD_STATUS_SKIPPED}:
        return None
    if isinstance(value, str):
        return _clean_text(value)
    return deepcopy(value)


def _display_value(value: Any, status: str) -> str:
    if status == FIELD_STATUS_UNKNOWN:
        return "모름"
    if status == FIELD_STATUS_NONE:
        return "없음"
    if status == FIELD_STATUS_SKIPPED:
        return "skip"
    if status == FIELD_STATUS_MISSING:
        return ""
    return _clean_text(value)


def make_field(
    value: Any = "",
    *,
    status: Any = None,
    source: str = VALUE_SOURCE_USER,
    note: Any = "",
) -> Field:
    resolved_status = normalize_status(status, value)
    return {
        "value": _canonical_value(value, resolved_status),
        "status": resolved_status,
        "source": _clean_text(source) or VALUE_SOURCE_USER,
        "note": _clean_text(note),
        "display_value": _display_value(value, resolved_status),
    }


def sanitize_field(raw: Any, *, default: Field | None = None, source: str = VALUE_SOURCE_USER) -> Field:
    if isinstance(raw, Mapping):
        fallback = default or make_field(source=source)
        value = raw.get("value", fallback.get("value", ""))
        status = raw.get("status") if "status" in raw else None
        field_source = raw.get("source", fallback.get("source", source))
        note = raw.get("note", fallback.get("note", ""))
        return make_field(value, status=status, source=field_source, note=note)
    if raw is None and default is not None:
        return deepcopy(default)
    return make_field(raw, source=source)


def field_value(field: Mapping[str, Any] | Any, default: Any = "") -> Any:
    if not isinstance(field, Mapping):
        return default
    if field.get("status") != FIELD_STATUS_PROVIDED:
        return default
    value = field.get("value")
    return default if value is None else value


def is_missing_like(field: Mapping[str, Any] | Any) -> bool:
    if not isinstance(field, Mapping):
        return True
    return str(field.get("status", FIELD_STATUS_MISSING)) != FIELD_STATUS_PROVIDED


def _row_id(prefix: str, index: int, raw_id: Any = "") -> str:
    token = _clean_text(raw_id)
    if not token:
        token = f"{prefix}_{index}"
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", token)
    return token or f"{prefix}_{index}"


def make_value_row(prefix: str, index: int, value: Any = "", *, status: Any = None, source: str = VALUE_SOURCE_USER) -> Field:
    row = make_field(value, status=status, source=source)
    row["id"] = _row_id(prefix, index)
    return row


def _raw_value_from_mapping(item: Mapping[str, Any]) -> Any:
    if "value" in item or "status" in item:
        return item
    for key in ("modeling_no", "part_no", "partNo", "name", "label"):
        if key in item:
            return item.get(key)
    return ""


def sanitize_value_rows(raw: Any, *, prefix: str, min_rows: int = 1) -> list[Field]:
    rows_raw: Iterable[Any]
    if isinstance(raw, list):
        rows_raw = raw
    elif raw is None:
        rows_raw = []
    else:
        rows_raw = [raw]

    rows: list[Field] = []
    for index, item in enumerate(rows_raw, start=1):
        raw_id = item.get("id", "") if isinstance(item, Mapping) else ""
        row = sanitize_field(_raw_value_from_mapping(item) if isinstance(item, Mapping) else item)
        row["id"] = _row_id(prefix, index, raw_id)
        rows.append(row)

    while len(rows) < min_rows:
        rows.append(make_value_row(prefix, len(rows) + 1))
    return rows


def _geometry_modeling_value(item: Mapping[str, Any]) -> Any:
    for key in ("modeling_no", "drawing_no", "drawing_number", "npdm_mcad", "part_no", "partNo", "value", "name", "label"):
        if key in item:
            return item.get(key)
    return ""


def _geometry_description_value(item: Mapping[str, Any]) -> Any:
    for key in ("description", "desc"):
        if key in item:
            return item.get(key)
    return ""


def sanitize_geometry_row(raw: Any, *, prefix: str, index: int) -> Field:
    raw_map = raw if isinstance(raw, Mapping) else {}
    raw_id = raw_map.get("id", "") if isinstance(raw_map, Mapping) else ""
    modeling_raw = _geometry_modeling_value(raw_map) if isinstance(raw_map, Mapping) else raw
    description_raw = _geometry_description_value(raw_map) if isinstance(raw_map, Mapping) else ""
    modeling_field = sanitize_field(modeling_raw)
    description_field = sanitize_field(description_raw)
    row = deepcopy(modeling_field)
    row["id"] = _row_id(prefix, index, raw_id)
    row["modeling_no"] = deepcopy(modeling_field)
    row["description"] = description_field
    return row


def sanitize_geometry_rows(raw: Any, *, prefix: str, min_rows: int = 1) -> list[Field]:
    rows_raw: Iterable[Any]
    if isinstance(raw, list):
        rows_raw = raw
    elif raw is None:
        rows_raw = []
    else:
        rows_raw = [raw]

    rows = [sanitize_geometry_row(item, prefix=prefix, index=index) for index, item in enumerate(rows_raw, start=1)]
    while len(rows) < min_rows:
        rows.append(sanitize_geometry_row("", prefix=prefix, index=len(rows) + 1))
    return rows


def sanitize_geometry_entry(raw: Any, *, default: Field | None = None, source: str = VALUE_SOURCE_USER) -> Field:
    if isinstance(raw, Mapping) and ("modeling_no" in raw or "description" in raw or "drawing_no" in raw or "npdm_mcad" in raw):
        modeling_field = sanitize_field(raw.get("modeling_no", raw.get("drawing_no", raw.get("npdm_mcad"))), source=source)
        description_field = sanitize_field(raw.get("description"), source=source)
        row = deepcopy(modeling_field)
        row["modeling_no"] = deepcopy(modeling_field)
        row["description"] = description_field
        return row
    row = sanitize_field(raw, default=default, source=source)
    row["modeling_no"] = deepcopy(row)
    row["description"] = make_field(source=source)
    return row


def sanitize_complete_product(raw: Any, *, role: str, index: int) -> dict[str, Any]:
    """Keep one registered, complete-product card without legacy conversion."""
    item = raw if isinstance(raw, Mapping) else {}
    raw_id = _clean_text(item.get("geometry_id"))
    geometry_id = _slug(raw_id, f"{role}_{index:03d}")
    drawing_no = sanitize_field(item.get("drawing_no"))
    drawing_text = _clean_text(field_value(drawing_no))
    supplied_display_name = sanitize_field(item.get("display_name"))
    supplied_display_text = _clean_text(field_value(supplied_display_name))
    display_name_custom = _coerce_bool(
        item.get("display_name_custom"),
        default=bool(supplied_display_text and supplied_display_text != drawing_text),
    )
    display_name = supplied_display_name if display_name_custom else make_field(
        drawing_text,
        source=VALUE_SOURCE_SYSTEM if drawing_text else VALUE_SOURCE_USER,
    )
    return {
        "geometry_id": geometry_id,
        "role": role,
        "drawing_no": drawing_no,
        "display_name": display_name,
        "display_name_custom": display_name_custom,
        "difference_from_base": sanitize_field(item.get("difference_from_base")) if role == "comparison" else make_field(),
    }


def sanitize_complete_products(raw: Any) -> list[dict[str, Any]]:
    items = raw if isinstance(raw, list) else []
    products: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items, start=1):
        product = sanitize_complete_product(item, role="comparison", index=index)
        while product["geometry_id"] in seen_ids:
            product["geometry_id"] = f"comparison_{index:03d}_{len(seen_ids) + 1}"
        seen_ids.add(product["geometry_id"])
        products.append(product)
    return products


def _initial_fields(specs: tuple[FieldSpec, ...]) -> dict[str, Field]:
    return {spec.key: make_field() for spec in specs}


def _sanitize_field_section(
    raw: Any,
    specs: tuple[FieldSpec, ...],
    default_section: Mapping[str, Field],
) -> dict[str, Field]:
    raw_map = raw if isinstance(raw, Mapping) else {}
    section: dict[str, Field] = {}
    for spec in specs:
        default = default_section.get(spec.key, make_field())
        raw_value = raw_map.get(spec.key)
        if raw_value is None and spec.legacy_key:
            raw_value = raw_map.get(spec.legacy_key)
        section[spec.key] = normalize_decision_use_field(raw_value, default=default) if spec.key == "decision_use" else sanitize_field(raw_value, default=default)
    return section


def _condition_field_from_spec(spec: FieldSpec, raw: Any = None) -> dict[str, Any]:
    raw_map = raw if isinstance(raw, Mapping) else {}
    values_raw = raw_map.get("values") if isinstance(raw_map, Mapping) else None
    sanitized_values = sanitize_value_rows(values_raw, prefix=f"{spec.key}_value", min_rows=1)
    has_explicit_active = "active" in raw_map if isinstance(raw_map, Mapping) else False
    active_default = any(row.get("status") == FIELD_STATUS_PROVIDED for row in sanitized_values)
    active = _coerce_bool(raw_map.get("active"), default=active_default) if has_explicit_active else active_default
    return {
        "key": spec.key,
        "label": spec.label,
        "required": spec.required,
        "value_type": spec.value_type,
        "unit": spec.unit,
        "binding": spec.binding,
        "legacy_key": spec.legacy_key,
        "active": active,
        "values": sanitized_values,
    }


def _custom_condition_field(item: Mapping[str, Any], *, default_active: bool = True) -> dict[str, Any] | None:
    key = _condition_key_alias(item.get("key"))
    if not key:
        return None
    return {
        "key": key,
        "label": _clean_text(item.get("label")) or key,
        "required": bool(item.get("required", False)),
        "value_type": _clean_text(item.get("value_type")) or "text",
        "unit": _clean_text(item.get("unit")),
        "binding": _clean_text(item.get("binding")) or "condition-linked",
        "legacy_key": _clean_text(item.get("legacy_key")),
        "active": _coerce_bool(item.get("active"), default=default_active),
        "values": sanitize_value_rows(item.get("values"), prefix=f"{key}_value", min_rows=1),
    }


def _sanitize_condition_fields(raw: Any, *, mode: str = "") -> list[dict[str, Any]]:
    raw_list = raw if isinstance(raw, list) else []
    raw_by_key = {
        _condition_key_alias(item.get("key")): item
        for item in raw_list
        if isinstance(item, Mapping) and _condition_key_alias(item.get("key"))
    }
    if _clean_text(mode) == DEMO_CONDITION_MODE:
        fields: list[dict[str, Any]] = []
        for item in raw_list:
            if not isinstance(item, Mapping):
                continue
            field = _custom_condition_field(item)
            if field is not None:
                fields.append(field)
        return fields

    fields = [_condition_field_from_spec(spec, raw_by_key.get(spec.key)) for spec in CONDITION_FIELD_SPECS]

    known = {spec.key for spec in CONDITION_FIELD_SPECS}
    for item in raw_list:
        if not isinstance(item, Mapping):
            continue
        key = _condition_key_alias(item.get("key"))
        if not key or key in known:
            continue
        field = _custom_condition_field(item)
        if field is not None:
            fields.append(field)
    return fields


def _sanitize_condition_values(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {}
    values: dict[str, Any] = {}
    for key, value in raw.items():
        clean_key = _condition_key_alias(key)
        if not clean_key:
            continue
        if isinstance(value, list):
            cleaned = [_clean_text(_as_value(item)) if isinstance(item, Mapping) else _clean_text(item) for item in value]
            values[clean_key] = [item for item in cleaned if item]
        elif isinstance(value, Mapping):
            text = _clean_text(_as_value(value))
            if text:
                values[clean_key] = text
        else:
            text = _clean_text(value)
            if text:
                values[clean_key] = text
    return values


def _condition_values_from_fields(fields: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field in fields:
        if not isinstance(field, Mapping):
            continue
        key = _condition_key_alias(field.get("key"))
        if not key:
            continue
        provided = [_clean_text(field_value(row)) for row in field.get("values", []) if isinstance(row, Mapping) and row.get("status") == FIELD_STATUS_PROVIDED and _clean_text(field_value(row))]
        if not provided:
            continue
        values[key] = provided[0] if len(provided) == 1 else provided
    return values


def _sanitize_hex_spec(raw: Any) -> dict[str, Field]:
    """Keep the heat-exchanger detail inputs as normal state fields.

    The composed ``heat_exchanger_spec`` condition remains the compatibility
    value consumed by validation, payload, and Case Matrix code.
    """

    raw_map = raw if isinstance(raw, Mapping) else {}
    return {
        key: sanitize_field(raw_map.get(key), default=make_field(value, source=VALUE_SOURCE_SYSTEM))
        for key, value in HEX_SPEC_DEFAULTS.items()
    }


def _hex_spec_display(hex_spec: Mapping[str, Any]) -> str:
    return " / ".join(
        _clean_text(field_value(hex_spec.get(key), ""))
        for key in HEX_SPEC_DEFAULTS
    )


def _hex_spec_has_user_input(hex_spec: Mapping[str, Any]) -> bool:
    return any(
        isinstance(hex_spec.get(key), Mapping)
        and hex_spec[key].get("status") == FIELD_STATUS_PROVIDED
        and _field_source(hex_spec[key]) == VALUE_SOURCE_USER
        for key in HEX_SPEC_DEFAULTS
    )


def _fieldset_field_keys(context: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    for group in context.get("condition_fieldset_snapshot", []) if isinstance(context.get("condition_fieldset_snapshot"), list) else []:
        if not isinstance(group, Mapping) or group.get("active") is not True:
            continue
        for field in group.get("fields", []) if isinstance(group.get("fields"), list) else []:
            if isinstance(field, Mapping) and field.get("active") is not False and _clean_text(field.get("key")):
                keys.add(_clean_text(field.get("key")))
    return keys


def _apply_legacy_condition_value_aliases(values: dict[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    next_values = deepcopy(values)
    field_keys = _fieldset_field_keys(context)
    for source_key, value in list(values.items()):
        canonical_key = _condition_key_alias(source_key)
        if canonical_key and canonical_key not in next_values:
            next_values[canonical_key] = deepcopy(value)
    aliases = {
        "fan_rpm": ("fan_rpm", "fan_rpm_indoor", "fan_rpm_outdoor"),
        "room_temp": ("indoor_temp", "outdoor_temp"),
        "room_rh": ("indoor_rh", "outdoor_rh"),
    }
    for source_key, target_keys in aliases.items():
        source_value = next_values.get(source_key, values.get(source_key))
        if source_value in (None, ""):
            continue
        for target_key in target_keys:
            if target_key in field_keys and target_key not in next_values:
                next_values[target_key] = deepcopy(source_value)
    return next_values


def _legacy_geometry_sources(raw_state: Mapping[str, Any], geometry_map: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    return (
        geometry_map,
        raw_state,
        raw_state.get(SECTION_METADATA) if isinstance(raw_state.get(SECTION_METADATA), Mapping) else {},
        raw_state.get(SECTION_BASIC_INFO) if isinstance(raw_state.get(SECTION_BASIC_INFO), Mapping) else {},
        raw_state.get(SECTION_ANALYSIS_OVERVIEW) if isinstance(raw_state.get(SECTION_ANALYSIS_OVERVIEW), Mapping) else {},
    )


def _first_legacy_geometry_value(sources: Iterable[Mapping[str, Any]], *keys: str) -> Any:
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        for key in keys:
            if key not in source:
                continue
            value = source.get(key)
            if isinstance(value, list):
                if value:
                    return value
                continue
            if isinstance(value, Mapping):
                if _clean_text(_as_value(value)) or any(item in value for item in ("modeling_no", "drawing_no", "npdm_mcad", "description")):
                    return value
                continue
            if _clean_text(value):
                return value
    return None


def _sanitize_condition_options(raw: Any) -> dict[str, bool]:
    if not isinstance(raw, Mapping):
        return {}
    return {_clean_text(key): _coerce_bool(value, default=False) for key, value in raw.items() if _clean_text(key)}


def _ensure_condition_fieldset_snapshot(context: dict[str, Any]) -> dict[str, Any]:
    analysis_type = _clean_text(context.get("analysis_type"))
    if not analysis_type:
        return context
    if context.get("condition_fieldset_snapshot") and analysis_type not in ENABLED_ANALYSIS_TYPE_OPTIONS:
        return context
    fieldset = build_condition_fieldset(context)
    context["analysis_type"] = _clean_text(fieldset.get("analysis_type")) or _clean_text(context.get("analysis_type"))
    context["operation_mode"] = _clean_text(fieldset.get("operation_mode"))
    context["condition_fieldset_key"] = _clean_text(fieldset.get("key"))
    context["condition_fieldset_snapshot"] = deepcopy(fieldset.get("groups")) if isinstance(fieldset.get("groups"), list) else []
    return context
def default_request_context() -> dict[str, Any]:
    return {
        "taxonomy_id": "",
        "taxonomy_version": "",
        "division": "",
        "product_lineup": "",
        "platform": "",
        "chassis": None,
        "display_path": "",
        "analysis_type": "",
        "operation_mode": "",
        "context_locked": False,
        "condition_fieldset_key": "",
        "condition_fieldset_snapshot": [],
    }


def _mapping_value(mapping: Mapping[str, Any] | Any, *keys: str) -> str:
    if not isinstance(mapping, Mapping):
        return ""
    for key in keys:
        if key not in mapping:
            continue
        value = _clean_text(_as_value(mapping.get(key)))
        if value:
            return value
    return ""


def _first_mapping_value(sources: Iterable[Mapping[str, Any] | Any], *keys: str) -> str:
    for source in sources:
        value = _mapping_value(source, *keys)
        if value:
            return value
    return ""


def _legacy_context_sources(raw_state: Mapping[str, Any] | Any, normalized_state: Mapping[str, Any] | None) -> dict[str, Any]:
    raw_map = raw_state if isinstance(raw_state, Mapping) else {}
    normalized = normalized_state if isinstance(normalized_state, Mapping) else {}
    return {
        "raw_context": raw_map.get(SECTION_REQUEST_CONTEXT) if isinstance(raw_map.get(SECTION_REQUEST_CONTEXT), Mapping) else {},
        "raw_metadata": raw_map.get(SECTION_METADATA) if isinstance(raw_map.get(SECTION_METADATA), Mapping) else {},
        "raw_basic": raw_map.get(SECTION_BASIC_INFO) if isinstance(raw_map.get(SECTION_BASIC_INFO), Mapping) else {},
        "raw_overview": raw_map.get(SECTION_ANALYSIS_OVERVIEW) if isinstance(raw_map.get(SECTION_ANALYSIS_OVERVIEW), Mapping) else {},
        "raw_conditions": raw_map.get(SECTION_CONDITIONS) if isinstance(raw_map.get(SECTION_CONDITIONS), Mapping) else {},
        "normalized_basic": normalized.get(SECTION_BASIC_INFO) if isinstance(normalized.get(SECTION_BASIC_INFO), Mapping) else {},
        "normalized_overview": normalized.get(SECTION_ANALYSIS_OVERVIEW) if isinstance(normalized.get(SECTION_ANALYSIS_OVERVIEW), Mapping) else {},
        "normalized_conditions": normalized.get(SECTION_CONDITIONS) if isinstance(normalized.get(SECTION_CONDITIONS), Mapping) else {},
        "top": raw_map,
    }


def migrate_legacy_context(raw_state: Mapping[str, Any] | Any, normalized_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Recover only fields belonging to the current taxonomy contract."""

    sources = _legacy_context_sources(raw_state, normalized_state)
    context = default_request_context()
    context_sources = (sources["raw_context"], sources["top"], sources["raw_metadata"])
    overview_sources = (sources["raw_overview"], sources["normalized_overview"])

    for key in ("taxonomy_id", "taxonomy_version", "division", "product_lineup", "platform", "display_path"):
        context[key] = _first_mapping_value(context_sources, key)
    context["chassis"] = _first_mapping_value(context_sources, "chassis") or None
    context["analysis_type"] = _normalize_analysis_type_text(_first_mapping_value(
        (*context_sources, *overview_sources),
        "analysis_type",
        "analysisType",
    ))
    context["operation_mode"] = _first_mapping_value(
        context_sources,
        "operation_mode",
        "operationMode",
        "operation",
    )
    context["condition_fieldset_key"] = _first_mapping_value(
        context_sources,
        "condition_fieldset_key",
        "conditionFieldsetKey",
        "fieldset_key",
        "fieldsetKey",
        "condition_mode",
        "conditionMode",
    )
    return context


def normalize_request_context(raw_context: Any, raw_state: Mapping[str, Any] | Any = None, normalized_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the h5 request_context without importing overview-era values."""

    raw_map = raw_context if isinstance(raw_context, Mapping) else {}
    context = default_request_context()
    for key in (
        "taxonomy_id",
        "taxonomy_version",
        "division",
        "product_lineup",
        "platform",
        "display_path",
        "analysis_type",
        "operation_mode",
        "condition_fieldset_key",
    ):
        context[key] = _clean_text(_as_value(raw_map.get(key)))
    context["chassis"] = None if raw_map.get("chassis") is None else _clean_text(_as_value(raw_map.get("chassis")))
    context["analysis_type"] = _normalize_analysis_type_text(context["analysis_type"])
    context["context_locked"] = _coerce_bool(raw_map.get("context_locked", raw_map.get("contextLocked")), default=False)
    snapshot = raw_map.get("condition_fieldset_snapshot", raw_map.get("conditionFieldsetSnapshot"))
    context["condition_fieldset_snapshot"] = deepcopy(snapshot) if isinstance(snapshot, list) else []
    if context["taxonomy_id"]:
        taxonomy_path = taxonomy_path_by_id(context["taxonomy_id"])
        current_version = _clean_text(load_product_taxonomy().get("taxonomy_version"))
        if taxonomy_path is None or context["taxonomy_version"] != current_version:
            return default_request_context()
        for key in ("division", "product_lineup", "platform"):
            if context[key] and context[key].casefold() != _clean_text(taxonomy_path.get(key)).casefold():
                return default_request_context()
        if "chassis" in raw_map:
            supplied_chassis = context["chassis"]
            canonical_chassis = taxonomy_path.get("chassis")
            if (supplied_chassis is None) != (canonical_chassis is None):
                return default_request_context()
            if supplied_chassis is not None and supplied_chassis.casefold() != _clean_text(canonical_chassis).casefold():
                return default_request_context()
        context.update(
            {
                "division": _clean_text(taxonomy_path.get("division")),
                "product_lineup": _clean_text(taxonomy_path.get("product_lineup")),
                "platform": _clean_text(taxonomy_path.get("platform")),
                "chassis": taxonomy_path.get("chassis") if taxonomy_path.get("chassis") is None else _clean_text(taxonomy_path.get("chassis")),
                "display_path": _clean_text(taxonomy_path.get("display_path")),
            }
        )
    return context


def ensure_request_context(state: State) -> State:
    """Mutate and return state with a normalized request_context section."""

    if not isinstance(state, dict):
        state = {}
    state[SECTION_REQUEST_CONTEXT] = normalize_request_context(
        state.get(SECTION_REQUEST_CONTEXT),
        raw_state=state,
        normalized_state=state,
    )
    return state


def legacy_condition_value_migration_candidates() -> dict[str, tuple[str, ...]]:
    """Document likely legacy locations for condition value migration in later stages."""

    return deepcopy(LEGACY_CONDITION_VALUE_MIGRATION_CANDIDATES)


def _manual_matrix_product_options(products: list[dict[str, Any]]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for index, product in enumerate(products, start=1):
        drawing_no = _clean_text(field_value(product.get("drawing_no")))
        if not drawing_no:
            continue
        geometry_id = _clean_text(product.get("geometry_id"))
        if not geometry_id:
            continue
        options.append({"value": geometry_id, "label": f"형상 {index}"})
    return options


def _manual_matrix_condition_options(
    condition_sets: list[dict[str, Any]],
    columns: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Return latest user-entered dropdown values for the active Matrix columns."""

    options: dict[str, list[dict[str, str]]] = {column["key"]: [] for column in columns}

    def add(key: str, value: Any, label: Any | None = None) -> None:
        text = _clean_text(value)
        if not text or key not in options or any(item["value"] == text for item in options[key]):
            return
        options[key].append({"value": text, "label": _clean_text(label) or text})

    for card in condition_sets:
        card_type = _clean_text(card.get("type"))
        fields = card.get("fields") if isinstance(card.get("fields"), Mapping) else {}
        if card_type == "operating":
            add("fan", card.get("id"), card.get("name"))
            continue
        if card_type == "heat_exchanger":
            add("heat_exchanger", card.get("id"), field_value(fields.get("name")))
            continue
        for column in columns:
            if column.get("card_type") == card_type:
                add(column["key"], field_value(fields.get(column["key"])))
    return options


def _manual_case_row(row_id: str, *, geometry_id: str = "", auto_geometry_id: str = "", condition_values: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "case_id": _slug(row_id, "case_001"),
        "geometry_id": _clean_text(geometry_id),
        "auto_geometry_id": _clean_text(auto_geometry_id),
        "condition_values": {
            _clean_text(key): _clean_text(value)
            for key, value in (condition_values.items() if isinstance(condition_values, Mapping) else [])
            if _clean_text(key)
        },
    }


def _migrate_manual_condition_label(key: str, value: Any) -> str:
    """Map former system-generated Matrix labels to their current Korean names."""

    text = _clean_text(value)
    legacy_prefix, current_prefix = {
        "fan": ("Fan", "운전"),
        "heat_exchanger": ("HEX", "사양"),
    }.get(key, ("", ""))
    if legacy_prefix and text.startswith(f"{legacy_prefix} "):
        suffix = text[len(legacy_prefix) + 1 :]
        if suffix.isdigit():
            return f"{current_prefix} {suffix}"
    return text


def _sanitize_manual_case_matrix(
    raw_matrix: Any,
    *,
    products: list[dict[str, Any]],
    condition_sets: list[dict[str, Any]],
    request_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize the manual Case Matrix and invalidate obsolete selections."""

    raw = raw_matrix if isinstance(raw_matrix, Mapping) else {}
    condition_columns = get_active_case_matrix_columns(request_context)
    geometry_options = _manual_matrix_product_options(products)
    condition_options = _manual_matrix_condition_options(condition_sets, condition_columns)
    valid_geometry_ids = {item["value"] for item in geometry_options}
    valid_values = {key: {item["value"] for item in values} for key, values in condition_options.items()}
    condition_aliases = {
        key: {
            alias: item["value"]
            for item in values
            for alias in {_clean_text(item.get("value")), _clean_text(item.get("label"))}
            if alias
        }
        for key, values in condition_options.items()
    }
    default_condition_values = {
        key: _clean_text(values[0].get("value"))
        for key, values in condition_options.items()
        if values and _clean_text(values[0].get("value"))
    }
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, raw_row in enumerate(raw.get("rows") if isinstance(raw.get("rows"), list) else [], start=1):
        if not isinstance(raw_row, Mapping):
            continue
        row = _manual_case_row(
            _clean_text(raw_row.get("case_id")) or f"case_{index:03d}",
            geometry_id=_clean_text(raw_row.get("geometry_id")),
            auto_geometry_id=_clean_text(raw_row.get("auto_geometry_id")),
            condition_values=raw_row.get("condition_values", raw_row.get("selections")),
        )
        while row["case_id"] in seen_ids:
            row["case_id"] = f"case_{index:03d}_{len(seen_ids) + 1}"
        seen_ids.add(row["case_id"])
        # A deleted geometry removes its automatically maintained base row;
        # manual rows are retained with a safely-cleared selection instead.
        if row["auto_geometry_id"] and row["auto_geometry_id"] not in valid_geometry_ids:
            continue
        if row["geometry_id"] not in valid_geometry_ids:
            row["geometry_id"] = ""
        supplied_condition_keys = set(row["condition_values"])
        row["condition_values"] = {
            column["key"]: value
            for column in condition_columns
            for legacy_value in [_migrate_manual_condition_label(column["key"], row["condition_values"].get(column["key"]))]
            for value in [condition_aliases.get(column["key"], {}).get(legacy_value, legacy_value)]
            if value in valid_values.get(column["key"], set())
        }
        if row["auto_geometry_id"]:
            for key, value in default_condition_values.items():
                if key not in supplied_condition_keys:
                    row["condition_values"].setdefault(key, value)
        rows.append(row)

    prior_snapshot = {
        _clean_text(value)
        for value in raw.get("geometry_snapshot_ids", [])
        if _clean_text(value)
    } if isinstance(raw.get("geometry_snapshot_ids"), list) else set()
    for option in geometry_options:
        geometry_id = option["value"]
        if geometry_id in prior_snapshot:
            continue
        row_id = f"case_{len(rows) + 1:03d}"
        while row_id in seen_ids:
            row_id = f"case_{len(rows) + 1:03d}_{len(seen_ids) + 1}"
        rows.append(_manual_case_row(
            row_id,
            geometry_id=geometry_id,
            auto_geometry_id=geometry_id,
            condition_values=default_condition_values,
        ))
        seen_ids.add(row_id)

    visible_columns = [
        {"key": "case_no", "label": "No.", "kind": "number"},
        {"key": "geometry_id", "label": "형상", "kind": "geometry"},
        *[{"key": column["key"], "label": column["label"], "kind": "condition"} for column in condition_columns],
        {"key": "remove", "label": "제거", "kind": "remove"},
    ]
    geometry_labels = {item["value"]: item["label"] for item in geometry_options}
    condition_labels = {
        key: {item["value"]: item["label"] for item in values}
        for key, values in condition_options.items()
    }
    for case_no, row in enumerate(rows, start=1):
        row["visible_cells"] = {
            "case_no": str(case_no),
            "geometry_id": geometry_labels.get(row["geometry_id"], ""),
            **{
                column["key"]: condition_labels.get(column["key"], {}).get(
                    row["condition_values"].get(column["key"], ""),
                    row["condition_values"].get(column["key"], ""),
                )
                for column in condition_columns
            },
        }

    return {
        "matrix_type": "manual_mapping",
        "rows": rows,
        "visible_columns": visible_columns,
        "dropdown_options": {"geometry_id": geometry_options, **condition_options},
        "geometry_snapshot_ids": [item["value"] for item in geometry_options],
        "generation_status": FIELD_STATUS_PROVIDED if rows else FIELD_STATUS_MISSING,
        "source_inputs": {
            "geometry_count": len(geometry_options),
            "active_condition_keys": [column["key"] for column in condition_columns],
        },
    }


def create_initial_state() -> State:
    basic_info = _initial_fields(BASIC_INFO_SPECS)
    request_no = ""
    basic_info["request_no"] = make_field(request_no, source=VALUE_SOURCE_SYSTEM)
    basic_info["division"] = make_field("연구소", source=VALUE_SOURCE_SYSTEM)
    basic_info["department"] = make_field("ES CAE팀", source=VALUE_SOURCE_SYSTEM)
    basic_info["requester_name"] = make_field("김대곤", source=VALUE_SOURCE_SYSTEM)
    basic_info["requester_role"] = make_field("선임연구원", source=VALUE_SOURCE_SYSTEM)
    analysis_overview = _initial_fields(ANALYSIS_OVERVIEW_SPECS)
    analysis_overview["request_date"] = make_field(date.today().isoformat(), source=VALUE_SOURCE_SYSTEM)

    state: State = {
        SECTION_METADATA: {
            "schema_version": STATE_SCHEMA_VERSION,
            "app_domain": "cae_request_assistant",
            "app_version_tag": "i0_0",
            "request_no": request_no,
            "request_no_generated": False,
            "rag_enabled": False,
            "rag_scope": DEFAULT_RAG_SCOPE,
            "rag_ranking": "product_first",
            "active_top_tab": "write",
            "opened_sections": {
                "basic_info": False,
                "analysis_overview": False,
                "geometry": False,
                "conditions": False,
                "case_matrix": False,
            },
            "chat_history": [],
            "touched_fields": [],
            "issue_registry": [],
        },
        SECTION_REQUEST_CONTEXT: default_request_context(),
        SECTION_BASIC_INFO: basic_info,
        SECTION_ANALYSIS_OVERVIEW: analysis_overview,
        SECTION_GEOMETRY: {
            "base_product": sanitize_complete_product({}, role="base", index=1),
            "comparison_products": [],
            "boundary_bindings": [],
            "axis": {
                "geometry_variants": [],
                "generation_status": FIELD_STATUS_MISSING,
            },
        },
        SECTION_CONDITIONS: {
            "mode": "standard",
            "fields": [_condition_field_from_spec(spec) for spec in CONDITION_FIELD_SPECS],
            "input_structure": build_condition_input_structure(),
            "condition_sets": default_condition_sets(),
            "common_conditions": {},
            "variable_conditions": {},
            "axis": {
                "condition_variants": [],
                "generation_status": FIELD_STATUS_MISSING,
            },
        },
        SECTION_CASE_MATRIX: {
            "matrix_type": "manual_mapping",
            "rows": [],
            "visible_columns": [],
            "dropdown_options": {"geometry_id": []},
            "geometry_snapshot_ids": [],
            "generation_status": FIELD_STATUS_MISSING,
            "source_inputs": {"geometry_count": 0, "active_condition_keys": []},
        },
        SECTION_REVIEW: {
            "validator": {"blocking": [], "warning": [], "info": []},
            "draft": {"status": "not_started"},
            "submission": {"status": "not_ready", "blocking_reasons": []},
        },
        SECTION_LEGACY_INTERNAL: {
            "conditionPerPart": make_field(1, source=VALUE_SOURCE_LEGACY_INTERNAL),
            "sameCondition": make_field(None, source=VALUE_SOURCE_LEGACY_INTERNAL),
            "ignored_fields": [],
        },
    }
    for row in state[SECTION_LEGACY_INTERNAL].values():
        if not isinstance(row, Mapping):
            continue
        row["derived"] = True
        row["core_input"] = False
    return state


def get_initial_state() -> State:
    return create_initial_state()


def assign_request_no_if_missing(raw_state: Any) -> State:
    state = sanitize_state(raw_state)
    request_no = _request_no_from_raw(state)
    if not request_no:
        request_no = generate_request_no()
    metadata = dict(state.get(SECTION_METADATA, {}))
    metadata["request_no"] = request_no
    metadata["request_no_generated"] = True
    state[SECTION_METADATA] = metadata
    state[SECTION_BASIC_INFO]["request_no"] = make_field(request_no, source=VALUE_SOURCE_SYSTEM)
    return state


def sanitize_state(raw_state: Any) -> State:
    base = create_initial_state()
    if not isinstance(raw_state, Mapping):
        return base

    state = create_initial_state()
    raw_metadata = raw_state.get(SECTION_METADATA) if isinstance(raw_state.get(SECTION_METADATA), Mapping) else {}
    preserved_request_no = _request_no_from_raw(raw_state) or base[SECTION_METADATA]["request_no"]
    raw_opened_sections = raw_metadata.get("opened_sections") if isinstance(raw_metadata, Mapping) else {}
    opened_sections = deepcopy(base[SECTION_METADATA]["opened_sections"])
    if isinstance(raw_opened_sections, Mapping):
        for key in opened_sections:
            if key in raw_opened_sections:
                opened_sections[key] = bool(raw_opened_sections.get(key))
    raw_touched = raw_metadata.get("touched_fields") if isinstance(raw_metadata, Mapping) else []
    raw_issues = raw_metadata.get("issue_registry") if isinstance(raw_metadata, Mapping) else []
    raw_chat_history = raw_metadata.get("chat_history") if isinstance(raw_metadata, Mapping) else []
    state[SECTION_METADATA] = {
        **deepcopy(base[SECTION_METADATA]),
        **(
            {
                key: deepcopy(value)
                for key, value in raw_metadata.items()
                if key
                in {
                    "app_version_tag",
                    "active_top_tab",
                    "rag_scope",
                    "rag_ranking",
                    "assistant_notified_completed_stages",
                    "assistant_final_submit_prompted",
                }
            }
            if isinstance(raw_metadata, Mapping)
            else {}
        ),
        "schema_version": STATE_SCHEMA_VERSION,
        "app_domain": "cae_request_assistant",
        "request_no": preserved_request_no,
        "request_no_generated": bool(preserved_request_no),
        "rag_enabled": _coerce_bool(raw_metadata.get("rag_enabled"), default=False) if isinstance(raw_metadata, Mapping) else False,
        "rag_scope": _clean_text(raw_metadata.get("rag_scope")) if isinstance(raw_metadata, Mapping) and _clean_text(raw_metadata.get("rag_scope")) else DEFAULT_RAG_SCOPE,
        "rag_ranking": _clean_text(raw_metadata.get("rag_ranking")) if isinstance(raw_metadata, Mapping) and _clean_text(raw_metadata.get("rag_ranking")) else "product_first",
        "active_top_tab": _clean_text(raw_metadata.get("active_top_tab")) if isinstance(raw_metadata, Mapping) and _clean_text(raw_metadata.get("active_top_tab")) else "write",
        "opened_sections": opened_sections,
        "chat_history": _sanitize_chat_history(raw_chat_history),
        "touched_fields": [_clean_text(item) for item in raw_touched] if isinstance(raw_touched, list) else [],
        "issue_registry": deepcopy(raw_issues) if isinstance(raw_issues, list) else [],
    }

    state[SECTION_BASIC_INFO] = _sanitize_field_section(
        raw_state.get(SECTION_BASIC_INFO),
        BASIC_INFO_SPECS,
        base[SECTION_BASIC_INFO],
    )
    state[SECTION_BASIC_INFO]["request_no"] = make_field(preserved_request_no, source=VALUE_SOURCE_SYSTEM)
    state[SECTION_ANALYSIS_OVERVIEW] = _sanitize_field_section(
        raw_state.get(SECTION_ANALYSIS_OVERVIEW),
        ANALYSIS_OVERVIEW_SPECS,
        base[SECTION_ANALYSIS_OVERVIEW],
    )
    overview_raw_map = raw_state.get(SECTION_ANALYSIS_OVERVIEW) if isinstance(raw_state.get(SECTION_ANALYSIS_OVERVIEW), Mapping) else {}

    state[SECTION_REQUEST_CONTEXT] = _ensure_condition_fieldset_snapshot(normalize_request_context(
        raw_state.get(SECTION_REQUEST_CONTEXT),
        raw_state=raw_state,
        normalized_state=state,
    ))

    geometry_raw = raw_state.get(SECTION_GEOMETRY)
    geometry_map = geometry_raw if isinstance(geometry_raw, Mapping) else {}
    state[SECTION_GEOMETRY] = {
        "base_product": sanitize_complete_product(geometry_map.get("base_product"), role="base", index=1),
        "comparison_products": sanitize_complete_products(geometry_map.get("comparison_products")),
        "boundary_bindings": list(geometry_map.get("boundary_bindings", []))
        if isinstance(geometry_map.get("boundary_bindings"), list)
        else [],
        "axis": deepcopy(geometry_map.get("axis"))
        if isinstance(geometry_map.get("axis"), Mapping)
        else deepcopy(base[SECTION_GEOMETRY]["axis"]),
    }

    conditions_raw = raw_state.get(SECTION_CONDITIONS)
    conditions_map = conditions_raw if isinstance(conditions_raw, Mapping) else {}
    condition_mode = _clean_text(conditions_map.get("mode")) or "standard"
    condition_sets = sanitize_condition_sets(conditions_map.get("condition_sets"), state[SECTION_REQUEST_CONTEXT])
    products = [state[SECTION_GEOMETRY]["base_product"], *state[SECTION_GEOMETRY]["comparison_products"]]
    state[SECTION_CONDITIONS] = {
        "mode": condition_mode,
        "fields": [],
        "input_structure": build_condition_input_structure(),
        "condition_sets": condition_sets,
        "common_conditions": deepcopy(conditions_map.get("common_conditions"))
        if isinstance(conditions_map.get("common_conditions"), Mapping)
        else {},
        "variable_conditions": deepcopy(conditions_map.get("variable_conditions"))
        if isinstance(conditions_map.get("variable_conditions"), Mapping)
        else {},
        "axis": deepcopy(conditions_map.get("axis"))
        if isinstance(conditions_map.get("axis"), Mapping)
        else deepcopy(base[SECTION_CONDITIONS]["axis"]),
    }
    state[SECTION_CONDITIONS]["fields"] = get_active_condition_fields(state)

    state[SECTION_CASE_MATRIX] = _sanitize_manual_case_matrix(
        raw_state.get(SECTION_CASE_MATRIX),
        products=products,
        condition_sets=condition_sets,
        request_context=state[SECTION_REQUEST_CONTEXT],
    )

    review_raw = raw_state.get(SECTION_REVIEW)
    state[SECTION_REVIEW] = deepcopy(review_raw) if isinstance(review_raw, Mapping) else deepcopy(base[SECTION_REVIEW])

    legacy_raw = raw_state.get(SECTION_LEGACY_INTERNAL)
    legacy_map = legacy_raw if isinstance(legacy_raw, Mapping) else {}
    ignored_fields = deepcopy(legacy_map.get("ignored_fields")) if isinstance(legacy_map.get("ignored_fields"), list) else []
    representative_raw = overview_raw_map.get("representative_model", overview_raw_map.get("representativeModelName"))
    representative_field = sanitize_field(representative_raw, source=VALUE_SOURCE_LEGACY_INTERNAL) if representative_raw is not None else None
    if representative_field and representative_field.get("status") != FIELD_STATUS_MISSING:
        ignored_fields.append(
            {
                "path": "analysis_overview.representative_model",
                "reason": "removed_from_h2_v2_public_contract",
                "field": representative_field,
            }
        )
    legacy_chassis_raw = overview_raw_map.get("chassis_name", overview_raw_map.get("chassisName"))
    legacy_chassis_field = sanitize_field(legacy_chassis_raw, source=VALUE_SOURCE_LEGACY_INTERNAL) if legacy_chassis_raw is not None else None
    if legacy_chassis_field and legacy_chassis_field.get("status") != FIELD_STATUS_MISSING:
        ignored_fields.append(
            {
                "path": "analysis_overview.chassis_name",
                "reason": "replaced_by_model_suffix",
                "field": legacy_chassis_field,
            }
        )
    state[SECTION_LEGACY_INTERNAL] = {
        "conditionPerPart": sanitize_field(
            legacy_map.get("conditionPerPart", raw_state.get("conditionPerPart")),
            default=base[SECTION_LEGACY_INTERNAL]["conditionPerPart"],
            source=VALUE_SOURCE_LEGACY_INTERNAL,
        ),
        "sameCondition": sanitize_field(
            legacy_map.get("sameCondition", raw_state.get("sameCondition")),
            default=base[SECTION_LEGACY_INTERNAL]["sameCondition"],
            source=VALUE_SOURCE_LEGACY_INTERNAL,
        ),
        "ignored_fields": ignored_fields,
    }
    for row in state[SECTION_LEGACY_INTERNAL].values():
        if not isinstance(row, Mapping):
            continue
        row["source"] = VALUE_SOURCE_LEGACY_INTERNAL
        row["derived"] = True
        row["core_input"] = False

    return apply_analysis_overview_defaults(state)


def normalize_state(raw_state: Any) -> State:
    return sanitize_state(raw_state)


def collect_field_statuses(state: Mapping[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            if "status" in value and "value" in value:
                statuses[path] = _clean_text(value.get("status")) or FIELD_STATUS_MISSING
                return
            for key, child in value.items():
                walk(child, f"{path}.{key}" if path else str(key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(state, "")
    return statuses


def collect_paths_by_status(state: Mapping[str, Any], statuses: Iterable[str]) -> list[str]:
    wanted = {str(item) for item in statuses}
    return [path for path, status in collect_field_statuses(state).items() if status in wanted]


def collect_missing_paths(state: Mapping[str, Any]) -> list[str]:
    return collect_paths_by_status(state, [FIELD_STATUS_MISSING])
