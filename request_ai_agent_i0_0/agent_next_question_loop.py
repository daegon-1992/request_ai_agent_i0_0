"""Conversation application boundary for one already-planned next question."""

from __future__ import annotations

from typing import Iterable

from .agent_next_question import NextQuestion
from .conversation_store import ConversationSnapshot, ConversationStore
from .workflow_machine import (
    WorkflowContext,
    WorkflowEvent,
    WorkflowEventType,
    transition,
)


def synchronize_active_field(
    conversations: ConversationStore,
    conversation: ConversationSnapshot,
    planned: NextQuestion,
) -> ConversationSnapshot:
    """Clear stale focus without displaying or recording a Planner message."""

    active_field_id = conversation.active_field_id
    planned_field_id = planned["active_field_id"] if planned["kind"] == "field_question" else None
    if active_field_id is not None and active_field_id != planned_field_id:
        return conversations.clear_active_field(conversation.conversation_id)
    return conversation


def answer_planning_events(workflow_status: str) -> tuple[WorkflowEvent, ...]:
    """Select only the existing events needed to enter next-question planning."""

    if workflow_status == "started":
        return (
            WorkflowEvent(WorkflowEventType.START),
            WorkflowEvent(WorkflowEventType.ANSWER_RECEIVED),
        )
    if workflow_status == "awaiting_answer":
        return (WorkflowEvent(WorkflowEventType.ANSWER_RECEIVED),)
    if workflow_status == "proposal_completed":
        return (WorkflowEvent(WorkflowEventType.PLAN_NEXT_QUESTION),)
    return ()


def apply_next_question(
    conversations: ConversationStore,
    conversation_id: str,
    planned: NextQuestion,
    *,
    prior_events: Iterable[WorkflowEvent] = (),
) -> ConversationSnapshot:
    """Apply exactly one Planner result using existing Workflow transitions."""

    snapshot = conversations.read(conversation_id)
    context = WorkflowContext.from_conversation(snapshot)
    events = tuple(prior_events)
    if planned["kind"] == "field_question":
        events = (*events, WorkflowEvent(WorkflowEventType.QUESTION_PLANNED))
    for event in events:
        outcome = transition(context, event)
        context = WorkflowContext(
            workflow_status=outcome.state.value,
            pending_proposal_id=outcome.pending_proposal_id,
            paused=context.paused,
            lifecycle_status=context.lifecycle_status,
        )

    return conversations.apply_planner_message(
        conversation_id,
        planned["message"],
        active_field_id=planned["active_field_id"] if planned["kind"] == "field_question" else None,
        record_question=planned["kind"] == "field_question",
        workflow_status=context.workflow_status,
        pending_proposal_id=context.pending_proposal_id,
        expected_version=snapshot.version,
    )
