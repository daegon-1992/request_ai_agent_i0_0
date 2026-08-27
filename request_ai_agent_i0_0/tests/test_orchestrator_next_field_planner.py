from copy import deepcopy
import inspect
from unittest.mock import patch

from request_ai_agent_i0_0.field_registry import FieldRegistryDTO
from request_ai_agent_i0_0.conversation_store import ConversationStore
from request_ai_agent_i0_0.next_field_planner import (
    NextFieldPlannerInput,
    PlannerFailureDTO,
    QuestionHistoryDTO,
    ValidationReadyDecisionDTO,
    plan_next_fields,
    planner_input_from_state,
)
from request_ai_agent_i0_0.proposal_store import ProposalService
from request_ai_agent_i0_0.request_state_store import RequestStateStore


def _field(field_id, *, required=True, active=True, dependencies=()):
    return FieldRegistryDTO(
        field_id=field_id, canonical_path=field_id, value_path=field_id,
        label=field_id, value_type="text", unit="", active=active, required=required,
        required_level="required" if required else "optional_non_blocking", dependencies=dependencies,
        validation_binding="existing", priority="blocking_required" if required else "optional",
    )


def _input(state, registry, history=(), validation=None):
    return NextFieldPlannerInput(state, tuple(registry), tuple(history), "planning_next_question", validation)


def test_same_snapshots_return_the_same_two_fields_and_reasons_with_a_three_field_cap():
    state = {"request_context": {"analysis_type": ""}, "analysis_overview": {"request_description": {"value": ""}}}
    registry = (_field("request_context.analysis_type"), _field("analysis_overview.request_description"), _field("basic_info.owner"))
    validation = {"blocking": [{"path": "analysis_overview.request_description"}]}
    first = plan_next_fields(_input(state, registry, validation=validation))
    second = plan_next_fields(_input(state, registry, validation=validation))
    assert first == second
    assert [item.field_id for item in first.fields] == ["analysis_overview.request_description", "basic_info.owner"]
    assert len(first.fields) == 2
    assert first.fields[0].reasons == ("validation_blocker", "required")


def test_required_dependency_and_blockers_beat_optional_and_inactive_or_repeated_candidates():
    state = {"request_context": {"analysis_type": ""}, "basic_info": {"owner": {"value": ""}}, "extra": {"value": ""}}
    registry = (
        _field("request_context.analysis_type"),
        _field("basic_info.owner", dependencies=("request_context.analysis_type",)),
        _field("extra", required=False),
        _field("inactive", active=False),
    )
    decision = plan_next_fields(_input(state, registry, (QuestionHistoryDTO("request_context.analysis_type"),), {"blocking": [{"path": "basic_info.owner"}]}))
    assert [item.field_id for item in decision.fields] == ["request_context.analysis_type", "basic_info.owner"]
    assert decision.fields[0].reasons == ("unmet_dependency", "required", "previously_asked")
    assert decision.fields[1].reasons == ("validation_blocker", "required")

    same_tier = plan_next_fields(_input({"a": {"value": ""}, "b": {"value": ""}}, (_field("a"), _field("b")), (QuestionHistoryDTO("a"),), {"blocking": []}))
    assert [item.field_id for item in same_tier.fields] == ["b", "a"]


def test_no_candidates_or_existing_ready_validation_returns_validation_ready():
    filled = {"basic_info": {"owner": {"value": "Kim"}}, "review": {"submission": {"can_submit": False}}}
    registry = (_field("basic_info.owner"),)
    assert plan_next_fields(_input(filled, registry)).reason == "no_active_unfilled_fields"
    ready = plan_next_fields(_input({"review": {"submission": {"can_submit": True}}}, registry))
    assert isinstance(ready, ValidationReadyDecisionDTO)
    assert ready.reason == "existing_validation_ready"


def test_malformed_or_registry_or_validation_read_failure_returns_stable_failure_without_mutation():
    state = {"basic_info": {"owner": {"value": ""}}}
    before = deepcopy(state)
    bad = NextFieldPlannerInput(state, (_field("basic_info.owner"),), tuple(QuestionHistoryDTO("x") for _ in range(101)), "planning_next_question")
    assert plan_next_fields(bad) == PlannerFailureDTO("planner_failure", "invalid_question_history")
    assert plan_next_fields(NextFieldPlannerInput(state, ("bad",), (), "planning_next_question")) == PlannerFailureDTO("planner_failure", "invalid_registry_snapshot")
    assert plan_next_fields(NextFieldPlannerInput(state, (), (), "planning_next_question", "bad")) == PlannerFailureDTO("planner_failure", "invalid_validation_snapshot")
    assert plan_next_fields(NextFieldPlannerInput(state, (), None, "planning_next_question")) == PlannerFailureDTO("planner_failure", "invalid_question_history")
    assert planner_input_from_state("bad", (), "planning_next_question") == PlannerFailureDTO("planner_failure", "invalid_request_state")
    with patch("request_ai_agent_i0_0.next_field_planner.get_field_registry", side_effect=RuntimeError("unavailable")):
        assert planner_input_from_state(state, (), "planning_next_question") == PlannerFailureDTO("planner_failure", "registry_read_failed")
    assert state == before

    malformed_state = {"basic_info": {"owner": {"value": ""}}, "review": {"validator": "bad"}}
    requests = RequestStateStore(lambda item: deepcopy(dict(item)))
    request = requests.create(malformed_state)
    conversations = ConversationStore()
    conversation = conversations.create(request.request_id)
    proposals = ProposalService(requests)
    request_before = requests.read(request.request_id)
    conversation_before = conversations.read(conversation.conversation_id)
    assert plan_next_fields(_input(request.state, (_field("basic_info.owner"),))) == PlannerFailureDTO("planner_failure", "validation_read_failed")
    assert requests.read(request.request_id) == request_before
    assert conversations.read(conversation.conversation_id) == conversation_before
    assert proposals.proposal_count() == 0


def test_request_and_history_inputs_are_isolated_and_planner_has_no_store_or_dispatch_boundary():
    first = _input({"basic_info": {"owner": {"value": ""}}}, (_field("basic_info.owner"),))
    second = _input({"basic_info": {"owner": {"value": "Lee"}}}, (_field("basic_info.owner"),))
    assert [item.field_id for item in plan_next_fields(first).fields] == ["basic_info.owner"]
    assert plan_next_fields(second).reason == "no_active_unfilled_fields"
    # Focused source inspection proves the planner cannot call those authorities.
    assert set(NextFieldPlannerInput.__dataclass_fields__) == {"request_state", "registry", "question_history", "workflow_state", "validation"}
    source = inspect.getsource(plan_next_fields)
    assert "RequestStateStore" not in source
    assert "ConversationStore" not in source
    assert ".dispatch(" not in source
