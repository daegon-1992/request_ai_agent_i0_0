"""Build a human-readable request preview document."""

from __future__ import annotations

from typing import Any, Mapping

from .state import field_value
from .validator import state_with_validation


def _clean(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _value(section: Mapping[str, Any], key: str) -> str:
    return _clean(field_value(section.get(key), ""))


def _display_field(field: Any) -> str:
    if isinstance(field, Mapping):
        value = field_value(field, "")
        if _clean(value):
            return _clean(value)
        display = _clean(field.get("display_value"))
        if display:
            return display
    return ""


def _row_values(rows: Any) -> list[str]:
    out: list[str] = []
    for row in _as_list(rows):
        value = _display_field(row) if isinstance(row, Mapping) else row
        text = _clean(value)
        if text:
            out.append(text)
    return out


def _kv(label: str, value: Any) -> dict[str, str]:
    return {"label": label, "value": _clean(value) or "-"}


def _condition_items(conditions: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for field in _as_list(conditions.get("fields")):
        if not isinstance(field, Mapping):
            continue
        if field.get("value_type") == "checkbox" and field.get("active") is False:
            values = _row_values([row for row in _as_list(field.get("values")) if isinstance(row, Mapping) and row.get("status") in {"none", "unknown", "skipped"}])
        else:
            values = _row_values(field.get("values"))
        if not values:
            continue
        items.append(
            {
                "label": _clean(field.get("label")) or _clean(field.get("key")),
                "value": ", ".join(values),
                "candidate": any(isinstance(row, Mapping) and row.get("source") == "ai_suggested" for row in _as_list(field.get("values"))),
            }
        )
    return items


def _markdown_section(title: str, items: list[dict[str, Any]]) -> str:
    lines = [f"## {title}"]
    if not items:
        lines.append("- 입력 없음")
        return "\n".join(lines)
    for item in items:
        label = _clean(item.get("label"))
        value = _clean(item.get("value"))
        suffix = " (AI 추천)" if bool(item.get("candidate")) else ""
        lines.append(f"- {label}: {value}{suffix}")
    return "\n".join(lines)


def build_request_preview(raw_state: Mapping[str, Any]) -> dict[str, Any]:
    state = state_with_validation(raw_state if isinstance(raw_state, Mapping) else {})
    basic = _as_mapping(state.get("basic_info"))
    metadata = _as_mapping(state.get("metadata"))
    overview = _as_mapping(state.get("analysis_overview"))
    geometry = _as_mapping(state.get("geometry"))
    conditions = _as_mapping(state.get("conditions"))
    case_matrix = _as_mapping(state.get("case_matrix"))
    validation = _as_mapping(_as_mapping(state.get("review")).get("validator"))
    summary = _as_mapping(validation.get("summary"))

    sections = [
        {
            "key": "basic_info",
            "title": "기본 정보",
            "items": [
                _kv("의뢰 번호", _clean(metadata.get("request_no")) or _value(basic, "request_no")),
                _kv("사업부", _value(basic, "division")),
                _kv("부서", _value(basic, "department")),
                _kv("요청자", _value(basic, "requester_name")),
                _kv("직급", _value(basic, "requester_role")),
            ],
        },
        {
            "key": "analysis_overview",
            "title": "해석 개요",
            "items": [
                _kv("해석 유형", _value(overview, "analysis_type")),
                _kv("프로젝트명", _value(overview, "project_name")),
                _kv("개발 등급", _value(overview, "grade")),
                _kv("NPI 단계", _value(overview, "npi_stage")),
                _kv("PMS 제품군", _display_field(overview.get("pms_group"))),
                _kv("플랫폼", _value(overview, "platform")),
                _kv("샷시명", _value(overview, "chassis_name")),
                _kv("요청일", _value(overview, "request_date")),
                _kv("희망 완료일", _value(overview, "due_date")),
                _kv("배경", _value(overview, "background")),
                _kv("목적", _value(overview, "purpose")),
                _kv("목표", _value(overview, "goal")),
                _kv("요청 산출물", _value(overview, "deliverables")),
            ],
        },
        {
            "key": "geometry",
            "title": "형상/모델 정보",
            "items": [
                _kv("제품", ", ".join(_row_values(geometry.get("products")))),
                _kv("변경 부품 있음", _value(geometry, "has_changed_part")),
                _kv("기존 부품", _value(geometry, "changed_from_part")),
                _kv("변경 부품", ", ".join(_row_values(geometry.get("parts")))),
            ],
        },
        {
            "key": "conditions",
            "title": "해석조건",
            "items": _condition_items(conditions),
        },
    ]
    case_rows = [
        {
            "case_id": _clean(case.get("case_id")),
            "display_case_no": index,
            "visible_cells": dict(_as_mapping(case.get("visible_cells"))),
        }
        for index, case in enumerate(_as_list(case_matrix.get("rows")), start=1)
        if isinstance(case, Mapping)
    ]
    case_items = [_kv("Case 수", len(case_rows))]
    sections.append({"key": "case_matrix", "title": "Case Matrix", "items": case_items})

    markdown = "\n\n".join(_markdown_section(section["title"], section["items"]) for section in sections)
    return {
        "status": "ready" if bool(summary.get("can_generate_case_matrix", False)) else "needs_input",
        "sections": sections,
        "case_matrix": {
            "visible_columns": case_matrix.get("visible_columns", []),
            "rows": case_rows,
            "source_inputs": case_matrix.get("source_inputs", {}),
        },
        "validation_summary": summary,
        "markdown": markdown,
    }
