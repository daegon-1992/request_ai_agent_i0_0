"""Final review and submission readiness pipeline."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from .draft_pipeline import build_request_draft
from .export_contract import build_submission_contract
from .rag_search import SOURCE_TYPE_NXI, SOURCE_TYPE_SOP, search_rag_documents
from .state import field_value
from .validator import state_with_validation


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _final_case_count(state: Mapping[str, Any]) -> int:
    case_matrix = _as_mapping(state.get("case_matrix"))
    return len(_as_list(case_matrix.get("rows")))


def _blocking_from_validation(validation: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in _as_list(validation.get("blocking")) if isinstance(item, Mapping)]


def _warnings_from_validation(validation: Mapping[str, Any], draft: Mapping[str, Any], state: Mapping[str, Any]) -> list[dict[str, Any]]:
    warnings = [dict(item) for item in _as_list(validation.get("warning")) if isinstance(item, Mapping)]
    for check in _as_list(draft.get("quality_checks")):
        if not isinstance(check, Mapping) or bool(check.get("passed", False)):
            continue
        warnings.append(
            {
                "severity": "warning",
                "code": _clean_text(check.get("code")) or "draft.quality_check_failed",
                "section": "review",
                "message": "Draft quality check needs attention.",
                "path": "review.draft.quality_checks",
                "action": _clean_text(check.get("action")) or "Review draft wording.",
                "evidence": "derived_draft",
            }
        )
    warnings.extend(_rag_advisory_warnings(state))
    return warnings


def _rag_review_query(state: Mapping[str, Any]) -> str:
    overview = _as_mapping(state.get("analysis_overview"))
    geometry = _as_mapping(state.get("geometry"))
    products: list[str] = []
    for row in _as_list(geometry.get("products")):
        products.append(_clean_text(field_value(row, "")))
    parts = [
        "최종 해석 의뢰 검토 제출 전 확인 기준",
        _clean_text(field_value(overview.get("analysis_type"), "")),
        _clean_text(field_value(overview.get("purpose"), "")),
        _clean_text(field_value(overview.get("goal"), "")),
        " ".join(item for item in products if item),
        "SOP NXI 필수 조건 산출물 case matrix",
    ]
    return " ".join(part for part in parts if part)


def _rag_advisory_warnings(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    query = _rag_review_query(state)
    if not query:
        return []
    hits = search_rag_documents(query, top_k=3, source_types=[SOURCE_TYPE_SOP, SOURCE_TYPE_NXI], use_vector=False)
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        source = _clean_text(hit.get("source"))
        location = _clean_text(hit.get("location"))
        key = f"{source}|{location}"
        if key in seen:
            continue
        seen.add(key)
        warnings.append(
            {
                "severity": "warning",
                "code": "rag_advisory.reference_check",
                "section": "review",
                "message": "RAG reference found a related SOP/NXI snippet for final human review.",
                "path": "review.final_review.warnings",
                "action": "Check the cited SOP/NXI source if this request is near submission.",
                "evidence": "rag_read_only",
                "source_type": _clean_text(hit.get("source_type")),
                "source_name": source,
                "source_location": location,
                "source_snippet": _clean_text(hit.get("content"))[:260],
                "state_authority": "structured_state_and_case_matrix_only",
            }
        )
    return warnings


def _ensure_final_case_blocker(blocking: list[dict[str, Any]], final_case_count: int) -> None:
    if final_case_count > 0:
        return
    if any(item.get("code") == "case_matrix.no_included_cases" for item in blocking):
        return
    blocking.append(
        {
            "severity": "blocking",
            "code": "final_review.final_case_count_missing",
            "section": "case_matrix",
            "message": "No manual Case row is available for submission.",
            "path": "case_matrix.rows",
            "action": "Add a Case and map its geometry and active conditions.",
            "evidence": "structured_state",
        }
    )


def _edit_guidance(blocking: list[dict[str, Any]]) -> list[dict[str, str]]:
    guidance: list[dict[str, str]] = []
    for item in blocking:
        path = _clean_text(item.get("path")) or _clean_text(item.get("section"))
        guidance.append(
            {
                "path": path,
                "section": _clean_text(item.get("section")),
                "field_key": _clean_text(item.get("field_key")),
                "field_label": _clean_text(item.get("field_label")),
                "message": _clean_text(item.get("message")),
                "action": _clean_text(item.get("action")) or "Update the indicated input field.",
                "ui_anchor": _ui_anchor(path),
            }
        )
    return guidance


def _ui_anchor(path: str) -> str:
    if path.startswith("basic_info."):
        return "기본 정보"
    if path.startswith("analysis_overview."):
        return "해석 개요"
    if path.startswith("geometry."):
        return "형상/모델 정보"
    if path.startswith("conditions."):
        return "해석조건"
    if path.startswith("case_matrix."):
        return "Case Matrix Preview"
    return "최종 검토"


def _draft_for_final_review(
    state: Mapping[str, Any],
    draft_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    draft = draft_payload if isinstance(draft_payload, Mapping) else _as_mapping(_as_mapping(state.get("review")).get("draft"))
    if draft.get("status") == "ready" and _as_mapping(draft.get("document")).get("markdown"):
        return dict(draft)
    return build_request_draft(state)


def build_final_review(
    raw_state: Mapping[str, Any],
    *,
    draft_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build final submission readiness using structured state and case matrix only."""

    state = state_with_validation(raw_state if isinstance(raw_state, Mapping) else {})
    validation = _as_mapping(_as_mapping(state.get("review")).get("validator"))
    summary = _as_mapping(validation.get("summary"))
    draft = _draft_for_final_review(state, draft_payload)

    final_case_count = _final_case_count(state)
    blocking = _blocking_from_validation(validation)
    _ensure_final_case_blocker(blocking, final_case_count)
    warnings = _warnings_from_validation(validation, draft, state)
    validator_can_submit = bool(summary.get("can_submit", False))
    can_submit = validator_can_submit and final_case_count > 0 and not blocking
    status = "submittable" if can_submit else "blocked"

    final_validator = {
        "blocking": blocking,
        "warning": warnings,
        "info": deepcopy(_as_list(validation.get("info"))),
        "summary": {
            "can_submit": can_submit,
            "validator_can_submit": validator_can_submit,
            "final_case_count": final_case_count,
            "blocking_count": len(blocking),
            "warning_count": len(warnings),
            "decision_basis": "structured_state_and_case_matrix_only",
        },
    }
    final_review: dict[str, Any] = {
        "status": status,
        "can_submit": can_submit,
        "reviewed_at": _utc_now(),
        "decision_basis": "structured_state_and_case_matrix_only",
        "blocking_reasons": blocking,
        "warnings": warnings,
        "edit_guidance": _edit_guidance(blocking),
        "final_validator": final_validator,
        "draft": draft,
        "final_payload": None,
    }
    if can_submit:
        final_review["final_payload"] = build_submission_contract(
            state=state,
            draft=draft,
            final_review=final_review,
        )
    return final_review


def state_with_final_review(
    raw_state: Mapping[str, Any],
    *,
    draft_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a validated state copy with final review and submission status populated."""

    state = state_with_validation(raw_state if isinstance(raw_state, Mapping) else {})
    final_review = build_final_review(state, draft_payload=draft_payload)
    state["review"]["draft"] = deepcopy(final_review["draft"])
    state["review"]["final_review"] = deepcopy(final_review)
    state["review"]["submission"] = {
        "status": final_review["status"],
        "can_submit": final_review["can_submit"],
        "blocking_reasons": [item.get("code", "") for item in final_review["blocking_reasons"]],
        "warning_reasons": [item.get("code", "") for item in final_review["warnings"]],
        "edit_guidance": deepcopy(final_review["edit_guidance"]),
    }
    return state
