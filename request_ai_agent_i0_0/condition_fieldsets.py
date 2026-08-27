"""Stage 04 condition-card templates and canonical condition-set helpers."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping
from uuid import uuid4


FIELDSET_BUILDER_VERSION = "h5_v0_stage04_condition_cards"
ANALYSIS_TYPE_DEW = "이슬맺힘"
# Legacy types remain readable for previously saved requests, but are no longer
# exposed as selectable analysis types.
ANALYSIS_TYPE_GENERAL_FLOW = "일반 유동 해석"
ANALYSIS_TYPE_THERMAL_FLOW = "열유동 해석"
ANALYSIS_TYPE_HEX_PROFILE = "열교환기 유속 프로파일"
ANALYSIS_TYPE_AIRFLOW_PATTERN = "기류 패턴"
ANALYSIS_TYPE_AIR_VOLUME = "풍량"
HEAT_EXCHANGER_TYPES = ("Fin&Tube", "Micro-Channel")
_CONDITION_CARD_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,95}$")

ANALYSIS_TYPE_ALIASES = {
    "airflow": ANALYSIS_TYPE_AIRFLOW_PATTERN,
    "flow": ANALYSIS_TYPE_AIRFLOW_PATTERN,
    "air volume": ANALYSIS_TYPE_AIR_VOLUME,
    "airvolume": ANALYSIS_TYPE_AIR_VOLUME,
}

CARD_TEMPLATES = (
    {"key": "operating", "label": "운전 조건", "fields": (("fan_rpm", "팬 회전수(RPM)", "RPM"),)},
    {"key": "heat_exchanger", "label": "열교환기 사양", "fields": (("name", "사양", ""), ("tube_diameter", "관 직경(Pi)", "mm"), ("fin_type", "Fin type", ""), ("row_count", "열 수", ""), ("fpi", "FPI", ""))},
    {"key": "supply_air", "label": "취출 공기 조건", "fields": (("heat_exchanger_temp", "취출 온도", "°C"), ("heat_exchanger_rh", "취출 상대습도", "%"))},
    {"key": "space_environment", "label": "공간 환경 조건", "fields": (("room_temp", "공간 온도", "°C"), ("room_rh", "공간 상대습도", "%"))},
)

# Case Matrix is a manual mapping table.  These are the only active-condition
# columns it may expose, and their order is part of the public UI contract.
CASE_MATRIX_CONDITION_COLUMNS = (
    {"key": "fan", "label": "운전", "card_type": "operating"},
    {"key": "heat_exchanger", "label": "사양", "card_type": "heat_exchanger"},
    {"key": "room_temp", "label": "공간 온도 (°C)", "card_type": "space_environment"},
    {"key": "room_rh", "label": "공간 상대습도 (%)", "card_type": "space_environment"},
    {"key": "heat_exchanger_temp", "label": "취출 온도 (°C)", "card_type": "supply_air"},
    {"key": "heat_exchanger_rh", "label": "취출 상대습도 (%)", "card_type": "supply_air"},
)

_THERMAL_FLOW_REQUIRED_CARDS = {"operating", "heat_exchanger", "supply_air", "space_environment"}
_FLOW_ONLY_REQUIRED_CARDS = {"operating", "heat_exchanger"}
_THERMAL_FLOW_EXCLUDED_FIELDS = {"heat_exchanger_rh", "room_rh"}

_REQUIRED_BY_TYPE = {
    ANALYSIS_TYPE_DEW: {"operating", "heat_exchanger", "supply_air", "space_environment"},
    ANALYSIS_TYPE_GENERAL_FLOW: _FLOW_ONLY_REQUIRED_CARDS,
    ANALYSIS_TYPE_THERMAL_FLOW: _THERMAL_FLOW_REQUIRED_CARDS,
    ANALYSIS_TYPE_HEX_PROFILE: _FLOW_ONLY_REQUIRED_CARDS,
    ANALYSIS_TYPE_AIRFLOW_PATTERN: _THERMAL_FLOW_REQUIRED_CARDS,
    ANALYSIS_TYPE_AIR_VOLUME: _FLOW_ONLY_REQUIRED_CARDS,
}

_EXCLUDED_FIELDS_BY_TYPE = {
    ANALYSIS_TYPE_THERMAL_FLOW: _THERMAL_FLOW_EXCLUDED_FIELDS,
    ANALYSIS_TYPE_AIRFLOW_PATTERN: _THERMAL_FLOW_EXCLUDED_FIELDS,
}

_VALUE_OR_NONE_TEMPERATURE_POLICY = {
    "analysis_types": {
        ANALYSIS_TYPE_AIRFLOW_PATTERN,
    },
    "field_keys": {"room_temp", "heat_exchanger_temp"},
    "field_metadata": {
        "allowed_values": ["없음"],
        "allow_custom_input": True,
    },
}


def _clean(value: Any) -> str:
    return str("" if value is None else value).replace("\x00", "").strip()


def new_condition_card_id(card_type: str) -> str:
    """Return an opaque, immutable identifier for a newly created card."""

    clean_type = _clean(card_type).lower()
    if clean_type not in {item["key"] for item in CARD_TEMPLATES}:
        raise ValueError("unsupported condition card type")
    return f"{clean_type}_{uuid4().hex}"


def is_valid_condition_card_id(card_id: Any, card_type: Any) -> bool:
    """Accept legacy ordinal IDs and new opaque IDs without interpreting them."""

    raw_id = _clean(card_id)
    clean_id = raw_id.lower()
    clean_type = _clean(card_type).lower()
    return bool(
        raw_id == clean_id
        and clean_id.startswith(f"{clean_type}_")
        and _CONDITION_CARD_ID_RE.fullmatch(clean_id)
    )


def heat_exchanger_type_from_tube_diameter(value: Any) -> str:
    """Reuse the existing W-prefixed Catalog partition rule."""

    return HEAT_EXCHANGER_TYPES[1] if _clean(value).upper().startswith("W") else HEAT_EXCHANGER_TYPES[0]


def _context(context: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return context.get("request_context", {}) if isinstance(context, Mapping) and isinstance(context.get("request_context"), Mapping) else (context or {})


def _analysis_type(value: Any) -> str:
    value = _clean(value)
    return ANALYSIS_TYPE_ALIASES.get(value, value if value in _REQUIRED_BY_TYPE else ANALYSIS_TYPE_DEW)


def _field(key: str, label: str, unit: str, active: bool, analysis_type: str) -> dict[str, Any]:
    field = {"key": key, "label": label, "unit": unit, "required": active, "required_level": "required" if active else "optional_non_blocking", "active": active, "source": "condition_card_template"}
    if (
        analysis_type in _VALUE_OR_NONE_TEMPERATURE_POLICY["analysis_types"]
        and key in _VALUE_OR_NONE_TEMPERATURE_POLICY["field_keys"]
    ):
        field.update(deepcopy(_VALUE_OR_NONE_TEMPERATURE_POLICY["field_metadata"]))
    return field


def build_condition_fieldset(request_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context = _context(request_context)
    analysis_type = _analysis_type(context.get("analysis_type"))
    required_cards = _REQUIRED_BY_TYPE[analysis_type]
    excluded_fields = _EXCLUDED_FIELDS_BY_TYPE.get(analysis_type, set())
    groups = []
    for order, template in enumerate(CARD_TEMPLATES, 1):
        active = template["key"] in required_cards
        groups.append({"key": template["key"], "label": template["label"], "order": order * 10, "active": active, "fields": [_field(*field, active and field[0] not in excluded_fields, analysis_type) for field in template["fields"]]})
    return {"version": FIELDSET_BUILDER_VERSION, "key": f"analysis_type_{analysis_type}", "analysis_type": analysis_type, "operation_mode": "", "groups": groups, "field_keys": [field["key"] for group in groups for field in group["fields"] if group["active"] and field["active"]]}


def build_condition_input_structure() -> dict[str, Any]:
    return {"version": FIELDSET_BUILDER_VERSION, "groups": deepcopy(list(CARD_TEMPLATES)), "canonical_source": "condition_sets"}


def make_condition_card(
    card_type: str,
    index: int = 1,
    template: Mapping[str, Any] | None = None,
    *,
    card_id: str | None = None,
) -> dict[str, Any]:
    template = template or next((item for item in CARD_TEMPLATES if item["key"] == card_type), CARD_TEMPLATES[0])
    fields = {key: {"value": "", "status": "missing", "source": "user", "display_value": ""} for key, _label, _unit in template["fields"]}
    preserved_id = _clean(card_id)
    if not is_valid_condition_card_id(preserved_id, template["key"]):
        preserved_id = f"{template['key']}_{index}"
    card = {"id": preserved_id, "type": template["key"], "label": template["label"], "is_default": index == 1, "fields": fields}
    if template["key"] == "operating":
        card["name"] = f"운전 {index}"
        card["fan_rpm_mode"] = ""
        card["fans"] = [{"id": "fan_1", "name": "", "location": "", "running": True, "values": {"fan_rpm": ""}}]
        card["fan_count"] = 1
        card["fan_locations"] = [""]
        card["fan_rpms"] = [""]
    if template["key"] == "heat_exchanger":
        card["heat_exchanger_type"] = HEAT_EXCHANGER_TYPES[0]
        spec = f"사양 {index}"
        card["fields"]["name"] = {"value": spec, "status": "provided", "source": "system", "display_value": spec}
    return card


def default_condition_sets(request_context: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    fieldset = build_condition_fieldset(request_context)
    cards = []
    for group in fieldset["groups"]:
        if not group["active"]:
            continue
        card = make_condition_card(group["key"], 1)
        active_fields = {field["key"] for field in group["fields"] if field["active"]}
        card["fields"] = {key: value for key, value in card["fields"].items() if key in active_fields}
        cards.append(card)
    return cards


def sanitize_condition_sets(raw: Any, request_context: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    fieldset = build_condition_fieldset(request_context)
    templates = {item["key"]: item for item in CARD_TEMPLATES}
    active = {group["key"] for group in fieldset["groups"] if group["active"]}
    active_fields = {
        group["key"]: {field["key"] for field in group["fields"] if field["active"]}
        for group in fieldset["groups"]
        if group["active"]
    }
    source = raw if isinstance(raw, list) else []
    by_type: dict[str, list[Mapping[str, Any]]] = {key: [] for key in active}
    for card in source:
        if isinstance(card, Mapping) and _clean(card.get("type")) in active:
            by_type[_clean(card.get("type"))].append(card)
    result = []
    seen_ids: set[str] = set()
    for card_type in (item["key"] for item in CARD_TEMPLATES if item["key"] in active):
        has_source_cards = bool(by_type[card_type])
        cards = by_type[card_type] or [{}]
        for index, raw_card in enumerate(cards, 1):
            raw_id = _clean(raw_card.get("id"))
            if is_valid_condition_card_id(raw_id, card_type) and raw_id not in seen_ids:
                card_id = raw_id
            elif not has_source_cards and index == 1:
                card_id = f"{card_type}_1"
            else:
                card_id = new_condition_card_id(card_type)
                while card_id in seen_ids:
                    card_id = new_condition_card_id(card_type)
            seen_ids.add(card_id)
            card = make_condition_card(card_type, index, templates[card_type], card_id=card_id)
            card["fields"] = {key: value for key, value in card["fields"].items() if key in active_fields[card_type]}
            raw_fields = raw_card.get("fields") if isinstance(raw_card.get("fields"), Mapping) else {}
            for key in card["fields"]:
                value = raw_fields.get(key, "")
                value = value.get("value", "") if isinstance(value, Mapping) else value
                text = _clean(value)
                card["fields"][key] = {"value": text, "status": "provided" if text else "missing", "source": "user", "display_value": text}
            if card_type == "heat_exchanger":
                spec = f"사양 {index}"
                card["fields"]["name"] = {"value": spec, "status": "provided", "source": "system", "display_value": spec}
                heat_exchanger_type = _clean(raw_card.get("heat_exchanger_type"))
                if heat_exchanger_type not in HEAT_EXCHANGER_TYPES:
                    tube_diameter = _clean(card["fields"]["tube_diameter"].get("value"))
                    heat_exchanger_type = heat_exchanger_type_from_tube_diameter(tube_diameter)
                card["heat_exchanger_type"] = heat_exchanger_type
                if heat_exchanger_type == "Micro-Channel":
                    card["fields"]["fin_type"] = {"value": "Flat", "status": "provided", "source": "user", "display_value": "Flat"}
            if card_type == "operating":
                card["name"] = f"운전 {index}"
                fan_rpm_mode = _clean(raw_card.get("fan_rpm_mode"))
                card["fan_rpm_mode"] = fan_rpm_mode if fan_rpm_mode in {"common", "individual"} else ""
                fans = raw_card.get("fans") if isinstance(raw_card.get("fans"), list) else []
                if not fans and isinstance(raw_card.get("fan_rpms"), list):
                    fans = [
                        {"id": f"fan_{fan_index}", "name": "", "location": "", "running": True, "values": {"fan_rpm": rpm}}
                        for fan_index, rpm in enumerate(raw_card["fan_rpms"], 1)
                    ]
                card["fans"] = []
                for fan_index, fan in enumerate(fans or [{}], 1):
                    fan = fan if isinstance(fan, Mapping) else {}
                    values = fan.get("values") if isinstance(fan.get("values"), Mapping) else {}
                    rpm = _clean(values.get("fan_rpm"))
                    if not rpm and (fan.get("running") is False or _clean(fan.get("status")).lower() == "stopped"):
                        rpm = "0"
                    card["fans"].append({
                        "id": _clean(fan.get("id")) or f"fan_{fan_index}",
                        "name": _clean(fan.get("name")),
                        "location": _clean(fan.get("location")),
                        "running": True,
                        "values": {"fan_rpm": rpm},
                    })
                card["fan_count"] = len(card["fans"])
                if card["fan_count"] == 1:
                    card["fan_rpm_mode"] = ""
                card["fan_locations"] = [fan["location"] for fan in card["fans"]]
                card["fan_rpms"] = [fan["values"]["fan_rpm"] for fan in card["fans"]]
            result.append(card)
    return result


def get_active_case_matrix_columns(request_context: Mapping[str, Any] | None = None) -> list[dict[str, str]]:
    """Return ordered manual-mapping columns enabled by the selected analysis type."""

    fieldset = build_condition_fieldset(request_context)
    active_card_types = {
        group["key"]
        for group in fieldset.get("groups", [])
        if group.get("active") is True
    }
    active_fields = {
        field["key"]
        for group in fieldset.get("groups", [])
        if group.get("active") is True
        for field in group.get("fields", [])
        if field.get("active") is True
    }
    return [
        dict(column)
        for column in CASE_MATRIX_CONDITION_COLUMNS
        if column["card_type"] in active_card_types and (
            column["card_type"] == "operating"
            or ("name" if column["key"] == "heat_exchanger" else column["key"]) in active_fields
        )
    ]


def get_active_condition_fields(state: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    state = state or {}
    context = _context(state)
    conditions = state.get("conditions", {}) if isinstance(state, Mapping) else {}
    cards = sanitize_condition_sets(conditions.get("condition_sets") if isinstance(conditions, Mapping) else None, context)
    fieldset = build_condition_fieldset(context)
    required = {key for group in fieldset["groups"] if group["active"] for key in [group["key"]]}
    metas = {field["key"]: field for group in fieldset["groups"] for field in group["fields"]}
    result = []
    for card in cards:
        for key, value in card["fields"].items():
            meta = metas[key]
            rows = []
            extra: dict[str, Any] = {}
            if card["type"] == "operating" and key == "fan_rpm":
                running_fans = [fan for fan in card.get("fans", []) if fan.get("running") is not False]
                rpms = [_clean(fan.get("values", {}).get(key)) for fan in running_fans]
                locations = [_clean(fan.get("location")) for fan in running_fans]
                fan_rpm_mode = _clean(card.get("fan_rpm_mode")) if len(rpms) >= 2 else ""
                display_values = [
                    f"{location} {rpm or '-'}" if len(rpms) >= 2 and location else (rpm or "-")
                    for location, rpm in zip(locations, rpms)
                ]
                display_value = " / ".join(display_values) if any(rpms) else ""
                provided = bool(rpms) and all(rpms)
                if len(rpms) >= 2:
                    if fan_rpm_mode == "common":
                        provided = provided and len(set(rpms)) == 1
                        display_value = f"모든 팬 {rpms[0]}" if provided else display_value
                    elif fan_rpm_mode == "individual":
                        provided = provided and all(locations)
                    else:
                        provided = False
                configuration = {
                    "name": _clean(card.get("name")) or "운전",
                    "fan_count": len(rpms),
                    "fan_rpm_mode": fan_rpm_mode,
                    "fan_locations": locations,
                    "fan_rpms": rpms,
                }
                rows = [{
                    "id": f"{card['id']}_fan_configuration",
                    "value": display_value,
                    "display_value": display_value,
                    "status": "provided" if provided else "missing",
                    "source": "user",
                    "fan_configuration": configuration,
                }]
                extra = {
                    "label": f"{configuration['name']} 팬 회전수(RPM)",
                    "value_semantics": "fan_configuration",
                    "fan_configuration": configuration,
                }
            else:
                rows = [value]
            result.append({**meta, **extra, "key": f"{card['id']}.{key}", "field_key": key, "card_id": card["id"], "values": rows, "required": card["type"] in required})
    return result
