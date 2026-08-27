from copy import deepcopy
import inspect
import json

import pytest

import request_ai_agent_i0_0.orchestrator_extraction_tool as extraction_tool
from request_ai_agent_i0_0.conversation_store import ConversationStore
from request_ai_agent_i0_0.field_registry import FieldRegistryDTO, get_geometry_products_adapter
from request_ai_agent_i0_0.orchestrator_extraction_tool import (
    ExtractionFailureDTO,
    ExtractionNoCandidateDTO,
    ExtractionToolInput,
    extract_candidates,
)
from request_ai_agent_i0_0.proposal_store import ProposalService
from request_ai_agent_i0_0.request_state_store import RequestStateStore


def _field(field_id, path, *, unit="", field_key=""):
    return FieldRegistryDTO(
        field_id=field_id, canonical_path=path, value_path=path, label=field_id,
        value_type="text", unit=unit, active=True, required=False, required_level="optional_non_blocking",
        dependencies=(), validation_binding="existing", priority="optional", operation_path=path, field_key=field_key,
    )


def _input(extractor, state_summary=None, fields=None):
    return ExtractionToolInput(
        "set description", state_summary if state_summary is not None else {"request": "one"},
        tuple(fields or (_field("analysis_overview.request_description", "analysis_overview.request_description"),)),
        get_geometry_products_adapter(), extractor,
    )


def test_mocked_llm_output_is_sanitized_and_projected_to_allowed_candidate_dto():
    seen = {}
    def extractor(message, *, state_summary, schema):
        seen.update(message=message, state_summary=state_summary, schema=schema)
        return {"payload": {"operations": [{
            "op": "set", "path": "analysis_overview.request_description", "value": "New request",
            "confidence": "high", "evidence_phrase": "New request로", "unit": "",
        }]}}

    result = extract_candidates(_input(extractor))
    assert result.kind == "candidates"
    assert result.candidates[0].field_id == "analysis_overview.request_description"
    assert result.candidates[0].candidate_value == "New request"
    assert result.candidates[0].operation["source"] == "llm_structured_output"
    assert seen["schema"]["allowed_fields"][0]["field_id"] == "analysis_overview.request_description"

    geometry = extract_candidates(_input(
        lambda *args, **kwargs: {"operations": [{"op": "list_values", "path": "geometry.products", "values": ["A100"]}]}
    ))
    assert geometry.candidates[0].field_id == "geometry.products"
    assert geometry.candidates[0].operation["adapter"] == "geometry_products_to_complete_product_cards"


@pytest.mark.parametrize("operation, code", [
    ({"op": "set", "path": "analysis_overview.request_description", "value": ""}, "missing_or_invalid_value"),
    ({"op": "set", "path": "analysis_overview.request_description", "value": {"not": "scalar"}}, "missing_or_invalid_value"),
    ({"op": "delete", "path": "analysis_overview.request_description"}, "unsupported_operation"),
    ({"op": "set", "path": "unknown.field", "value": "x"}, "unknown_field"),
    ({"op": "set", "path": "analysis_overview.request_description", "value": "x", "ambiguity": True}, "ambiguous_value"),
])
def test_invalid_operations_are_stable_no_candidates(operation, code):
    result = extract_candidates(_input(lambda *args, **kwargs: {"operations": [operation]}))
    assert result == ExtractionNoCandidateDTO("no_candidate", code, reasons=result.reasons)


def test_missing_required_unit_and_extractor_or_structured_output_failures_are_stable_and_non_mutating(monkeypatch):
    temperature = _field("conditions.room_temp", "conditions.fields.room_temp.values", unit="degC", field_key="room_temp")
    missing_unit = extract_candidates(_input(
        lambda *args, **kwargs: {"operations": [{"op": "condition_values", "field_key": "room_temp", "path": "conditions.fields.room_temp.values", "values": ["25"]}]},
        fields=(temperature,),
    ))
    assert missing_unit == ExtractionNoCandidateDTO("no_candidate", "missing_unit", reasons=missing_unit.reasons)
    state = {"basic_info": {"owner": {"value": "Kim"}}}
    requests = RequestStateStore(lambda item: deepcopy(dict(item)))
    request = requests.create(state)
    conversations = ConversationStore()
    conversation = conversations.create(request.request_id)
    proposals = ProposalService(requests)
    before_request, before_conversation = requests.read(request.request_id), conversations.read(conversation.conversation_id)
    monkeypatch.setattr(extraction_tool, "_existing_extractor", None)
    failures = (
        extract_candidates(_input(None)),
        extract_candidates(_input(lambda *args, **kwargs: {"payload": "bad"})),
        extract_candidates(_input(lambda *args, **kwargs: {"operations": "bad"})),
        extract_candidates(_input(lambda *args, **kwargs: (_ for _ in ()).throw(json.JSONDecodeError("bad", "x", 0)))),
        extract_candidates(_input(lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))),
    )
    assert failures == (
        ExtractionFailureDTO("failure", "extractor_unavailable"),
        ExtractionFailureDTO("failure", "invalid_structured_output"),
        ExtractionFailureDTO("failure", "invalid_structured_output"),
        ExtractionFailureDTO("failure", "invalid_json"),
        ExtractionFailureDTO("failure", "extractor_error"),
    )
    for _ in failures:
        assert requests.read(request.request_id) == before_request
        assert conversations.read(conversation.conversation_id) == before_conversation
        assert proposals.proposal_count() == 0


def test_same_input_is_deterministic_and_snapshots_are_isolated_without_store_or_workflow_calls():
    output = {"operations": [{"op": "set", "path": "analysis_overview.request_description", "value": "same", "confidence": "high"}]}
    seen = []
    def extractor(*args, **kwargs):
        seen.append(deepcopy(kwargs["state_summary"]))
        return deepcopy(output)
    first = extract_candidates(_input(extractor, {"request": "one"}))
    second = extract_candidates(_input(extractor, {"request": "one"}))
    other = extract_candidates(_input(extractor, {"request": "two"}))
    assert first == second
    assert first.candidates[0].operation == other.candidates[0].operation
    assert seen == [{"request": "one"}, {"request": "one"}, {"request": "two"}]
    assert set(ExtractionToolInput.__dataclass_fields__) == {"message", "state_summary", "allowed_fields", "geometry_products_adapter", "extractor"}
    source = inspect.getsource(extract_candidates)
    assert "RequestStateStore" not in source
    assert "ConversationStore" not in source
    assert "ProposalService" not in source
    assert ".dispatch(" not in source
    assert "rag" not in source.lower()


def test_candidate_and_multiple_reasons_keep_output_order_and_do_not_mutate_the_caller_snapshot():
    state_summary = {"request": {"owner": "Kim"}}
    output = {"operations": [
        {"op": "set", "path": "analysis_overview.request_description", "value": "candidate"},
        {"op": "delete", "path": "analysis_overview.request_description"},
        {"op": "set", "path": "unknown.field", "value": "x"},
    ]}
    def extractor(*args, **kwargs):
        kwargs["state_summary"]["request"]["owner"] = "mutated extractor copy"
        return deepcopy(output)

    first = extract_candidates(_input(extractor, state_summary))
    second = extract_candidates(_input(extractor, state_summary))
    assert first == second
    assert [item.candidate_value for item in first.candidates] == ["candidate"]
    assert [(item.operation_index, item.code) for item in first.reasons] == [
        (1, "unsupported_operation"), (2, "unknown_field"),
    ]
    assert state_summary == {"request": {"owner": "Kim"}}
