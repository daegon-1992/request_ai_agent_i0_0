from copy import deepcopy

from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.chat_patch import apply_patch_operations
from request_ai_agent_i0_0.conversation_store import ConversationStore
from request_ai_agent_i0_0.field_registry import FieldRegistryDTO, get_geometry_products_adapter
from request_ai_agent_i0_0.orchestrator_service import OrchestratorMessageInput, OrchestratorProposalResult, OrchestratorService
from request_ai_agent_i0_0.proposal_store import ProposalService
from request_ai_agent_i0_0.request_state_store import RequestStateStore
from request_ai_agent_i0_0.workflow_machine import ConversationWorkflowMachine


def _runtime(value):
    def extractor(*_args, **_kwargs):
        return {
            "operations": [
                {"op": "set", "path": "analysis_overview.request_description", "value": value}
            ]
        }

    app = create_app(orchestrator_extractor=extractor)
    app.config["TESTING"] = True
    client = app.test_client()
    request_id = client.post("/api/request/versioned", json={}).get_json()["request_id"]
    conversation_id = client.post("/api/conversations", json={"request_id": request_id}).get_json()["conversation_id"]
    return app, client, request_id, conversation_id


def _set_server_value(app, request_id, value):
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)
    return requests.compare_and_swap(
        request_id,
        before.version,
        lambda state: apply_patch_operations(
            state,
            ({"op": "set", "path": "analysis_overview.request_description", "value": value},),
        ),
    )


def _message(client, conversation_id):
    return client.post(
        "/api/orchestrator/messages",
        json={"conversation_id": conversation_id, "message": "update the description", "intent": "patch"},
    )


def test_differing_existing_value_creates_server_latest_correction_without_preapproval_mutation_or_workflow_dispatch():
    app, client, request_id, conversation_id = _runtime("new server value")
    latest = _set_server_value(app, request_id, "old server value")
    requests = app.extensions["request_state_store"]
    conversations = app.extensions["conversation_store"]
    proposals = app.extensions["proposal_service"]
    before_request = requests.read(request_id)
    before_conversation = conversations.read(conversation_id)

    response = _message(client, conversation_id)

    assert response.status_code == 200
    body = response.get_json()
    assert body["kind"] == "proposal_created"
    proposal = proposals.read_proposal(body["proposal"]["proposal_id"])
    assert proposal.request_id == request_id
    assert proposal.base_version == latest.version == before_request.version
    assert proposal.source == "orchestrator_llm"
    assert proposal.status == "pending"
    assert proposal.diff_summary["changed_path_count"] > 0
    assert requests.read(request_id) == before_request
    assert conversations.read(conversation_id) == before_conversation

    approved = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal.proposal_id, "decision": "approve"},
    )
    assert approved.get_json()["status"] == "approved"
    latest_get = client.get(f"/api/request/versioned/{request_id}").get_json()
    assert latest_get["request_version"] == before_request.version + 1
    assert latest_get["state"]["analysis_overview"]["request_description"]["value"] == "new server value"


def test_same_existing_value_is_a_read_only_clarification_without_ledger_or_state_change():
    app, client, request_id, conversation_id = _runtime("unchanged")
    _set_server_value(app, request_id, "unchanged")
    requests = app.extensions["request_state_store"]
    conversations = app.extensions["conversation_store"]
    proposals = app.extensions["proposal_service"]
    before = (deepcopy(requests.read(request_id)), deepcopy(conversations.read(conversation_id)), proposals.proposal_count())

    response = _message(client, conversation_id)

    assert response.status_code == 200
    assert response.get_json()["kind"] == "clarification"
    assert response.get_json()["reasons"] == ["intent_patch", "tool_candidates", "same_value"]
    assert response.get_json()["question"] == "현재 값과 동일합니다. 다른 값을 알려주세요."
    assert (requests.read(request_id), conversations.read(conversation_id), proposals.proposal_count()) == before


def test_correction_rejects_a_server_version_race_without_creating_a_noop_ledger_record(monkeypatch):
    app, client, request_id, conversation_id = _runtime("new server value")
    _set_server_value(app, request_id, "old server value")
    requests = app.extensions["request_state_store"]
    proposals = app.extensions["proposal_service"]
    original = proposals.create_proposal

    def racing_create(server_request_id, operations, **kwargs):
        _set_server_value(app, server_request_id, "new server value")
        return original(server_request_id, operations, **kwargs)

    monkeypatch.setattr(proposals, "create_proposal", racing_create)
    response = _message(client, conversation_id)

    assert response.status_code == 503
    assert response.get_json()["error"] == "proposal_creation_failed"
    assert proposals.proposal_count() == 0
    assert requests.read(request_id).state["analysis_overview"]["request_description"]["value"] == "new server value"


def test_condition_correction_reads_the_registry_canonical_condition_set_not_legacy_transport_rows():
    state = {
        "conditions": {
            "condition_sets": [
                {"id": "space_environment_1", "fields": {"room_temp": {"value": "25"}}}
            ],
            "fields": [{"key": "space_environment_1.room_temp", "values": [{"value": ""}]}],
        }
    }
    registry = FieldRegistryDTO(
        field_id="conditions.space_environment_1.room_temp",
        canonical_path="conditions.condition_sets[card_id=space_environment_1].fields.room_temp.value",
        value_path="conditions.condition_sets[card_id=space_environment_1].fields.room_temp.value",
        label="room temperature", value_type="text", unit="degC", active=True, required=False,
        required_level="optional_non_blocking", dependencies=(), validation_binding="existing", priority="optional",
        operation_path="conditions.fields.room_temp.values", field_key="room_temp", card_id="space_environment_1",
    )
    requests = RequestStateStore(lambda value: deepcopy(dict(value)))
    request = requests.create(state)
    conversations = ConversationStore()
    conversation = conversations.create(request.request_id)
    proposals = ProposalService(requests)
    service = OrchestratorService(
        conversations=conversations, requests=requests, proposals=proposals,
        workflow=ConversationWorkflowMachine(conversations), registry_reader=lambda _state: (registry,),
        geometry_adapter_reader=get_geometry_products_adapter,
        extractor=lambda *_args, **_kwargs: {
            "operations": [{
                "op": "condition_values", "path": "conditions.fields.room_temp.values", "field_key": "room_temp",
                "values": ["30"], "unit": "degC",
            }]
        },
    )

    result = service.handle(OrchestratorMessageInput(conversation.conversation_id, "set temperature", "patch"))

    assert isinstance(result, OrchestratorProposalResult)
    proposal = proposals.read_proposal(result.proposal_id)
    assert proposal.base_version == request.version
    assert proposals.proposal_count() == 1
    assert conversations.read(conversation.conversation_id) == conversation
