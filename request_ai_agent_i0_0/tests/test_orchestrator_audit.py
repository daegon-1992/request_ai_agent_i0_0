from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.state import create_initial_state


def _runtime():
    app = create_app()
    app.config["TESTING"] = True
    return app, app.test_client()


def _events(client):
    response = client.get("/api/orchestrator/audit/events")
    assert response.status_code == 200
    return response.get_json()["events"]


def test_audit_events_are_isolated_to_each_browser_workspace():
    app = create_app()
    app.config["TESTING"] = True
    client_a = app.test_client()
    client_b = app.test_client()

    request_a = client_a.post(
        "/api/request/versioned",
        json={"state": create_initial_state()},
    ).get_json()["request_id"]
    request_b = client_b.post(
        "/api/request/versioned",
        json={"state": create_initial_state()},
    ).get_json()["request_id"]

    assert client_a.post("/api/orchestrator/preview/action", json={"request_id": request_a}).status_code == 200
    assert client_b.post("/api/orchestrator/preview/action", json={"request_id": request_b}).status_code == 200

    assert {event["request_id"] for event in _events(client_a)} == {request_a}
    assert {event["request_id"] for event in _events(client_b)} == {request_b}


def test_audit_observes_existing_proposal_cas_undo_and_action_results_after_their_authorities():
    app, client = _runtime()
    requests = app.extensions["request_state_store"]
    proposals = app.extensions["proposal_service"]
    created = requests.create(create_initial_state())

    approved = proposals.create_proposal(
        created.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "server value"}],
        source="llm_structured_output",
    )
    assert client.post("/api/orchestrator/proposals/decision", json={"proposal_id": approved.proposal_id, "decision": "approve"}).get_json()["status"] == "approved"
    rejected = proposals.create_proposal(
        created.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "discarded"}],
        source="llm_structured_output",
    )
    assert client.post("/api/orchestrator/proposals/decision", json={"proposal_id": rejected.proposal_id, "decision": "reject"}).get_json()["status"] == "rejected"

    current = requests.read(created.request_id)
    assert client.put(
        f"/api/request/versioned/{created.request_id}",
        json={"expected_version": current.version - 1, "state": current.state},
    ).status_code == 409
    assert client.post("/api/orchestrator/proposals/undo", json={"proposal_id": rejected.proposal_id}).get_json()["kind"] == "undo_unavailable"
    assert client.post("/api/orchestrator/case-matrix/action", json={"request_id": created.request_id}).status_code == 200
    assert client.post("/api/orchestrator/validation/action", json={"request_id": created.request_id}).status_code == 200
    assert client.post("/api/orchestrator/preview/action", json={"request_id": created.request_id}).status_code == 200

    events = _events(client)
    assert [(event["action"], event["result_code"]) for event in events] == [
        ("proposal_approve", "approved"),
        ("proposal_reject", "rejected"),
        ("request_cas", "request_version_conflict"),
        ("proposal_undo", "undo_not_approved"),
        ("case_matrix_action", "case_matrix_blocked"),
        ("validation_action", "validation_blocked"),
        ("preview_action", "preview_ready"),
    ]
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert all(event["request_id"] == created.request_id for event in events)
    assert requests.read(created.request_id).version == current.version


def test_audit_dto_is_redacted_and_forged_unknown_requests_do_not_append_or_mutate():
    app, client = _runtime()
    requests = app.extensions["request_state_store"]
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)

    forged = client.post("/api/orchestrator/preview/action", json={"request_id": "forged-request"})
    malformed = client.post("/api/orchestrator/validation/action", json={"request_id": created.request_id, "state": {}})

    assert forged.status_code == 404
    assert malformed.status_code == 400
    assert _events(client) == []
    assert requests.read(created.request_id) == before

    assert client.post("/api/orchestrator/preview/action", json={"request_id": created.request_id}).status_code == 200
    event = _events(client)[0]
    assert set(event) == {
        "event_id", "timestamp", "sequence", "action", "result_code", "status", "request_id", "conversation_id", "proposal_id"
    }
    forbidden = {"state", "snapshot", "version", "operation", "diff", "message", "qa", "evidence", "validation", "preview", "word"}
    assert not (set(event) & forbidden)
    assert requests.read(created.request_id) == before


def test_audit_observes_rag_result_and_server_validated_paused_workflow_failure_only():
    app, client = _runtime()
    requests = app.extensions["request_state_store"]
    created = requests.create(create_initial_state())
    rag = app.extensions["rag_guidance_action_service"]
    rag._rag_runner = lambda _question, *, state: {  # noqa: SLF001 - focused existing-action seam
        "ok": True,
        "question_type": "rag_qa",
        "sources": [{"source": "existing"}],
        "read_only": True,
        "state_changed": False,
    }
    conversation = client.post("/api/conversations", json={"request_id": created.request_id}).get_json()
    assert client.post(f"/api/conversations/{conversation['conversation_id']}/pause", json={}).status_code == 200
    paused = client.post(
        "/api/orchestrator/messages",
        json={"conversation_id": conversation["conversation_id"], "message": "unchanged", "intent": "general_qa"},
    )
    ready = client.post(
        "/api/orchestrator/rag-guidance/action",
        json={"request_id": created.request_id, "question": "document question"},
    )

    assert paused.status_code == 409
    assert ready.get_json()["kind"] == "rag_guidance_ready"
    events = _events(client)
    assert [(event["action"], event["result_code"]) for event in events] == [
        ("conversation_pause", "conversation_paused"),
        ("orchestrator_message", "conversation_paused"),
        ("rag_guidance_action", "rag_guidance_ready"),
    ]


def test_audit_read_failure_is_stable_read_only_and_never_changes_existing_authorities(monkeypatch):
    app, client = _runtime()
    requests = app.extensions["request_state_store"]
    proposals = app.extensions["proposal_service"]
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)

    monkeypatch.setattr(
        app.extensions["runtime_audit_log"],
        "events",
        lambda: (_ for _ in ()).throw(RuntimeError("audit unavailable")),
    )
    response = client.get("/api/orchestrator/audit/events")

    assert response.status_code == 503
    assert response.get_json() == {"ok": False, "error": "audit_read_failed", "events": [], "read_only": True}
    assert requests.read(created.request_id) == before
    assert proposals.proposal_count() == 0
