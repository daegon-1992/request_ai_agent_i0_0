"""Submission payload contract for final request review."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from .constants import APP_VERSION, STATE_SCHEMA_VERSION


EXPORT_CONTRACT_VERSION = "request_submission_v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_submission_contract(
    *,
    state: Mapping[str, Any],
    draft: Mapping[str, Any],
    final_review: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the final payload handed to a future export/submit layer."""

    case_matrix = _as_mapping(state.get("case_matrix"))
    review = _as_mapping(state.get("review"))
    validator = _as_mapping(review.get("validator"))
    draft_document = _as_mapping(draft.get("document"))
    evidence = _as_mapping(draft_document.get("evidence_summary"))

    return {
        "contract_version": EXPORT_CONTRACT_VERSION,
        "app_version": APP_VERSION,
        "schema_version": STATE_SCHEMA_VERSION,
        "created_at": _utc_now(),
        "submit_ready": bool(final_review.get("can_submit", False)),
        "source_authority": "structured_state_and_case_matrix_only",
        "state": deepcopy(dict(state)),
        "case_matrix": {
            "visible_columns": deepcopy(_as_list(case_matrix.get("visible_columns"))),
            "rows": deepcopy(_as_list(case_matrix.get("rows"))),
            "dropdown_options": deepcopy(_as_mapping(case_matrix.get("dropdown_options"))),
            "source_inputs": deepcopy(_as_mapping(case_matrix.get("source_inputs"))),
        },
        "draft_document": deepcopy(dict(draft_document)),
        "validator": deepcopy(dict(validator)),
        "submission": {
            "status": final_review.get("status", "blocked"),
            "can_submit": bool(final_review.get("can_submit", False)),
            "blocking_reasons": deepcopy(_as_list(final_review.get("blocking_reasons"))),
            "warnings": deepcopy(_as_list(final_review.get("warnings"))),
        },
        "supporting_evidence": {
            "usage": "sentence_support_only",
            "state_authority": "structured_state_only",
            "sources": deepcopy(_as_list(evidence.get("sources"))),
        },
    }
