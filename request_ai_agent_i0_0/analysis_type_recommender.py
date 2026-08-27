"""Analysis-type recommendation and candidate-condition helpers."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping

from .constants import (
    ANALYSIS_TYPE_ALIASES,
    ANALYSIS_TYPE_OPTIONS,
    CONDITION_FIELD_DEFS,
    SECTION_ANALYSIS_OVERVIEW,
    SECTION_CONDITIONS,
    SECTION_GEOMETRY,
    SECTION_REQUEST_CONTEXT,
    VALUE_SOURCE_USER,
)
from .rag_search import (
    SOURCE_TYPE_PRODUCT_INFORMATION,
    SOURCE_TYPE_SIMILAR_REPORT,
    SOURCE_TYPE_SOP,
    search_rag_documents,
)
from .state import assign_request_no_if_missing, ensure_request_context, field_value, sanitize_state
from .validator import state_with_validation


AI_SUGGESTED_SOURCE = "ai_suggested"

DEFAULT_CONDITION_CANDIDATES = {
    "기류 패턴": {
        "material_type": ["Air"],
        "fan_rpm": ["1000", "1200"],
        "room_temp": ["27"],
        "room_rh": ["50"],
        "heat_exchanger_temp": ["7"],
        "heat_exchanger_rh": ["90"],
    },
    "풍량": {
        "material_type": ["Air"],
        "fan_rpm": ["1000", "1200"],
        "room_temp": ["27"],
        "room_rh": ["50"],
        "heat_exchanger_temp": ["7"],
        "heat_exchanger_rh": ["90"],
    },
    "압력손실 해석": {
        "material_type": ["Air"],
        "fan_rpm": ["1000", "1200"],
        "pressure": ["0"],
    },
    "이슬맺힘": {
        "material_type": ["Air"],
        "pressure": ["대기압"],
        "fan_rpm": ["780"],
        "room_temp": ["27"],
        "room_rh": ["78"],
        "heat_exchanger_temp": ["15"],
        "heat_exchanger_rh": ["95"],
        "heat_exchanger_spec": ["P7.0 2R 18FPISlit(Half)"],
    },
    "구조 해석": {
        "material_type": ["N/A"],
    },
    "진동/소음 검토": {
        "material_type": ["Air"],
        "fan_rpm": ["1000", "1200"],
    },
}

CONDITION_FIELD_LABELS = {str(item.get("key", "")): str(item.get("label", "") or item.get("key", "")) for item in CONDITION_FIELD_DEFS}
CONDITION_FIELD_UNITS = {str(item.get("key", "")): str(item.get("unit", "") or "") for item in CONDITION_FIELD_DEFS}


def _clean(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def canonical_analysis_type(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    if text in ANALYSIS_TYPE_OPTIONS:
        return text
    if text in ANALYSIS_TYPE_ALIASES:
        return ANALYSIS_TYPE_ALIASES[text]
    lowered = text.lower()
    for alias, canonical in ANALYSIS_TYPE_ALIASES.items():
        if alias.lower() == lowered:
            return canonical
    if any(token in lowered for token in ("dew", "condensation")) or any(token in text for token in ("이슬", "결로")):
        return "이슬맺힘"
    return text


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _candidate_row(field_key: str, index: int, value: Any, *, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    row = {
        "id": f"{field_key}_candidate_{index}",
        "value": value,
        "status": "provided",
        "source": AI_SUGGESTED_SOURCE,
        "note": "AI recommended candidate. Confirm during final review.",
        "candidate": True,
        "approved": False,
    }
    if isinstance(evidence, Mapping) and evidence:
        source = _line(evidence.get("source_name")) or _line(evidence.get("source_type_label")) or "Chroma evidence"
        location = _line(evidence.get("source_location"))
        suffix = f" ({source} {location})" if location else f" ({source})"
        row["note"] = f"AI recommended candidate with read-only Chroma evidence{suffix}. Confirm during final review."
        row["evidence"] = dict(evidence)
    return row


ANALYSIS_RULES = [
    ("압력손실 해석", ("압력", "손실", "pressure"), "압력손실 관련 표현이 포함되어 압력손실 해석을 우선 추천합니다."),
    ("기류 패턴", ("열", "온도", "냉각", "유동", "풍속", "토출", "흡입", "heat", "thermal", "hot", "flow", "air"), "온도 조건을 포함한 공기 흐름과 유로 검토 의도가 있어 기류 패턴이 적합합니다."),
    ("풍량", ("풍량", "유량", "air volume", "airvolume"), "풍량 또는 유량 검토 의도가 있어 풍량 해석이 적합합니다."),
    ("이슬맺힘", ("이슬", "결로", "condensation", "습도", "dew"), "결로/습도 관련 표현이 있어 이슬맺힘을 추천합니다."),
    ("진동/소음 검토", ("진동", "소음", "noise", "vibration"), "진동 또는 소음 관련 표현이 있어 진동/소음 검토를 추천합니다."),
    ("구조 해석", ("강도", "변형", "응력", "structure", "stress"), "강도/변형 관련 표현이 있어 구조 해석을 추천합니다."),
]

EXACT_ANALYSIS_HINTS = {
    "압력손실 해석": ("압력손실", "pressure loss"),
    "기류 패턴": ("기류 패턴", "유동", "열유동", "airflow", "thermal flow"),
    "풍량": ("풍량", "air volume", "airvolume"),
    "이슬맺힘": ("이슬맺힘", "이슬맺힘 검토", "결로", "condensation", "dew"),
    "진동/소음 검토": ("진동", "소음", "noise", "vibration"),
    "구조 해석": ("구조", "응력", "변형", "stress"),
}


def _line(value: Any) -> str:
    return " ".join(_clean(value).split())


def _evidence_record(hit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_type": _line(hit.get("source_type")),
        "source_type_label": _line(hit.get("source_type_label")),
        "source_name": _line(hit.get("source")),
        "source_location": _line(hit.get("location")),
        "source_snippet": _line(hit.get("content"))[:260],
        "retrieval_mode": _line(hit.get("retrieval_mode")),
        "read_only": True,
        "state_authority": "structured_state_only",
    }


def _dedupe_evidence(hits: list[Mapping[str, Any]], *, max_items: int = 3) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        row = _evidence_record(hit)
        key = f"{row['source_type']}|{row['source_name']}|{row['source_location']}|{row['source_snippet'][:80]}"
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= max_items:
            break
    return out


def _rag_hits_for_recommendation(text: str) -> list[dict[str, Any]]:
    query = _line(text)
    if not query:
        return []
    return search_rag_documents(
        query,
        top_k=6,
        source_types=[SOURCE_TYPE_SIMILAR_REPORT, SOURCE_TYPE_PRODUCT_INFORMATION, SOURCE_TYPE_SOP],
        use_vector=True,
        vector_only=True,
    )


def _rag_diagnostics(hits: list[Mapping[str, Any]]) -> dict[str, Any]:
    modes: list[str] = []
    seen: set[str] = set()
    vector_hit_count = 0
    for hit in hits:
        mode = _line(hit.get("retrieval_mode"))
        if mode.startswith("chroma_vector_e5"):
            vector_hit_count += 1
        if mode and mode not in seen:
            seen.add(mode)
            modes.append(mode)
    return {
        "hit_count": len(hits),
        "vector_hit_count": vector_hit_count,
        "retrieval_modes": modes,
        "vector_only": True,
        "state_authority": "structured_state_only",
    }


def _recommendation_evidence_scores(text: str, *, rag_enabled: bool = True) -> tuple[dict[str, float], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    hits = _rag_hits_for_recommendation(text) if rag_enabled else []
    scores: dict[str, float] = {}
    evidence: dict[str, list[dict[str, Any]]] = {}
    for analysis_type, tokens, _reason in ANALYSIS_RULES:
        matched: list[Mapping[str, Any]] = []
        for hit in hits:
            haystack = f"{hit.get('source', '')} {hit.get('content', '')}".lower()
            token_hits = sum(1 for token in tokens if str(token).lower() in haystack)
            if token_hits:
                scores[analysis_type] = scores.get(analysis_type, 0.0) + min(0.18, 0.06 * token_hits)
                matched.append(hit)
        if matched:
            evidence[analysis_type] = _dedupe_evidence(list(matched))
    for analysis_type in list(scores):
        scores[analysis_type] = min(scores[analysis_type], 0.18)
    return scores, evidence, _rag_diagnostics(hits)


def recommend_analysis_types(message: str, *, product_family: str = "", rag_enabled: bool = True) -> dict[str, Any]:
    """Return up to 3 deterministic recommendations for the current planning flow."""

    text = f"{product_family} {message}".lower()
    scored: list[tuple[float, str, str, str]] = []
    evidence_scores, evidence_by_type, rag_diagnostics = _recommendation_evidence_scores(text, rag_enabled=rag_enabled)
    for analysis_type, tokens, reason in ANALYSIS_RULES:
        hits = sum(1 for token in tokens if token in text)
        evidence_bonus = evidence_scores.get(analysis_type, 0.0)
        exact_bonus = 0.22 if any(token in text for token in EXACT_ANALYSIS_HINTS.get(analysis_type, ())) else 0.0
        if hits or evidence_bonus:
            source = "message_and_chroma" if hits and evidence_bonus else ("message" if hits else "chroma")
            score = (0.58 + min(hits, 3) * 0.12 if hits else 0.52) + evidence_bonus + exact_bonus
            rag_reason = (
                " data Chroma store의 유사보고서/제품정보/SOP 근거도 함께 검색되었습니다."
                if evidence_bonus
                else ""
            )
            scored.append((score, canonical_analysis_type(analysis_type), reason + rag_reason, source))
    if not scored:
        scored = [
            (0.58, "기류 패턴", "제품군과 검토 내용을 더 확인해야 하지만 일반 CAE 의뢰에서는 기류 패턴 가능성이 높습니다.", "fallback"),
            (0.48, "풍량", "풍량 또는 유량 목표가 포함될 가능성을 보조 후보로 둡니다.", "fallback"),
            (0.38, "압력손실 해석", "압력/유량 목표가 추가되면 적합할 수 있습니다.", "fallback"),
        ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    dew_entry = next((item for item in scored if canonical_analysis_type(item[1]) == "이슬맺힘"), None)
    if dew_entry:
        dew_entry = (max(dew_entry[0], 0.93), "이슬맺힘", dew_entry[2], dew_entry[3])
    else:
        dew_entry = (0.93, "이슬맺힘", "이슬맺힘 해석유형을 우선 추천하도록 설정되어 있습니다.", "default_priority")
    scored = [dew_entry, *[item for item in scored if canonical_analysis_type(item[1]) != "이슬맺힘"]]
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for score, analysis_type, reason, source in scored:
        if analysis_type in seen:
            continue
        seen.add(analysis_type)
        deduped.append(
            {
                "analysis_type": analysis_type,
                "confidence": round(min(score, 0.92), 2),
                "reason": reason,
                "recommendation_source": source,
                "evidence": evidence_by_type.get(analysis_type, []),
            }
        )
        if len(deduped) >= 3:
            break
    return {
        "ok": True,
        "recommendations": deduped,
        "message": "제품군, 검토 내용, 읽기 전용 Chroma 근거를 기준으로 해석유형 후보를 추천했습니다.",
        "rag_usage": "recommendation_evidence_only" if rag_enabled else "disabled_by_user",
        "rag_diagnostics": rag_diagnostics,
        "state_changed": False,
    }


def _state_query_bits(state: Mapping[str, Any], analysis_type: str) -> str:
    overview = state.get(SECTION_ANALYSIS_OVERVIEW, {})
    geometry = state.get(SECTION_GEOMETRY, {})
    product_values = []
    for row in (geometry.get("products", []) if isinstance(geometry, Mapping) else []):
        product_values.append(_line(field_value(row, "")))
    parts = [
        analysis_type,
        _line(field_value(overview.get("purpose"), "")) if isinstance(overview, Mapping) else "",
        _line(field_value(overview.get("goal"), "")) if isinstance(overview, Mapping) else "",
        " ".join(product_values),
        "해석 조건 fan rpm pressure temperature humidity boundary condition",
    ]
    return " ".join(part for part in parts if part)


def _add_candidate_value(
    bucket: dict[str, list[dict[str, Any]]],
    field_key: str,
    value: Any,
    evidence: Mapping[str, Any],
    *,
    limit: int = 3,
) -> None:
    text = _line(value)
    if not text:
        return
    rows = bucket.setdefault(field_key, [])
    if any(_line(row.get("value")) == text for row in rows):
        return
    if len(rows) >= limit:
        return
    rows.append({"value": text, "evidence": dict(evidence)})


def _extract_numeric_candidates(hit: Mapping[str, Any], bucket: dict[str, list[dict[str, Any]]]) -> None:
    text = _line(hit.get("content"))
    if not text:
        return
    lowered = f"{hit.get('source', '')} {hit.get('location', '')} {text}".lower()
    evidence = _evidence_record(hit)
    for match in re.finditer(r"(?<!\d)(\d{3,5})\s*(?:rpm|r/min)\b", lowered, flags=re.IGNORECASE):
        rpm = int(match.group(1))
        if 100 <= rpm <= 50000:
            _add_candidate_value(bucket, "fan_rpm", str(rpm), evidence)
    if any(token in lowered for token in ("pressure", "압력", "pa", "kpa")):
        for match in re.finditer(r"(?<!\d)([-+]?\d+(?:\.\d+)?)\s*(?:pa|kpa)\b", lowered, flags=re.IGNORECASE):
            _add_candidate_value(bucket, "pressure", match.group(1), evidence)
    if any(token in lowered for token in ("humidity", "relative humidity", "습도", "rh", "%")):
        for match in re.finditer(r"(?<!\d)(\d{1,3})\s*(?:%|rh)\b", lowered, flags=re.IGNORECASE):
            rh = int(float(match.group(1)))
            if 0 <= rh <= 100:
                target = "heat_exchanger_rh" if any(token in lowered for token in ("heat exchanger", "evaporator", "열교환")) else "room_rh"
                _add_candidate_value(bucket, target, str(rh), evidence)
    if any(token in lowered for token in ("temperature", "temp", "온도", "degc", "°c")):
        for match in re.finditer(r"(?<!\d)([-+]?\d{1,2}(?:\.\d+)?)\s*(?:°c|degc|c)\b", lowered, flags=re.IGNORECASE):
            value = float(match.group(1))
            if -50 <= value <= 120:
                has_heat_exchanger_context = any(token in lowered for token in ("heat exchanger", "evaporator", "열교환", "hex"))
                has_room_context = any(token in lowered for token in ("room", "ambient", "indoor", "실내"))
                if not has_heat_exchanger_context and not has_room_context:
                    continue
                field_key = "heat_exchanger_temp" if has_heat_exchanger_context else "room_temp"
                _add_candidate_value(bucket, field_key, str(int(value) if value.is_integer() else value), evidence)


def _rag_candidate_conditions(state: Mapping[str, Any], analysis_type: str, *, rag_enabled: bool = True) -> dict[str, list[dict[str, Any]]]:
    if not rag_enabled:
        return {}
    query = _state_query_bits(state, analysis_type)
    if not query:
        return {}
    hits = search_rag_documents(
        query,
        top_k=8,
        source_types=[SOURCE_TYPE_SIMILAR_REPORT, SOURCE_TYPE_SOP, SOURCE_TYPE_PRODUCT_INFORMATION],
        use_vector=True,
        vector_only=True,
    )
    bucket: dict[str, list[dict[str, Any]]] = {}
    for hit in hits:
        _extract_numeric_candidates(hit, bucket)
    if any(token in analysis_type for token in ("이슬", "결로")):
        rows = bucket.get("heat_exchanger_temp", [])
        filtered: list[dict[str, Any]] = []
        for row in rows:
            try:
                value = float(str(row.get("value", "999")).replace(",", ""))
            except ValueError:
                continue
            if value <= 30:
                filtered.append(row)
        bucket["heat_exchanger_temp"] = filtered
    return bucket


def _merged_candidate_conditions(state: Mapping[str, Any], analysis_type: str, *, rag_enabled: bool = True) -> dict[str, list[dict[str, Any]]]:
    merged: dict[str, list[dict[str, Any]]] = {}
    canonical = canonical_analysis_type(analysis_type)
    for field_key, values in DEFAULT_CONDITION_CANDIDATES.get(canonical, {}).items():
        merged[field_key] = [{"value": value, "evidence": {}} for value in values]
    for field_key, rows in _rag_candidate_conditions(state, canonical, rag_enabled=rag_enabled).items():
        current = merged.setdefault(field_key, [])
        for row in rows:
            value = _line(row.get("value"))
            if not value or any(_line(item.get("value")) == value for item in current):
                continue
            current.insert(0, row)
        merged[field_key] = current[:4]
    return merged


def condition_recommendation_payload(raw_state: Mapping[str, Any], analysis_type: str, *, rag_enabled: bool = True) -> dict[str, Any]:
    """Build read-only condition recommendation rows and patch operations."""

    state = sanitize_state(raw_state if isinstance(raw_state, Mapping) else {})
    canonical = canonical_analysis_type(analysis_type)
    candidates = _merged_candidate_conditions(state, canonical, rag_enabled=rag_enabled)
    items: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    for field_key, rows in candidates.items():
        values = [_line(row.get("value")) for row in rows if isinstance(row, Mapping) and _line(row.get("value"))]
        if not values:
            continue
        label = CONDITION_FIELD_LABELS.get(field_key, field_key)
        unit = CONDITION_FIELD_UNITS.get(field_key, "")
        items.extend(
            {
                "field_key": field_key,
                "field_label": label,
                "value": value,
                "unit": unit,
            }
            for value in values
        )
        operations.append(
            {
                "op": "condition_values",
                "field_key": field_key,
                "path": f"conditions.fields.{field_key}.values",
                "values": values,
                "merge_strategy": "replace",
                "label": label,
                "confidence": "medium",
                "source": "condition_recommendation",
            }
        )
    return {
        "analysis_type": canonical,
        "items": items,
        "operations": operations,
        "count": len(items),
        "state_changed": False,
    }


def apply_analysis_type_selection(
    raw_state: Mapping[str, Any],
    analysis_type: str,
    *,
    rag_enabled: bool = True,
    inject_candidates: bool = True,
    assign_request_no: bool = True,
) -> dict[str, Any]:
    """Set analysis type and inject common candidate condition values."""

    state = (
        assign_request_no_if_missing(raw_state if isinstance(raw_state, Mapping) else {})
        if assign_request_no
        else sanitize_state(raw_state if isinstance(raw_state, Mapping) else {})
    )
    canonical = canonical_analysis_type(analysis_type)
    ensure_request_context(state)
    state[SECTION_REQUEST_CONTEXT]["analysis_type"] = canonical

    if inject_candidates:
        candidates = _merged_candidate_conditions(state, canonical, rag_enabled=rag_enabled)
        conditions = dict(state.get(SECTION_CONDITIONS, {}))
        updated_fields: list[Any] = []
        for field in conditions.get("fields", []):
            if not isinstance(field, Mapping):
                updated_fields.append(field)
                continue
            key = _clean(field.get("key"))
            next_field = dict(field)
            current_values = [row for row in next_field.get("values", []) if isinstance(row, Mapping) and row.get("status") == "provided"]
            if key in candidates and not current_values:
                next_field["values"] = [
                    _candidate_row(key, index, row.get("value"), evidence=row.get("evidence") if isinstance(row, Mapping) else None)
                    for index, row in enumerate(candidates[key], start=1)
                ]
            updated_fields.append(next_field)
        conditions["fields"] = updated_fields
        state[SECTION_CONDITIONS] = conditions
    return state_with_validation(state)


def candidate_condition_summary(raw_state: Mapping[str, Any]) -> dict[str, Any]:
    state = sanitize_state(raw_state if isinstance(raw_state, Mapping) else {})
    items: list[dict[str, Any]] = []
    for field in state.get(SECTION_CONDITIONS, {}).get("fields", []):
        if not isinstance(field, Mapping):
            continue
        for row in field.get("values", []):
            if not isinstance(row, Mapping) or row.get("source") != AI_SUGGESTED_SOURCE:
                continue
            items.append(
                {
                    "field_key": _clean(field.get("key")),
                    "field_label": _clean(field.get("label")) or _clean(field.get("key")),
                    "value": row.get("value"),
                    "approved": bool(row.get("approved", False)),
                    "note": _clean(row.get("note")),
                    "evidence_source": _clean(_as_mapping(row.get("evidence")).get("source_name")) if isinstance(row.get("evidence"), Mapping) else "",
                }
            )
    return {
        "count": len(items),
        "items": items,
        "requires_approval": bool(items),
    }


def approve_candidate_conditions(raw_state: Mapping[str, Any]) -> dict[str, Any]:
    """Mark AI-suggested condition candidates as user approved."""

    state = sanitize_state(deepcopy(raw_state if isinstance(raw_state, Mapping) else {}))
    conditions = dict(state.get(SECTION_CONDITIONS, {}))
    fields: list[Any] = []
    for field in conditions.get("fields", []):
        if not isinstance(field, Mapping):
            fields.append(field)
            continue
        next_field = dict(field)
        rows: list[Any] = []
        for row in next_field.get("values", []):
            if not isinstance(row, Mapping):
                rows.append(row)
                continue
            next_row = dict(row)
            if next_row.get("source") == AI_SUGGESTED_SOURCE:
                next_row["source"] = VALUE_SOURCE_USER
                next_row["note"] = "AI recommended candidate approved by user."
                next_row["candidate"] = False
                next_row["approved"] = True
            rows.append(next_row)
        next_field["values"] = rows
        fields.append(next_field)
    conditions["fields"] = fields
    state[SECTION_CONDITIONS] = conditions
    return state_with_validation(state)
