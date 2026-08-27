"""Flask app for the request assistant."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from secrets import token_urlsafe
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4

from flask import Flask, jsonify, request, send_file, session

from .agent_context import build_agent_context
from .agent_decision import (
    ANALYSIS_TYPE_FIELD_ID,
    AgentDecision,
    AgentDecisionError,
    LLM_FAILURE_MESSAGE,
    decide_agent_action,
    operations_match_write_contract,
    proposal_changes,
    validate_agent_decision,
    writable_active_field_ids,
)
from .agent_next_question import plan_next_question
from .agent_next_question_loop import answer_planning_events, apply_next_question, synchronize_active_field
from .agent_write_contract import build_agent_write_contract
from .analysis_type_recommender import (
    apply_analysis_type_selection,
    approve_candidate_conditions,
    candidate_condition_summary,
    canonical_analysis_type,
    condition_recommendation_payload,
    recommend_analysis_types,
)
from .case_matrix_action import CaseMatrixActionService
from .preview_action import PreviewActionService
from .rag_guidance_action import RagGuidanceActionService
from .validation_action import ValidationActionService
from .analysis_type_master import get_analysis_result_guidance
from .chat_patch import (
    apply_patch_operations,
    proposal_from_operations,
)
from .config import env_flag
from .condition_fieldsets import build_condition_fieldset, get_active_condition_fields
from .conversation_store import ConversationCapacityError, ConversationNotFoundError, ConversationStateError, ConversationStore
from .constants import APP_VERSION, DISABLED_ANALYSIS_TYPE_OPTIONS, ENABLED_ANALYSIS_TYPE_OPTIONS, SECTION_ANALYSIS_OVERVIEW, SECTION_BASIC_INFO, SECTION_REQUEST_CONTEXT, VALUE_SOURCE_SYSTEM, VALUE_SOURCE_USER
from .demo_analysis_type import apply_demo_analysis_type_state, is_demo_analysis_type
from .demo_db_store import upload_submission_to_demo_db
from .draft_pipeline import build_request_draft
from .embedding_runtime import embedding_status
from .heat_exchanger_catalog import build_heat_exchanger_catalog_payload
from .llm_client import extract_form_patch_with_llm, llm_status, synthesize_general_chat_answer, synthesize_rag_answer, synthesize_request_draft
from .orchestrator_extraction_tool import Extractor
from .orchestrator_audit import RuntimeAuditLog
from .orchestrator_service import (
    OrchestratorFailureResult,
    OrchestratorClarificationResult,
    OrchestratorMessageInput,
    OrchestratorProposalResult,
    OrchestratorReadOnlyResult,
    OrchestratorService,
)
from .product_hierarchy import build_product_hierarchy_payload
from .proposal_store import ProposalNotFoundError, ProposalService, ProposalStore, ProposalValidationError
from .rag_qa import looks_like_current_input_question, run_rag_qa, summarize_current_state
from .review_pipeline import build_final_review, state_with_final_review
from .request_state_store import RequestNotFoundError, RequestStateSnapshot, RequestStateStore, RequestVersionConflictError
from .schema import ANALYSIS_OVERVIEW_SPECS, CONDITION_FIELD_SPECS, get_public_schema
from .state import apply_analysis_overview_defaults, create_initial_state, decision_use_is_complete, field_value, generate_request_no, make_field
from .ui import HTML_TEMPLATE
from .validator import state_with_validation
from .word_export import DOCX_MIMETYPE, build_word_docx, word_filename
from .workflow_machine import ConversationWorkflowMachine, WorkflowEvent, WorkflowEventType


STAGE_NAME = "stage09_condition_state_progress_20260630"
PROPOSAL_SOURCE_SECTIONS = {
    "original_fields": ("basic_info", "analysis_overview", "geometry"),
    "analysis_type": (SECTION_REQUEST_CONTEXT,),
    "condition_snapshot": (SECTION_REQUEST_CONTEXT, "conditions"),
    "case_matrix": ("case_matrix",),
}
PROPOSAL_STALE_LABELS = {
    "original_fields": "원본 입력 Field가 변경되었습니다.",
    "analysis_type": "선택한 해석유형이 변경되었습니다.",
    "condition_snapshot": "해석조건 Snapshot이 변경되었습니다.",
    "case_matrix": "Case Matrix 매핑이 변경되었습니다.",
}
LLM_CHAT_INTENTS = {"patch", "general_qa", "rag_qa", "current_input", "needs_clarification"}
FEATURE_LOCKS = {
    "ppt_io": False,
    "image_capture_input": False,
    "preview_screen": False,
    "word_export": True,
    "dbms_integration": False,
    "vision_ai": False,
    "analysis_type_recommendation": False,
    "condition_recommendation": False,
}
FEATURE_DISABLED_MESSAGE = "This feature is disabled in h5_v0."



def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _metadata(raw_state: Mapping[str, Any] | None) -> Mapping[str, Any]:
    state = raw_state if isinstance(raw_state, Mapping) else {}
    return _as_mapping(state.get("metadata"))


def _rag_enabled(raw_state: Mapping[str, Any] | None) -> bool:
    value = _metadata(raw_state).get("rag_enabled", False)
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().lower()
    if not token:
        return False
    return token not in {"0", "false", "no", "off"}


def _rag_scope(raw_state: Mapping[str, Any] | None) -> str:
    return str(_metadata(raw_state).get("rag_scope", "LG CFD Reports 2025 해석보고서") or "LG CFD Reports 2025 해석보고서")


def _rag_source_types(raw_state: Mapping[str, Any] | None) -> list[str]:
    scope = _rag_scope(raw_state)
    if "LG CFD Reports 2025" in scope:
        return ["similar_report"]
    return ["similar_report", "sop", "nxi", "theory_basis", "product_information"]


def _request_no(raw_state: Mapping[str, Any] | None) -> str:
    state = raw_state if isinstance(raw_state, Mapping) else {}
    metadata = _as_mapping(state.get("metadata"))
    basic = _as_mapping(state.get("basic_info"))
    return str(metadata.get("request_no") or field_value(basic.get("request_no"), "") or "")


def _download_metadata(state: Mapping[str, Any], *, can_submit: bool) -> dict[str, Any]:
    filename = word_filename()
    return {
        "auto_download": False,
        "download_url": "",
        "retry_url": "",
        "filename": filename,
        "content_source": "preview_document",
        "same_as_preview": False,
        "disabled": True,
        "message": FEATURE_DISABLED_MESSAGE,
    }


def _disabled_feature_payload(feature: str) -> tuple[Any, int]:
    return (
        jsonify(
            {
                "ok": False,
                "version": APP_VERSION,
                "stage": STAGE_NAME,
                "feature": feature,
                "message": FEATURE_DISABLED_MESSAGE,
                "state_changed": False,
            }
        ),
        403,
    )


def _disabled_db_upload() -> dict[str, Any]:
    return {
        "enabled": False,
        "attempted": False,
        "status": "disabled",
        "message": FEATURE_DISABLED_MESSAGE,
    }

def _db_upload_message(db_upload: Mapping[str, Any]) -> str:
    if not db_upload.get("enabled"):
        return ""
    status = str(db_upload.get("status", "") or "")
    if status == "saved":
        return (
            f"DB 업로드 완료: request_no={db_upload.get('request_no', '')}, "
            f"id={db_upload.get('db_id', '')}, cases={db_upload.get('case_count', 0)}"
        )
    if status in {"failed", "unconfigured"}:
        return f"DB 업로드 실패: {db_upload.get('message', '')}"
    if status == "skipped":
        return f"DB 업로드 생략: {db_upload.get('message', '')}"
    return ""


def _rag_disabled_qa(question: str) -> dict[str, Any]:
    return {
        "ok": True,
        "question": question,
        "question_type": "rag_disabled",
        "query": "",
        "sources": [],
        "hit_count": 0,
        "source_types_searched": [],
        "confidence": "low",
        "limitations": ["RAG Off 상태이므로 문서 검색을 수행하지 않았습니다."],
        "answer_text": "RAG Off · 문서 검색 없음",
        "read_only": True,
        "state_changed": False,
    }


def _rag_error_qa(question: str, exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "question": question,
        "question_type": "rag_error",
        "query": "",
        "sources": [],
        "hit_count": 0,
        "source_types_searched": [],
        "confidence": "low",
        "limitations": ["RAG search failed; no document result was used."],
        "answer_text": "문서 검색 중 오류가 발생했습니다. 입력 state는 변경되지 않았습니다.",
        "read_only": True,
        "state_changed": False,
        "error": str(exc),
    }


def _run_rag_qa_read_only(question: str, *, state: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Run an enabled RAG query without allowing errors to escape as mutations."""

    try:
        return run_rag_qa(question, state=state, **kwargs)
    except Exception as exc:  # pragma: no cover - dependency/network dependent
        return _rag_error_qa(question, exc)


def _current_input_qa(state: Mapping[str, Any]) -> dict[str, Any]:
    """Render an LLM-classified current-input question from structured state."""

    summary = summarize_current_state(state)
    overview = _as_mapping(summary.get("analysis_overview"))
    geometry = _as_mapping(summary.get("geometry"))
    validation = _as_mapping(summary.get("validation"))
    products = ", ".join(_as_list(geometry.get("products"))) or "-"
    return {
        "answer_text": (
            "현재 입력 상태입니다.\n"
            f"- 해석 유형: {overview.get('analysis_type') or '-'}\n"
            f"- 제품: {products}\n"
            f"- 제출 가능: {validation.get('can_submit', False)}"
        ),
        "summary": summary,
        "read_only": True,
        "state_changed": False,
    }


def _derive_state(raw_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return state_with_validation(raw_state if isinstance(raw_state, Mapping) else create_initial_state())


def _versioned_request_payload(snapshot: RequestStateSnapshot) -> dict[str, Any]:
    """Additive response envelope; legacy state payloads remain unchanged."""

    return {
        "ok": True,
        "version": APP_VERSION,
        "stage": STAGE_NAME,
        "request_id": snapshot.request_id,
        "request_version": snapshot.version,
        "state": snapshot.state,
    }


def _conversation_payload(snapshot: Any) -> dict[str, Any]:
    """Render only the Conversation projection; Request/Proposal remain separate."""

    return {
        "ok": True,
        "conversation_id": snapshot.conversation_id,
        "request_id": snapshot.request_id,
        "workflow_status": snapshot.workflow_status,
        "paused": snapshot.paused,
        "status": snapshot.status,
        "question_history": snapshot.question_history,
        "summary": snapshot.summary,
        "conversation_version": snapshot.version,
        "proposal_id": snapshot.pending_proposal_id,
    }


def _conversation_request_payload(*, allowed_keys: set[str]) -> tuple[Mapping[str, Any] | None, tuple[Any, int] | None]:
    """Accept the small reference-only Conversation API input surface."""

    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, Mapping) or set(payload) - allowed_keys:
        return None, (jsonify({"ok": False, "error": "invalid_conversation_payload"}), 400)
    return payload, None


_ORCHESTRATOR_MESSAGE_KEYS = {
    "conversation_id",
    "message",
    "intent",
    "extraction_payload",
    "extraction_metadata",
}


def _orchestrator_message_input() -> tuple[OrchestratorMessageInput | None, tuple[Any, int] | None]:
    """Build only the public message DTO; all authority remains server-side."""

    payload = request.get_json(silent=True)
    if not isinstance(payload, Mapping) or set(payload) - _ORCHESTRATOR_MESSAGE_KEYS:
        return None, (
            jsonify(
                {
                    "ok": False,
                    "kind": "failure",
                    "error": "invalid_orchestrator_message_payload",
                    "reasons": ["invalid_orchestrator_message_payload"],
                    "state_changed": False,
                    "read_only": True,
                }
            ),
            400,
        )
    return (
        OrchestratorMessageInput(
            conversation_id=payload.get("conversation_id"),
            message=payload.get("message"),
            intent=payload.get("intent"),
            extraction_payload=payload.get("extraction_payload"),
            extraction_metadata=payload.get("extraction_metadata"),
        ),
        None,
    )


def _planner_decision_payload(decision: Any) -> dict[str, Any] | None:
    if decision is None:
        return None
    if not is_dataclass(decision):
        return {"kind": "planner_failure", "code": "invalid_planner_result", "fields": []}
    return asdict(decision)


def _orchestrator_failure_status(code: str) -> int:
    if code in {
        "invalid_service_input",
        "invalid_conversation_id",
        "invalid_message",
        "invalid_extraction_payload",
        "invalid_extraction_metadata",
    }:
        return 400
    if code == "conversation_read_failed":
        return 404
    if code in {
        "conversation_closed",
        "conversation_paused",
        "workflow_paused",
        "workflow_terminal",
        "approval_wait_required",
        "invalid_workflow_event",
        "invalid_workflow_state",
        "proposal_reference_mismatch",
    }:
        return 409
    return 503


def _state_from_request(default_state: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, Mapping):
        return default_state
    state = payload.get("state", payload)
    return state if isinstance(state, Mapping) else default_state


def _payload_mapping() -> Mapping[str, Any]:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, Mapping) else {}


def _assign_request_no_at_context_confirm(state: dict[str, Any]) -> dict[str, Any]:
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


def _context_confirm_state(raw_state: Mapping[str, Any], raw_context: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    state = _derive_state(raw_state)
    current_context = dict(state.get(SECTION_REQUEST_CONTEXT) if isinstance(state.get(SECTION_REQUEST_CONTEXT), Mapping) else {})
    for key in ("business_unit", "product_group", "platform", "analysis_type", "operation_mode"):
        value = _clean_text(raw_context.get(key))
        if value:
            current_context[key] = value
    missing = [key for key in ("business_unit", "product_group", "platform", "analysis_type") if not _clean_text(current_context.get(key))]
    if missing:
        raise ValueError("missing_context:" + ",".join(missing))
    analysis_type = _clean_text(current_context.get("analysis_type"))
    if analysis_type in DISABLED_ANALYSIS_TYPE_OPTIONS:
        raise ValueError("disabled_analysis_type:" + analysis_type)
    if analysis_type not in ENABLED_ANALYSIS_TYPE_OPTIONS:
        raise ValueError("unsupported_analysis_type:" + analysis_type)

    fieldset = build_condition_fieldset(current_context)
    current_context["analysis_type"] = _clean_text(fieldset.get("analysis_type")) or _clean_text(current_context.get("analysis_type"))
    current_context["operation_mode"] = _clean_text(fieldset.get("operation_mode"))
    current_context["condition_fieldset_key"] = _clean_text(fieldset.get("key"))
    current_context["condition_fieldset_snapshot"] = deepcopy(_as_list(fieldset.get("groups")))
    current_context["context_locked"] = True
    state[SECTION_REQUEST_CONTEXT] = current_context

    state = apply_analysis_overview_defaults(state)
    state = _assign_request_no_at_context_confirm(state)
    return _derive_state(state), fieldset


def _context_fieldset_state(raw_state: Mapping[str, Any], raw_context: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    state = _derive_state(raw_state)
    current_context = dict(state.get(SECTION_REQUEST_CONTEXT) if isinstance(state.get(SECTION_REQUEST_CONTEXT), Mapping) else {})
    for key in ("business_unit", "product_group", "platform", "analysis_type", "operation_mode"):
        value = _clean_text(raw_context.get(key))
        if value:
            current_context[key] = value
    missing = [key for key in ("business_unit", "product_group", "platform", "analysis_type") if not _clean_text(current_context.get(key))]
    if missing:
        raise ValueError("missing_context:" + ",".join(missing))
    analysis_type = _clean_text(current_context.get("analysis_type"))
    if analysis_type in DISABLED_ANALYSIS_TYPE_OPTIONS:
        raise ValueError("disabled_analysis_type:" + analysis_type)
    if analysis_type not in ENABLED_ANALYSIS_TYPE_OPTIONS:
        raise ValueError("unsupported_analysis_type:" + analysis_type)
    fieldset = build_condition_fieldset(current_context)
    current_context["analysis_type"] = _clean_text(fieldset.get("analysis_type")) or _clean_text(current_context.get("analysis_type"))
    current_context["operation_mode"] = _clean_text(fieldset.get("operation_mode"))
    current_context["condition_fieldset_key"] = _clean_text(fieldset.get("key"))
    current_context["condition_fieldset_snapshot"] = deepcopy(_as_list(fieldset.get("groups")))
    current_context["context_locked"] = current_context.get("context_locked") is True
    state[SECTION_REQUEST_CONTEXT] = current_context
    return _derive_state(state), fieldset
STAGE_KEYS = ("analysis_overview", "geometry", "conditions", "case_matrix")
STAGE_LABELS = {
    "analysis_overview": "해석 요청 내용",
    "geometry": "형상/모델 정보",
    "conditions": "해석조건",
    "case_matrix": "Case Matrix",
}
ANALYSIS_PROGRESS_SPECS = tuple(spec for spec in ANALYSIS_OVERVIEW_SPECS if spec.track_progress)
ANALYSIS_FIELD_LABELS = {spec.key: spec.label for spec in ANALYSIS_PROGRESS_SPECS}
CONDITION_FIELD_LABELS = {spec.key: spec.label for spec in CONDITION_FIELD_SPECS}


def _value_is_filled(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    return _clean_text(value) != ""


def _field_is_filled(field: Any) -> bool:
    if not isinstance(field, Mapping):
        return _value_is_filled(field)
    if _clean_text(field.get("status")) != "provided":
        return False
    return _value_is_filled(field_value(field, ""))


def _field_is_user_provided(field: Any) -> bool:
    if not _field_is_filled(field):
        return False
    if not isinstance(field, Mapping):
        return True
    return _clean_text(field.get("source")) == VALUE_SOURCE_USER


def _rows_have_user_value(rows: Any) -> bool:
    return any(_field_is_user_provided(row) for row in _as_list(rows))


def _condition_progress_required_level(field: Mapping[str, Any]) -> str:
    required_level = _clean_text(field.get("required_level"))
    if required_level in {"required", "conditional_required", "optional_non_blocking"}:
        return required_level
    return "required" if bool(field.get("required", False)) else "optional_non_blocking"


def _stage_row(key: str, label: str, total: int, filled: int, missing_fields: list[str]) -> dict[str, Any]:
    total = max(int(total), 0)
    filled = max(min(int(filled), total), 0)
    percent = 100 if total == 0 else round(filled / max(total, 1) * 100)
    return {
        "key": key,
        "label": label,
        "filled_count": filled,
        "total_count": total,
        "completion_percent": percent,
        "is_complete": total > 0 and filled >= total,
        "missing_fields": missing_fields,
    }


def _stage_progress(raw_state: Mapping[str, Any]) -> dict[str, Any]:
    state = raw_state if isinstance(raw_state, Mapping) else {}
    overview = _as_mapping(state.get("analysis_overview"))
    geometry = _as_mapping(state.get("geometry"))
    conditions = _as_mapping(state.get("conditions"))

    overview_total = len(ANALYSIS_FIELD_LABELS)
    overview_filled = 0
    overview_missing: list[str] = []
    for key, label in ANALYSIS_FIELD_LABELS.items():
        is_complete = decision_use_is_complete(overview.get(key)) if key == "decision_use" else _field_is_user_provided(overview.get(key))
        if is_complete:
            overview_filled += 1
        else:
            overview_missing.append(label)

    geometry_total = 1 + len(geometry.get("comparison_products", []) if isinstance(geometry.get("comparison_products"), list) else [])
    geometry_filled = 0
    geometry_missing: list[str] = []
    if _field_is_user_provided(_as_mapping(geometry.get("base_product")).get("drawing_no")):
        geometry_filled += 1
    else:
        geometry_missing.append("기준 제품 도면번호")
    for index, product in enumerate(geometry.get("comparison_products", []) if isinstance(geometry.get("comparison_products"), list) else [], start=1):
        product_map = _as_mapping(product)
        if _field_is_user_provided(product_map.get("drawing_no")) and _field_is_user_provided(product_map.get("difference_from_base")):
            geometry_filled += 1
        else:
            geometry_missing.append(f"비교 제품 {index}")

    request_context = _as_mapping(state.get(SECTION_REQUEST_CONTEXT))
    if request_context.get("context_locked") is not True:
        condition_fields = []
        conditions_total = 1
        conditions_filled = 0
        conditions_missing = ["request_context"]
    else:
        condition_fields = get_active_condition_fields(state)
        conditions_filled = 0
        conditions_missing: list[str] = []
        required_condition_fields: list[Mapping[str, Any]] = []
        conditional_condition_groups: dict[str, list[Mapping[str, Any]]] = {}
        for field in condition_fields:
            required_level = _condition_progress_required_level(field)
            if required_level == "optional_non_blocking":
                continue
            if required_level == "conditional_required":
                group_key = _clean_text(field.get("conditional_group")) or _clean_text(field.get("key"))
                conditional_condition_groups.setdefault(group_key, []).append(field)
                continue
            required_condition_fields.append(field)

        for field in required_condition_fields:
            label = _clean_text(field.get("label")) or CONDITION_FIELD_LABELS.get(_clean_text(field.get("key")), _clean_text(field.get("key")))
            if _rows_have_user_value(field.get("values")):
                conditions_filled += 1
            else:
                conditions_missing.append(label)

        for fields in conditional_condition_groups.values():
            label_field = fields[0]
            label = _clean_text(label_field.get("label")) or CONDITION_FIELD_LABELS.get(
                _clean_text(label_field.get("key")), _clean_text(label_field.get("key"))
            )
            if any(_rows_have_user_value(field.get("values")) for field in fields):
                conditions_filled += 1
            else:
                conditions_missing.append(label)

        conditions_total = len(required_condition_fields) + len(conditional_condition_groups)

    matrix = _as_mapping(state.get("case_matrix"))
    matrix_rows = _as_list(matrix.get("rows"))
    matrix_columns = _as_list(matrix.get("visible_columns"))
    active_case_keys = [
        _clean_text(column.get("key"))
        for column in matrix_columns
        if _as_mapping(column).get("kind") == "condition" and _clean_text(_as_mapping(column).get("key"))
    ]
    matrix_total = max(len(matrix_rows), 1)
    matrix_filled = 0
    matrix_missing: list[str] = []
    for index, raw_row in enumerate(matrix_rows, start=1):
        row = _as_mapping(raw_row)
        values = _as_mapping(row.get("condition_values"))
        if _clean_text(row.get("geometry_id")) and all(_clean_text(values.get(key)) for key in active_case_keys):
            matrix_filled += 1
        else:
            matrix_missing.append(f"Case {index}")
    if not matrix_rows:
        matrix_missing.append("Case 추가")

    stages = {
        "analysis_overview": _stage_row("analysis_overview", STAGE_LABELS["analysis_overview"], overview_total, overview_filled, overview_missing),
        "geometry": _stage_row("geometry", STAGE_LABELS["geometry"], geometry_total, geometry_filled, geometry_missing),
        "conditions": _stage_row("conditions", STAGE_LABELS["conditions"], conditions_total, conditions_filled, conditions_missing),
        "case_matrix": _stage_row("case_matrix", STAGE_LABELS["case_matrix"], matrix_total, matrix_filled, matrix_missing),
    }
    return {
        "stages": stages,
        "order": list(STAGE_KEYS),
        "all_complete": all(stages[key]["is_complete"] for key in STAGE_KEYS),
        "remaining_stages": [stages[key] for key in STAGE_KEYS if not stages[key]["is_complete"]],
    }


def _response_payload(state: Mapping[str, Any], *, timestamp_key: str) -> dict[str, Any]:
    progress = _stage_progress(state)
    return {
        "ok": True,
        "version": APP_VERSION,
        "stage": STAGE_NAME,
        timestamp_key: _utc_now(),
        "state": state,
        "stage_progress": progress,
        "case_matrix": state.get("case_matrix", {}),
        "validation": state.get("review", {}).get("validator", {}),
        "draft": state.get("review", {}).get("draft", {}),
        "final_review": state.get("review", {}).get("final_review", {}),
        "submission": state.get("review", {}).get("submission", {}),
        "candidate_conditions": candidate_condition_summary(state),
    }


def _response_payload_with_notifications(state: Mapping[str, Any], *, timestamp_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    next_state, notifications = _progress_notifications(state)
    response = _response_payload(next_state, timestamp_key=timestamp_key)
    response["chat_notifications"] = notifications
    return response, next_state


def _proposal_from_request(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    proposal = payload.get("proposal")
    return proposal if isinstance(proposal, Mapping) else {}


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _proposal_source_fingerprints(state: Mapping[str, Any]) -> dict[str, str]:
    context = _as_mapping(state.get(SECTION_REQUEST_CONTEXT))
    conditions = _as_mapping(state.get("conditions"))
    matrix = _as_mapping(state.get("case_matrix"))
    sources = {
        "original_fields": {key: state.get(key, {}) for key in PROPOSAL_SOURCE_SECTIONS["original_fields"]},
        "analysis_type": {"analysis_type": context.get("analysis_type", "")},
        "condition_snapshot": {
            "condition_fieldset_snapshot": context.get("condition_fieldset_snapshot", []),
            "condition_sets": conditions.get("condition_sets", []),
        },
        "case_matrix": {
            key: matrix.get(key)
            for key in ("rows", "visible_columns", "dropdown_options")
        },
    }
    return {key: _fingerprint(value) for key, value in sources.items()}


def _stamp_proposal(proposal: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    stamped = dict(proposal)
    sources = _proposal_source_fingerprints(state)
    stamped["proposal_context"] = {"source_fingerprints": sources}
    return stamped


def _proposal_stale_reasons(proposal: Mapping[str, Any], state: Mapping[str, Any]) -> list[str]:
    saved = _as_mapping(_as_mapping(proposal.get("proposal_context")).get("source_fingerprints"))
    if not saved:
        return ["제안의 기준 상태를 확인할 수 없습니다."]
    current = _proposal_source_fingerprints(state)
    return [PROPOSAL_STALE_LABELS[key] for key in PROPOSAL_STALE_LABELS if saved.get(key) != current.get(key)]


def _store_pending_proposal(proposal: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    """Stamp a proposal carried by the requesting browser, without server storage."""

    return _stamp_proposal(proposal, state)


def _chat_requested_mode(payload: Mapping[str, Any]) -> str:
    raw = str(payload.get("mode", "auto") or "auto").strip().lower()
    return raw if raw in {"auto", "patch", "rag"} else "auto"


def _looks_like_question(message: str) -> bool:
    lowered = str(message or "").strip().lower()
    return any(
        token in lowered
        for token in (
            "?", "？", "알려줘", "뭐야", "뭐지", "뭘", "무엇", "어떤", "어떻게", "왜",
            "의미", "설명", "차이", "필요", "가능", "방법", "인가", "인가요", "나요", "까요",
            "요약해줘", "summary",
        )
    )


def _looks_like_edit_intent(message: str) -> bool:
    lowered = str(message or "").strip().lower()
    return any(token in lowered for token in ("입력", "설정", "수정", "변경", "바꿔", "추가", "넣어", "제외", "포함", "set", "change", "update", "add"))


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    lowered = _clean_text(text).lower()
    return any(token.lower() in lowered for token in tokens)


def _operation_value_text(operation: Mapping[str, Any]) -> str:
    if operation.get("op") in {"list_values", "condition_values", "append_unique", "remove_list_values"}:
        value_text = ", ".join(_clean_text(item) for item in _as_list(operation.get("values")) if _clean_text(item))
        value_count = int(operation.get("value_count") or 0)
        if value_count > 1:
            return f"{value_text} ({value_count}개 값으로 해석했습니다)"
        return value_text
    value = operation.get("value")
    if isinstance(value, bool):
        return "예" if value else "아니오"
    return _clean_text(value)


def _proposal_confirmation_text(proposal: Mapping[str, Any]) -> str:
    operations = [op for op in _as_list(proposal.get("operations")) if isinstance(op, Mapping)]
    if not operations:
        questions = [_clean_text(item) for item in _as_list(proposal.get("questions")) if _clean_text(item)]
        return "\n".join(questions) if questions else "의뢰서에 반영할 명확한 필드와 값을 찾지 못했습니다."
    lines = ["입력하신 내용을 의뢰서 항목으로 해석했습니다.", ""]
    for operation in operations:
        label = _clean_text(operation.get("label")) or _clean_text(operation.get("path")) or _clean_text(operation.get("field_key"))
        value = _operation_value_text(operation)
        if label and value:
            lines.append(f"- {label}: {value}")
    warnings = [_clean_text(item) for item in _as_list(proposal.get("warnings")) if _clean_text(item)]
    if warnings:
        lines.append("")
        lines.extend(f"주의: {item}" for item in warnings)
    lines.append("")
    lines.append("의뢰서에 반영할까요?")
    return "\n".join(lines)


def _missing_items_answer(state: Mapping[str, Any]) -> str:
    derived = _derive_state(state)
    progress = _stage_progress(derived)
    if progress.get("all_complete"):
        return "현재 해석 개요, 형상/모델 정보, 해석조건 단계의 빈 칸이 모두 채워졌습니다. 해석 의뢰 완성 여부를 확인하면 됩니다."
    analysis_type = _clean_text(_as_mapping(derived.get(SECTION_REQUEST_CONTEXT)).get("analysis_type"))
    lines = ["현재 의뢰서를 완성하려면 아래 항목을 보완해야 합니다."]
    if analysis_type:
        lines.append(f"현재 해석유형: {analysis_type}")
    lines.append("")
    for key in STAGE_KEYS:
        stage = _as_mapping(_as_mapping(progress.get("stages")).get(key))
        missing = [_clean_text(item) for item in _as_list(stage.get("missing_fields")) if _clean_text(item)]
        if not missing:
            continue
        lines.append(f"{stage.get('label', key)}")
        lines.extend(f"- {item}" for item in missing)
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _field_list_text(fields: list[str], *, max_items: int = 4) -> str:
    clean = [_clean_text(item) for item in fields if _clean_text(item)]
    if not clean:
        return "없음"
    head = clean[:max_items]
    suffix = " 등" if len(clean) > max_items else ""
    return ", ".join(head) + suffix


def _condition_example_text() -> str:
    return "예: 작동유체 Air, Fan RPM 780, Room 온도 27도, Room 상대습도 78%처럼 입력할 수 있습니다."


STAGE_WRITING_GUIDES: dict[str, dict[str, Any]] = {
    "analysis_overview": {
        "description": "해석 개요는 왜 이 해석을 의뢰하는지와 결과로 무엇을 확인하려는지 정리하는 단계입니다.",
        "examples": [
            ("해석을 요청하게 된 배경", "예: 토출부 주변에 이슬맺힘이 반복되어 원인 검토가 필요합니다."),
            ("해석으로 확인하고 싶은 내용", "예: 이슬맺힘 발생 원인과 개선안별 차이를 확인하고 싶습니다."),
        ],
    },
    "geometry": {
        "description": "형상/모델 정보는 어떤 제품과 부품 형상으로 계산할지 정하는 단계입니다.",
        "examples": [
            ("해석 대상 제품", "예: ABQ30014402, MBN66569202처럼 여러 개를 입력할 수 있습니다."),
            ("부품 변경 있음", "예: 부품 변경 있음 또는 없음"),
            ("기존 부품(Base)", "예: BASE-DUCT-01"),
            ("변경 부품(Variant)", "예: DUCT-A와 DUCT-B처럼 두 개 이상 입력할 수 있습니다."),
        ],
    },
    "conditions": {
        "description": "해석조건은 계산할 환경과 운전 조건을 정하는 단계입니다. 조건 값은 필요하면 두 개 이상 넣어 Case를 비교할 수 있습니다.",
        "examples": [
            ("작동유체", "예: Air"),
            ("Fan RPM", "예: 780 또는 780/900"),
            ("Room 온도", "예: 27도 또는 27도와 30도"),
            ("Room 상대습도", "예: 78%"),
        ],
    },
}


def _stage_key_from_writing_question(message: str) -> str:
    if not _looks_like_question(message):
        return ""
    if _contains_any(message, ("해석 개요", "개요")):
        return "analysis_overview"
    if _contains_any(message, ("형상/모델", "형상", "모델정보", "모델 정보", "모델링 정보", "모델 정보")):
        return "geometry"
    if _contains_any(message, ("해석조건", "해석 조건", "조건 입력", "조건값", "조건 값", "조건에는", "조건 예시")):
        return "conditions"
    return ""


def _stage_writing_guide_answer(message: str, state: Mapping[str, Any]) -> str:
    stage_key = _stage_key_from_writing_question(message)
    if not stage_key:
        return ""
    guide = STAGE_WRITING_GUIDES.get(stage_key, {})
    progress = _stage_progress(_derive_state(state))
    stage = _as_mapping(_as_mapping(progress.get("stages")).get(stage_key))
    missing = [_clean_text(item) for item in _as_list(stage.get("missing_fields")) if _clean_text(item)]
    lines = [
        _clean_text(guide.get("description")),
        "",
        "필드별 작성 예시:",
    ]
    for label, example in _as_list(guide.get("examples")):
        lines.append(f"- {label}: {example}")
    if missing:
        lines.append("")
        lines.append(f"현재 이 단계에서 비어 있는 항목은 {_field_list_text(missing)}입니다.")
    return "\n".join(line for line in lines if line is not None)


def _condition_recommend_offer_proposal() -> dict[str, Any]:
    return {
        "proposal_id": f"condition_offer_{uuid4().hex[:10]}",
        "proposal_type": "condition_recommend_offer",
        "status": "pending",
        "summary": "AI 조건 추천을 받아볼까요?",
        "operations": [],
        "state_changed": False,
        "read_only": True,
    }


def _final_submit_proposal() -> dict[str, Any]:
    return {
        "proposal_id": f"final_submit_{uuid4().hex[:10]}",
        "proposal_type": "final_submit",
        "status": "pending",
        "summary": "해석 의뢰를 완성시킬까요?",
        "operations": [],
        "state_changed": False,
        "read_only": True,
    }


def _final_review_blocking_answer(review_payload: Mapping[str, Any]) -> str:
    guidance = [_as_mapping(item) for item in _as_list(review_payload.get("edit_guidance")) if isinstance(item, Mapping)]
    lines = ["최종 검토 결과, 제출 전 보완이 필요한 항목이 있습니다.", ""]
    if guidance:
        lines.append("먼저 아래 항목을 수정해 주세요.")
        for item in guidance[:8]:
            label = _clean_text(item.get("field_label")) or _clean_text(item.get("path")) or _clean_text(item.get("section"))
            anchor = _clean_text(item.get("ui_anchor"))
            message = _clean_text(item.get("message"))
            prefix = f"{anchor} - {label}" if anchor and label else label or anchor or "보완 항목"
            lines.append(f"- {prefix}: {message}")
        if len(guidance) > 8:
            lines.append("- 등")
    else:
        lines.append("현재 의뢰서의 누락 항목을 먼저 보완해 주세요.")
    lines.append("")
    lines.append("보완이 끝나면 다시 '최종 검토해줘' 또는 '해석 의뢰 완성시켜줘'라고 요청해 주세요.")
    return "\n".join(lines)


def _final_review_ready_answer(review_payload: Mapping[str, Any]) -> str:
    summary = _as_mapping(_as_mapping(review_payload.get("final_validator")).get("summary"))
    final_case_count = int(summary.get("final_case_count") or 0)
    warning_count = int(summary.get("warning_count") or 0)
    lines = [
        "최종 검토 결과, 제출을 막는 blocking 항목은 없습니다.",
        f"최종 포함 Case 수: {final_case_count}",
    ]
    if warning_count:
        lines.append(f"참고 warning {warning_count}건이 있으나 제출 가능 상태입니다.")
    lines.append("")
    lines.append("해석 의뢰를 완성시킬까요?")
    return "\n".join(lines)


def _final_review_chat_result(raw_state: Mapping[str, Any]) -> dict[str, Any]:
    state = state_with_final_review(raw_state if isinstance(raw_state, Mapping) else {})
    review_payload = _as_mapping(_as_mapping(state.get("review")).get("final_review"))
    if review_payload.get("can_submit"):
        return {
            "intent": "final_review",
            "answer": _final_review_ready_answer(review_payload),
            "state": state,
            "final_review": review_payload,
            "proposal": _final_submit_proposal(),
        }
    return {
        "intent": "final_review",
        "answer": _final_review_blocking_answer(review_payload),
        "state": state,
        "final_review": review_payload,
    }


def _analysis_type_guidance_message(state: Mapping[str, Any], analysis_type: str) -> str:
    progress = _stage_progress(state)
    lines = [f"{analysis_type} 해석유형을 선택했습니다.", "의뢰서 완성을 위해 아래 단계를 채워 주세요.", ""]
    for key in STAGE_KEYS:
        stage = _as_mapping(_as_mapping(progress.get("stages")).get(key))
        missing = [_clean_text(item) for item in _as_list(stage.get("missing_fields")) if _clean_text(item)]
        lines.append(f"- {stage.get('label', key)}: {_field_list_text(missing)}")
    lines.append("")
    lines.append("처음이라면 한 단계씩 대화창에 입력해도 됩니다.")
    return "\n".join(lines)


def _condition_guidance_message(state: Mapping[str, Any]) -> str:
    return (
        "이제 해석조건을 입력하면 됩니다.\n"
        f"{_condition_example_text()}\n"
        "필요할 때 아래 빠른 실행을 선택하세요."
    )


def _condition_quick_actions() -> list[dict[str, str]]:
    return [
        {"id": "condition_example", "label": "조건 입력 예시"},
        {"id": "missing_items", "label": "누락 항목 확인"},
    ]


def _stage_completion_message(state: Mapping[str, Any], completed_key: str) -> str:
    progress = _stage_progress(state)
    completed = _as_mapping(_as_mapping(progress.get("stages")).get(completed_key))
    remaining = [_as_mapping(item) for item in _as_list(progress.get("remaining_stages")) if isinstance(item, Mapping)]
    lines = [f"{completed.get('label', completed_key)} 입력이 완료되었습니다."]
    if not remaining:
        lines.append("모든 단계의 빈 칸이 채워졌습니다.")
        return "\n".join(lines)
    lines.append("남은 단계와 누락 필드는 다음과 같습니다.")
    lines.append("")
    for stage in remaining:
        missing = [_clean_text(item) for item in _as_list(stage.get("missing_fields")) if _clean_text(item)]
        lines.append(f"- {stage.get('label')}: {_field_list_text(missing)}")
    return "\n".join(lines)


def _progress_notifications(state: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    next_state = deepcopy(dict(state if isinstance(state, Mapping) else {}))
    metadata = dict(next_state.get("metadata") if isinstance(next_state.get("metadata"), Mapping) else {})
    progress = _stage_progress(next_state)
    notifications: list[dict[str, Any]] = []
    notified = set(str(item) for item in _as_list(metadata.get("assistant_notified_completed_stages")))
    remaining_stages = [_as_mapping(item) for item in _as_list(progress.get("remaining_stages")) if isinstance(item, Mapping)]
    only_conditions_remaining = len(remaining_stages) == 1 and _clean_text(remaining_stages[0].get("key")) == "conditions"

    for key in STAGE_KEYS:
        stage = _as_mapping(_as_mapping(progress.get("stages")).get(key))
        if not stage.get("is_complete") or key in notified:
            continue
        notified.add(key)
        notification: dict[str, Any] = {
            "kind": "stage_completed",
            "stage_key": key,
            "message": _stage_completion_message(next_state, key),
        }
        notifications.append(notification)

    if len(notifications) > 1:
        for notification in notifications[:-1]:
            stage = _as_mapping(_as_mapping(progress.get("stages")).get(_clean_text(notification.get("stage_key"))))
            notification["message"] = f"{stage.get('label', notification.get('stage_key'))} 입력이 완료되었습니다."

    if only_conditions_remaining:
        for notification in reversed(notifications):
            if notification.get("kind") == "stage_completed" and notification.get("stage_key") != "conditions":
                notification["followup"] = {
                    "message": _condition_guidance_message(next_state),
                    "quick_actions": _condition_quick_actions(),
                }
                break

    metadata["assistant_notified_completed_stages"] = sorted(notified)
    next_state["metadata"] = metadata
    return next_state, notifications


_FIELD_HELP: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("작동유체", "유체", "material_type", "working fluid"),
        "작동유체는 해석 영역 안에서 흐르거나 열을 전달하는 유체입니다. 공조/CFD 의뢰에서는 보통 Air, Water 같은 물질을 적으며, 물성 선택과 유동/열유동 계산 조건의 기준이 됩니다.",
    ),
    (
        ("fan rpm", "팬 rpm", "rpm"),
        "Fan RPM은 팬 회전수 조건입니다. 유량, 압력손실, 열교환기 통과 유속에 영향을 주므로 비교하려는 회전수가 있으면 하나 이상 입력합니다.",
    ),
    (
        ("해석 대상 제품", "제품모델링번호", "제품 번호", "모델링 번호", "product"),
        "해석 대상 제품는 해석 대상 형상 또는 CAD 모델을 식별하는 번호입니다. Case Matrix의 형상 축을 만들기 위해 최소 1개가 필요합니다.",
    ),
    (
        ("변경 부품", "부품 모델링", "changed part"),
        "변경 부품은 기준 제품 대비 바뀐 부품이나 비교 대상 부품입니다. 변경 부품이 있으면 부품 모델링 번호와 기준 부품 정보를 함께 적으면 Case 구성이 명확해집니다.",
    ),
    (
        ("해석 목적", "purpose"),
        "해석 목적은 이번 의뢰로 확인하려는 이유입니다. 예를 들어 '토출부 이슬맺힘 원인 분석'처럼 문제 상황과 검토 의도를 적습니다.",
    ),
    (
        ("해석 목표", "goal"),
        "해석 목표는 결과로 판단하려는 기준이나 기대 결론입니다. 예를 들어 '이슬맺힘 발생 위치와 개선 방향 도출'처럼 검토 완료 시 확인할 내용을 적습니다.",
    ),
    (
        ("case matrix", "케이스 매트릭스", "case matrix preview"),
        "Case Matrix는 형상 조건과 해석 조건을 조합해 실제 계산할 Case 목록을 만든 표입니다. 제품/부품 축과 조건 값이 준비되어야 생성됩니다.",
    ),
    (
        ("상대습도", "습도", "rh"),
        "상대습도는 현재 온도에서 공기가 포함할 수 있는 최대 수증기량 대비 실제 수증기량의 비율입니다. 이슬맺힘 해석에서는 노점과 결로 가능성을 판단하는 핵심 조건입니다.",
    ),
    (
        ("열교환기 온도", "hex temp", "heat exchanger temp"),
        "열교환기 온도는 공기가 열교환기 표면과 만날 때 냉각/가열되는 조건입니다. 이슬맺힘 검토에서는 표면 온도와 주변 공기 습도 조건의 조합이 중요합니다.",
    ),
    (
        ("열교환기 사양", "열교환기 이름", "hex spec", "heat exchanger spec"),
        "열교환기 사양은 Case에서 사용할 열교환기 구조를 식별하는 정보입니다. Fin&Tube는 Fin type, 관 직경(Pi), 열 수, FPI를 사용하고 Micro-Channel은 Flat Fin type, 채널 폭(Width), 열 수, FPDM을 사용합니다.",
    ),
)


def _field_help_answer(message: str) -> str:
    for tokens, answer in _FIELD_HELP:
        if _contains_any(message, tokens) and _looks_like_question(message):
            return answer
    return ""


def _looks_like_completion_question(message: str) -> bool:
    return _contains_any(
        message,
        (
            "나머지",
            "남은",
            "누락",
            "빠진",
            "채워야",
            "완성",
            "완료",
            "제출하려면",
            "제출 가능",
            "무엇을 입력",
            "뭘 입력",
            "입력해야",
            "필요한 항목",
        ),
    )


def _looks_like_final_review_request(message: str) -> bool:
    info_question_tokens = (
        "남은",
        "남아",
        "나머지",
        "누락",
        "빠진",
        "무엇",
        "뭐",
        "뭘",
        "어떤",
        "입력해야",
        "필요한",
        "알려줘",
    )
    final_tokens = (
        "최종 점검",
        "최종점검",
        "최종 검토",
        "최종검토",
        "검토 요청",
        "제출 검토",
        "제출 가능",
        "최종 제출",
        "저장/최종 제출",
        "해석 의뢰 완성",
        "해석의뢰 완성",
        "의뢰서 완성",
        "해석 의뢰 완료",
        "해석의뢰 완료",
        "의뢰서 완료",
        "완성시켜",
        "완성해",
        "완료 부탁",
        "완료해",
        "제출해",
    )
    if _contains_any(message, ("최종 검토", "최종검토", "최종 점검", "최종점검", "검토 요청", "제출 검토")):
        return True
    if _contains_any(message, info_question_tokens):
        return False
    return _contains_any(message, final_tokens)


def _looks_like_service_question(message: str) -> bool:
    return _contains_any(
        message,
        (
            "이 서비스",
            "서비스 내용",
            "사용법",
            "무엇을 할 수",
            "뭘 할 수",
            "기능",
            "의뢰 agent",
            "의뢰agent",
            "대화창",
            "도와",
            "어떻게 사용",
        ),
    )


def _service_overview_answer() -> str:
    return (
        "이 대화창에서는 의뢰서 입력 보조, 현재 의뢰서의 누락 항목 안내, 필드 의미 설명, 일반 CAE 질문 답변을 처리합니다.\n"
        "의뢰서에 들어갈 값으로 판단되면 먼저 어떤 필드에 어떤 값을 넣을지 보여주고 Yes/No 확인을 요청합니다. "
        "Yes를 누른 경우에만 의뢰서 state에 반영하고, No를 누르면 반영하지 않습니다.\n"
        "사내 문서, 유사 보고서, SOP/NXI 근거가 필요한 질문은 RAG 문서 검색으로 답변합니다."
    )


def _local_chat_answer(message: str, state: Mapping[str, Any]) -> dict[str, Any] | None:
    stage_guide = _stage_writing_guide_answer(message, state)
    if stage_guide:
        return {"intent": "stage_writing_guide", "answer": stage_guide}
    if _looks_like_final_review_request(message):
        return _final_review_chat_result(state)
    if _looks_like_completion_question(message):
        return {"intent": "form_guidance", "answer": _missing_items_answer(state)}
    field_answer = _field_help_answer(message)
    if field_answer:
        return {"intent": "field_help", "answer": field_answer}
    if _looks_like_service_question(message):
        return {"intent": "service_help", "answer": _service_overview_answer()}
    if looks_like_current_input_question(message):
        summary = summarize_current_state(state)
        return {
            "intent": "current_state",
            "answer": (
                "현재 입력 상태를 요약하면 다음과 같습니다.\n"
                f"- 해석유형: {_as_mapping(summary.get('analysis_overview')).get('analysis_type') or '-'}\n"
                f"- 목적: {_as_mapping(summary.get('analysis_overview')).get('purpose') or '-'}\n"
                f"- 목표: {_as_mapping(summary.get('analysis_overview')).get('goal') or '-'}\n"
                f"- 제품: {', '.join(_as_mapping(summary.get('geometry')).get('products', []) or []) or '-'}\n"
                f"- 제출 가능: {_as_mapping(summary.get('validation')).get('can_submit', False)}"
            ),
        }
    return None


def _should_use_document_rag(message: str) -> bool:
    return _contains_any(
        message,
        (
            "rag",
            "유사 보고서",
            "유사보고서",
            "유사사례",
            "보고서",
            "sop",
            "nxi",
            "규정",
            "기준서",
            "절차",
            "표준",
            "근거 문서",
            "문서 근거",
        ),
    )


def _general_chat_answer(message: str, state: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    status = llm_status()
    if status.get("ready"):
        try:
            payload = synthesize_general_chat_answer(message, state_summary=summarize_current_state(state))
            return _clean_text(payload.get("answer_text")) or "답변을 생성하지 못했습니다.", payload
        except Exception as exc:  # pragma: no cover - network/config dependent
            return (
                "일반 Q&A 답변 생성 중 오류가 발생했습니다. 의뢰서 입력값을 반영하려면 항목명과 값을 함께 적어주세요.",
                {"used": False, "error": str(exc), "status": llm_status()},
            )
    return (
        "이 질문은 일반 Q&A로 분류했습니다. 현재 LLM이 준비되지 않아 상세 답변은 제한됩니다. "
        "의뢰서에 반영할 값이라면 예: '작동유체는 Air, Fan RPM은 780'처럼 항목명과 값을 함께 적어주세요.",
        {"used": False, "status": status},
    )


def _llm_form_patch_proposal(message: str, base_state: Mapping[str, Any]) -> dict[str, Any] | None:
    if not env_flag("REQUEST_AGENT_LLM_FORM_EXTRACTION_ENABLED", default=True):
        return None
    status = llm_status()
    if not status.get("ready"):
        return None
    try:
        extracted = extract_form_patch_with_llm(
            message,
            state_summary=summarize_current_state(base_state),
            schema=get_public_schema(),
        )
    except Exception as exc:  # pragma: no cover - network/config dependent
        proposal = proposal_from_operations(
            message,
            [],
            source="azure_gpt_form_extraction",
            warnings=[f"LLM form extraction failed: {exc}"],
            questions=["LLM 응답을 처리하지 못했습니다. 다시 요청해 주세요."],
            state=base_state,
        )
        proposal["chat_intent"] = "needs_clarification"
        proposal["llm"] = {"used": False, "error": str(exc), "status": llm_status()}
        return proposal
    payload = extracted.get("payload") if isinstance(extracted, Mapping) else {}
    payload_map = payload if isinstance(payload, Mapping) else {}
    operations = payload_map.get("operations") if isinstance(payload_map.get("operations"), list) else []
    proposal = proposal_from_operations(
        message,
        operations,
        source="azure_gpt_form_extraction",
        summary=str(payload_map.get("summary", "") or ""),
        warnings=payload_map.get("warnings") if isinstance(payload_map.get("warnings"), list) else [],
        questions=payload_map.get("questions") if isinstance(payload_map.get("questions"), list) else [],
        state=base_state,
    )
    proposal["chat_intent"] = str(payload_map.get("intent", "needs_clarification") or "needs_clarification").strip().lower()
    if proposal["chat_intent"] not in LLM_CHAT_INTENTS:
        proposal["chat_intent"] = "needs_clarification"
    if proposal["chat_intent"] == "patch" and not proposal.get("operations"):
        proposal["status"] = "needs_clarification"
        proposal["intent"] = "question"
        proposal["chat_intent"] = "needs_clarification"
        proposal["warnings"] = [*proposal.get("warnings", []), "LLM operation was not allowed by the structured-operation contract."]
        proposal["questions"] = [*proposal.get("questions", []), "적용할 수 있는 입력 항목과 값을 다시 알려 주세요."]
    proposal["llm"] = {
        "used": True,
        "provider": extracted.get("provider", ""),
        "deployment": extracted.get("deployment", ""),
        "api_version": extracted.get("api_version", ""),
    }
    return proposal


def _proposal_response_with_llm(message: str, base_state: Mapping[str, Any]) -> dict[str, Any]:
    llm_proposal = _llm_form_patch_proposal(message, base_state)
    if isinstance(llm_proposal, Mapping):
        proposal = dict(llm_proposal)
        dry_run_state = apply_patch_operations(base_state, proposal.get("operations", [])) if proposal.get("operations") else _derive_state(base_state)
    else:
        proposal = proposal_from_operations(
            message,
            [],
            source="llm_unavailable",
            questions=["LLM이 준비되지 않았거나 응답을 처리하지 못했습니다. 잠시 후 다시 요청해 주세요."],
            state=base_state,
        )
        proposal["chat_intent"] = "needs_clarification"
        proposal["llm"] = {"used": False, "status": llm_status()}
        dry_run_state = _derive_state(base_state)
    assistant = _proposal_confirmation_text(proposal) if proposal.get("status") == "pending" else "\n".join(proposal.get("questions", [])) or proposal.get("summary", "")
    return {
        "proposal": proposal,
        "assistant": assistant,
        "dry_run": {
            "state": dry_run_state,
            "case_matrix": dry_run_state.get("case_matrix", {}),
            "validation": dry_run_state.get("review", {}).get("validator", {}),
            "submission": dry_run_state.get("review", {}).get("submission", {}),
        },
        "llm_form_extraction": proposal.get("llm", {"used": False}),
        "chat_intent": proposal.get("chat_intent", "needs_clarification"),
        "state_changed": False,
    }


def _draft_rag_question(state: Mapping[str, Any]) -> str:
    overview = state.get("analysis_overview", {}) if isinstance(state, Mapping) else {}
    geometry = state.get("geometry", {}) if isinstance(state, Mapping) else {}
    products = []
    if isinstance(geometry, Mapping):
        for row in geometry.get("products", []):
            products.append(str(field_value(row, "") or "").strip())
    parts = [
        "해석 의뢰서 초안 문장 보강 근거",
        str(field_value(overview.get("analysis_type"), "") or "").strip() if isinstance(overview, Mapping) else "",
        str(field_value(overview.get("purpose"), "") or "").strip() if isinstance(overview, Mapping) else "",
        str(field_value(overview.get("goal"), "") or "").strip() if isinstance(overview, Mapping) else "",
        " ".join(item for item in products if item),
        "유사보고서 SOP 제품정보 산출물",
    ]
    return " ".join(part for part in parts if part)


def _approve_draft_suggestion(draft_payload: Any, *, approve: bool = True) -> Mapping[str, Any] | None:
    if not isinstance(draft_payload, Mapping):
        return None
    draft = deepcopy(dict(draft_payload))
    document = draft.get("document")
    if not approve or not isinstance(document, Mapping):
        return draft
    suggestion = str(document.get("llm_markdown_suggestion", "") or "").strip()
    if not suggestion:
        return draft
    next_document = dict(document)
    current_markdown = str(next_document.get("markdown", "") or "")
    next_document.setdefault("markdown_structured", current_markdown)
    next_document["markdown"] = suggestion
    next_document["markdown_approved_source"] = "llm_markdown_suggestion"
    next_document["llm_markdown_approved"] = True
    draft["document"] = next_document
    draft["draft_text_source"] = "approved_llm_suggestion"
    return draft


def create_app(*, orchestrator_extractor: Extractor | None = None) -> Flask:
    app = Flask(__name__)
    # A browser receives an opaque workspace id.  This is deliberately a
    # lightweight demo boundary, not an identity/login system: it prevents one
    # user's browser from reading or mutating another browser's runtime work.
    # Set a stable secret in deployment so browser workspaces survive restarts.
    app.config["SECRET_KEY"] = os.getenv("REQUEST_AGENT_SESSION_SECRET") or token_urlsafe(32)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["JSON_AS_ASCII"] = False
    request_state_store = RequestStateStore(_derive_state)
    case_matrix_action_service = CaseMatrixActionService(request_state_store)
    preview_action_service = PreviewActionService(request_state_store)
    rag_guidance_action_service = RagGuidanceActionService(request_state_store)
    validation_action_service = ValidationActionService(request_state_store)
    runtime_audit_log = RuntimeAuditLog()
    conversation_store = ConversationStore()
    proposal_store = ProposalStore()
    proposal_service = ProposalService(request_state_store, proposal_store)
    workflow_machine = ConversationWorkflowMachine(conversation_store)
    orchestrator_service = OrchestratorService(
        conversations=conversation_store,
        requests=request_state_store,
        proposals=proposal_service,
        workflow=workflow_machine,
        extractor=orchestrator_extractor,
    )
    proposal_conversations: dict[str, str] = {}
    # These process-local stores are deliberately separate authorities.  The
    # extension references support focused in-process tests only; they are not
    # an HTTP state/snapshot surface.
    app.extensions["request_state_store"] = request_state_store
    app.extensions["case_matrix_action_service"] = case_matrix_action_service
    app.extensions["validation_action_service"] = validation_action_service
    app.extensions["runtime_audit_log"] = runtime_audit_log
    app.extensions["rag_guidance_action_service"] = rag_guidance_action_service
    app.extensions["conversation_store"] = conversation_store
    app.extensions["proposal_service"] = proposal_service
    app.extensions["conversation_workflow_machine"] = workflow_machine
    app.extensions["orchestrator_service"] = orchestrator_service

    # Request ids are already unguessable UUIDs, but that alone does not make
    # the ownership rule explicit.  Keep the owner separately so every
    # server-held Request, Conversation, and Proposal is fenced to its browser
    # workspace before the route handler can act on it.
    request_workspace_owners: dict[str, str] = {}
    request_workspace_lock = RLock()

    def _workspace_id() -> str:
        workspace_id = session.get("request_agent_workspace_id")
        if not isinstance(workspace_id, str) or not workspace_id:
            workspace_id = token_urlsafe(32)
            session["request_agent_workspace_id"] = workspace_id
        return workspace_id

    def _register_request_workspace(request_id: str) -> None:
        with request_workspace_lock:
            request_workspace_owners[request_id] = _workspace_id()

    def _owns_request(request_id: str) -> bool:
        with request_workspace_lock:
            owner = request_workspace_owners.get(request_id)
            if owner is None:
                # Normal HTTP creation registers ownership before returning.
                # This fallback only covers server-created runtime records
                # (for example, an operator/test fixture) without exposing a
                # non-existent id or changing an already-owned record.
                try:
                    request_state_store.read(request_id)
                except RequestNotFoundError:
                    return False
                request_workspace_owners[request_id] = _workspace_id()
                return True
            return owner == _workspace_id()

    def _workspace_not_found():
        # Do not disclose whether another browser owns the supplied id.
        return jsonify({"ok": False, "error": "workspace_resource_not_found"}), 404

    @app.before_request
    def enforce_browser_workspace():
        """Fence server-runtime resources to the current browser workspace."""

        if not request.path.startswith("/api/") or request.endpoint == "create_versioned_request":
            return None

        view_args = request.view_args or {}
        payload = request.get_json(silent=True) if request.is_json else None
        payload = payload if isinstance(payload, Mapping) else {}

        request_ids = [value for value in (view_args.get("request_id"),) if isinstance(value, str)]
        conversation_ids = [value for value in (view_args.get("conversation_id"),) if isinstance(value, str)]
        proposal_ids: list[str] = []
        if request.endpoint in {
            "create_conversation",
            "run_orchestrator_case_matrix_action",
            "run_orchestrator_validation_action",
            "run_orchestrator_preview_action",
            "run_orchestrator_rag_guidance_action",
        } and isinstance(payload.get("request_id"), str):
            request_ids.append(payload["request_id"])
        if request.endpoint in {"orchestrator_message", "chat_send"} and isinstance(payload.get("conversation_id"), str):
            conversation_ids.append(payload["conversation_id"])
        if request.endpoint in {"decide_orchestrator_proposal", "create_orchestrator_undo_proposal"} and isinstance(payload.get("proposal_id"), str):
            proposal_ids.append(payload["proposal_id"])

        for request_id in request_ids:
            try:
                request_state_store.read(request_id)
            except RequestNotFoundError:
                return jsonify({"ok": False, "error": "request_not_found", "request_id": request_id}), 404
            if not _owns_request(request_id):
                return _workspace_not_found()
        for conversation_id in conversation_ids:
            try:
                conversation = conversation_store.read(conversation_id)
            except ConversationNotFoundError:
                # Preserve the route's established response for an unknown id;
                # there is no shared resource to expose or mutate in that case.
                continue
            try:
                request_state_store.read(conversation.request_id)
            except RequestNotFoundError:
                # Preserve the route's existing corrupt-reference handling.
                continue
            if not _owns_request(conversation.request_id):
                return _workspace_not_found()
        for proposal_id in proposal_ids:
            try:
                proposal = proposal_service.read_proposal(proposal_id)
            except ProposalNotFoundError:
                # As above, let the route report its existing unknown-id error.
                continue
            if not _owns_request(proposal.request_id):
                return _workspace_not_found()
        return None

    def _audit_after_result(
        *,
        action: str,
        result_code: str,
        success: bool,
        request_id: str | None = None,
        conversation_id: str | None = None,
        proposal_id: str | None = None,
    ) -> None:
        """Best-effort observer: it never changes or replaces the result path."""

        try:
            runtime_audit_log.append(
                action=action,
                result_code=result_code,
                status="success" if success else "failure",
                request_id=request_id,
                conversation_id=conversation_id,
                proposal_id=proposal_id,
            )
        except Exception:
            # Audit availability must not alter established authority/results.
            pass

    @app.get("/api/orchestrator/audit/events")
    def read_orchestrator_audit_events():
        """Return only bounded, server-generated runtime audit DTOs."""

        try:
            events = [event.dto() for event in runtime_audit_log.events()]
        except Exception:
            # Observation read availability has no authority over Request,
            # Proposal, workflow, or panel state.
            return jsonify({"ok": False, "error": "audit_read_failed", "events": [], "read_only": True}), 503
        return jsonify({"ok": True, "events": events, "read_only": True})

    @app.post("/api/request/versioned")
    def create_versioned_request():
        """Create a server-identified Request from a new or legacy state payload."""

        payload = _payload_mapping()
        raw_state = payload.get("state") if isinstance(payload.get("state"), Mapping) else create_initial_state()
        snapshot = request_state_store.create(raw_state)
        _register_request_workspace(snapshot.request_id)
        response = _versioned_request_payload(snapshot)
        response["state_changed"] = True
        return jsonify(response), 201

    @app.get("/api/request/versioned/<request_id>")
    def get_versioned_request(request_id: str):
        try:
            snapshot = request_state_store.read(request_id)
        except RequestNotFoundError:
            return jsonify({"ok": False, "error": "request_not_found", "request_id": request_id}), 404
        return jsonify(_versioned_request_payload(snapshot))

    @app.put("/api/request/versioned/<request_id>")
    def replace_versioned_request(request_id: str):
        payload = _payload_mapping()
        expected_version = payload.get("expected_version")
        raw_state = payload.get("state")
        if not isinstance(raw_state, Mapping):
            return jsonify({"ok": False, "error": "invalid_request_state", "state_changed": False}), 400
        try:
            snapshot = request_state_store.replace(request_id, expected_version, raw_state)
        except RequestNotFoundError:
            return jsonify({"ok": False, "error": "request_not_found", "request_id": request_id, "state_changed": False}), 404
        except RequestVersionConflictError as exc:
            _audit_after_result(
                action="request_cas",
                result_code="request_version_conflict",
                success=False,
                request_id=exc.request_id,
            )
            return jsonify(
                {
                    "ok": False,
                    "error": "request_version_conflict",
                    "request_id": exc.request_id,
                    "expected_version": exc.expected_version,
                    "current_version": exc.current_version,
                    "state_changed": False,
                }
            ), 409
        except ValueError as exc:
            return jsonify({"ok": False, "error": "invalid_expected_version", "message": str(exc), "state_changed": False}), 400
        response = _versioned_request_payload(snapshot)
        response["state_changed"] = True
        _audit_after_result(action="request_cas", result_code="request_updated", success=True, request_id=snapshot.request_id)
        return jsonify(response)

    @app.post("/api/conversations")
    def create_conversation():
        payload, error_response = _conversation_request_payload(allowed_keys={"request_id", "proposal_id"})
        if error_response is not None:
            return error_response
        request_id = payload.get("request_id")
        proposal_id = payload.get("proposal_id")
        if (
            not isinstance(request_id, str)
            or (proposal_id is not None and (not isinstance(proposal_id, str) or not proposal_id or len(proposal_id) > 256))
        ):
            return jsonify({"ok": False, "error": "invalid_conversation_payload"}), 400
        try:
            # Conversation creation is allowed only for a server-issued Request.
            request_state_store.read(request_id)
            snapshot = conversation_store.create(request_id)
            if proposal_id is not None:
                snapshot = conversation_store.set_pending_proposal(snapshot.conversation_id, proposal_id)
        except RequestNotFoundError:
            return jsonify({"ok": False, "error": "request_not_found", "request_id": request_id}), 404
        except ConversationCapacityError:
            return jsonify({"ok": False, "error": "conversation_store_full"}), 409
        except ValueError:
            return jsonify({"ok": False, "error": "invalid_conversation_payload"}), 400
        return jsonify(_conversation_payload(snapshot)), 201

    @app.get("/api/conversations/<conversation_id>")
    def get_conversation(conversation_id: str):
        try:
            return jsonify(_conversation_payload(conversation_store.read(conversation_id)))
        except ConversationNotFoundError:
            return jsonify({"ok": False, "error": "conversation_not_found", "conversation_id": conversation_id}), 404

    def _conversation_transition(conversation_id: str, transition: str):
        payload, error_response = _conversation_request_payload(allowed_keys=set())
        if error_response is not None:
            return error_response
        try:
            snapshot = getattr(conversation_store, transition)(conversation_id)
        except ConversationNotFoundError:
            return jsonify({"ok": False, "error": "conversation_not_found", "conversation_id": conversation_id}), 404
        except ConversationStateError:
            return jsonify({"ok": False, "error": "invalid_conversation_transition", "conversation_id": conversation_id}), 409
        _audit_after_result(
            action=f"conversation_{transition}",
            result_code={"pause": "conversation_paused", "resume": "conversation_resumed", "close": "conversation_closed"}[transition],
            success=True,
            request_id=snapshot.request_id,
            conversation_id=snapshot.conversation_id,
        )
        return jsonify(_conversation_payload(snapshot))

    @app.post("/api/conversations/<conversation_id>/pause")
    def pause_conversation(conversation_id: str):
        return _conversation_transition(conversation_id, "pause")

    @app.post("/api/conversations/<conversation_id>/resume")
    def resume_conversation(conversation_id: str):
        return _conversation_transition(conversation_id, "resume")

    @app.post("/api/conversations/<conversation_id>/close")
    def close_conversation(conversation_id: str):
        return _conversation_transition(conversation_id, "close")

    @app.post("/api/orchestrator/messages")
    def orchestrator_message():
        input_dto, error_response = _orchestrator_message_input()
        if error_response is not None:
            return error_response
        result = orchestrator_service.handle(input_dto)
        if isinstance(result, OrchestratorProposalResult):
            try:
                proposal = proposal_service.read_proposal(result.proposal_id)
            except Exception:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "kind": "failure",
                            "error": "proposal_read_failed",
                            "reasons": ["proposal_read_failed"],
                            "state_changed": False,
                            "read_only": True,
                        }
                    ),
                    503,
                )
            _audit_after_result(
                action="orchestrator_message",
                result_code=result.kind,
                success=True,
                request_id=proposal.request_id,
                conversation_id=input_dto.conversation_id,
                proposal_id=proposal.proposal_id,
            )
            proposal_conversations[proposal.proposal_id] = input_dto.conversation_id
            return jsonify(
                {
                    "ok": True,
                    "kind": result.kind,
                    "route_category": result.route_category,
                    "reasons": list(result.reasons),
                    "proposal": {
                        "proposal_id": proposal.proposal_id,
                        "status": proposal.status,
                        "diff": {**deepcopy(proposal.diff_summary), "read_only": True},
                    },
                    "state_changed": False,
                    "read_only": True,
                }
            )
        if isinstance(result, OrchestratorReadOnlyResult):
            return jsonify(
                {
                    "ok": True,
                    "kind": result.kind,
                    "route_category": result.route_category,
                    "reasons": list(result.reasons),
                    "planner_decision": _planner_decision_payload(result.planner_decision),
                    "state_changed": False,
                    "read_only": True,
                }
            )
        if isinstance(result, OrchestratorClarificationResult):
            return jsonify(
                {
                    "ok": True,
                    "kind": result.kind,
                    "route_category": result.route_category,
                    "reasons": list(result.reasons),
                    "question": result.question,
                    "state_changed": False,
                    "read_only": True,
                }
            )
        if isinstance(result, OrchestratorFailureResult):
            # A failed workflow result is observable only after the service has
            # validated the server Conversation reference.  Never log the raw
            # message or an unknown client-supplied conversation id.
            if result.code in {"conversation_paused", "workflow_paused", "workflow_terminal", "invalid_workflow_event", "proposal_reference_mismatch"}:
                try:
                    conversation = conversation_store.read(input_dto.conversation_id)
                except Exception:
                    conversation = None
                if conversation is not None:
                    _audit_after_result(
                        action="orchestrator_message",
                        result_code=result.code,
                        success=False,
                        request_id=conversation.request_id,
                        conversation_id=conversation.conversation_id,
                    )
            return (
                jsonify(
                    {
                        "ok": False,
                        "kind": result.kind,
                        "error": result.code,
                        "reasons": list(result.reasons),
                        "state_changed": False,
                        "read_only": True,
                    }
                ),
                _orchestrator_failure_status(result.code),
            )
        return (
            jsonify(
                {
                    "ok": False,
                    "kind": "failure",
                    "error": "invalid_orchestrator_result",
                    "reasons": ["invalid_orchestrator_result"],
                    "state_changed": False,
                    "read_only": True,
                }
            ),
            503,
        )

    @app.post("/api/orchestrator/proposals/decision")
    def decide_orchestrator_proposal():
        """Resolve one server-ledger Proposal from an explicit panel decision.

        This deliberately accepts no Request snapshot, version, operation, diff,
        workflow event, or result.  ProposalService remains the sole lifecycle,
        CAS, and replay authority.
        """

        payload = request.get_json(silent=True)
        if not isinstance(payload, Mapping) or set(payload) != {"proposal_id", "decision"}:
            return jsonify({"ok": False, "error": "invalid_proposal_decision_payload", "read_only": True}), 400
        proposal_id = payload.get("proposal_id")
        decision = payload.get("decision")
        if (
            not isinstance(proposal_id, str)
            or not proposal_id
            or len(proposal_id) > 256
            or decision not in {"approve", "reject"}
        ):
            return jsonify({"ok": False, "error": "invalid_proposal_decision_payload", "read_only": True}), 400
        try:
            proposal = (
                proposal_service.approve_proposal(proposal_id)
                if decision == "approve"
                else proposal_service.reject_proposal(proposal_id)
            )
        except ProposalNotFoundError:
            return jsonify({"ok": False, "error": "proposal_not_found", "read_only": True}), 404
        except Exception:
            return jsonify({"ok": False, "error": "proposal_decision_failed", "read_only": True}), 503
        conversation_id = proposal_conversations.get(proposal.proposal_id)
        next_question = None
        if conversation_id and proposal.status in {"approved", "rejected"}:
            try:
                request_snapshot = request_state_store.read(proposal.request_id)
                planned = plan_next_question(request_snapshot)
                updated_conversation = apply_next_question(
                    conversation_store,
                    conversation_id,
                    planned,
                    prior_events=(
                        WorkflowEvent(WorkflowEventType.PROPOSAL_TERMINAL, proposal.proposal_id),
                        WorkflowEvent(WorkflowEventType.PLAN_NEXT_QUESTION),
                    ),
                )
                next_question = dict(planned)
                next_question["active_field_id"] = updated_conversation.active_field_id
            except Exception:
                try:
                    workflow_machine.dispatch_many(
                        conversation_id,
                        (
                            WorkflowEvent(WorkflowEventType.PROPOSAL_TERMINAL, proposal.proposal_id),
                            WorkflowEvent(WorkflowEventType.PLAN_NEXT_QUESTION),
                        ),
                    )
                except Exception:
                    pass
        elif conversation_id and proposal.status in {"conflicted", "failed", "expired"}:
            try:
                workflow_machine.dispatch(
                    conversation_id,
                    WorkflowEvent(WorkflowEventType.PROPOSAL_TERMINAL, proposal.proposal_id),
                )
            except Exception:
                pass
        _audit_after_result(
            action=f"proposal_{decision}",
            result_code=proposal.status,
            success=proposal.status in {"approved", "rejected"},
            request_id=proposal.request_id,
            proposal_id=proposal.proposal_id,
        )
        response = {
            "ok": True,
            "proposal_id": proposal.proposal_id,
            "status": proposal.status,
            "read_only": True,
        }
        if next_question is not None:
            response["next_question"] = next_question
        return jsonify(response)

    @app.post("/api/orchestrator/proposals/undo")
    def create_orchestrator_undo_proposal():
        """Request one server-evidenced inverse Proposal; never restore State."""

        payload = request.get_json(silent=True)
        if not isinstance(payload, Mapping) or set(payload) != {"proposal_id"}:
            return jsonify({"ok": False, "error": "invalid_undo_payload", "read_only": True}), 400
        proposal_id = payload.get("proposal_id")
        if not isinstance(proposal_id, str) or not proposal_id or len(proposal_id) > 256:
            return jsonify({"ok": False, "error": "invalid_undo_payload", "read_only": True}), 400
        result = proposal_service.create_undo_proposal(proposal_id)
        if result.code == "undo_proposal_not_found":
            return jsonify({"ok": False, "error": result.code, "read_only": True}), 404
        if result.proposal is None:
            # The original Proposal was server-read by ProposalService; only its
            # stable outcome is observed, never inverse evidence or operations.
            try:
                original = proposal_service.read_proposal(proposal_id)
            except ProposalNotFoundError:
                original = None
            if original is not None:
                _audit_after_result(
                    action="proposal_undo",
                    result_code=result.code,
                    success=False,
                    request_id=original.request_id,
                    proposal_id=original.proposal_id,
                )
            return jsonify({"ok": True, "kind": "undo_unavailable", "code": result.code, "read_only": True})
        proposal = result.proposal
        _audit_after_result(
            action="proposal_undo",
            result_code=result.code,
            success=True,
            request_id=proposal.request_id,
            proposal_id=proposal.proposal_id,
        )
        return jsonify(
            {
                "ok": True,
                "kind": result.code,
                "proposal": {
                    "proposal_id": proposal.proposal_id,
                    "status": proposal.status,
                    "diff": {**deepcopy(proposal.diff_summary), "read_only": True},
                },
                "read_only": True,
            }
        )

    @app.post("/api/orchestrator/case-matrix/action")
    def run_orchestrator_case_matrix_action():
        """Run one explicit read-only Matrix action from the panel Request id."""

        payload = request.get_json(silent=True)
        if not isinstance(payload, Mapping) or set(payload) != {"request_id"}:
            return jsonify({"ok": False, "error": "invalid_case_matrix_action_payload", "read_only": True}), 400
        request_id = payload.get("request_id")
        if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
            return jsonify({"ok": False, "error": "invalid_case_matrix_action_payload", "read_only": True}), 400

        result = case_matrix_action_service.run(request_id)
        payload = {
            "ok": result.code == "case_matrix_ready",
            "kind": result.code,
            "request_id": result.request_id,
            "request_version": result.request_version,
            "blocking_reasons": list(result.blocking_reasons),
            "matrix_summary": result.matrix_summary,
            "read_only": True,
            "state_changed": False,
        }
        status = 200 if result.code in {"case_matrix_ready", "case_matrix_blocked", "request_version_conflict"} else 404 if result.code == "request_not_found" else 503
        if result.code != "request_not_found":
            _audit_after_result(
                action="case_matrix_action",
                result_code=result.code,
                success=result.code == "case_matrix_ready",
                request_id=result.request_id,
            )
        return jsonify(payload), status

    @app.post("/api/orchestrator/validation/action")
    def run_orchestrator_validation_action():
        """Run one explicit read-only Validator action from the panel Request id."""

        payload = request.get_json(silent=True)
        if not isinstance(payload, Mapping) or set(payload) != {"request_id"}:
            return jsonify({"ok": False, "error": "invalid_validation_action_payload", "read_only": True}), 400
        request_id = payload.get("request_id")
        if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
            return jsonify({"ok": False, "error": "invalid_validation_action_payload", "read_only": True}), 400

        result = validation_action_service.run(request_id)
        response_payload = {
            "ok": result.code == "validation_ready",
            "kind": result.code,
            "request_id": result.request_id,
            "request_version": result.request_version,
            "validation": result.validation,
            "read_only": True,
            "state_changed": False,
        }
        status = 200 if result.code in {"validation_ready", "validation_blocked", "request_version_conflict"} else 404 if result.code == "request_not_found" else 503
        if result.code != "request_not_found":
            _audit_after_result(
                action="validation_action",
                result_code=result.code,
                success=result.code == "validation_ready",
                request_id=result.request_id,
            )
        return jsonify(response_payload), status

    @app.post("/api/orchestrator/preview/action")
    def run_orchestrator_preview_action():
        """Read one fenced server snapshot for the existing browser Preview."""

        payload = request.get_json(silent=True)
        if not isinstance(payload, Mapping) or set(payload) != {"request_id"}:
            return jsonify({"ok": False, "error": "invalid_preview_action_payload", "read_only": True}), 400
        request_id = payload.get("request_id")
        if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
            return jsonify({"ok": False, "error": "invalid_preview_action_payload", "read_only": True}), 400

        result = preview_action_service.run(request_id)
        response_payload = {
            "ok": result.code == "preview_ready",
            "kind": result.code,
            "request_id": result.request_id,
            "request_version": result.request_version,
            "state": result.state,
            "read_only": True,
            "state_changed": False,
        }
        status = 200 if result.code in {"preview_ready", "request_version_conflict"} else 404 if result.code == "request_not_found" else 503
        if result.code != "request_not_found":
            _audit_after_result(
                action="preview_action",
                result_code=result.code,
                success=result.code == "preview_ready",
                request_id=result.request_id,
            )
        return jsonify(response_payload), status

    @app.post("/api/orchestrator/rag-guidance/action")
    def run_orchestrator_rag_guidance_action():
        """Display existing RAG evidence for one explicit document question only."""

        payload = request.get_json(silent=True)
        if not isinstance(payload, Mapping) or set(payload) != {"request_id", "question"}:
            return jsonify({"ok": False, "error": "invalid_rag_guidance_action_payload", "read_only": True, "state_changed": False}), 400
        request_id = payload.get("request_id")
        question = payload.get("question")
        if (
            not isinstance(request_id, str)
            or not request_id
            or len(request_id) > 256
            or not isinstance(question, str)
            or len(question) > 4000
        ):
            return jsonify({"ok": False, "error": "invalid_rag_guidance_action_payload", "read_only": True, "state_changed": False}), 400

        result = rag_guidance_action_service.run(request_id, question)
        response_payload = {
            "ok": result.code in {"rag_guidance_ready", "rag_guidance_no_result", "rag_guidance_disabled"},
            "kind": result.code,
            "request_id": result.request_id,
            "qa": result.qa,
            "read_only": True,
            "state_changed": False,
        }
        status = 200 if result.code in {"rag_guidance_ready", "rag_guidance_no_result", "rag_guidance_disabled", "rag_guidance_error", "request_version_conflict"} else 404 if result.code == "request_not_found" else 400 if result.code in {"invalid_rag_guidance_question", "rag_guidance_requires_document_question"} else 503
        if result.code not in {"request_not_found", "invalid_rag_guidance_question", "rag_guidance_requires_document_question"}:
            _audit_after_result(
                action="rag_guidance_action",
                result_code=result.code,
                success=result.code in {"rag_guidance_ready", "rag_guidance_no_result", "rag_guidance_disabled"},
                request_id=result.request_id,
            )
        return jsonify(response_payload), status

    @app.get("/")
    def index() -> str:
        return HTML_TEMPLATE.replace("__APP_VERSION__", APP_VERSION)

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "app": "request_ai_agent_h6_v0", "version": APP_VERSION})

    @app.get("/api/product-hierarchy")
    def product_hierarchy():
        return jsonify(
            {
                "ok": True,
                "version": APP_VERSION,
                "stage": STAGE_NAME,
                **build_product_hierarchy_payload(),
            }
        )

    @app.get("/api/heat-exchanger-catalog")
    def heat_exchanger_catalog():
        return jsonify(
            {
                "ok": True,
                "version": APP_VERSION,
                "stage": STAGE_NAME,
                **build_heat_exchanger_catalog_payload(),
            }
        )

    @app.post("/api/request-context/confirm")
    def request_context_confirm():
        default_state = _derive_state()
        payload_map = _payload_mapping()
        raw_state = payload_map.get("state") if isinstance(payload_map.get("state"), Mapping) else _state_from_request(default_state)
        raw_context = payload_map.get("request_context")
        if not isinstance(raw_context, Mapping):
            raw_context = _as_mapping(_as_mapping(raw_state).get(SECTION_REQUEST_CONTEXT))
        try:
            state, fieldset = _context_confirm_state(raw_state, raw_context)
        except ValueError as exc:
            if str(exc).startswith("disabled_analysis_type:"):
                return jsonify({"ok": False, "version": APP_VERSION, "stage": STAGE_NAME, "message": "선택한 해석유형은 추후 지원 예정입니다."}), 400
            if str(exc).startswith("unsupported_analysis_type:"):
                return jsonify({"ok": False, "version": APP_VERSION, "stage": STAGE_NAME, "message": "지원하지 않는 해석유형입니다."}), 400
            missing = str(exc).removeprefix("missing_context:").split(",") if str(exc).startswith("missing_context:") else []
            return jsonify(
                {
                    "ok": False,
                    "version": APP_VERSION,
                    "stage": STAGE_NAME,
                    "message": "사업부, 제품군, platform, 해석유형을 모두 선택해 주세요.",
                    "missing_fields": [item for item in missing if item],
                }
            ), 400
        response = _response_payload(state, timestamp_key="context_confirmed_at")
        response.update(
            {
                "assistant": "선택한 조합 기준으로 입력항목을 준비했습니다.",
                "fieldset": fieldset,
                "request_context": state.get(SECTION_REQUEST_CONTEXT, {}),
                "state_changed": True,
            }
        )
        return jsonify(response)
    @app.post("/api/request-context/fieldset")
    def request_context_fieldset():
        default_state = _derive_state()
        payload_map = _payload_mapping()
        raw_state = payload_map.get("state") if isinstance(payload_map.get("state"), Mapping) else _state_from_request(default_state)
        raw_context = payload_map.get("request_context")
        if not isinstance(raw_context, Mapping):
            raw_context = _as_mapping(_as_mapping(raw_state).get(SECTION_REQUEST_CONTEXT))
        try:
            state, fieldset = _context_fieldset_state(raw_state, raw_context)
        except ValueError as exc:
            if str(exc).startswith("disabled_analysis_type:"):
                return jsonify({"ok": False, "version": APP_VERSION, "stage": STAGE_NAME, "message": "선택한 해석유형은 추후 지원 예정입니다."}), 400
            if str(exc).startswith("unsupported_analysis_type:"):
                return jsonify({"ok": False, "version": APP_VERSION, "stage": STAGE_NAME, "message": "지원하지 않는 해석유형입니다."}), 400
            missing = str(exc).removeprefix("missing_context:").split(",") if str(exc).startswith("missing_context:") else []
            return jsonify(
                {
                    "ok": False,
                    "version": APP_VERSION,
                    "stage": STAGE_NAME,
                    "message": "request_context is incomplete.",
                    "missing_fields": [item for item in missing if item],
                }
            ), 400
        response = _response_payload(state, timestamp_key="condition_fieldset_refreshed_at")
        response.update(
            {
                "assistant": "운전 구분 기준으로 해석조건 입력항목을 갱신했습니다.",
                "fieldset": fieldset,
                "request_context": state.get(SECTION_REQUEST_CONTEXT, {}),
                "state_changed": True,
            }
        )
        return jsonify(response)
    @app.get("/api/bootstrap")
    def bootstrap():
        state = _derive_state()
        heat_exchanger_catalog = build_heat_exchanger_catalog_payload()
        return jsonify(
            {
                "ok": True,
                "version": APP_VERSION,
                "layout": {
                    "left": ["input"],
                    "right": ["chat"],
                },
                "schema": get_public_schema(),
                "state": state,
                "heat_exchanger_catalog": heat_exchanger_catalog,
                "stage_progress": _stage_progress(state),
                "case_matrix": state.get("case_matrix", {}),
                "validation": state.get("review", {}).get("validator", {}),
                "llm": llm_status(),
                "embedding": embedding_status(),
                "feature_locks": FEATURE_LOCKS,
                "api": {
                    "save_input": "/api/input/save",
                    "refresh_preview": "/api/preview",
                    "select_analysis_type": "/api/analysis-type/select",
                    "analysis_result_guidance": "/api/analysis-type-guidance",
                    "confirm_request_context": "/api/request-context/confirm",
                    "refresh_request_context_fieldset": "/api/request-context/fieldset",
                    "chat_instant": "/api/chat/instant",
                    "chat_propose": "/api/chat/propose",
                    "chat_apply": "/api/chat/apply",
                    "chat_reject": "/api/chat/reject",
                    "chat_send": "/api/chat/send",
                    "rag_qa": "/api/rag/qa",
                    "product_hierarchy": "/api/product-hierarchy",
                    "heat_exchanger_catalog": "/api/heat-exchanger-catalog",
                    "llm_status": "/api/llm/status",
                    "rag_status": "/api/rag/status",
                    "bootstrap": "/api/bootstrap",
                    "health": "/api/health",
                },
                "stage": STAGE_NAME,
            }
        )

    @app.post("/api/request/new")
    def new_request():
        state = _derive_state()
        response = _response_payload(state, timestamp_key="new_request_started_at")
        response.update(
            {
                "assistant": "새 해석 의뢰를 시작합니다.",
                "state_changed": True,
            }
        )
        return jsonify(response)

    @app.post("/api/input/save")
    def save_input():
        default_state = _derive_state()
        state = _derive_state(_state_from_request(default_state))
        response = _response_payload(state, timestamp_key="saved_at")
        return jsonify(response)

    @app.post("/api/preview")
    def preview():
        default_state = _derive_state()
        state = _derive_state(_state_from_request(default_state))
        response = _response_payload(state, timestamp_key="refreshed_at")
        return jsonify(response)

    @app.post("/api/document-preview")
    def document_preview():
        return _disabled_feature_payload("preview_screen")
        default_state = _derive_state()
        state = _derive_state(_state_from_request(default_state))
        preview_document = build_request_preview(state)
        state.setdefault("review", {})
        state["review"]["preview_document"] = preview_document
        response = _response_payload(state, timestamp_key="previewed_at")
        response.update(
            {
                "preview_document": preview_document,
                "state_changed": False,
            }
        )
        return jsonify(response)

    @app.post("/api/export/word")
    def word_export_download():
        payload = request.get_json(silent=True)
        preview_dom = _as_mapping(payload)
        content = build_word_docx(preview_dom)
        return send_file(
            BytesIO(content),
            mimetype=DOCX_MIMETYPE,
            as_attachment=True,
            download_name=word_filename(),
        )

    @app.get("/api/llm/status")
    def llm_status_api():
        return jsonify(
            {
                "ok": True,
                "version": APP_VERSION,
                "stage": STAGE_NAME,
                "checked_at": _utc_now(),
                "llm": llm_status(),
            }
        )

    @app.get("/api/rag/status")
    def rag_status_api():
        return jsonify(
            {
                "ok": True,
                "version": APP_VERSION,
                "stage": STAGE_NAME,
                "checked_at": _utc_now(),
                "llm": llm_status(),
                "embedding": embedding_status(),
            }
        )

    @app.post("/api/analysis-type/recommend")
    def recommend_analysis_type():
        return _disabled_feature_payload("analysis_type_recommendation")
        payload = request.get_json(silent=True)
        payload_map = payload if isinstance(payload, Mapping) else {}
        request_state = _state_from_request(_derive_state())
        if isinstance(payload_map.get("state"), Mapping):
            request_state = payload_map["state"]
        result = recommend_analysis_types(
            str(payload_map.get("message", "") or ""),
            product_family=str(payload_map.get("product_family", "") or ""),
            rag_enabled=_rag_enabled(request_state),
        )
        return jsonify(
            {
                "ok": True,
                "version": APP_VERSION,
                "stage": STAGE_NAME,
                "recommended_at": _utc_now(),
                **result,
                "state_changed": False,
            }
        )

    @app.post("/api/analysis-type/select")
    def select_analysis_type():
        default_state = _derive_state()
        payload = request.get_json(silent=True)
        payload_map = payload if isinstance(payload, Mapping) else {}
        analysis_type = str(payload_map.get("analysis_type", "") or "")
        base_state = _state_from_request(default_state)
        if not analysis_type:
            return jsonify({"ok": False, "message": "analysis_type is required.", "stage": STAGE_NAME}), 400
        canonical = canonical_analysis_type(analysis_type)
        if is_demo_analysis_type(analysis_type):
            state = apply_demo_analysis_type_state(base_state)
            assistant = "데모용 해석유형을 선택하고 해석 개요, 형상 정보, 기본 조건을 자동 입력했습니다."
            action_proposal = None
        elif canonical in DISABLED_ANALYSIS_TYPE_OPTIONS:
            return jsonify({"ok": False, "message": "선택한 해석유형은 추후 지원 예정입니다.", "stage": STAGE_NAME}), 400
        elif canonical not in ENABLED_ANALYSIS_TYPE_OPTIONS:
            return jsonify({"ok": False, "message": "지원하지 않는 해석유형입니다.", "stage": STAGE_NAME}), 400
        else:
            state = apply_analysis_type_selection(
                base_state,
                canonical,
                rag_enabled=False,
                inject_candidates=False,
                assign_request_no=False,
            )
            assistant = _analysis_type_guidance_message(state, canonical)
            action_proposal = None
        response = _response_payload(state, timestamp_key="selected_at")
        response.update(
            {
                "assistant": assistant,
                "action_proposal": action_proposal,
                "candidate_conditions": candidate_condition_summary(state),
                "state_changed": True,
            }
        )
        return jsonify(response)

    @app.get("/api/analysis-type-guidance")
    def analysis_type_guidance():
        selected = _clean_text(request.args.get("analysis_type"))
        try:
            return jsonify({"ok": True, **get_analysis_result_guidance(selected)})
        except LookupError as exc:
            return jsonify({"ok": False, "retryable": True, "message": str(exc)}), 503

    @app.post("/api/conditions/recommend")
    def recommend_conditions():
        return _disabled_feature_payload("condition_recommendation")
        default_state = _derive_state()
        payload = request.get_json(silent=True)
        payload_map = payload if isinstance(payload, Mapping) else {}
        base_state = _derive_state(_state_from_request(default_state))
        overview = _as_mapping(base_state.get("analysis_overview"))
        analysis_type = _clean_text(payload_map.get("analysis_type")) or _clean_text(field_value(overview.get("analysis_type"), ""))
        if not analysis_type:
            return jsonify({"ok": False, "message": "해석유형을 먼저 선택해 주세요.", "stage": STAGE_NAME}), 400
        recommendation = condition_recommendation_payload(base_state, analysis_type, rag_enabled=_rag_enabled(base_state))
        operations = recommendation.get("operations") if isinstance(recommendation.get("operations"), list) else []
        proposal = proposal_from_operations(
            f"{analysis_type} AI 조건 추천",
            operations,
            source="condition_recommendation",
            summary="AI 조건 추천 후보",
            state=base_state,
        )
        proposal["proposal_type"] = "condition_recommend_apply"
        proposal["items"] = recommendation.get("items", [])
        proposal = _store_pending_proposal(proposal, base_state)
        item_lines = [
            f"- {item.get('field_label')}: {item.get('value')}{(' ' + item.get('unit')) if item.get('unit') else ''}"
            for item in _as_list(recommendation.get("items"))
            if isinstance(item, Mapping)
        ]
        assistant = "AI가 자주 쓰이는 조건 후보를 찾았습니다.\n" + "\n".join(item_lines[:8])
        if len(item_lines) > 8:
            assistant += "\n- 등"
        assistant += "\n\n이대로 반영할까요?"
        return jsonify(
            {
                "ok": True,
                "version": APP_VERSION,
                "stage": STAGE_NAME,
                "recommended_at": _utc_now(),
                "assistant": assistant,
                "proposal": proposal,
                "condition_recommendation": recommendation,
                "state_changed": False,
            }
        )

    @app.post("/api/draft")
    def draft():
        default_state = _derive_state()
        payload = request.get_json(silent=True)
        payload_map = payload if isinstance(payload, Mapping) else {}
        base_state = _state_from_request(default_state)
        rag_package = payload_map.get("rag_package")
        rag_package_map = rag_package if isinstance(rag_package, Mapping) else None
        draft_payload = build_request_draft(
            base_state,
            rag_package=rag_package_map,
            use_rag=bool(payload_map.get("use_rag", False)) and _rag_enabled(base_state),
            rag_question=str(payload_map.get("rag_question", "") or "") or _draft_rag_question(base_state),
            db_root_path=str(payload_map.get("db_root_path", "") or "") or None,
        )
        llm_payload: dict[str, Any] = {"used": False, "status": llm_status()}
        document = draft_payload.get("document") if isinstance(draft_payload.get("document"), Mapping) else {}
        markdown = str(document.get("markdown", "") or "") if isinstance(document, Mapping) else ""
        evidence = document.get("evidence_summary", {}) if isinstance(document, Mapping) else {}
        sources = evidence.get("sources", []) if isinstance(evidence, Mapping) else []
        if draft_payload.get("status") == "ready" and markdown and llm_payload["status"].get("ready"):
            try:
                llm_payload = synthesize_request_draft(markdown, sources if isinstance(sources, list) else [])
                if llm_payload.get("markdown") and isinstance(document, dict):
                    document["markdown_structured"] = markdown
                    document["llm_markdown_suggestion"] = llm_payload["markdown"]
                    document["llm"] = llm_payload
                    draft_payload["document"] = document
            except Exception as exc:  # pragma: no cover - network/config dependent
                llm_payload = {"used": False, "error": str(exc), "status": llm_status()}
        state = _derive_state(base_state)
        state["review"]["draft"] = draft_payload
        response = _response_payload(state, timestamp_key="drafted_at")
        response.update(
            {
                "draft": draft_payload,
                "assistant": "해석 의뢰서 초안을 생성했습니다."
                if draft_payload.get("status") == "ready"
                else "초안 생성 전 blocking 항목을 먼저 보완해야 합니다.",
                "state_changed": False,
                "structured_state_changed": False,
                "llm": llm_payload,
            }
        )
        return jsonify(response)

    @app.post("/api/review")
    def final_review():
        default_state = _derive_state()
        payload = request.get_json(silent=True)
        payload_map = payload if isinstance(payload, Mapping) else {}
        base_state = _state_from_request(default_state)
        draft_payload = payload_map.get("draft")
        approved_draft = _approve_draft_suggestion(
            draft_payload if isinstance(draft_payload, Mapping) else _as_mapping(_as_mapping(base_state.get("review")).get("draft")),
            approve=bool(payload_map.get("approve_draft_suggestion", True)),
        )
        review_base_state = (
            approve_candidate_conditions(base_state)
            if bool(payload_map.get("approve_candidates", False))
            else base_state
        )
        state = state_with_final_review(
            review_base_state,
            draft_payload=approved_draft,
        )
        review_payload = state["review"]["final_review"]
        response = _response_payload(state, timestamp_key="reviewed_at")
        response.update(
            {
                "final_review": review_payload,
                "final_payload": review_payload.get("final_payload"),
                "assistant": "제출 가능한 상태입니다."
                if review_payload.get("can_submit")
                else "제출 전 blocking 항목을 수정해야 합니다.",
                "state_changed": False,
                "structured_state_changed": False,
            }
        )
        return jsonify(response)

    @app.post("/api/submit")
    def submit():
        default_state = _derive_state()
        payload = request.get_json(silent=True)
        payload_map = payload if isinstance(payload, Mapping) else {}
        base_state = _state_from_request(default_state)
        submit_base_state = (
            approve_candidate_conditions(base_state)
            if bool(payload_map.get("approve_candidates", False))
            else base_state
        )
        state = state_with_validation(submit_base_state)
        validation = _as_mapping(_as_mapping(state.get("review")).get("validator"))
        summary = _as_mapping(validation.get("summary"))
        can_submit = bool(summary.get("can_submit", False))
        if can_submit and not _request_no(state):
            submit_base_state = deepcopy(dict(submit_base_state))
            metadata = dict(submit_base_state.get("metadata") if isinstance(submit_base_state.get("metadata"), Mapping) else {})
            metadata["request_no"] = generate_request_no(sequence=int(uuid4().hex[:8], 16) % 999_999_999 + 1)
            metadata["request_no_generated"] = True
            submit_base_state["metadata"] = metadata
            state = state_with_validation(submit_base_state)
            validation = _as_mapping(_as_mapping(state.get("review")).get("validator"))
            summary = _as_mapping(validation.get("summary"))
            can_submit = bool(summary.get("can_submit", False))
        blocking = [dict(item) for item in _as_list(validation.get("blocking")) if isinstance(item, Mapping)]
        warnings = [dict(item) for item in _as_list(validation.get("warning")) if isinstance(item, Mapping)]
        review_payload = {
            "status": "OK" if can_submit else "NG",
            "can_submit": can_submit,
            "decision_basis": "structured_state_and_active_fieldset",
            "blocking_reasons": blocking,
            "warnings": warnings,
            "edit_guidance": [
                {
                    "path": _clean_text(item.get("path")) or _clean_text(item.get("section")),
                    "section": _clean_text(item.get("section")),
                    "field_key": _clean_text(item.get("field_key")),
                    "field_label": _clean_text(item.get("field_label")),
                    "message": _clean_text(item.get("message")),
                    "action": _clean_text(item.get("action")) or "입력값을 보완해 주세요.",
                    "ui_anchor": _clean_text(item.get("field_label")) or _clean_text(item.get("section")) or "의뢰 검토",
                }
                for item in blocking
            ],
            "final_validator": validation,
            "final_payload": None,
        }
        state.setdefault("review", {})
        state["review"]["final_review"] = review_payload
        state["review"]["submission"] = {
            "status": "OK" if can_submit else "NG",
            "can_submit": can_submit,
            "blocking_reasons": [item.get("code", "") for item in blocking],
            "warning_reasons": [item.get("code", "") for item in warnings],
        }
        db_upload = _disabled_db_upload()
        db_upload_text = ""
        assistant = (
            f"의뢰서 상태: OK\n해석 의뢰번호: {_request_no(state)}"
            if can_submit
            else "의뢰서 상태: NG\n누락/보완 항목을 확인해 주세요."
        )
        if db_upload_text:
            assistant = f"{assistant}\n{db_upload_text}"
        response = _response_payload(state, timestamp_key="submit_checked_at")
        response.update(
            {
                "final_review": review_payload,
                "final_payload": review_payload.get("final_payload"),
                "db_upload": db_upload,
                "assistant": assistant,
                "state_changed": False,
                "structured_state_changed": False,
            }
        )
        return jsonify(response)

    @app.post("/api/chat/instant")
    def chat_instant():
        default_state = _derive_state()
        payload = request.get_json(silent=True)
        payload_map = payload if isinstance(payload, Mapping) else {}
        message = str(payload_map.get("message", "") or "")
        base_state = _state_from_request(default_state)
        result = _proposal_response_with_llm(message, base_state)
        proposal = result.get("proposal", {})
        if proposal.get("status") == "pending":
            proposal = _store_pending_proposal(proposal, base_state)
            response = _response_payload(base_state, timestamp_key="proposed_at")
            response.update(
                {
                    "assistant": "입력값을 후보 patch로 해석했습니다. 승인 전에는 의뢰서 state를 변경하지 않습니다.",
                    "proposal": proposal,
                    "state_changed": False,
                    "candidate_conditions": candidate_condition_summary(base_state),
                }
            )
            return jsonify(response)
        return jsonify(
            {
                "ok": True,
                "version": APP_VERSION,
                "stage": STAGE_NAME,
                "assistant": "바로 반영할 명확한 입력값을 찾지 못했습니다. 질문은 문서검색/RAG로 답변할 수 있습니다.",
                "proposal": proposal,
                "state_changed": False,
            }
        )

    @app.post("/api/chat/propose")
    def chat_propose():
        default_state = _derive_state()
        payload = request.get_json(silent=True)
        payload_map = payload if isinstance(payload, Mapping) else {}
        message = str(payload_map.get("message", "") or "")
        base_state = _state_from_request(default_state)
        result = _proposal_response_with_llm(message, base_state)
        proposal = result.get("proposal", {})
        if isinstance(proposal, Mapping) and proposal.get("status") == "pending":
            proposal = _store_pending_proposal(proposal, base_state)
        return jsonify(
            {
                "ok": True,
                "version": APP_VERSION,
                "stage": STAGE_NAME,
                "proposed_at": _utc_now(),
                "assistant": result["assistant"],
                "proposal": proposal,
                "dry_run": result["dry_run"],
                "llm_form_extraction": result.get("llm_form_extraction", {"used": False}),
                "state_changed": False,
            }
        )

    @app.post("/api/chat/apply")
    def chat_apply():
        default_state = _derive_state()
        payload = request.get_json(silent=True)
        payload_map = payload if isinstance(payload, Mapping) else {}
        requested_proposal = _proposal_from_request(payload_map)
        proposal = requested_proposal
        if not proposal:
            return jsonify({"ok": True, "state_changed": False, "assistant": "이미 처리되었거나 만료된 제안입니다. 새 제안을 받아 주세요.", "proposal": {**dict(requested_proposal), "status": "invalidated", "state_changed": False}, "proposal_recovery_action": "request_new_proposal"})
        base_state = _state_from_request(default_state)
        stale_reasons = _proposal_stale_reasons(proposal, base_state)
        if stale_reasons:
            return jsonify({"ok": True, "state_changed": False, "assistant": "제안 기준이 변경되어 반영할 수 없습니다. 새 제안을 받아 주세요.", "proposal": {**dict(proposal), "status": "invalidated", "state_changed": False, "invalidation_reasons": stale_reasons}, "proposal_recovery_action": "request_new_proposal"})
        operations = proposal.get("operations") if isinstance(proposal, Mapping) else []
        if not isinstance(operations, list) or not operations:
            return (
                jsonify(
                    {
                        "ok": False,
                        "version": APP_VERSION,
                        "stage": STAGE_NAME,
                        "message": "No patch operations were approved.",
                        "state_changed": False,
                    }
                ),
                400,
            )
        state = apply_patch_operations(base_state, operations)
        if any(_clean_text(_as_mapping(operation).get("path")) == "analysis_overview.decision_use" for operation in operations):
            overview = dict(_as_mapping(state.get(SECTION_ANALYSIS_OVERVIEW)))
            decision_use = dict(_as_mapping(overview.get("decision_use")))
            decision_use["source"] = "agent_approved"
            overview["decision_use"] = decision_use
            state[SECTION_ANALYSIS_OVERVIEW] = state_with_validation(state)[SECTION_ANALYSIS_OVERVIEW]
        response = _response_payload(state, timestamp_key="applied_at")
        response.update(
            {
                "proposal": {**dict(proposal), "status": "applied", "state_changed": True},
                "state_changed": True,
            }
        )
        return jsonify(response)

    @app.post("/api/chat/reject")
    def chat_reject():
        payload = request.get_json(silent=True)
        payload_map = payload if isinstance(payload, Mapping) else {}
        proposal = _proposal_from_request(payload_map)
        return jsonify(
            {
                "ok": True,
                "version": APP_VERSION,
                "stage": STAGE_NAME,
                "rejected_at": _utc_now(),
                "proposal": {**dict(proposal), "status": "rejected", "state_changed": False},
                "state_changed": False,
            }
        )

    @app.post("/api/rag/qa")
    def rag_qa():
        default_state = _derive_state()
        payload = request.get_json(silent=True)
        payload_map = payload if isinstance(payload, Mapping) else {}
        question = str(payload_map.get("question", payload_map.get("message", "")) or "")
        state = _state_from_request(default_state)
        if not _rag_enabled(state):
            qa = _rag_disabled_qa(question)
        else:
            qa = _run_rag_qa_read_only(
                question,
                state=state,
                top_k=int(payload_map.get("top_k", 5) or 5),
                source_types=payload_map.get("source_types") if isinstance(payload_map.get("source_types"), list) else _rag_source_types(state),
                db_root_path=str(payload_map.get("db_root_path", "") or "") or None,
                use_vector=bool(payload_map.get("use_vector", False)),
            )
        return jsonify(
            {
                "ok": True,
                "version": APP_VERSION,
                "stage": STAGE_NAME,
                "answered_at": _utc_now(),
                "assistant": qa.get("answer_text", ""),
                "qa": qa,
                "state_changed": False,
            }
        )

    @app.post("/api/chat/send")
    def chat_send():
        payload = request.get_json(silent=True)
        payload_map = payload if isinstance(payload, Mapping) else {}
        message = payload_map.get("message")
        conversation_id = payload_map.get("conversation_id")
        requested_mode = _chat_requested_mode(payload_map)
        if not isinstance(message, str) or not message.strip():
            return jsonify({"ok": False, "error": "invalid_message", "state_changed": False}), 400
        if not isinstance(conversation_id, str) or not conversation_id:
            return jsonify({"ok": False, "error": "invalid_conversation_id", "state_changed": False}), 400
        try:
            conversation = conversation_store.read(conversation_id)
            if conversation.status == "closed":
                raise ConversationStateError("conversation is closed")
            if conversation.paused or conversation.status == "paused":
                raise ConversationStateError("conversation is paused")
            request_snapshot = request_state_store.read(conversation.request_id)
        except (ConversationNotFoundError, RequestNotFoundError):
            return jsonify({"ok": False, "error": "conversation_request_not_found", "state_changed": False}), 404
        except ConversationStateError:
            return jsonify({"ok": False, "error": "conversation_not_active", "state_changed": False}), 409

        has_pending_proposal = False
        if (
            conversation.workflow_status == "awaiting_proposal_approval"
            and isinstance(conversation.pending_proposal_id, str)
            and conversation.pending_proposal_id
        ):
            try:
                has_pending_proposal = proposal_service.read_proposal(conversation.pending_proposal_id).status == "pending"
            except ProposalNotFoundError:
                has_pending_proposal = False

        planned_next_question = None
        if not has_pending_proposal:
            planned_next_question = plan_next_question(request_snapshot)
            conversation = synchronize_active_field(
                conversation_store,
                conversation,
                planned_next_question,
            )

        agent_context = build_agent_context(
            message,
            conversation,
            request_snapshot,
            has_pending_proposal=has_pending_proposal,
        )
        write_contract = build_agent_write_contract(request_snapshot.state)
        try:
            raw_decision = decide_agent_action(agent_context, write_contract)
            decision = raw_decision if isinstance(raw_decision, AgentDecision) else validate_agent_decision(raw_decision)
            if decision.action == "propose" and not operations_match_write_contract(decision.operations, write_contract):
                raise AgentDecisionError("operations_outside_write_contract")
        except Exception:
            return (
                jsonify(
                    {
                        "ok": False,
                        "assistant": LLM_FAILURE_MESSAGE,
                        "error": "agent_decision_failed",
                        "state_changed": False,
                    }
                ),
                503,
            )

        response = {
            "ok": True,
            "version": APP_VERSION,
            "stage": STAGE_NAME,
            "sent_at": _utc_now(),
            "assistant": decision.reply,
            "action": decision.action,
            "kind": decision.action,
            "chat_mode": {"requested": requested_mode, "resolved": decision.action},
            "state_changed": False,
            "read_only": True,
        }

        if decision.action == "propose" and has_pending_proposal:
            pending_reply = "현재 승인 대기 중인 변경 제안을 먼저 반영하거나 반영하지 않음으로 결정해 주세요."
            conversation_store.append_exchange(conversation_id, message, pending_reply)
            response.update(
                {
                    "assistant": pending_reply,
                    "action": "answer",
                    "kind": "pending_proposal_wait",
                    "pending_proposal_id": conversation.pending_proposal_id,
                }
            )
            return jsonify(response)

        if decision.action in {"answer", "clarify"}:
            active_field_id = None
            if decision.action == "clarify" and decision.active_field_id in writable_active_field_ids(agent_context, write_contract):
                active_field_id = decision.active_field_id
            updated_conversation = conversation_store.append_exchange(
                conversation_id,
                message,
                decision.reply,
                active_field_id=active_field_id,
            )
            if (
                decision.action == "answer"
                and decision.active_field_id != ANALYSIS_TYPE_FIELD_ID
                and planned_next_question is not None
            ):
                updated_conversation = apply_next_question(
                    conversation_store,
                    conversation_id,
                    planned_next_question,
                    prior_events=answer_planning_events(updated_conversation.workflow_status),
                )
                response["next_question"] = dict(planned_next_question)
            response["active_field_id"] = updated_conversation.active_field_id
            return jsonify(response)

        if conversation.workflow_status not in {"started", "awaiting_answer", "planning_next_question"}:
            return jsonify({"ok": False, "error": "workflow_not_ready_for_proposal", "state_changed": False}), 409
        try:
            proposal = proposal_service.create_proposal(
                conversation.request_id,
                decision.operations,
                source="main_agent_decision",
                message=message,
                client_base_version=request_snapshot.version,
            )
        except RequestVersionConflictError:
            return (
                jsonify(
                    {
                        "ok": False,
                        "assistant": "의뢰서가 변경되어 이전 상태를 기준으로 한 제안을 만들지 않았습니다. 다시 요청해 주세요.",
                        "error": "request_version_conflict",
                        "state_changed": False,
                    }
                ),
                409,
            )
        except ProposalValidationError:
            return jsonify({"ok": False, "assistant": LLM_FAILURE_MESSAGE, "error": "agent_decision_failed", "state_changed": False}), 503

        events = (WorkflowEvent(WorkflowEventType.PROPOSAL_CREATED, proposal.proposal_id),)
        if conversation.workflow_status == "started":
            events = (WorkflowEvent(WorkflowEventType.START), *events)
        try:
            workflow_machine.dispatch_many(conversation_id, events)
        except Exception:
            return jsonify({"ok": False, "error": "workflow_transition_failed", "state_changed": False}), 503
        proposal_conversations[proposal.proposal_id] = conversation_id
        conversation_store.append_exchange(conversation_id, message, decision.reply)
        response.update(
            {
                "proposal": {
                    "proposal_id": proposal.proposal_id,
                    "status": proposal.status,
                    "changes": proposal_changes(decision.operations, agent_context, write_contract),
                },
                "read_only": True,
            }
        )
        return jsonify(response)

    return app
