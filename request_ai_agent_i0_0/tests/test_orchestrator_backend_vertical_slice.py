from copy import deepcopy
import inspect

import pytest

from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.workflow_machine import WorkflowEvent, WorkflowEventType


def _mock_extractor(message, **_kwargs):
    if message == "next question":
        return {"operations": []}
    if message == "tool failure":
        raise RuntimeError("mock extractor failure")
    return {
        "operations": [
            {
                "op": "set",
                "path": "analysis_overview.request_description",
                "value": "server candidate",
                "evidence_phrase": message,
            }
        ]
    }


def _runtime(*, extractor=_mock_extractor):
    app = create_app(orchestrator_extractor=extractor)
    app.config["TESTING"] = True
    client = app.test_client()
    request_response = client.post("/api/request/versioned", json={})
    assert request_response.status_code == 201
    request_id = request_response.get_json()["request_id"]
    conversation_response = client.post("/api/conversations", json={"request_id": request_id})
    assert conversation_response.status_code == 201
    conversation_id = conversation_response.get_json()["conversation_id"]
    return app, client, request_id, conversation_id


def _message(client, conversation_id, *, message="set the description", intent="patch", **extra):
    return client.post(
        "/api/orchestrator/messages",
        json={
            "conversation_id": conversation_id,
            "message": message,
            "intent": intent,
            **extra,
        },
    )


@pytest.mark.parametrize(
    "forbidden",
    [
        {"state": {"forged": True}},
        {"request_state": {"forged": True}},
        {"request_id": "forged-request"},
        {"version": 99},
        {"request_version": 99},
        {"operation": {"op": "set"}},
        {"operations": [{"op": "set"}]},
        {"proposal": {"proposal_id": "forged"}},
        {"proposal_id": "forged"},
        {"event": "proposal_terminal"},
        {"workflow_event": "proposal_terminal"},
        {"workflow_status": "completed"},
        {"approved": True},
    ],
)
def test_http_input_builds_only_the_allowed_dto_and_rejects_client_authority(forbidden):
    app, client, request_id, conversation_id = _runtime()
    requests = app.extensions["request_state_store"]
    conversations = app.extensions["conversation_store"]
    proposals = app.extensions["proposal_service"]
    before = (
        requests.read(request_id),
        conversations.read(conversation_id),
        proposals.proposal_count(),
    )

    response = _message(client, conversation_id, **forbidden)

    assert response.status_code == 400
    assert response.get_json() == {
        "ok": False,
        "kind": "failure",
        "error": "invalid_orchestrator_message_payload",
        "reasons": ["invalid_orchestrator_message_payload"],
        "state_changed": False,
        "read_only": True,
    }
    assert (
        requests.read(request_id),
        conversations.read(conversation_id),
        proposals.proposal_count(),
    ) == before


def test_message_proposal_approval_latest_request_and_clarification_vertical_flow():
    app, client, request_id, conversation_id = _runtime()
    requests = app.extensions["request_state_store"]
    proposals = app.extensions["proposal_service"]
    workflow = app.extensions["conversation_workflow_machine"]
    before = requests.read(request_id)
    assert app.extensions["conversation_store"].read(conversation_id).workflow_status == "started"

    response = _message(client, conversation_id)
    assert response.status_code == 200
    body = response.get_json()
    assert body["kind"] == "proposal_created"
    assert body["state_changed"] is False
    assert body["read_only"] is True
    assert body["reasons"] == ["intent_patch", "tool_candidates"]
    assert set(body["proposal"]) == {"proposal_id", "status", "diff"}
    assert body["proposal"]["status"] == "pending"
    assert body["proposal"]["diff"]["read_only"] is True
    assert body["proposal"]["diff"]["changed_path_count"] > 0
    proposal_id = body["proposal"]["proposal_id"]
    proposal = proposals.read_proposal(proposal_id)
    assert proposal.request_id == request_id
    assert proposal.base_version == before.version
    assert requests.read(request_id) == before
    assert app.extensions["conversation_store"].read(conversation_id).workflow_status == "awaiting_proposal_approval"

    approved = proposals.approve_proposal(proposal_id)
    assert approved.status == "approved"
    latest_response = client.get(f"/api/request/versioned/{request_id}")
    assert latest_response.status_code == 200
    latest = latest_response.get_json()
    assert latest["request_id"] == request_id
    assert latest["request_version"] == before.version + 1
    assert latest["state"]["analysis_overview"]["request_description"]["value"] == "server candidate"

    workflow.dispatch(conversation_id, WorkflowEvent(WorkflowEventType.PROPOSAL_TERMINAL, proposal_id))
    workflow.dispatch(conversation_id, WorkflowEvent(WorkflowEventType.PLAN_NEXT_QUESTION))
    next_response = _message(client, conversation_id, message="next question")
    assert next_response.status_code == 200
    next_body = next_response.get_json()
    assert next_body["kind"] == "clarification"
    assert next_body["route_category"] == "needs_clarification"
    assert next_body["question"] == "변경할 항목과 값을 구체적으로 다시 알려주세요."
    assert next_body["state_changed"] is False
    assert "planner_decision" not in next_body
    assert requests.read(request_id).version == before.version + 1


@pytest.mark.parametrize("intent", ["general_qa", "rag_qa", "current_input", "needs_clarification"])
def test_qa_current_input_and_clarification_are_stable_read_only_without_extractor_or_writes(intent):
    calls = []

    def forbidden_extractor(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("read-only route called extractor")

    app, client, request_id, conversation_id = _runtime(extractor=forbidden_extractor)
    requests = app.extensions["request_state_store"]
    conversations = app.extensions["conversation_store"]
    proposals = app.extensions["proposal_service"]
    before = (requests.read(request_id), conversations.read(conversation_id), proposals.proposal_count())

    response = _message(client, conversation_id, message="question", intent=intent)

    assert response.status_code == 200
    assert response.get_json()["route_category"] == intent
    assert response.get_json()["state_changed"] is False
    assert not calls
    assert (requests.read(request_id), conversations.read(conversation_id), proposals.proposal_count()) == before


def test_no_candidate_tool_and_router_failures_are_read_only_and_keep_reason_order():
    app, client, request_id, conversation_id = _runtime()
    requests = app.extensions["request_state_store"]
    conversations = app.extensions["conversation_store"]
    proposals = app.extensions["proposal_service"]
    before = (requests.read(request_id), conversations.read(conversation_id), proposals.proposal_count())

    no_candidate = _message(client, conversation_id, message="next question")
    assert no_candidate.status_code == 200
    assert no_candidate.get_json()["kind"] == "clarification"
    assert no_candidate.get_json()["reasons"] == ["intent_patch", "tool_no_candidate", "no_operations"]

    tool_failure = _message(client, conversation_id, message="tool failure")
    assert tool_failure.status_code == 200
    assert tool_failure.get_json()["reasons"] == ["intent_patch", "tool_failure", "extractor_error"]

    router_failure = _message(client, conversation_id, extraction_payload=[])
    assert router_failure.status_code == 400
    assert router_failure.get_json()["error"] == "invalid_extraction_payload"
    assert (requests.read(request_id), conversations.read(conversation_id), proposals.proposal_count()) == before


@pytest.mark.parametrize(
    ("lifecycle", "expected", "status"),
    [
        ("unknown", "conversation_read_failed", 404),
        ("closed", "conversation_closed", 409),
        ("paused", "conversation_paused", 409),
    ],
)
def test_unknown_closed_and_paused_conversations_are_deterministic_without_partial_writes(lifecycle, expected, status):
    app, client, request_id, conversation_id = _runtime()
    requests = app.extensions["request_state_store"]
    conversations = app.extensions["conversation_store"]
    proposals = app.extensions["proposal_service"]
    if lifecycle == "unknown":
        target = "missing-conversation"
    else:
        target = conversation_id
        getattr(conversations, {"closed": "close", "paused": "pause"}[lifecycle])(conversation_id)
    before = (requests.read(request_id), conversations.read(conversation_id), proposals.proposal_count())

    response = _message(client, target)

    assert response.status_code == status
    assert response.get_json()["error"] == expected
    assert (requests.read(request_id), conversations.read(conversation_id), proposals.proposal_count()) == before


def test_request_read_and_proposal_creation_failures_leave_request_conversation_and_ledger_unchanged():
    app, client, request_id, conversation_id = _runtime()
    requests = app.extensions["request_state_store"]
    conversations = app.extensions["conversation_store"]
    proposals = app.extensions["proposal_service"]
    missing = conversations.create("missing-request", workflow_status="awaiting_answer")
    before_missing = (requests.read(request_id), conversations.read(missing.conversation_id), proposals.proposal_count())
    missing_response = _message(client, missing.conversation_id)
    assert missing_response.status_code == 503
    assert missing_response.get_json()["error"] == "request_read_failed"
    assert (requests.read(request_id), conversations.read(missing.conversation_id), proposals.proposal_count()) == before_missing

    class BrokenProposalService:
        def create_proposal(self, *_args, **_kwargs):
            raise RuntimeError("mock proposal failure")

    service = app.extensions["orchestrator_service"]
    original = service._proposals
    service._proposals = BrokenProposalService()
    before_broken = (requests.read(request_id), conversations.read(conversation_id), proposals.proposal_count())
    try:
        broken_response = _message(client, conversation_id)
    finally:
        service._proposals = original
    assert broken_response.status_code == 503
    assert broken_response.get_json()["error"] == "proposal_creation_failed"
    assert (requests.read(request_id), conversations.read(conversation_id), proposals.proposal_count()) == before_broken


def test_stale_approval_is_terminal_without_extra_request_or_conversation_write():
    app, client, request_id, conversation_id = _runtime()
    requests = app.extensions["request_state_store"]
    conversations = app.extensions["conversation_store"]
    proposals = app.extensions["proposal_service"]
    proposal_id = _message(client, conversation_id).get_json()["proposal"]["proposal_id"]
    conversation_before = conversations.read(conversation_id)
    current = requests.read(request_id)
    replaced = client.put(
        f"/api/request/versioned/{request_id}",
        json={"expected_version": current.version, "state": current.state},
    )
    assert replaced.status_code == 200
    request_before_approval = requests.read(request_id)

    terminal = proposals.approve_proposal(proposal_id)

    assert terminal.status == "conflicted"
    assert requests.read(request_id) == request_before_approval
    assert conversations.read(conversation_id) == conversation_before
    assert proposals.read_proposal(proposal_id) == terminal


def test_different_request_conversation_pairs_are_isolated_and_endpoint_has_no_direct_mutation_authority():
    app, client, first_request_id, first_conversation_id = _runtime()
    requests = app.extensions["request_state_store"]
    conversations = app.extensions["conversation_store"]
    proposals = app.extensions["proposal_service"]
    second_request = requests.create({})
    second_conversation = conversations.create(second_request.request_id, workflow_status="awaiting_answer")
    second_before = (requests.read(second_request.request_id), conversations.read(second_conversation.conversation_id))

    first_response = _message(client, first_conversation_id)

    assert first_response.status_code == 200
    assert proposals.read_proposal(first_response.get_json()["proposal"]["proposal_id"]).request_id == first_request_id
    assert (requests.read(second_request.request_id), conversations.read(second_conversation.conversation_id)) == second_before
    endpoint_source = inspect.getsource(app.view_functions["orchestrator_message"])
    assert "orchestrator_service.handle" in endpoint_source
    assert "proposal_service.read_proposal" in endpoint_source
    for forbidden in (
        "compare_and_swap",
        "request_state_store.replace",
        "approve_proposal",
        "reject_proposal",
        "expire_proposal",
        "apply_patch_operations",
        "workflow_machine.dispatch",
    ):
        assert forbidden not in endpoint_source
