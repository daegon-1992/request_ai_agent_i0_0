from copy import deepcopy
import inspect

import pytest

from request_ai_agent_i0_0.conversation_store import ConversationStore
from request_ai_agent_i0_0.field_registry import FieldRegistryDTO, get_geometry_products_adapter
from request_ai_agent_i0_0.orchestrator_service import (
    OrchestratorClarificationResult,
    OrchestratorFailureResult,
    OrchestratorMessageInput,
    OrchestratorProposalResult,
    OrchestratorReadOnlyResult,
    OrchestratorService,
)
from request_ai_agent_i0_0.proposal_store import ProposalService
from request_ai_agent_i0_0.request_state_store import RequestStateStore
from request_ai_agent_i0_0.workflow_machine import ConversationWorkflowMachine


def _field():
    return FieldRegistryDTO(
        field_id="analysis_overview.request_description",
        canonical_path="analysis_overview.request_description",
        value_path="analysis_overview.request_description",
        label="Description", value_type="text", unit="", active=True, required=True,
        required_level="required", dependencies=(), validation_binding="existing", priority="blocking_required",
        operation_path="analysis_overview.request_description",
    )


def _extractor(*_args, **_kwargs):
    return {"operations": [{"op": "set", "path": "analysis_overview.request_description", "value": "server candidate"}]}


def _service(*, workflow_status="awaiting_answer", extractor=_extractor, registry_reader=lambda _state: (_field(),), proposals=None):
    requests = RequestStateStore(lambda item: deepcopy(dict(item)))
    request = requests.create({"analysis_overview": {"request_description": ""}})
    conversations = ConversationStore()
    conversation = conversations.create(request.request_id, workflow_status=workflow_status)
    proposals = proposals or ProposalService(requests)
    service = OrchestratorService(
        conversations=conversations, requests=requests, proposals=proposals,
        workflow=ConversationWorkflowMachine(conversations), extractor=extractor,
        registry_reader=registry_reader, geometry_adapter_reader=get_geometry_products_adapter,
    )
    return service, requests, conversations, proposals, request, conversation


def test_patch_uses_server_latest_request_and_conversation_and_is_unchanged_until_approval():
    service, requests, conversations, proposals, request, conversation = _service()
    before_request = requests.read(request.request_id)
    result = service.handle(OrchestratorMessageInput(conversation.conversation_id, "change it", "patch"))
    assert isinstance(result, OrchestratorProposalResult)
    proposal = proposals.read_proposal(result.proposal_id)
    assert proposal.request_id == request.request_id
    assert proposal.base_version == before_request.version
    assert requests.read(request.request_id) == before_request
    updated_conversation = conversations.read(conversation.conversation_id)
    assert updated_conversation.pending_proposal_id == result.proposal_id
    assert updated_conversation.workflow_status == "awaiting_proposal_approval"
    assert not hasattr(OrchestratorMessageInput, "request_state")
    assert not hasattr(OrchestratorMessageInput, "proposal")


@pytest.mark.parametrize("lifecycle, expected", [("closed", "conversation_closed"), ("paused", "conversation_paused")])
def test_closed_or_paused_conversations_have_stable_failures_without_writes(lifecycle, expected):
    service, requests, conversations, proposals, request, conversation = _service()
    (conversations.close if lifecycle == "closed" else conversations.pause)(conversation.conversation_id)
    before = (requests.read(request.request_id), conversations.read(conversation.conversation_id), proposals.proposal_count())
    assert service.handle(OrchestratorMessageInput(conversation.conversation_id, "x", "patch")) == OrchestratorFailureResult("failure", expected, (expected,))
    assert (requests.read(request.request_id), conversations.read(conversation.conversation_id), proposals.proposal_count()) == before


def test_request_router_tool_and_proposal_failures_are_stable_without_partial_writes():
    service, requests, conversations, proposals, request, conversation = _service()
    missing = conversations.create("missing-request", workflow_status="awaiting_answer")
    assert service.handle(OrchestratorMessageInput(missing.conversation_id, "x", "patch")).code == "request_read_failed"
    before = (requests.read(request.request_id), conversations.read(conversation.conversation_id), proposals.proposal_count())
    assert service.handle(OrchestratorMessageInput(conversation.conversation_id, "x", "patch", extraction_payload=[])).code == "invalid_extraction_payload"
    invalid_tool_service, _, _, invalid_tool_proposals, _, invalid_tool_conversation = _service(
        extractor=lambda *_args, **_kwargs: {"operations": "bad"}
    )
    invalid_tool_result = invalid_tool_service.handle(OrchestratorMessageInput(invalid_tool_conversation.conversation_id, "x", "patch"))
    assert isinstance(invalid_tool_result, OrchestratorClarificationResult)
    assert invalid_tool_result.route_category == "needs_clarification"
    assert invalid_tool_proposals.proposal_count() == 0

    class BrokenProposalService:
        def create_proposal(self, *_args, **_kwargs):
            raise RuntimeError("no ledger write")
        def proposal_count(self):
            return 0
    broken, b_requests, b_conversations, _proposals, b_request, b_conversation = _service(proposals=BrokenProposalService())
    before_broken = (b_requests.read(b_request.request_id), b_conversations.read(b_conversation.conversation_id))
    assert broken.handle(OrchestratorMessageInput(b_conversation.conversation_id, "x", "patch")).code == "proposal_creation_failed"
    assert (b_requests.read(b_request.request_id), b_conversations.read(b_conversation.conversation_id)) == before_broken
    assert (requests.read(request.request_id), conversations.read(conversation.conversation_id), proposals.proposal_count()) == before


def test_invalid_workflow_snapshot_is_rejected_before_proposal_or_conversation_write():
    service, requests, conversations, proposals, request, conversation = _service(workflow_status="not_a_workflow_state")
    before = (requests.read(request.request_id), conversations.read(conversation.conversation_id), proposals.proposal_count())
    result = service.handle(OrchestratorMessageInput(conversation.conversation_id, "x", "patch"))
    assert result == OrchestratorFailureResult("failure", "invalid_workflow_state", ("invalid_workflow_state",))
    assert (requests.read(request.request_id), conversations.read(conversation.conversation_id), proposals.proposal_count()) == before


@pytest.mark.parametrize("intent", ["general_qa", "rag_qa", "current_input", "needs_clarification"])
def test_non_patch_and_clarification_routes_do_not_invoke_extractor_or_mutate(intent):
    calls = []
    service, requests, conversations, proposals, request, conversation = _service(extractor=lambda *_args, **_kwargs: calls.append(True))
    before = (requests.read(request.request_id), conversations.read(conversation.conversation_id), proposals.proposal_count())
    result = service.handle(OrchestratorMessageInput(conversation.conversation_id, "question", intent))
    expected_type = OrchestratorClarificationResult if intent == "needs_clarification" else OrchestratorReadOnlyResult
    assert isinstance(result, expected_type)
    assert result.route_category == intent
    assert not calls
    assert (requests.read(request.request_id), conversations.read(conversation.conversation_id), proposals.proposal_count()) == before
    clarification = service.handle(OrchestratorMessageInput(conversation.conversation_id, "?", "unknown"))
    assert clarification.route_category == "needs_clarification"
    assert not calls


def test_no_candidate_returns_server_clarification_without_planning_or_store_writes():
    no_candidate = lambda *_args, **_kwargs: {"operations": []}
    service, requests, conversations, proposals, request, conversation = _service(workflow_status="planning_next_question", extractor=no_candidate)
    other = conversations.create(request.request_id, workflow_status="planning_next_question")
    first = service.handle(OrchestratorMessageInput(conversation.conversation_id, "x", "patch"))
    second = service.handle(OrchestratorMessageInput(conversation.conversation_id, "x", "patch"))
    assert isinstance(first, OrchestratorClarificationResult)
    assert first == second
    assert first.kind == "clarification"
    assert first.question == "변경할 항목과 값을 구체적으로 다시 알려주세요."
    assert proposals.proposal_count() == 0
    assert conversations.read(other.conversation_id).version == other.version
    source = inspect.getsource(OrchestratorService)
    for forbidden in ("approve_proposal", "reject_proposal", "expire_proposal", "rag_", "app.", "ui."):
        assert forbidden not in source


def test_tool_failure_is_a_stable_clarification_without_proposal_or_store_writes():
    service, requests, conversations, proposals, request, conversation = _service(
        extractor=lambda *_args, **_kwargs: {"operations": "malformed"}
    )
    before = (requests.read(request.request_id), conversations.read(conversation.conversation_id), proposals.proposal_count())
    result = service.handle(OrchestratorMessageInput(conversation.conversation_id, "x", "patch"))
    assert result == OrchestratorClarificationResult(
        "clarification", "needs_clarification", ("intent_patch", "tool_failure", "invalid_structured_output"),
        "응답을 해석하지 못했습니다. 변경할 항목과 값을 다시 알려주세요.",
    )
    assert (requests.read(request.request_id), conversations.read(conversation.conversation_id), proposals.proposal_count()) == before


def test_different_requests_and_conversations_are_isolated_for_read_only_planning():
    first, first_requests, first_conversations, first_proposals, first_request, first_conversation = _service(
        workflow_status="planning_next_question", extractor=lambda *_args, **_kwargs: {"operations": []}
    )
    second, second_requests, second_conversations, second_proposals, second_request, second_conversation = _service(
        workflow_status="planning_next_question", extractor=lambda *_args, **_kwargs: {"operations": []}
    )
    second_before = (second_requests.read(second_request.request_id), second_conversations.read(second_conversation.conversation_id))
    first_result = first.handle(OrchestratorMessageInput(first_conversation.conversation_id, "x", "patch"))
    second_result = second.handle(OrchestratorMessageInput(second_conversation.conversation_id, "x", "patch"))
    assert first_request.request_id != second_request.request_id
    assert first_result == second_result
    assert first_proposals.proposal_count() == second_proposals.proposal_count() == 0
    assert (second_requests.read(second_request.request_id), second_conversations.read(second_conversation.conversation_id)) == second_before
