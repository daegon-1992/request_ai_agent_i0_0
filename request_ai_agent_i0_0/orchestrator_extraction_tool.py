"""Read-only natural-language extraction candidates for orchestration.

This adapter deliberately stops before Proposal creation.  It only calls the
existing structured-output extractor and ``sanitize_external_operations``;
callers own Request reads, Proposal creation, and every mutation.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .chat_patch import sanitize_external_operations
from .field_registry import FieldRegistryDTO, GeometryProductsAdapterDTO


Extractor = Callable[..., Mapping[str, Any]]


@dataclass(frozen=True)
class ExtractionToolInput:
    """Caller-owned snapshots and an injected structured-output callable."""

    message: str
    state_summary: Mapping[str, Any]
    allowed_fields: tuple[FieldRegistryDTO, ...]
    geometry_products_adapter: GeometryProductsAdapterDTO
    extractor: Extractor | None = None


@dataclass(frozen=True)
class ExtractionCandidateDTO:
    field_id: str
    candidate_value: str | tuple[str, ...]
    confidence: str
    evidence_phrase: str
    ambiguity: bool
    unit: str
    operation: Mapping[str, Any]


@dataclass(frozen=True)
class ExtractionReasonDTO:
    code: str
    operation_index: int | None = None
    field_id: str = ""


@dataclass(frozen=True)
class ExtractionCandidatesDTO:
    kind: str
    candidates: tuple[ExtractionCandidateDTO, ...]
    reasons: tuple[ExtractionReasonDTO, ...] = ()


@dataclass(frozen=True)
class ExtractionNoCandidateDTO:
    kind: str
    code: str
    candidates: tuple[()] = ()
    reasons: tuple[ExtractionReasonDTO, ...] = ()


@dataclass(frozen=True)
class ExtractionFailureDTO:
    kind: str
    code: str
    candidates: tuple[()] = ()
    reasons: tuple[ExtractionReasonDTO, ...] = ()


ExtractionToolResult = ExtractionCandidatesDTO | ExtractionNoCandidateDTO | ExtractionFailureDTO


def extract_candidates(input_dto: ExtractionToolInput) -> ExtractionToolResult:
    """Return sanitized candidate DTOs without reading or changing any store."""

    invalid = _validate_input(input_dto)
    if invalid:
        return ExtractionFailureDTO("failure", invalid)
    extractor = input_dto.extractor or _existing_extractor
    if extractor is None:
        return ExtractionFailureDTO("failure", "extractor_unavailable")
    try:
        extracted = extractor(
            input_dto.message,
            state_summary=deepcopy(input_dto.state_summary),
            schema=_extractor_schema(input_dto.allowed_fields, input_dto.geometry_products_adapter),
        )
    except json.JSONDecodeError:
        return ExtractionFailureDTO("failure", "invalid_json")
    except Exception:
        return ExtractionFailureDTO("failure", "extractor_error")

    payload = _payload_from_extractor_result(extracted)
    if payload is None:
        return ExtractionFailureDTO("failure", "invalid_structured_output")
    operations = payload.get("operations")
    if not isinstance(operations, (list, tuple)):
        return ExtractionFailureDTO("failure", "invalid_structured_output")
    if not operations:
        return ExtractionNoCandidateDTO("no_candidate", "no_operations")

    candidates: list[ExtractionCandidateDTO] = []
    reasons: list[ExtractionReasonDTO] = []
    for index, raw in enumerate(operations):
        candidate, reason = _candidate_from_operation(raw, index, input_dto)
        if candidate is not None:
            candidates.append(candidate)
        elif reason is not None:
            reasons.append(reason)
    if candidates:
        return ExtractionCandidatesDTO("candidates", tuple(candidates), tuple(reasons))
    return ExtractionNoCandidateDTO("no_candidate", reasons[0].code if reasons else "no_allowed_operations", reasons=tuple(reasons))


def _existing_extractor(message: str, *, state_summary: Mapping[str, Any], schema: Mapping[str, Any]) -> Mapping[str, Any]:
    from .llm_client import extract_form_patch_with_llm

    return extract_form_patch_with_llm(message, state_summary=state_summary, schema=schema)


def _validate_input(input_dto: Any) -> str | None:
    if not isinstance(input_dto, ExtractionToolInput):
        return "invalid_tool_input"
    if not isinstance(input_dto.message, str) or not isinstance(input_dto.state_summary, Mapping):
        return "invalid_tool_input"
    if not isinstance(input_dto.allowed_fields, tuple) or not all(isinstance(item, FieldRegistryDTO) for item in input_dto.allowed_fields):
        return "invalid_allowed_fields"
    if not isinstance(input_dto.geometry_products_adapter, GeometryProductsAdapterDTO):
        return "invalid_geometry_adapter"
    if input_dto.extractor is not None and not callable(input_dto.extractor):
        return "extractor_unavailable"
    return None


def _extractor_schema(fields: tuple[FieldRegistryDTO, ...], adapter: GeometryProductsAdapterDTO) -> dict[str, Any]:
    """Expose only caller-provided, read-only field metadata to the extractor."""

    return {
        "allowed_fields": [field.to_dict() for field in fields],
        "geometry_products_adapter": adapter.to_dict(),
    }


def _payload_from_extractor_result(extracted: Any) -> Mapping[str, Any] | None:
    if not isinstance(extracted, Mapping):
        return None
    payload = extracted.get("payload", extracted)
    return payload if isinstance(payload, Mapping) else None


def _candidate_from_operation(
    raw: Any, index: int, input_dto: ExtractionToolInput
) -> tuple[ExtractionCandidateDTO | None, ExtractionReasonDTO | None]:
    if not isinstance(raw, Mapping):
        return None, ExtractionReasonDTO("malformed_operation", index)
    operation = str(raw.get("op") or "").strip()
    if operation not in {"set", "list_values", "condition_values"}:
        return None, ExtractionReasonDTO("unsupported_operation", index)
    field_matches = _field_matches(raw, operation, input_dto)
    if not field_matches:
        return None, ExtractionReasonDTO("unknown_field", index)
    if len(field_matches) != 1:
        return None, ExtractionReasonDTO("ambiguous_field", index)
    field_id, unit = field_matches[0]
    if _is_ambiguous(raw):
        return None, ExtractionReasonDTO("ambiguous_value", index, field_id)
    if not _has_expected_value_shape(raw, operation):
        return None, ExtractionReasonDTO("missing_or_invalid_value", index, field_id)
    if unit and not _text(raw.get("unit")):
        return None, ExtractionReasonDTO("missing_unit", index, field_id)
    normalized = sanitize_external_operations([raw], source="llm_structured_output")
    if len(normalized) != 1:
        return None, ExtractionReasonDTO("missing_or_invalid_value", index, field_id)
    accepted = normalized[0]
    value = accepted.get("value") if accepted.get("op") == "set" else accepted.get("values")
    candidate_value: str | tuple[str, ...]
    if isinstance(value, list):
        candidate_value = tuple(str(item) for item in value)
    elif _text(value):
        candidate_value = str(value).strip()
    else:
        return None, ExtractionReasonDTO("missing_or_invalid_value", index, field_id)
    return (
        ExtractionCandidateDTO(
            field_id=field_id,
            candidate_value=candidate_value,
            confidence=str(accepted.get("confidence") or "medium"),
            evidence_phrase=_text(raw.get("evidence_phrase")),
            ambiguity=False,
            unit=_text(raw.get("unit")),
            operation=accepted,
        ),
        None,
    )


def _field_matches(raw: Mapping[str, Any], operation: str, input_dto: ExtractionToolInput) -> list[tuple[str, str]]:
    path = _text(raw.get("path"))
    field_key = _text(raw.get("field_key"))
    matches: list[tuple[str, str]] = []
    if operation == "list_values" and path == input_dto.geometry_products_adapter.transport_path:
        matches.append((path, ""))
    for field in input_dto.allowed_fields:
        if not field.active:
            continue
        if operation == "condition_values":
            if field.operation_path == path and field.field_key == field_key:
                matches.append((field.field_id, field.unit))
        elif field.operation_path == path:
            matches.append((field.field_id, field.unit))
    return matches


def _is_ambiguous(raw: Mapping[str, Any]) -> bool:
    value = raw.get("ambiguity", raw.get("ambiguous", False))
    return value is True or isinstance(value, str) and value.strip().lower() in {"ambiguous", "true", "yes"}


def _has_expected_value_shape(raw: Mapping[str, Any], operation: str) -> bool:
    """Reject malformed DTO values before the existing sanitizer projects them."""

    if operation == "set":
        value = raw.get("value")
        return isinstance(value, (str, int, float)) and not isinstance(value, bool)
    values = raw.get("values")
    return isinstance(values, (list, tuple)) and all(
        isinstance(value, (str, int, float)) and not isinstance(value, bool) for value in values
    )


def _text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()
