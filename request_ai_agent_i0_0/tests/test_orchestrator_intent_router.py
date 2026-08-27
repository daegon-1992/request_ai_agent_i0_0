from copy import deepcopy
import inspect

import pytest

from request_ai_agent_i0_0.conversation_store import ConversationStore
from request_ai_agent_i0_0.orchestrator_extraction_tool import (
    ExtractionCandidateDTO, ExtractionCandidatesDTO, ExtractionFailureDTO, ExtractionNoCandidateDTO,
)
from request_ai_agent_i0_0.orchestrator_intent_router import (
    IntentRouteDTO, IntentRouterFailureDTO, IntentRouterInput, route_intent,
)
from request_ai_agent_i0_0.proposal_store import ProposalService
from request_ai_agent_i0_0.request_state_store import RequestStateStore


@pytest.mark.parametrize("intent", ["patch", "general_qa", "rag_qa", "current_input", "needs_clarification"])
def test_allowed_llm_intents_are_deterministic_routes_with_stable_reason_order(intent):
    tool = ExtractionNoCandidateDTO("no_candidate", "no_operations") if intent == "patch" else None
    input_dto = IntentRouterInput(intent, {"intent": intent, "operations": []}, {"provider": "mock"}, tool)
    first, second = route_intent(input_dto), route_intent(input_dto)
    assert first == second
    assert isinstance(first, IntentRouteDTO)
    assert first.intent == intent
    assert first.route_category == intent
    assert [reason.code for reason in first.reasons] == (
        ["intent_patch", "tool_no_candidate"] if intent == "patch" else [f"intent_{intent}"]
    )


@pytest.mark.parametrize("intent, expected", [(None, "missing_intent"), ("", "missing_intent"), ("rewrite", "unknown_intent"), ({"intent": "patch"}, "missing_intent")])
def test_missing_unknown_or_malformed_intent_returns_stable_clarification(intent, expected):
    result = route_intent(IntentRouterInput(intent))
    assert result == IntentRouteDTO("route", "needs_clarification", "needs_clarification", (result.reasons[0],), None)
    assert result.reasons[0].code == expected


@pytest.mark.parametrize("input_dto, code", [
    (object(), "invalid_router_input"),
    (IntentRouterInput("patch", extraction_payload=[]), "invalid_extraction_payload"),
    (IntentRouterInput("patch", extraction_metadata=[]), "invalid_extraction_metadata"),
    (IntentRouterInput("patch", tool_result=object()), "invalid_tool_result"),
    (IntentRouterInput("patch", tool_result=ExtractionCandidatesDTO("candidates", ("bad",))), "invalid_tool_result"),
    (IntentRouterInput("patch", tool_result=ExtractionCandidatesDTO("candidates", ())), "invalid_tool_result"),
    (IntentRouterInput("patch", tool_result=ExtractionNoCandidateDTO("no_candidate", " ")), "invalid_tool_result"),
    (IntentRouterInput("patch", tool_result=ExtractionFailureDTO("failure", "")), "invalid_tool_result"),
])
def test_invalid_inputs_and_tool_results_are_stable_failures_without_operations(input_dto, code):
    result = route_intent(input_dto)
    assert isinstance(result, IntentRouterFailureDTO)
    assert result.code == code
    assert result.intent == result.route_category == "needs_clarification"
    assert not hasattr(result, "operations")


def test_patch_only_surfaces_precomputed_tool_decision_metadata():
    candidates = ExtractionCandidatesDTO("candidates", (_candidate(),))
    no_candidate = ExtractionNoCandidateDTO("no_candidate", "unknown_field")
    failure = ExtractionFailureDTO("failure", "extractor_error")
    assert route_intent(IntentRouterInput("patch", tool_result=candidates)).patch_tool_outcome == "candidates"
    assert route_intent(IntentRouterInput("patch", tool_result=no_candidate)).patch_tool_code == "unknown_field"
    assert route_intent(IntentRouterInput("patch", tool_result=failure)).patch_tool_outcome == "failure"


def test_multiple_tool_candidates_keep_the_existing_route_and_expose_no_selection_authority():
    candidates = ExtractionCandidatesDTO("candidates", (_candidate(), _candidate()))
    result = route_intent(IntentRouterInput("patch", tool_result=candidates))
    assert isinstance(result, IntentRouteDTO)
    assert [reason.code for reason in result.reasons] == ["intent_patch", "tool_candidates"]
    assert result.patch_tool_code == "multiple_candidates"


def _candidate():
    return ExtractionCandidateDTO(
        "analysis_overview.request_description", "candidate", "medium", "candidate", False, "",
        {"op": "set", "path": "analysis_overview.request_description", "value": "candidate"},
    )


def test_payloads_are_isolated_and_router_does_not_touch_stores_or_workflow():
    requests = RequestStateStore(lambda item: deepcopy(dict(item)))
    request = requests.create({"owner": "Kim"})
    conversations = ConversationStore()
    conversation = conversations.create(request.request_id)
    proposals = ProposalService(requests)
    before = (requests.read(request.request_id), conversations.read(conversation.conversation_id), proposals.proposal_count())
    metadata = {"provider": "mock"}
    first = route_intent(IntentRouterInput("PATCH", {"operations": [{"unsafe": True}]}, metadata, ExtractionNoCandidateDTO("no_candidate", "no_operations")))
    second = route_intent(IntentRouterInput("patch", {"operations": []}, {"provider": "other"}, ExtractionFailureDTO("failure", "offline")))
    metadata["provider"] = "mutated caller"
    assert first.extraction_metadata == {"provider": "mock"}
    assert second.patch_tool_code == "offline"
    assert (requests.read(request.request_id), conversations.read(conversation.conversation_id), proposals.proposal_count()) == before
    source = inspect.getsource(route_intent)
    for forbidden in ("RequestStateStore", "ConversationStore", "ProposalService", ".dispatch(", "sanitize", "rag", "extract_candidates"):
        assert forbidden not in source
