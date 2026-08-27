import pytest

from request_ai_agent_i0_0.conversation_store import ConversationStore
from request_ai_agent_i0_0.request_state_store import RequestStateStore
from request_ai_agent_i0_0.state import create_initial_state
from request_ai_agent_i0_0.validator import state_with_validation
from request_ai_agent_i0_0.workflow_machine import (
    ConversationWorkflowMachine,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowState,
    WorkflowTransitionError,
    transition,
    WorkflowContext,
)


def _machine():
    requests = RequestStateStore(state_with_validation)
    request = requests.create(create_initial_state())
    conversations = ConversationStore()
    conversation = conversations.create(request.request_id)
    return requests, conversations, conversation, ConversationWorkflowMachine(conversations)


def _event(kind, proposal_id=None):
    return WorkflowEvent(WorkflowEventType(kind), proposal_id=proposal_id)


def test_deterministic_normal_paths_keep_proposal_terminal_reference_opaque():
    _requests, conversations, conversation, machine = _machine()
    cid = conversation.conversation_id
    assert machine.dispatch(cid, _event("start")).workflow_status == WorkflowState.AWAITING_ANSWER.value
    assert machine.dispatch(cid, _event("proposal_created", "proposal_server_only")).workflow_status == WorkflowState.AWAITING_PROPOSAL_APPROVAL.value
    finished = machine.dispatch(cid, _event("proposal_terminal", "proposal_server_only"))
    assert finished.workflow_status == WorkflowState.PROPOSAL_COMPLETED.value
    assert finished.pending_proposal_id == "proposal_server_only"
    assert machine.dispatch(cid, _event("plan_next_question")).workflow_status == WorkflowState.PLANNING_NEXT_QUESTION.value
    assert machine.dispatch(cid, _event("validation_ready")).workflow_status == WorkflowState.VALIDATION_READY.value
    assert machine.dispatch(cid, _event("complete")).workflow_status == WorkflowState.COMPLETED.value
    assert conversations.read(cid).pending_proposal_id == "proposal_server_only"


def test_answer_question_and_failure_paths_are_deterministic():
    _requests, _conversations, conversation, machine = _machine()
    cid = conversation.conversation_id
    machine.dispatch(cid, _event("start"))
    assert machine.dispatch(cid, _event("answer_received")).workflow_status == "planning_next_question"
    assert machine.dispatch(cid, _event("question_planned")).workflow_status == "awaiting_answer"
    assert machine.dispatch(cid, _event("fail")).workflow_status == "error"


def test_server_selected_event_sequence_is_atomic_and_uses_existing_transition_rules():
    _requests, conversations, conversation, machine = _machine()
    cid = conversation.conversation_id

    created = machine.dispatch_many(cid, (_event("start"), _event("proposal_created", "proposal_sequence")))
    assert created.workflow_status == "awaiting_proposal_approval"
    assert created.pending_proposal_id == "proposal_sequence"
    assert created.version == conversation.version + 1

    other = conversations.create("request_other")
    before = conversations.read(other.conversation_id)
    with pytest.raises(WorkflowTransitionError) as exc:
        machine.dispatch_many(other.conversation_id, (_event("start"), _event("complete")))
    assert exc.value.code == "invalid_workflow_event"
    assert conversations.read(other.conversation_id) == before


def test_invalid_bypass_paused_and_closed_events_do_not_mutate_conversation_or_request():
    requests, conversations, conversation, machine = _machine()
    cid = conversation.conversation_id
    request_before = requests.read(conversation.request_id)
    conversation_before = conversations.read(cid)
    for event in (_event("complete"), _event("proposal_terminal", "proposal_missing")):
        with pytest.raises(WorkflowTransitionError) as exc:
            machine.dispatch(cid, event)
        assert exc.value.code == "invalid_workflow_event"
        assert conversations.read(cid) == conversation_before
    machine.dispatch(cid, _event("start"))
    awaiting = conversations.read(cid)
    with pytest.raises(WorkflowTransitionError) as exc:
        machine.dispatch(cid, _event("complete"))
    assert exc.value.code == "invalid_workflow_event"
    assert conversations.read(cid) == awaiting
    paused = conversations.pause(cid)
    with pytest.raises(WorkflowTransitionError) as exc:
        machine.dispatch(cid, _event("answer_received"))
    assert exc.value.code == "workflow_paused"
    assert conversations.read(cid) == paused
    conversations.resume(cid)
    closed = conversations.close(cid)
    with pytest.raises(WorkflowTransitionError) as exc:
        machine.dispatch(cid, _event("answer_received"))
    assert exc.value.code == "conversation_closed"
    assert conversations.read(cid) == closed
    assert requests.read(conversation.request_id) == request_before


def test_terminal_event_requires_the_same_server_reference_and_never_reads_proposal_ledger():
    _requests, conversations, conversation, machine = _machine()
    cid = conversation.conversation_id
    machine.dispatch(cid, _event("start"))
    machine.dispatch(cid, _event("proposal_created", "proposal_a"))
    before = conversations.read(cid)
    with pytest.raises(WorkflowTransitionError) as exc:
        machine.dispatch(cid, _event("proposal_terminal", "proposal_b"))
    assert exc.value.code == "proposal_reference_mismatch"
    assert conversations.read(cid) == before


def test_approval_wait_rejects_bypass_events_without_mutating_conversation_or_request():
    requests, conversations, conversation, machine = _machine()
    cid = conversation.conversation_id
    machine.dispatch(cid, _event("start"))
    machine.dispatch(cid, _event("proposal_created", "proposal_waiting"))
    request_before = requests.read(conversation.request_id)
    conversation_before = conversations.read(cid)

    for event in (_event("plan_next_question"), _event("validation_ready"), _event("complete")):
        with pytest.raises(WorkflowTransitionError) as exc:
            machine.dispatch(cid, event)
        assert exc.value.code == "approval_wait_required"
        assert conversations.read(cid) == conversation_before
        assert requests.read(conversation.request_id) == request_before


def test_completed_and_error_workflow_states_reject_later_events_without_mutation():
    requests, conversations, conversation, machine = _machine()
    cid = conversation.conversation_id
    machine.dispatch(cid, _event("start"))
    machine.dispatch(cid, _event("proposal_created", "proposal_completed"))
    machine.dispatch(cid, _event("proposal_terminal", "proposal_completed"))
    machine.dispatch(cid, _event("validation_ready"))
    completed = machine.dispatch(cid, _event("complete"))
    request_before = requests.read(conversation.request_id)

    with pytest.raises(WorkflowTransitionError) as exc:
        machine.dispatch(cid, _event("start"))
    assert exc.value.code == "workflow_terminal"
    assert conversations.read(cid) == completed
    assert requests.read(conversation.request_id) == request_before

    failed_requests, failed_conversations, failed, failed_machine = _machine()
    failed_machine.dispatch(failed.conversation_id, _event("fail"))
    error = failed_conversations.read(failed.conversation_id)
    failed_request_before = failed_requests.read(failed.request_id)
    with pytest.raises(WorkflowTransitionError) as exc:
        failed_machine.dispatch(failed.conversation_id, _event("start"))
    assert exc.value.code == "workflow_terminal"
    assert failed_conversations.read(failed.conversation_id) == error
    assert failed_requests.read(failed.request_id) == failed_request_before


def test_conversations_and_pure_contexts_are_isolated():
    _requests, conversations, first, machine = _machine()
    second = conversations.create("request_other")
    machine.dispatch(first.conversation_id, _event("start"))
    assert conversations.read(second.conversation_id).workflow_status == "started"
    with pytest.raises(WorkflowTransitionError) as exc:
        transition(WorkflowContext("not_a_state", None, False, "active"), _event("start"))
    assert exc.value.code == "invalid_workflow_state"
