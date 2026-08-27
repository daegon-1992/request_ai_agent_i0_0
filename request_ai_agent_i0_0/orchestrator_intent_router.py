"""Pure, read-only routing of existing LLM structured-output intents.

This module intentionally classifies only caller-provided data.  It does not
call an extractor, sanitizer, store, workflow, or Q&A/RAG implementation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from .orchestrator_extraction_tool import (
    ExtractionCandidateDTO,
    ExtractionCandidatesDTO,
    ExtractionFailureDTO,
    ExtractionNoCandidateDTO,
    ExtractionReasonDTO,
    ExtractionToolResult,
)


LLM_CHAT_INTENTS = frozenset({"patch", "general_qa", "rag_qa", "current_input", "needs_clarification"})


@dataclass(frozen=True)
class IntentRouterInput:
    """Opaque caller snapshots; their contents are never interpreted as operations."""

    intent: Any
    extraction_payload: Mapping[str, Any] | None = None
    extraction_metadata: Mapping[str, Any] | None = None
    tool_result: ExtractionToolResult | None = None


@dataclass(frozen=True)
class IntentRouteReasonDTO:
    code: str


@dataclass(frozen=True)
class IntentRouteDTO:
    kind: str
    intent: str
    route_category: str
    reasons: tuple[IntentRouteReasonDTO, ...]
    extraction_metadata: Mapping[str, Any] | None
    patch_tool_outcome: str = "not_applicable"
    patch_tool_code: str = ""


@dataclass(frozen=True)
class IntentRouterFailureDTO:
    kind: str
    intent: str
    route_category: str
    code: str
    reasons: tuple[IntentRouteReasonDTO, ...]


IntentRouterResult = IntentRouteDTO | IntentRouterFailureDTO


def route_intent(input_dto: IntentRouterInput) -> IntentRouterResult:
    """Return a deterministic route DTO without performing downstream work."""

    invalid = _validate_input(input_dto)
    if invalid:
        return _failure(invalid)
    normalized = _normalize_intent(input_dto.intent)
    if normalized is None:
        return _clarification("missing_intent")
    if normalized not in LLM_CHAT_INTENTS:
        return _clarification("unknown_intent")
    metadata = deepcopy(dict(input_dto.extraction_metadata)) if input_dto.extraction_metadata is not None else None
    if normalized != "patch":
        return IntentRouteDTO("route", normalized, normalized, (IntentRouteReasonDTO(f"intent_{normalized}"),), metadata)
    outcome, code = _patch_tool_decision(input_dto.tool_result)
    return IntentRouteDTO(
        "route", "patch", "patch", (IntentRouteReasonDTO("intent_patch"), IntentRouteReasonDTO(f"tool_{outcome}")),
        metadata, outcome, code,
    )


def _validate_input(input_dto: Any) -> str | None:
    if not isinstance(input_dto, IntentRouterInput):
        return "invalid_router_input"
    if input_dto.extraction_payload is not None and not isinstance(input_dto.extraction_payload, Mapping):
        return "invalid_extraction_payload"
    if input_dto.extraction_metadata is not None and not isinstance(input_dto.extraction_metadata, Mapping):
        return "invalid_extraction_metadata"
    if input_dto.tool_result is not None and not _is_valid_tool_result(input_dto.tool_result):
        return "invalid_tool_result"
    return None


def _normalize_intent(intent: Any) -> str | None:
    if not isinstance(intent, str):
        return None
    normalized = intent.strip().lower()
    return normalized or None


def _is_valid_tool_result(result: Any) -> bool:
    if isinstance(result, ExtractionCandidatesDTO):
        return (
            result.kind == "candidates"
            and isinstance(result.candidates, tuple)
            and bool(result.candidates)
            and all(isinstance(item, ExtractionCandidateDTO) for item in result.candidates)
            and isinstance(result.reasons, tuple)
            and all(isinstance(item, ExtractionReasonDTO) for item in result.reasons)
        )
    if isinstance(result, ExtractionNoCandidateDTO):
        return (
            result.kind == "no_candidate" and _nonempty_text(result.code) and isinstance(result.reasons, tuple)
            and all(isinstance(item, ExtractionReasonDTO) for item in result.reasons)
        )
    if isinstance(result, ExtractionFailureDTO):
        return (
            result.kind == "failure" and _nonempty_text(result.code) and isinstance(result.reasons, tuple)
            and all(isinstance(item, ExtractionReasonDTO) for item in result.reasons)
        )
    return False


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _patch_tool_decision(result: ExtractionToolResult | None) -> tuple[str, str]:
    if result is None:
        return "not_provided", ""
    if isinstance(result, ExtractionCandidatesDTO):
        # A candidate list is not a selection authority.  Preserve the Tool
        # outcome, but make a plural list explicit for the service-owned
        # clarification boundary.
        return "candidates", "multiple_candidates" if len(result.candidates) != 1 else ""
    if isinstance(result, ExtractionNoCandidateDTO):
        return "no_candidate", result.code
    return "failure", result.code


def _clarification(code: str) -> IntentRouteDTO:
    return IntentRouteDTO("route", "needs_clarification", "needs_clarification", (IntentRouteReasonDTO(code),), None)


def _failure(code: str) -> IntentRouterFailureDTO:
    return IntentRouterFailureDTO("failure", "needs_clarification", "needs_clarification", code, (IntentRouteReasonDTO(code),))
