"""Deterministic, Conversation-local workflow transition boundary.

This module intentionally does not read or mutate Request State and does not
invoke the Proposal ledger.  A pending proposal is only its server-issued id;
the caller must re-read the ledger to learn whether it is terminal.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .conversation_store import ConversationNotFoundError, ConversationSnapshot, ConversationStateError, ConversationStore


class WorkflowState(str, Enum):
    STARTED = "started"
    AWAITING_ANSWER = "awaiting_answer"
    AWAITING_PROPOSAL_APPROVAL = "awaiting_proposal_approval"
    PLANNING_NEXT_QUESTION = "planning_next_question"
    PROPOSAL_COMPLETED = "proposal_completed"
    VALIDATION_READY = "validation_ready"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class WorkflowEventType(str, Enum):
    START = "start"
    ANSWER_RECEIVED = "answer_received"
    QUESTION_PLANNED = "question_planned"
    PROPOSAL_CREATED = "proposal_created"
    PROPOSAL_TERMINAL = "proposal_terminal"
    PLAN_NEXT_QUESTION = "plan_next_question"
    VALIDATION_READY = "validation_ready"
    COMPLETE = "complete"
    FAIL = "fail"


@dataclass(frozen=True)
class WorkflowEvent:
    """A workflow event; proposal_id is an opaque server reference only."""

    event_type: WorkflowEventType
    proposal_id: str | None = None


@dataclass(frozen=True)
class WorkflowContext:
    """The minimal Conversation projection needed by the pure transition."""

    workflow_status: str
    pending_proposal_id: str | None
    paused: bool
    lifecycle_status: str

    @classmethod
    def from_conversation(cls, snapshot: ConversationSnapshot) -> "WorkflowContext":
        return cls(
            workflow_status=snapshot.workflow_status,
            pending_proposal_id=snapshot.pending_proposal_id,
            paused=snapshot.paused,
            lifecycle_status=snapshot.status,
        )


@dataclass(frozen=True)
class WorkflowTransition:
    state: WorkflowState
    pending_proposal_id: str | None


class WorkflowTransitionError(RuntimeError):
    """Stable rejection for a workflow event that cannot change a record."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def transition(context: WorkflowContext, event: WorkflowEvent) -> WorkflowTransition:
    """Return the only allowed next state without mutating any store."""

    if context.lifecycle_status == "closed":
        raise WorkflowTransitionError("conversation_closed")
    if context.paused or context.lifecycle_status == "paused":
        raise WorkflowTransitionError("workflow_paused")
    try:
        state = WorkflowState(context.workflow_status)
    except ValueError as exc:
        raise WorkflowTransitionError("invalid_workflow_state") from exc
    if state in {WorkflowState.COMPLETED, WorkflowState.ERROR, WorkflowState.PAUSED}:
        raise WorkflowTransitionError("workflow_terminal")

    if event.event_type is WorkflowEventType.FAIL:
        return WorkflowTransition(WorkflowState.ERROR, context.pending_proposal_id)

    if state is WorkflowState.STARTED and event.event_type is WorkflowEventType.START:
        return WorkflowTransition(WorkflowState.AWAITING_ANSWER, context.pending_proposal_id)
    if state is WorkflowState.AWAITING_ANSWER and event.event_type is WorkflowEventType.ANSWER_RECEIVED:
        return WorkflowTransition(WorkflowState.PLANNING_NEXT_QUESTION, context.pending_proposal_id)
    if state is WorkflowState.PLANNING_NEXT_QUESTION and event.event_type is WorkflowEventType.QUESTION_PLANNED:
        return WorkflowTransition(WorkflowState.AWAITING_ANSWER, context.pending_proposal_id)
    if state in {WorkflowState.AWAITING_ANSWER, WorkflowState.PLANNING_NEXT_QUESTION} and event.event_type is WorkflowEventType.PROPOSAL_CREATED:
        proposal_id = _proposal_id(event.proposal_id)
        return WorkflowTransition(WorkflowState.AWAITING_PROPOSAL_APPROVAL, proposal_id)
    if state is WorkflowState.AWAITING_PROPOSAL_APPROVAL and event.event_type is WorkflowEventType.PROPOSAL_TERMINAL:
        if event.proposal_id != context.pending_proposal_id:
            raise WorkflowTransitionError("proposal_reference_mismatch")
        return WorkflowTransition(WorkflowState.PROPOSAL_COMPLETED, context.pending_proposal_id)
    if state is WorkflowState.PROPOSAL_COMPLETED and event.event_type is WorkflowEventType.PLAN_NEXT_QUESTION:
        return WorkflowTransition(WorkflowState.PLANNING_NEXT_QUESTION, context.pending_proposal_id)
    if state in {WorkflowState.PLANNING_NEXT_QUESTION, WorkflowState.PROPOSAL_COMPLETED} and event.event_type is WorkflowEventType.VALIDATION_READY:
        return WorkflowTransition(WorkflowState.VALIDATION_READY, context.pending_proposal_id)
    if state in {WorkflowState.PROPOSAL_COMPLETED, WorkflowState.VALIDATION_READY} and event.event_type is WorkflowEventType.COMPLETE:
        return WorkflowTransition(WorkflowState.COMPLETED, context.pending_proposal_id)
    if state is WorkflowState.AWAITING_PROPOSAL_APPROVAL:
        raise WorkflowTransitionError("approval_wait_required")
    raise WorkflowTransitionError("invalid_workflow_event")


def _proposal_id(value: str | None) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise WorkflowTransitionError("invalid_proposal_reference")
    return value


class ConversationWorkflowMachine:
    """Applies a pure transition to one active Conversation after it succeeds."""

    def __init__(self, conversations: ConversationStore) -> None:
        self._conversations = conversations

    def dispatch(self, conversation_id: str, event: WorkflowEvent) -> ConversationSnapshot:
        snapshot = self._conversations.read(conversation_id)
        outcome = transition(WorkflowContext.from_conversation(snapshot), event)
        return self._persist(conversation_id, outcome)

    def dispatch_many(self, conversation_id: str, events: tuple[WorkflowEvent, ...]) -> ConversationSnapshot:
        """Apply an already server-selected event sequence as one record write.

        Every transition is evaluated from an in-memory context first.  A bad
        later event therefore leaves the Conversation record untouched; no
        caller can use this as a public workflow-event surface.
        """

        if not isinstance(events, tuple) or not events or not all(isinstance(event, WorkflowEvent) for event in events):
            raise WorkflowTransitionError("invalid_workflow_event")
        snapshot = self._conversations.read(conversation_id)
        context = WorkflowContext.from_conversation(snapshot)
        outcome: WorkflowTransition | None = None
        for event in events:
            outcome = transition(context, event)
            context = WorkflowContext(
                workflow_status=outcome.state.value,
                pending_proposal_id=outcome.pending_proposal_id,
                paused=context.paused,
                lifecycle_status=context.lifecycle_status,
            )
        return self._persist(conversation_id, outcome)

    def _persist(self, conversation_id: str, outcome: WorkflowTransition | None) -> ConversationSnapshot:
        if outcome is None:
            raise WorkflowTransitionError("invalid_workflow_event")
        try:
            return self._conversations.apply_workflow_transition(
                conversation_id,
                workflow_status=outcome.state.value,
                pending_proposal_id=outcome.pending_proposal_id,
            )
        except ConversationStateError as exc:
            # A lifecycle change between read and apply cannot advance workflow.
            raise WorkflowTransitionError("workflow_lifecycle_changed") from exc
        except ConversationNotFoundError:
            raise
