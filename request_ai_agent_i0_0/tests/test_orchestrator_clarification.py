import pytest

from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.field_registry import FieldRegistryDTO
from test_orchestrator_chat_panel import _run_panel_runtime


def _runtime(extractor):
    app = create_app(orchestrator_extractor=extractor)
    app.config["TESTING"] = True
    client = app.test_client()
    request_id = client.post("/api/request/versioned", json={}).get_json()["request_id"]
    conversation_id = client.post("/api/conversations", json={"request_id": request_id}).get_json()["conversation_id"]
    return app, client, request_id, conversation_id


def _message(client, conversation_id, message):
    return client.post("/api/orchestrator/messages", json={"conversation_id": conversation_id, "message": message, "intent": "patch"})


def _before(app, request_id, conversation_id):
    return (
        app.extensions["request_state_store"].read(request_id),
        app.extensions["conversation_store"].read(conversation_id),
        app.extensions["proposal_service"].proposal_count(),
    )


@pytest.mark.parametrize(
    ("message", "operations", "expected_reasons", "question"),
    [
        (
            "two values",
            [
                {"op": "set", "path": "analysis_overview.request_description", "value": "first"},
                {"op": "set", "path": "analysis_overview.project_name", "value": "second"},
            ],
            ["intent_patch", "tool_candidates", "multiple_candidates"],
            "한 번에 하나의 변경 항목과 값을 명확히 알려주세요.",
        ),
        (
            "ambiguous",
            [{"op": "set", "path": "analysis_overview.request_description", "value": "either", "ambiguity": True}],
            ["intent_patch", "tool_no_candidate", "ambiguous_value"],
            "변경할 항목과 값이 하나로 정해지도록 다시 알려주세요.",
        ),
    ],
)
def test_ambiguous_tool_outcomes_return_deterministic_server_questions_without_proposal_or_mutation(message, operations, expected_reasons, question):
    def extractor(*_args, **_kwargs):
        return {"operations": operations}

    app, client, request_id, conversation_id = _runtime(extractor)
    before = _before(app, request_id, conversation_id)
    first, second = _message(client, conversation_id, message), _message(client, conversation_id, message)
    assert first.get_json() == second.get_json()
    body = first.get_json()
    assert body["kind"] == "clarification"
    assert body["route_category"] == "needs_clarification"
    assert body["reasons"] == expected_reasons
    assert body["question"] == question
    assert body["state_changed"] is False and body["read_only"] is True
    assert _before(app, request_id, conversation_id) == before


def test_missing_unit_empty_irrelevant_and_tool_failures_are_read_only_without_client_draft_authority():
    def extractor(message, **_kwargs):
        if message == "unit":
            return {"operations": [{"op": "condition_values", "field_key": "room_temp", "path": "conditions.fields.room_temp.values", "values": ["25"]}]}
        if message == "irrelevant":
            return {"operations": []}
        raise RuntimeError("offline")

    app, client, request_id, conversation_id = _runtime(extractor)
    app.extensions["orchestrator_service"]._registry_reader = lambda _state: (
        FieldRegistryDTO(
            field_id="conditions.room_temp",
            canonical_path="conditions.fields.room_temp.values",
            value_path="conditions.fields.room_temp.values",
            label="room temperature",
            value_type="text",
            unit="degC",
            active=True,
            required=False,
            required_level="optional_non_blocking",
            dependencies=(),
            validation_binding="existing",
            priority="optional",
            operation_path="conditions.fields.room_temp.values",
            field_key="room_temp",
        ),
    )
    before = _before(app, request_id, conversation_id)
    empty = _message(client, conversation_id, "")
    missing_unit = _message(client, conversation_id, "unit")
    irrelevant = _message(client, conversation_id, "irrelevant")
    failure = _message(client, conversation_id, "failure")
    assert empty.get_json()["reasons"] == ["intent_patch", "tool_not_provided", "empty_message"]
    assert empty.get_json()["question"] == "입력 내용이 비어 있습니다. 변경할 항목과 값을 입력해 주세요."
    assert missing_unit.get_json()["reasons"] == ["intent_patch", "tool_no_candidate", "missing_unit"]
    assert missing_unit.get_json()["question"] == "값의 단위를 함께 알려주세요. 예: 25 °C"
    assert irrelevant.get_json()["reasons"] == ["intent_patch", "tool_no_candidate", "no_operations"]
    assert failure.get_json()["reasons"] == ["intent_patch", "tool_failure", "extractor_error"]
    assert failure.get_json()["question"] == "응답을 해석하지 못했습니다. 변경할 항목과 값을 다시 알려주세요."
    assert _before(app, request_id, conversation_id) == before


def test_panel_renders_the_server_question_without_sync_or_follow_up_message():
    _run_panel_runtime(
        """
const requests = [];
global.fetch = async (url, options={}) => { requests.push({url, body:options.body || null}); throw new Error("clarification must not fetch"); };
renderOrchestratorResponse({ok:true, kind:"clarification", route_category:"needs_clarification", reasons:["intent_patch", "tool_no_candidate", "missing_unit"], question:"값의 단위를 함께 알려주세요. 예: 25 °C", state_changed:false, read_only:true});
const message = elements.orchestratorLog.children[0];
if (!String(message.textContent).includes("값의 단위를 함께 알려주세요. 예: 25 °C")) throw new Error("server question missing");
if (requests.length || editorSyncs || derivedRenders || elements.chatLog.children.length || elements.formView.value !== "unchanged") throw new Error("clarification changed UI authority");
"""
    )
