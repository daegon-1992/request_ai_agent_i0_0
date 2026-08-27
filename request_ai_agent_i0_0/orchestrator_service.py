"""Server-owned message orchestration without an HTTP or UI surface.

Only this small application service composes the existing read-only Tool and
Router with the server Request, Conversation, Registry, Proposal, and Planner
boundaries.  It never approves or applies a Proposal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .chat_patch import apply_patch_operations
from .conversation_store import ConversationSnapshot, ConversationStore
from .field_registry import FieldRegistryDTO, GeometryProductsAdapterDTO, get_field_registry, get_geometry_products_adapter
from .next_field_planner import (
    NextFieldPlannerInput,
    PlannerDecisionDTO,
    QuestionHistoryDTO,
    plan_next_fields,
)
from .orchestrator_extraction_tool import (
    Extractor,
    ExtractionCandidatesDTO,
    ExtractionToolInput,
    ExtractionToolResult,
    extract_candidates,
)
from .orchestrator_intent_router import IntentRouteDTO, IntentRouterInput, route_intent
from .proposal_store import ProposalService
from .request_state_store import RequestStateStore
from .workflow_machine import (
    ConversationWorkflowMachine,
    WorkflowContext,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowState,
    WorkflowTransitionError,
    transition,
)


RegistryReader = Callable[[Mapping[str, Any]], tuple[Any, ...]]
GeometryAdapterReader = Callable[[], GeometryProductsAdapterDTO]
Planner = Callable[[NextFieldPlannerInput], PlannerDecisionDTO]


@dataclass(frozen=True)
class OrchestratorMessageInput:
    """Untrusted caller message data; authority stays in injected stores."""

    conversation_id: str
    message: str
    intent: Any
    extraction_payload: Mapping[str, Any] | None = None
    extraction_metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class OrchestratorProposalResult:
    kind: str
    route_category: str
    proposal_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class OrchestratorReadOnlyResult:
    kind: str
    route_category: str
    reasons: tuple[str, ...]
    planner_decision: PlannerDecisionDTO | None = None


@dataclass(frozen=True)
class OrchestratorClarificationResult:
    """A server-owned question which has no Proposal or workflow effect."""

    kind: str
    route_category: str
    reasons: tuple[str, ...]
    question: str


@dataclass(frozen=True)
class OrchestratorFailureResult:
    kind: str
    code: str
    reasons: tuple[str, ...]


OrchestratorMessageResult = (
    OrchestratorProposalResult | OrchestratorReadOnlyResult | OrchestratorClarificationResult | OrchestratorFailureResult
)


class OrchestratorService:
    """Compose only server-owned reads with existing Proposal and workflow APIs."""

    def __init__(
        self,
        *,
        conversations: ConversationStore,
        requests: RequestStateStore,
        proposals: ProposalService,
        workflow: ConversationWorkflowMachine,
        extractor: Extractor | None = None,
        registry_reader: RegistryReader = get_field_registry,
        geometry_adapter_reader: GeometryAdapterReader = get_geometry_products_adapter,
        planner: Planner = plan_next_fields,
    ) -> None:
        self._conversations = conversations
        self._requests = requests
        self._proposals = proposals
        self._workflow = workflow
        self._extractor = extractor
        self._registry_reader = registry_reader
        self._geometry_adapter_reader = geometry_adapter_reader
        self._planner = planner

    def handle(self, input_dto: OrchestratorMessageInput) -> OrchestratorMessageResult:
        """Handle one message using server snapshots; never mutate Request State."""

        invalid = _validate_input(input_dto)
        if invalid:
            return _failure(invalid)
        conversation_result = self._read_active_conversation(input_dto.conversation_id)
        if isinstance(conversation_result, OrchestratorFailureResult):
            return conversation_result
        conversation = conversation_result

        # Non-patch routes deliberately do not invoke the extractor/LLM.
        initial_route = route_intent(
            IntentRouterInput(input_dto.intent, input_dto.extraction_payload, input_dto.extraction_metadata)
        )
        if not isinstance(initial_route, IntentRouteDTO):
            return _failure(initial_route.code)
        if initial_route.route_category != "patch":
            if initial_route.route_category == "needs_clarification":
                return _clarification(initial_route)
            return _read_only(initial_route)

        if not input_dto.message.strip():
            return _clarification(initial_route, extra_reasons=("empty_message",))

        snapshot = self._read_request(conversation.request_id)
        if isinstance(snapshot, OrchestratorFailureResult):
            return snapshot
        try:
            registry = self._registry_reader(snapshot.state)
            adapter = self._geometry_adapter_reader()
        except Exception:
            return _failure("registry_read_failed")
        tool_result = extract_candidates(
            ExtractionToolInput(input_dto.message, snapshot.state, registry, adapter, self._extractor)
        )
        route = route_intent(
            IntentRouterInput(input_dto.intent, input_dto.extraction_payload, input_dto.extraction_metadata, tool_result)
        )
        if not isinstance(route, IntentRouteDTO):
            return _failure(route.code)
        if route.patch_tool_outcome == "candidates" and isinstance(tool_result, ExtractionCandidatesDTO) and len(tool_result.candidates) == 1:
            candidate = tool_result.candidates[0]
            correction = _correction_decision(snapshot.state, candidate, registry, adapter)
            if correction == "same_value":
                return _clarification(route, extra_reasons=(correction,))
            if correction == "correction":
                return self._create_correction_proposal(input_dto, conversation, route, candidate, snapshot.version)
            # Keep the established initial-value Proposal behavior. H5-023
            # adds its correction boundary only after a canonical value exists.
            return self._create_proposal(input_dto, conversation, route, tool_result.candidates)
        if route.patch_tool_outcome in {"candidates", "no_candidate", "failure"}:
            return _clarification(route, tool_result)
        return _read_only(route)

    def _read_active_conversation(self, conversation_id: str) -> ConversationSnapshot | OrchestratorFailureResult:
        try:
            snapshot = self._conversations.read(conversation_id)
        except Exception:
            return _failure("conversation_read_failed")
        if snapshot.status == "closed":
            return _failure("conversation_closed")
        if snapshot.paused or snapshot.status == "paused":
            return _failure("conversation_paused")
        return snapshot

    def _read_request(self, request_id: str):
        try:
            return self._requests.read(request_id)
        except Exception:
            return _failure("request_read_failed")

    def _create_proposal(self, input_dto, conversation, route, candidates) -> OrchestratorMessageResult:
        # Validate the server workflow boundary before recording a Proposal so
        # invalid/closed/stale workflow inputs cannot leave a ledger record.
        preflight_events = _proposal_creation_events(conversation.workflow_status, "preflight")
        try:
            _transition_sequence(WorkflowContext.from_conversation(conversation), preflight_events)
        except WorkflowTransitionError as exc:
            return _failure(exc.code)
        try:
            proposal = self._proposals.create_proposal(
                conversation.request_id,
                tuple(candidate.operation for candidate in candidates),
                source="orchestrator_llm",
                message=input_dto.message,
            )
        except Exception:
            return _failure("proposal_creation_failed")
        try:
            self._workflow.dispatch_many(
                conversation.conversation_id,
                _proposal_creation_events(conversation.workflow_status, proposal.proposal_id),
            )
        except Exception:
            # This can only happen after an external lifecycle race.  The
            # existing runtime ledger has no delete/rollback API, so callers
            # receive a stable failure and must not treat the id as delivered.
            return _failure("workflow_transition_failed")
        return OrchestratorProposalResult("proposal_created", "patch", proposal.proposal_id, _reason_codes(route))

    def _create_correction_proposal(self, input_dto, conversation, route, candidate, base_version: int) -> OrchestratorMessageResult:
        """Record one differing existing value without dispatching workflow."""

        try:
            proposal = self._proposals.create_proposal(
                conversation.request_id,
                (candidate.operation,),
                source="orchestrator_llm",
                message=input_dto.message,
                # This is a server-read snapshot version, not client input.
                # A concurrent Request update is a no-Proposal stable failure.
                client_base_version=base_version,
            )
        except Exception:
            return _failure("proposal_creation_failed")
        return OrchestratorProposalResult("proposal_created", "patch", proposal.proposal_id, _reason_codes(route))

def _validate_input(input_dto: Any) -> str | None:
    if not isinstance(input_dto, OrchestratorMessageInput):
        return "invalid_service_input"
    if not isinstance(input_dto.conversation_id, str) or not input_dto.conversation_id:
        return "invalid_conversation_id"
    if not isinstance(input_dto.message, str):
        return "invalid_message"
    if input_dto.extraction_payload is not None and not isinstance(input_dto.extraction_payload, Mapping):
        return "invalid_extraction_payload"
    if input_dto.extraction_metadata is not None and not isinstance(input_dto.extraction_metadata, Mapping):
        return "invalid_extraction_metadata"
    return None


def _reason_codes(route: IntentRouteDTO) -> tuple[str, ...]:
    codes = [reason.code for reason in route.reasons]
    if route.patch_tool_code:
        codes.append(route.patch_tool_code)
    return tuple(codes)


def _proposal_creation_events(workflow_status: str, proposal_id: str) -> tuple[WorkflowEvent, ...]:
    """Select existing server workflow events without interpreting client data."""

    proposal_event = WorkflowEvent(WorkflowEventType.PROPOSAL_CREATED, proposal_id)
    if workflow_status == WorkflowState.STARTED.value:
        return (WorkflowEvent(WorkflowEventType.START), proposal_event)
    return (proposal_event,)


def _transition_sequence(context: WorkflowContext, events: tuple[WorkflowEvent, ...]) -> None:
    """Preflight only through the existing pure workflow transition function."""

    current = context
    for event in events:
        outcome = transition(current, event)
        current = WorkflowContext(
            workflow_status=outcome.state.value,
            pending_proposal_id=outcome.pending_proposal_id,
            paused=current.paused,
            lifecycle_status=current.lifecycle_status,
        )


def _read_only(route: IntentRouteDTO) -> OrchestratorReadOnlyResult:
    return OrchestratorReadOnlyResult("read_only", route.route_category, _reason_codes(route))


def _clarification(
    route: IntentRouteDTO,
    tool_result: ExtractionToolResult | None = None,
    *,
    extra_reasons: tuple[str, ...] = (),
) -> OrchestratorClarificationResult:
    """Keep ordered Tool/Router reasons while choosing one stable Korean prompt."""

    reasons = list(_reason_codes(route))
    reasons.extend(extra_reasons)
    if tool_result is not None:
        reasons.extend(reason.code for reason in tool_result.reasons)
    ordered = tuple(dict.fromkeys(reasons))
    return OrchestratorClarificationResult(
        "clarification",
        "needs_clarification",
        ordered,
        _clarification_question(ordered),
    )


def _clarification_question(reasons: tuple[str, ...]) -> str:
    if "empty_message" in reasons:
        return "입력 내용이 비어 있습니다. 변경할 항목과 값을 입력해 주세요."
    if "multiple_candidates" in reasons:
        return "한 번에 하나의 변경 항목과 값을 명확히 알려주세요."
    if "missing_unit" in reasons:
        return "값의 단위를 함께 알려주세요. 예: 25 °C"
    if "ambiguous_value" in reasons or "ambiguous_field" in reasons:
        return "변경할 항목과 값이 하나로 정해지도록 다시 알려주세요."
    if "same_value" in reasons:
        return "현재 값과 동일합니다. 다른 값을 알려주세요."
    if "extractor_error" in reasons or "invalid_json" in reasons or "invalid_structured_output" in reasons:
        return "응답을 해석하지 못했습니다. 변경할 항목과 값을 다시 알려주세요."
    return "변경할 항목과 값을 구체적으로 다시 알려주세요."


def _failure(code: str) -> OrchestratorFailureResult:
    return OrchestratorFailureResult("failure", code, (code,))


def _correction_decision(
    state: Mapping[str, Any],
    candidate,
    registry: tuple[FieldRegistryDTO, ...],
    adapter: GeometryProductsAdapterDTO,
) -> str:
    """Classify one sanitized candidate against canonical latest State only."""

    try:
        projected = apply_patch_operations(state, (candidate.operation,))
    except Exception:
        return "not_correction"
    if projected == state:
        return "same_value"
    return "correction" if _has_existing_candidate_value(state, candidate, registry, adapter) else "not_correction"


def _has_existing_candidate_value(
    state: Mapping[str, Any],
    candidate,
    registry: tuple[FieldRegistryDTO, ...],
    adapter: GeometryProductsAdapterDTO,
) -> bool:
    """Read only the candidate's existing Registry/Adapter canonical binding."""

    field = next((item for item in registry if item.field_id == candidate.field_id), None)
    if field is not None:
        return _nonempty(_registry_canonical_value(state, field))
    if candidate.field_id == adapter.transport_path:
        geometry = state.get("geometry") if isinstance(state.get("geometry"), Mapping) else {}
        products = [geometry.get("base_product"), *(geometry.get("comparison_products") or [])]
        return any(_nonempty(_path_value(product, "drawing_no")) for product in products if isinstance(product, Mapping))
    return False


def _registry_canonical_value(state: Mapping[str, Any], field: FieldRegistryDTO) -> Any:
    if not field.card_id or not field.field_key:
        return _path_value(state, field.canonical_path)
    conditions = state.get("conditions") if isinstance(state.get("conditions"), Mapping) else {}
    cards = conditions.get("condition_sets") if isinstance(conditions.get("condition_sets"), list) else ()
    card = next((item for item in cards if isinstance(item, Mapping) and item.get("id") == field.card_id), None)
    if not isinstance(card, Mapping):
        return None
    if field.field_key == "fan_rpm":
        fans = card.get("fans") if isinstance(card.get("fans"), list) else ()
        return [_path_value(fan, f"values.{field.field_key}") for fan in fans if isinstance(fan, Mapping)]
    fields = card.get("fields") if isinstance(card.get("fields"), Mapping) else {}
    return _path_value(fields, field.field_key)


def _path_value(source: Any, path: str) -> Any:
    current = source
    for part in path.split("."):
        if not part or not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current.get("value") if isinstance(current, Mapping) and "value" in current else current


def _nonempty(value: Any) -> bool:
    if isinstance(value, Mapping):
        return _nonempty(value.get("value")) if "value" in value else bool(value)
    if isinstance(value, (list, tuple)):
        return any(_nonempty(item) for item in value)
    return (isinstance(value, str) and bool(value.strip())) or (
        isinstance(value, (int, float)) and not isinstance(value, bool)
    )
