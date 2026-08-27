import pytest

from request_ai_agent_i0_0.conversation_store import (
    MAX_IDENTIFIER_LENGTH,
    MAX_TURN_CONTENT_LENGTH,
    ConversationCapacityError,
    ConversationSnapshot,
    ConversationStateError,
    ConversationStore,
)
from request_ai_agent_i0_0.proposal_store import ProposalService
from request_ai_agent_i0_0.request_state_store import RequestStateStore
from request_ai_agent_i0_0.state import create_initial_state
from request_ai_agent_i0_0.validator import state_with_validation


def _requests() -> RequestStateStore:
    return RequestStateStore(state_with_validation)


def test_snapshot_direct_creation_keeps_backward_compatible_new_field_defaults():
    snapshot = ConversationSnapshot(
        conversation_id="conversation_a",
        request_id="request_a",
        workflow_status="started",
        pending_proposal_id=None,
        question_history=[],
        paused=False,
        summary="",
        version=0,
        status="active",
    )

    assert snapshot.recent_turns == []
    assert snapshot.active_field_id is None
    assert snapshot.pending_write_candidates == []


def test_create_and_read_are_deep_copies_and_do_not_copy_or_change_request_state():
    requests = _requests()
    request = requests.create(create_initial_state())
    before = requests.read(request.request_id)
    conversations = ConversationStore()

    conversation = conversations.create(request.request_id)
    local_copy = conversations.read(conversation.conversation_id)
    local_copy.question_history.append("forged local question")

    stored = conversations.read(conversation.conversation_id)
    assert stored.question_history == []
    assert stored.recent_turns == []
    assert stored.active_field_id is None
    assert stored.pending_write_candidates == []
    assert stored.summary == ""
    assert stored.request_id == request.request_id
    assert requests.read(request.request_id) == before
    assert "state" not in stored.__dict__
    assert "base_version" not in stored.__dict__
    assert "operations" not in stored.__dict__


def test_recent_turns_preserve_order_trim_edges_and_keep_internal_text():
    conversations = ConversationStore()
    created = conversations.create("request_a")

    first = conversations.append_turn(created.conversation_id, "assistant", "  Fan 회전수를 알려주세요.  ")
    stored = conversations.append_turn(created.conversation_id, "user", "  780\nRPM  ")

    assert first.version == created.version + 1
    assert stored.version == first.version + 1
    assert stored.recent_turns == [
        {"role": "assistant", "content": "Fan 회전수를 알려주세요."},
        {"role": "user", "content": "780\nRPM"},
    ]


def test_recent_turns_keep_only_the_latest_ten_messages():
    conversations = ConversationStore()
    created = conversations.create("request_a")

    for index in range(11):
        conversations.append_turn(created.conversation_id, "user", f"turn {index}")

    assert conversations.read(created.conversation_id).recent_turns == [
        {"role": "user", "content": f"turn {index}"} for index in range(1, 11)
    ]


@pytest.mark.parametrize("role", ["system", "tool", "", None])
def test_append_turn_rejects_invalid_roles_without_mutation(role):
    conversations = ConversationStore()
    created = conversations.create("request_a")

    with pytest.raises(ValueError):
        conversations.append_turn(created.conversation_id, role, "content")

    assert conversations.read(created.conversation_id) == created


@pytest.mark.parametrize("content", ["", "   ", "\n\t"])
def test_append_turn_rejects_empty_content_without_mutation(content):
    conversations = ConversationStore()
    created = conversations.create("request_a")

    with pytest.raises(ValueError):
        conversations.append_turn(created.conversation_id, "user", content)

    assert conversations.read(created.conversation_id) == created


def test_append_turn_rejects_content_over_maximum_length():
    conversations = ConversationStore()
    created = conversations.create("request_a")

    with pytest.raises(ValueError):
        conversations.append_turn(created.conversation_id, "user", "x" * (MAX_TURN_CONTENT_LENGTH + 1))


def test_active_field_can_be_set_and_cleared_as_an_opaque_reference():
    conversations = ConversationStore()
    created = conversations.create("request_a")

    active = conversations.set_active_field(created.conversation_id, "conditions.operating_1.fan_rpm")
    cleared = conversations.clear_active_field(created.conversation_id)

    assert active.active_field_id == "conditions.operating_1.fan_rpm"
    assert active.version == created.version + 1
    assert cleared.active_field_id is None
    assert cleared.version == active.version + 1
    with pytest.raises(ValueError):
        conversations.set_active_field(created.conversation_id, "")
    with pytest.raises(ValueError):
        conversations.set_active_field(created.conversation_id, "x" * (MAX_IDENTIFIER_LENGTH + 1))


def test_read_recent_turns_are_deep_copied():
    conversations = ConversationStore()
    created = conversations.create("request_a")
    conversations.append_turn(created.conversation_id, "assistant", "question")

    local_copy = conversations.read(created.conversation_id)
    local_copy.recent_turns[0]["content"] = "forged"
    local_copy.recent_turns.append({"role": "user", "content": "forged"})

    assert conversations.read(created.conversation_id).recent_turns == [
        {"role": "assistant", "content": "question"}
    ]


def test_existing_workflow_summary_and_lifecycle_mutations_preserve_new_fields():
    conversations = ConversationStore()
    created = conversations.create("request_a")
    conversations.append_turn(created.conversation_id, "assistant", "question")
    conversations.set_active_field(created.conversation_id, "conditions.operating_1.fan_rpm")

    transitioned = conversations.apply_workflow_transition(
        created.conversation_id,
        workflow_status="awaiting_answer",
        pending_proposal_id=None,
    )
    summarized = conversations.set_summary(created.conversation_id, "summary")
    paused = conversations.pause(created.conversation_id)
    resumed = conversations.resume(created.conversation_id)

    expected_turns = [{"role": "assistant", "content": "question"}]
    for snapshot in (transitioned, summarized, paused, resumed):
        assert snapshot.recent_turns == expected_turns
        assert snapshot.active_field_id == "conditions.operating_1.fan_rpm"

    closed = conversations.close(created.conversation_id)
    assert closed.recent_turns == expected_turns
    assert closed.active_field_id == "conditions.operating_1.fan_rpm"
    for mutation in (
        lambda: conversations.append_turn(created.conversation_id, "user", "answer"),
        lambda: conversations.set_active_field(created.conversation_id, "another.field"),
        lambda: conversations.clear_active_field(created.conversation_id),
    ):
        with pytest.raises(ConversationStateError):
            mutation()
    assert conversations.read(created.conversation_id) == closed


def test_conversations_and_request_references_are_isolated_and_storage_is_bounded():
    conversations = ConversationStore(max_conversations=2)
    first = conversations.create("request_a")
    second = conversations.create("request_b")
    conversations.append_question(first.conversation_id, "first question")
    conversations.set_pending_proposal(second.conversation_id, "proposal_second")

    assert conversations.read(first.conversation_id).request_id == "request_a"
    assert conversations.read(first.conversation_id).pending_proposal_id is None
    assert conversations.read(second.conversation_id).request_id == "request_b"
    assert conversations.read(second.conversation_id).question_history == []
    assert conversations.read(second.conversation_id).pending_proposal_id == "proposal_second"
    before_first = conversations.read(first.conversation_id)
    before_second = conversations.read(second.conversation_id)
    with pytest.raises(ConversationCapacityError):
        conversations.create("request_c")
    assert conversations.read(first.conversation_id) == before_first
    assert conversations.read(second.conversation_id) == before_second


def test_pause_resume_and_closed_conversation_reject_mutations():
    requests = _requests()
    request = requests.create(create_initial_state())
    request_before = requests.read(request.request_id)
    conversations = ConversationStore()
    created = conversations.create(request.request_id)

    paused = conversations.pause(created.conversation_id)
    assert paused.status == "paused"
    assert paused.paused is True
    with pytest.raises(ConversationStateError):
        conversations.pause(created.conversation_id)
    with pytest.raises(ConversationStateError):
        conversations.append_question(created.conversation_id, "not while paused")
    assert conversations.read(created.conversation_id) == paused
    resumed = conversations.resume(created.conversation_id)
    assert resumed.status == "active"
    assert resumed.paused is False
    with pytest.raises(ConversationStateError):
        conversations.resume(created.conversation_id)
    assert conversations.read(created.conversation_id) == resumed
    assert requests.read(request.request_id) == request_before
    closed = conversations.close(created.conversation_id)
    assert closed.status == "closed"
    assert closed.paused is False
    for mutation in (
        lambda: conversations.append_question(created.conversation_id, "after close"),
        lambda: conversations.set_workflow_status(created.conversation_id, "planning"),
        lambda: conversations.set_pending_proposal(created.conversation_id, "proposal_after_close"),
        lambda: conversations.pause(created.conversation_id),
        lambda: conversations.resume(created.conversation_id),
    ):
        with pytest.raises(ConversationStateError):
            mutation()
    assert conversations.read(created.conversation_id) == closed
    assert requests.read(request.request_id) == request_before


def test_question_history_is_bounded_without_retaining_request_or_proposal_payloads():
    conversations = ConversationStore(max_question_history=2)
    created = conversations.create("request_a")
    conversations.append_question(created.conversation_id, "one")
    conversations.append_question(created.conversation_id, "two")
    stored = conversations.append_question(created.conversation_id, "three")

    assert stored.question_history == ["two", "three"]
    assert stored.pending_proposal_id is None


def test_terminal_proposal_remains_reference_only_and_conversation_never_applies_it():
    requests = _requests()
    request = requests.create(create_initial_state())
    proposals = ProposalService(requests)
    proposal = proposals.create_proposal(
        request.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "server-only apply"}],
        source="llm_structured_output",
    )
    conversations = ConversationStore()
    conversation = conversations.create(request.request_id)
    conversations.set_pending_proposal(conversation.conversation_id, proposal.proposal_id)
    before = requests.read(request.request_id)

    # Only the server Proposal lifecycle can apply; Conversation only retains its id.
    terminal = proposals.approve_proposal(proposal.proposal_id)
    after = requests.read(request.request_id)
    stored = conversations.read(conversation.conversation_id)

    assert terminal.status == "approved"
    assert after.version == before.version + 1
    assert stored.pending_proposal_id == proposal.proposal_id
    assert stored.request_id == request.request_id
    assert "operations" not in stored.__dict__
    assert "base_version" not in stored.__dict__


@pytest.mark.parametrize(
    ("decision", "status"),
    [("reject_proposal", "rejected"), ("expire_proposal", "expired")],
)
def test_non_applying_terminal_proposals_remain_references_and_preserve_request(decision, status):
    requests = _requests()
    request = requests.create(create_initial_state())
    proposals = ProposalService(requests)
    proposal = proposals.create_proposal(
        request.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "not applied"}],
        source="llm_structured_output",
    )
    conversations = ConversationStore()
    conversation = conversations.create(request.request_id)
    conversations.set_pending_proposal(conversation.conversation_id, proposal.proposal_id)
    request_before = requests.read(request.request_id)

    terminal = getattr(proposals, decision)(proposal.proposal_id)

    assert terminal.status == status
    assert requests.read(request.request_id) == request_before
    assert conversations.read(conversation.conversation_id).pending_proposal_id == proposal.proposal_id
