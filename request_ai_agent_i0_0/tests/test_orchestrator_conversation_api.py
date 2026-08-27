from copy import deepcopy

from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.proposal_store import ProposalService


def _client_with_request():
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    response = client.post("/api/request/versioned", json={})
    assert response.status_code == 201
    return app, client, response.get_json()["request_id"]


def _create(client, request_id, **extra):
    return client.post("/api/conversations", json={"request_id": request_id, **extra})


def test_conversation_api_create_read_pause_resume_close_and_rejects_invalid_or_closed_transitions():
    _app, client, request_id = _client_with_request()
    created = _create(client, request_id)
    assert created.status_code == 201
    body = created.get_json()
    conversation_id = body["conversation_id"]
    assert body["request_id"] == request_id
    assert body["status"] == "active"
    assert body["paused"] is False
    assert body["conversation_version"] == 0

    assert client.get(f"/api/conversations/{conversation_id}").get_json() == body
    paused = client.post(f"/api/conversations/{conversation_id}/pause")
    assert paused.status_code == 200
    assert paused.get_json()["status"] == "paused"
    assert client.post(f"/api/conversations/{conversation_id}/pause").get_json()["error"] == "invalid_conversation_transition"
    resumed = client.post(f"/api/conversations/{conversation_id}/resume")
    assert resumed.status_code == 200
    assert resumed.get_json()["status"] == "active"
    closed = client.post(f"/api/conversations/{conversation_id}/close")
    assert closed.status_code == 200
    assert closed.get_json()["status"] == "closed"
    for endpoint in ("pause", "resume", "close"):
        response = client.post(f"/api/conversations/{conversation_id}/{endpoint}")
        assert response.status_code == 409
        assert response.get_json()["error"] == "invalid_conversation_transition"


def test_unknown_request_and_conversation_and_bounded_failure_preserve_existing_records_and_request():
    app, client, request_id = _client_with_request()
    unknown = _create(client, "missing-request")
    assert unknown.status_code == 404
    assert unknown.get_json()["error"] == "request_not_found"
    assert client.get("/api/conversations/missing-conversation").status_code == 404
    assert client.post("/api/conversations/missing-conversation/pause").status_code == 404

    request_before = deepcopy(app.extensions["request_state_store"].read(request_id))
    store = app.extensions["conversation_store"]
    store._max_conversations = 1
    first = _create(client, request_id)
    assert first.status_code == 201
    first_before = client.get(f"/api/conversations/{first.get_json()['conversation_id']}").get_json()
    second = _create(client, request_id)
    assert second.status_code == 409
    assert second.get_json()["error"] == "conversation_store_full"
    assert client.get(f"/api/conversations/{first.get_json()['conversation_id']}").get_json() == first_before
    assert app.extensions["request_state_store"].read(request_id) == request_before


def test_api_projection_is_a_deep_copy_and_never_exposes_or_accepts_request_state_or_proposal_payloads():
    app, client, request_id = _client_with_request()
    created = _create(client, request_id)
    conversation_id = created.get_json()["conversation_id"]
    projection = client.get(f"/api/conversations/{conversation_id}").get_json()
    projection["question_history"].append("forged response mutation")
    reread = client.get(f"/api/conversations/{conversation_id}").get_json()
    assert reread["question_history"] == []
    assert {"state", "request_version", "operations", "base_version", "diff_summary", "validation", "result"}.isdisjoint(reread)

    request_before = app.extensions["request_state_store"].read(request_id)
    rejected = client.post(
        "/api/conversations",
        json={"request_id": request_id, "state": {"forged": True}, "operations": [{"op": "set"}]},
    )
    assert rejected.status_code == 400
    assert rejected.get_json()["error"] == "invalid_conversation_payload"
    assert app.extensions["request_state_store"].read(request_id) == request_before
    assert client.post(f"/api/conversations/{conversation_id}/pause", json={"proposal_id": "forged"}).status_code == 400


def test_proposal_reference_is_server_id_only_and_terminal_status_is_reread_from_h5_009_ledger():
    app, client, request_id = _client_with_request()
    proposals = ProposalService(app.extensions["request_state_store"])
    proposal = proposals.create_proposal(
        request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "ledger-only"}],
        source="llm_structured_output",
    )
    created = _create(client, request_id, proposal_id=proposal.proposal_id)
    assert created.status_code == 201
    conversation_id = created.get_json()["conversation_id"]
    terminal = proposals.reject_proposal(proposal.proposal_id)
    projection = client.get(f"/api/conversations/{conversation_id}").get_json()

    assert terminal.status == "rejected"
    assert projection["proposal_id"] == proposal.proposal_id
    assert {"operations", "base_version", "diff_summary", "validation", "result", "proposal_status"}.isdisjoint(projection)
    assert proposals.read_proposal(proposal.proposal_id).status == "rejected"
