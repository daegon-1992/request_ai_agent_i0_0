"""Draft generation for CAE request outlines."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any, Mapping, Sequence

from .constants import (
    APP_VERSION,
    SECTION_ANALYSIS_OVERVIEW,
    SECTION_BASIC_INFO,
    SECTION_CASE_MATRIX,
    SECTION_CONDITIONS,
    SECTION_GEOMETRY,
    SECTION_REVIEW,
)
from .rag_bridge import build_request_rag_package
from .state import field_value
from .validator import state_with_validation


DraftPayload = dict[str, Any]

BACKGROUND_FALLBACK = "설계 판단 근거 확보를 위한 CAE 검토가 필요함."
CONDITION_TERMS = (
    "rpm",
    "fan",
    "room",
    "rh",
    "fpi",
    "pa",
    "kpa",
    "mpa",
    "degc",
    "case",
    "louver",
    "vane",
    "filter",
    "조건",
    "온도",
    "습도",
    "압력조건",
    "열교환기",
    "필터",
    "사양",
    "스펙",
)
NUMERIC_OR_UNIT_RE = re.compile(
    r"(?i)(\d+(?:\.\d+)?\s*(?:rpm|r/min|pa|kpa|mpa|degc|c|%|rh|fpi|hz)|case\s*\d+)"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _field_text(section: Mapping[str, Any], key: str) -> str:
    return _clean_text(field_value(_as_mapping(section).get(key)))


def _field_map(section: Mapping[str, Any], keys: Sequence[str]) -> dict[str, str]:
    return {key: _field_text(section, key) for key in keys}


def contains_condition_like_tokens(text: str) -> bool:
    """Return True when a background sentence looks like a condition list."""

    compact = _clean_text(text)
    if not compact:
        return False
    lowered = compact.lower()
    if NUMERIC_OR_UNIT_RE.search(lowered):
        return True
    separators = sum(lowered.count(token) for token in (",", "/", ";", ":", "=", "\n", "|"))
    term_count = sum(1 for token in CONDITION_TERMS if token in lowered)
    return separators >= 1 and term_count >= 2


def _fallback_background(state: Mapping[str, Any]) -> str:
    overview = _as_mapping(state.get(SECTION_ANALYSIS_OVERVIEW))
    geometry = _as_mapping(state.get(SECTION_GEOMETRY))
    analysis_type = _field_text(overview, "analysis_type")
    has_changed_part = bool(field_value(_as_mapping(geometry.get("has_changed_part")), False))
    if has_changed_part:
        return "설계 변경 영향 확인을 위한 CAE 검토가 필요함."
    if analysis_type:
        return f"{analysis_type} 해석을 통한 설계 판단 근거 확보가 필요함."
    return BACKGROUND_FALLBACK


def _quality_background(raw_background: str, state: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    background = _clean_text(raw_background)
    if background and not contains_condition_like_tokens(background):
        return background, {
            "code": "draft.background.no_condition_numeric_list",
            "passed": True,
            "source": "state.analysis_overview.background",
            "action": "kept",
        }
    fallback = _fallback_background(state)
    return fallback, {
        "code": "draft.background.no_condition_numeric_list",
        "passed": bool(fallback),
        "source": "derived_fallback",
        "action": "replaced_condition_like_background" if background else "filled_missing_background",
        "original_had_condition_like_tokens": contains_condition_like_tokens(background),
    }


def _default_deliverables(state: Mapping[str, Any]) -> str:
    overview = _as_mapping(state.get(SECTION_ANALYSIS_OVERVIEW))
    analysis_type = _field_text(overview, "analysis_type") or "CAE"
    return f"{analysis_type} 결과 요약, Case Matrix별 비교표, 검토 의견"


def _geometry_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    geometry = _as_mapping(state.get(SECTION_GEOMETRY))
    axis = _as_mapping(geometry.get("axis"))
    variants = [
        {
            "geometry_id": _clean_text(item.get("geometry_id")),
            "geometry_label": _clean_text(item.get("geometry_label")),
            "combination_type": _clean_text(item.get("combination_type")),
        }
        for item in _as_list(axis.get("geometry_variants"))
        if isinstance(item, Mapping)
    ]
    return {
        "variant_count": len(variants),
        "variants": variants,
    }


def _condition_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    conditions = _as_mapping(state.get(SECTION_CONDITIONS))
    cards: list[dict[str, Any]] = []
    for raw_card in _as_list(conditions.get("condition_sets")):
        card = _as_mapping(raw_card)
        fields = _as_mapping(card.get("fields"))
        values = {
            _clean_text(key): _clean_text(field_value(value, ""))
            for key, value in fields.items()
            if _clean_text(field_value(value, ""))
        }
        fans = []
        for raw_fan in _as_list(card.get("fans")):
            fan = _as_mapping(raw_fan)
            if fan.get("running") is False:
                continue
            fan_value = _clean_text(_as_mapping(fan.get("values")).get("fan_rpm"))
            if fan_value:
                fans.append({
                    "name": _clean_text(fan.get("name")),
                    "location": _clean_text(fan.get("location")),
                    "fan_rpm": fan_value,
                })
        cards.append(
            {
                "id": _clean_text(card.get("id")),
                "type": _clean_text(card.get("type")),
                "label": _clean_text(card.get("label")),
                "name": _clean_text(card.get("name")),
                "fan_count": card.get("fan_count") if _clean_text(card.get("type")) == "operating" else None,
                "fan_locations": list(card.get("fan_locations", [])) if isinstance(card.get("fan_locations"), list) else [],
                "fan_rpms": list(card.get("fan_rpms", [])) if isinstance(card.get("fan_rpms"), list) else [],
                "values": values,
                "fans": fans,
            }
        )
    return {
        "condition_cards": cards,
    }


def _case_matrix_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    case_matrix = _as_mapping(state.get(SECTION_CASE_MATRIX))
    rows = [
        {
            "case_id": _clean_text(item.get("case_id")),
            "case_no": index,
            "visible_cells": deepcopy(_as_mapping(item.get("visible_cells"))),
        }
        for index, item in enumerate(_as_list(case_matrix.get("rows")), start=1)
        if isinstance(item, Mapping)
    ]
    return {
        "case_count": len(rows),
        "visible_columns": deepcopy(_as_list(case_matrix.get("visible_columns"))),
        "rows": rows,
    }


def _sources_from_rag_package(rag_package: Mapping[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    qa = _as_mapping(rag_package.get("qa"))
    for source in _as_list(qa.get("sources")):
        if isinstance(source, Mapping):
            sources.append(dict(source))
    contexts = _as_mapping(rag_package.get("contexts"))
    for context in contexts.values():
        if not isinstance(context, Mapping):
            continue
        for hit in _as_list(context.get("hits")):
            if isinstance(hit, Mapping):
                sources.append(dict(hit))

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source in sources:
        row = dict(source)
        row["source_path"] = _clean_text(row.get("source_path") or row.get("file_path"))
        row["source_location"] = _clean_text(row.get("source_location") or row.get("location"))
        row["source_name"] = _clean_text(row.get("source_name") or row.get("source"))
        row["source_snippet"] = _clean_text(row.get("source_snippet") or row.get("content"))
        key = (row["source_path"], row["source_location"])
        if key in seen:
            continue
        seen.add(key)
        row["usage"] = "sentence_support_only"
        row["state_authority"] = "structured_state_only"
        deduped.append(row)
        if len(deduped) >= 5:
            break
    return deduped


def _rag_evidence(
    state: Mapping[str, Any],
    *,
    rag_package: Mapping[str, Any] | None = None,
    use_rag: bool = False,
    rag_question: str = "",
    search_roots: Sequence[str] | None = None,
    db_root_path: str | None = None,
) -> dict[str, Any]:
    package = rag_package if isinstance(rag_package, Mapping) else None
    if package is None and use_rag:
        package = build_request_rag_package(
            state,
            question=rag_question,
            search_roots=search_roots,
            db_root_path=db_root_path,
        )
    if package is None:
        return {
            "enabled": False,
            "read_only": True,
            "state_changed": False,
            "usage": "sentence_support_only",
            "state_authority": "structured_state_only",
            "sources": [],
            "limitations": ["No RAG package was provided for draft sentence support."],
        }
    read_only = bool(package.get("read_only", True))
    state_changed = bool(package.get("state_changed", False))
    return {
        "enabled": bool(package.get("enabled", True)),
        "read_only": read_only,
        "state_changed": state_changed,
        "usage": "sentence_support_only",
        "state_authority": "structured_state_only",
        "sources": _sources_from_rag_package(package),
        "limitations": []
        if read_only and not state_changed
        else ["RAG package is not read-only clean; use it only for display evidence, never for state confirmation."],
    }


def _markdown(document: Mapping[str, Any]) -> str:
    overview = _as_mapping(document.get("analysis_overview"))
    case_summary = _as_mapping(document.get("case_matrix_summary"))
    lines = [
        "# 해석 의뢰서 초안",
        "",
        "## 해석 개요",
        f"- 배경: {overview.get('background', '-')}",
        f"- 목적: {overview.get('purpose', '-')}",
        f"- 목표: {overview.get('goal', '-')}",
        f"- 산출물: {overview.get('deliverables', '-')}",
        "",
        "## Case Matrix 요약",
        f"- Case: {case_summary.get('case_count', 0)}건",
    ]
    for case in _as_list(case_summary.get("rows"))[:8]:
        cells = _as_mapping(case.get("visible_cells"))
        label = " / ".join(_clean_text(value) for value in cells.values() if _clean_text(value))
        lines.append(f"- {case.get('case_id')}: {label}")
    return "\n".join(lines).strip()


def build_request_draft(
    raw_state: Mapping[str, Any],
    *,
    rag_package: Mapping[str, Any] | None = None,
    use_rag: bool = False,
    rag_question: str = "",
    search_roots: Sequence[str] | None = None,
    db_root_path: str | None = None,
) -> DraftPayload:
    """Build a derived request draft without changing structured input state."""

    state = state_with_validation(raw_state if isinstance(raw_state, Mapping) else {})
    review = _as_mapping(state.get(SECTION_REVIEW))
    validation = _as_mapping(review.get("validator"))
    summary = _as_mapping(validation.get("summary"))
    blocking = _as_list(validation.get("blocking"))
    warnings = _as_list(validation.get("warning"))
    can_submit = bool(summary.get("can_submit", False))

    overview = _as_mapping(state.get(SECTION_ANALYSIS_OVERVIEW))
    background, background_check = _quality_background(_field_text(overview, "background"), state)
    purpose = _field_text(overview, "purpose")
    goal = _field_text(overview, "goal")
    deliverables = _field_text(overview, "deliverables") or _default_deliverables(state)
    evidence = _rag_evidence(
        state,
        rag_package=rag_package,
        use_rag=use_rag,
        rag_question=rag_question,
        search_roots=search_roots,
        db_root_path=db_root_path,
    )

    document = {
        "title": "해석 의뢰서 초안",
        "basic_info": _field_map(
            _as_mapping(state.get(SECTION_BASIC_INFO)),
            ("request_no", "division", "department", "requester_name", "requester_role"),
        ),
        "request_schedule": _field_map(
            _as_mapping(state.get(SECTION_ANALYSIS_OVERVIEW)),
            ("request_date", "due_date"),
        ),
        "analysis_overview": {
            "background": background,
            "purpose": purpose,
            "goal": goal,
            "deliverables": deliverables,
        },
        "geometry_summary": _geometry_summary(state),
        "condition_summary": _condition_summary(state),
        "case_matrix_summary": _case_matrix_summary(state),
        "evidence_summary": evidence,
    }
    document["markdown"] = _markdown(document) if can_submit else ""

    status = "ready" if can_submit else "blocked"
    return {
        "ok": can_submit,
        "version": APP_VERSION,
        "status": status,
        "generated_at": _utc_now(),
        "state_changed": False,
        "state_authority": "structured_state_and_case_matrix_only",
        "blocking_reasons": [dict(item) for item in blocking],
        "warnings": [dict(item) for item in warnings],
        "validation_summary": dict(summary),
        "quality_checks": [
            background_check,
            {
                "code": "draft.rag.read_only_sentence_support",
                "passed": bool(evidence.get("read_only", True)) and not bool(evidence.get("state_changed", False)),
                "source": "rag_package",
                "action": "sources_attached_only",
            },
        ],
        "document": document if can_submit else {**document, "markdown": ""},
        "input_contract": {
            "required_state_sections": [
                SECTION_BASIC_INFO,
                SECTION_ANALYSIS_OVERVIEW,
                SECTION_GEOMETRY,
                SECTION_CONDITIONS,
                SECTION_CASE_MATRIX,
            ],
            "requires_validator_can_submit": True,
            "requires_final_case_count_gt_zero": True,
            "rag_usage": "optional_sentence_support_only",
        },
    }


def state_with_draft(raw_state: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Return a validated state copy with review.draft populated."""

    state = state_with_validation(raw_state if isinstance(raw_state, Mapping) else {})
    draft = build_request_draft(state, **kwargs)
    state[SECTION_REVIEW]["draft"] = deepcopy(draft)
    return state
