"""Demo-only analysis type helpers for the h2_v2 Fluent POC."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any, Mapping

from .constants import (
    DEMO_ANALYSIS_TYPE_CODE,
    DEMO_ANALYSIS_TYPE_NAME,
    DEMO_CONDITION_MODE,
    SECTION_ANALYSIS_OVERVIEW,
    SECTION_CASE_MATRIX,
    SECTION_CONDITIONS,
    SECTION_GEOMETRY,
    SECTION_METADATA,
    SECTION_REQUEST_CONTEXT,
    VALUE_SOURCE_SYSTEM,
    VALUE_SOURCE_USER,
)
from .state import assign_request_no_if_missing, ensure_request_context, field_value, make_field, make_value_row
from .validator import state_with_validation


DEMO_WORKING_FLUID_DEFAULT = "air"
DEMO_INLET_VELOCITY_DEFAULT = "1.0"
DEMO_OUTLET_CONDITION_DEFAULT = "pressure outlet"


def _clean(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def is_demo_analysis_type(value: object) -> bool:
    token = _clean(value).lower().replace(" ", "").replace("-", "_")
    return token in {
        DEMO_ANALYSIS_TYPE_NAME.lower(),
        DEMO_ANALYSIS_TYPE_CODE.lower(),
        "demo",
        "demo_fluent",
        "demo_fluent_242r2",
        "fluent_demo",
    }


def _existing_condition_value(raw_state: Mapping[str, Any], key: str, default: str) -> str:
    conditions = raw_state.get(SECTION_CONDITIONS) if isinstance(raw_state.get(SECTION_CONDITIONS), Mapping) else {}
    fields = conditions.get("fields") if isinstance(conditions, Mapping) else []
    if not isinstance(fields, list):
        return default
    for field in fields:
        if not isinstance(field, Mapping) or _clean(field.get("key")) != key:
            continue
        values = field.get("values")
        if not isinstance(values, list):
            continue
        for row in values:
            if isinstance(row, Mapping):
                value = _clean(field_value(row, ""))
            else:
                value = _clean(row)
            if value:
                return value
    return default


def _demo_condition_field(
    *,
    key: str,
    label: str,
    value: str,
    value_type: str,
    unit: str = "",
    options: list[str] | None = None,
    source: str = VALUE_SOURCE_USER,
) -> dict[str, Any]:
    field = {
        "key": key,
        "label": label,
        "required": True,
        "value_type": value_type,
        "unit": unit,
        "binding": "condition-linked",
        "active": True,
        "values": [make_value_row(key, 1, value, source=source)],
    }
    if options:
        field["options"] = list(options)
    return field


def demo_condition_field_defs(raw_state: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    state = raw_state if isinstance(raw_state, Mapping) else {}
    return [
        _demo_condition_field(
            key="working_fluid",
            label="작동유체",
            value=_existing_condition_value(state, "working_fluid", DEMO_WORKING_FLUID_DEFAULT),
            value_type="select",
            options=["air", "water"],
            source=VALUE_SOURCE_USER,
        ),
        _demo_condition_field(
            key="inlet_velocity",
            label="입구조건",
            value=_existing_condition_value(state, "inlet_velocity", DEMO_INLET_VELOCITY_DEFAULT),
            value_type="number",
            unit="m/s",
            source=VALUE_SOURCE_USER,
        ),
        _demo_condition_field(
            key="outlet_condition",
            label="출구조건",
            value=_existing_condition_value(state, "outlet_condition", DEMO_OUTLET_CONDITION_DEFAULT),
            value_type="select",
            options=[DEMO_OUTLET_CONDITION_DEFAULT],
            source=VALUE_SOURCE_SYSTEM,
        ),
    ]


def _demo_product_name(request_no: str) -> str:
    suffixes = ("A", "B", "C")
    index = sum(ord(ch) for ch in request_no) % len(suffixes) if request_no else 0
    return f"Demo-Duct-{suffixes[index]}"


def apply_demo_analysis_type_state(raw_state: Mapping[str, Any]) -> dict[str, Any]:
    """Return a state configured for the demo-only Fluent 2024 R2 flow."""

    source = deepcopy(raw_state if isinstance(raw_state, Mapping) else {})
    state = assign_request_no_if_missing(source)
    request_no = _clean(state.get(SECTION_METADATA, {}).get("request_no"))
    product_name = _demo_product_name(request_no)

    overview = dict(state.get(SECTION_ANALYSIS_OVERVIEW, {}))
    overview.update(
        {
            "project_name": make_field("Fluent 2024 R2 Demo Case", source=VALUE_SOURCE_SYSTEM),
            "grade": make_field("선행", source=VALUE_SOURCE_SYSTEM),
            "npi_stage": make_field("DV", source=VALUE_SOURCE_SYSTEM),
            "pms_group": make_field("Demo CAE", source=VALUE_SOURCE_SYSTEM),
            "platform": make_field("Fluent 242R2", source=VALUE_SOURCE_SYSTEM),
            "chassis_name": make_field(product_name, source=VALUE_SOURCE_SYSTEM),
            "analysis_type": make_field(DEMO_ANALYSIS_TYPE_NAME, source=VALUE_SOURCE_USER, note="selected demo analysis type"),
            "request_date": make_field(date.today().isoformat(), source=VALUE_SOURCE_SYSTEM),
            "purpose": make_field("msh.h5 mesh 기반 Fluent case 생성 POC", source=VALUE_SOURCE_SYSTEM),
            "goal": make_field("DB 저장 조건을 journal에 반영하고 cas 파일 생성을 확인", source=VALUE_SOURCE_SYSTEM),
            "deliverables": make_field("Fluent journal, DB snapshot, run log, case file", source=VALUE_SOURCE_SYSTEM),
        }
    )
    state[SECTION_ANALYSIS_OVERVIEW] = overview

    state[SECTION_GEOMETRY] = {
        "products": [make_value_row("product", 1, product_name, source=VALUE_SOURCE_SYSTEM)],
        "has_changed_part": make_field(False, source=VALUE_SOURCE_SYSTEM),
        "changed_from_part": make_field("", source=VALUE_SOURCE_SYSTEM),
        "parts": [make_value_row("part", 1, "fluid-domain", source=VALUE_SOURCE_SYSTEM)],
        "boundary_bindings": [
            {"boundary_name": "inlet", "boundary_type": "velocity-inlet", "condition_key": "inlet_velocity"},
            {"boundary_name": "outlet", "boundary_type": "pressure-outlet", "condition_key": "outlet_condition"},
        ],
    }
    state[SECTION_CONDITIONS] = {
        "mode": DEMO_CONDITION_MODE,
        "fields": demo_condition_field_defs(source),
        "common_conditions": {},
        "variable_conditions": {},
    }
    state[SECTION_CASE_MATRIX] = {
        "preview_cases": [],
        "final_cases": [],
        "excluded_case_ids": [],
        "common_conditions": {},
        "generation_status": "missing",
    }

    metadata = dict(state.get(SECTION_METADATA, {}))
    metadata["analysis_type_code"] = DEMO_ANALYSIS_TYPE_CODE
    metadata["condition_mode"] = DEMO_CONDITION_MODE
    metadata["opened_sections"] = {
        **dict(metadata.get("opened_sections") if isinstance(metadata.get("opened_sections"), Mapping) else {}),
        "analysis_overview": True,
        "geometry": True,
        "conditions": True,
        "case_matrix": True,
    }
    state[SECTION_METADATA] = metadata
    ensure_request_context(state)
    state[SECTION_REQUEST_CONTEXT]["analysis_type"] = DEMO_ANALYSIS_TYPE_NAME
    state[SECTION_REQUEST_CONTEXT]["operation_mode"] = DEMO_CONDITION_MODE
    state[SECTION_REQUEST_CONTEXT]["condition_fieldset_key"] = DEMO_CONDITION_MODE
    return state_with_validation(state)


def extract_demo_conditions(raw_state: Mapping[str, Any]) -> dict[str, str]:
    conditions = raw_state.get(SECTION_CONDITIONS) if isinstance(raw_state.get(SECTION_CONDITIONS), Mapping) else {}
    fields = conditions.get("fields") if isinstance(conditions, Mapping) else []
    out = {
        "working_fluid": "",
        "inlet_velocity": "",
        "outlet_condition": "",
    }
    if not isinstance(fields, list):
        return out
    for field in fields:
        if not isinstance(field, Mapping):
            continue
        key = _clean(field.get("key"))
        if key not in out:
            continue
        values = field.get("values")
        if not isinstance(values, list):
            continue
        for row in values:
            if isinstance(row, Mapping):
                value = _clean(field_value(row, ""))
            else:
                value = _clean(row)
            if value:
                out[key] = value
                break
    return out
