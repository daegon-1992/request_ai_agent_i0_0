"""Pure, deterministic next-question selection for the orchestrator.

The planner accepts caller-provided snapshots only.  In particular, it does
not read a Request/Conversation/Proposal store and does not dispatch workflow
events.  Field activation and validation remain owned by the existing
Fieldset/Validator output supplied in those snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .field_registry import FieldRegistryDTO, get_field_registry


MAX_QUESTION_HISTORY = 100
_PLANNING_STATE = "planning_next_question"


@dataclass(frozen=True)
class QuestionHistoryDTO:
    """A bounded, reference-only record of an earlier question."""

    field_id: str


@dataclass(frozen=True)
class NextFieldPlannerInput:
    """Read-only inputs supplied by the caller after its latest reads."""

    request_state: Mapping[str, Any]
    registry: tuple[FieldRegistryDTO, ...]
    question_history: tuple[QuestionHistoryDTO, ...]
    workflow_state: str
    validation: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class PlannedFieldDTO:
    field_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class NextFieldPlanDTO:
    """The non-empty deterministic selection for ``question_planned``."""

    kind: str
    fields: tuple[PlannedFieldDTO, ...]


@dataclass(frozen=True)
class ValidationReadyDecisionDTO:
    """A no-field decision for the workflow's ``validation_ready`` event."""

    kind: str
    reason: str
    fields: tuple[()] = ()


@dataclass(frozen=True)
class PlannerFailureDTO:
    """Stable, non-mutating result for an unreadable caller snapshot."""

    kind: str
    code: str
    fields: tuple[()] = ()


PlannerDecisionDTO = NextFieldPlanDTO | ValidationReadyDecisionDTO | PlannerFailureDTO


def planner_input_from_state(
    request_state: Mapping[str, Any],
    question_history: tuple[QuestionHistoryDTO, ...],
    workflow_state: str,
    validation: Mapping[str, Any] | None = None,
) -> NextFieldPlannerInput | PlannerFailureDTO:
    """Build an input with the existing Registry adapter, without persistence.

    This convenience boundary is intentionally separate from ``plan_next_fields``
    so services can instead pass a Registry snapshot obtained during their own
    latest Request read.
    """

    if not isinstance(request_state, Mapping):
        return PlannerFailureDTO("planner_failure", "invalid_request_state")
    try:
        registry = get_field_registry(request_state)
    except Exception:
        return PlannerFailureDTO("planner_failure", "registry_read_failed")
    return NextFieldPlannerInput(request_state, registry, question_history, workflow_state, validation)


def plan_next_fields(input_dto: NextFieldPlannerInput) -> PlannerDecisionDTO:
    """Choose at most two active unfilled fields using only snapshot values."""

    failure = _validate_input(input_dto)
    if failure is not None:
        return failure
    if input_dto.workflow_state != _PLANNING_STATE:
        return PlannerFailureDTO("planner_failure", "invalid_workflow_state")

    state_validation, validation_failure = _validation_from_state(input_dto.request_state)
    if validation_failure:
        return PlannerFailureDTO("planner_failure", "validation_read_failed")
    validation = input_dto.validation if input_dto.validation is not None else state_validation
    if _is_ready(input_dto.request_state, validation):
        return ValidationReadyDecisionDTO("validation_ready", "existing_validation_ready")

    candidates = [field for field in input_dto.registry if field.active and not _is_filled(input_dto.request_state, field)]
    if not candidates:
        return ValidationReadyDecisionDTO("validation_ready", "no_active_unfilled_fields")

    asked = {entry.field_id for entry in input_dto.question_history}
    dependency_ids = {dependency for field in candidates for dependency in field.dependencies}
    blockers = _blocker_paths(validation)
    ranked = sorted(
        candidates,
        key=lambda field: (
            _tier(field, dependency_ids, blockers),
            field.field_id in asked,
            field.field_id,
        ),
    )
    return NextFieldPlanDTO(
        "next_fields",
        tuple(_planned(field, dependency_ids, blockers, asked) for field in ranked[:2]),
    )


def _validate_input(input_dto: Any) -> PlannerFailureDTO | None:
    if not isinstance(input_dto, NextFieldPlannerInput):
        return PlannerFailureDTO("planner_failure", "invalid_planner_input")
    if not isinstance(input_dto.request_state, Mapping):
        return PlannerFailureDTO("planner_failure", "invalid_request_state")
    if not isinstance(input_dto.registry, tuple) or not all(isinstance(item, FieldRegistryDTO) for item in input_dto.registry):
        return PlannerFailureDTO("planner_failure", "invalid_registry_snapshot")
    if not isinstance(input_dto.question_history, tuple) or len(input_dto.question_history) > MAX_QUESTION_HISTORY or not all(
        isinstance(item, QuestionHistoryDTO) and bool(item.field_id) for item in input_dto.question_history
    ):
        return PlannerFailureDTO("planner_failure", "invalid_question_history")
    if not isinstance(input_dto.workflow_state, str):
        return PlannerFailureDTO("planner_failure", "invalid_workflow_state")
    if input_dto.validation is not None and not isinstance(input_dto.validation, Mapping):
        return PlannerFailureDTO("planner_failure", "invalid_validation_snapshot")
    return None


def _validation_from_state(state: Mapping[str, Any]) -> tuple[Mapping[str, Any], bool]:
    """Read existing validation without treating a malformed review as empty."""

    review = state.get("review")
    if review is None:
        return {}, False
    if not isinstance(review, Mapping):
        return {}, True
    validator = review.get("validator")
    if validator is None:
        return {}, False
    if not isinstance(validator, Mapping):
        return {}, True
    return validator, False


def _is_ready(state: Mapping[str, Any], validation: Mapping[str, Any]) -> bool:
    review = state.get("review")
    if isinstance(review, Mapping):
        for key in ("submission", "final_review"):
            item = review.get(key)
            if isinstance(item, Mapping) and item.get("can_submit") is True:
                return True
    summary = validation.get("summary")
    return isinstance(summary, Mapping) and summary.get("can_submit") is True


def _blocker_paths(validation: Mapping[str, Any]) -> tuple[str, ...]:
    blocking = validation.get("blocking")
    if not isinstance(blocking, list):
        return ()
    return tuple(
        str(item.get("path") or "")
        for item in blocking
        if isinstance(item, Mapping) and isinstance(item.get("path"), str)
    )


def _tier(field: FieldRegistryDTO, dependency_ids: set[str], blockers: tuple[str, ...]) -> int:
    if field.field_id in dependency_ids:
        return 0
    if _has_blocker(field, blockers):
        return 1
    return 2 if field.required else 3


def _planned(
    field: FieldRegistryDTO, dependency_ids: set[str], blockers: tuple[str, ...], asked: set[str]
) -> PlannedFieldDTO:
    reasons: list[str] = []
    if field.field_id in dependency_ids:
        reasons.append("unmet_dependency")
    if _has_blocker(field, blockers):
        reasons.append("validation_blocker")
    reasons.append("required" if field.required else "optional")
    if field.field_id in asked:
        reasons.append("previously_asked")
    return PlannedFieldDTO(field.field_id, tuple(reasons))


def _has_blocker(field: FieldRegistryDTO, blockers: tuple[str, ...]) -> bool:
    paths = (field.field_id, field.canonical_path, field.value_path, field.operation_path)
    return any(path and (blocker == path or blocker.startswith(f"{path}.")) for path in paths for blocker in blockers)


def _is_filled(state: Mapping[str, Any], field: FieldRegistryDTO) -> bool:
    value = _value_at_path(state, field.value_path)
    if isinstance(value, Mapping):
        value = value.get("value")
    if isinstance(value, list):
        return any(_has_text(item.get("value") if isinstance(item, Mapping) else item) for item in value)
    return _has_text(value)


def _value_at_path(state: Mapping[str, Any], path: str) -> Any:
    current: Any = state
    for segment in path.split("."):
        if "[card_id=" in segment:
            name, selector = segment.split("[card_id=", 1)
            card_id = selector.removesuffix("]")
            if not isinstance(current, Mapping) or not isinstance(current.get(name), list):
                return None
            current = next((item for item in current[name] if isinstance(item, Mapping) and item.get("id") == card_id), None)
        elif isinstance(current, Mapping):
            current = current.get(segment)
        else:
            return None
    return current


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) or isinstance(value, (int, float)) and not isinstance(value, bool)
