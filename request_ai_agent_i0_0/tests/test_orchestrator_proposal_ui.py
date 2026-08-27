import pytest

from request_ai_agent_i0_0.app import create_app


def _runtime():
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    created = client.post("/api/request/versioned", json={}).get_json()
    return app, client, created["request_id"]


def _proposal(app, request_id, value="server candidate"):
    return app.extensions["proposal_service"].create_proposal(
        request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": value}],
        source="llm_structured_output",
    )


def _decide(client, proposal_id, decision, **extra):
    return client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal_id, "decision": decision, **extra},
    )


def test_decision_adapter_accepts_only_server_proposal_id_and_explicit_decision():
    app, client, request_id = _runtime()
    proposal = _proposal(app, request_id)
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)

    response = _decide(client, proposal.proposal_id, "approve", state={}, operations=[], request_version=4)

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": "invalid_proposal_decision_payload", "read_only": True}
    assert requests.read(request_id) == before


def test_invalid_decision_and_apply_failure_are_stable_and_do_not_change_request(monkeypatch):
    app, client, request_id = _runtime()
    proposal = _proposal(app, request_id)
    requests = app.extensions["request_state_store"]
    service = app.extensions["proposal_service"]
    before = requests.read(request_id)

    invalid = _decide(client, proposal.proposal_id, "expire")
    monkeypatch.setattr(service, "approve_proposal", lambda _proposal_id: (_ for _ in ()).throw(RuntimeError("apply failure")))
    failed = _decide(client, proposal.proposal_id, "approve")

    assert invalid.status_code == 400
    assert invalid.get_json()["error"] == "invalid_proposal_decision_payload"
    assert failed.status_code == 503
    assert failed.get_json() == {"ok": False, "error": "proposal_decision_failed", "read_only": True}
    assert requests.read(request_id) == before


def test_approve_delegates_once_to_existing_service_and_only_server_cas_changes_version(monkeypatch):
    app, client, request_id = _runtime()
    proposal = _proposal(app, request_id)
    service = app.extensions["proposal_service"]
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)
    calls = 0
    original = service.approve_proposal

    def tracked(proposal_id):
        nonlocal calls
        calls += 1
        return original(proposal_id)

    monkeypatch.setattr(service, "approve_proposal", tracked)
    approved = _decide(client, proposal.proposal_id, "approve")
    replay = _decide(client, proposal.proposal_id, "approve")

    assert approved.status_code == replay.status_code == 200
    assert approved.get_json() == {"ok": True, "proposal_id": proposal.proposal_id, "status": "approved", "read_only": True}
    assert replay.get_json()["status"] == "approved"
    assert calls == 2  # API delegates; ProposalService provides the exactly-once replay behavior.
    assert requests.read(request_id).version == before.version + 1


@pytest.mark.parametrize("decision, expected", [("reject", "rejected"), ("approve", "conflicted")])
def test_terminal_and_stale_decisions_are_read_only_without_unrelated_request_change(decision, expected):
    app, client, request_id = _runtime()
    proposal = _proposal(app, request_id)
    requests = app.extensions["request_state_store"]
    if expected == "conflicted":
        current = requests.read(request_id)
        assert client.put(f"/api/request/versioned/{request_id}", json={"expected_version": current.version, "state": current.state}).status_code == 200
    before = requests.read(request_id)

    response = _decide(client, proposal.proposal_id, decision)
    replay = _decide(client, proposal.proposal_id, decision)

    assert response.get_json()["status"] == replay.get_json()["status"] == expected
    assert requests.read(request_id) == before


def test_forged_unknown_and_terminal_ids_never_change_request():
    app, client, request_id = _runtime()
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)
    unknown = _decide(client, "proposal_forged", "approve")
    proposal = _proposal(app, request_id)
    assert _decide(client, proposal.proposal_id, "reject").get_json()["status"] == "rejected"
    terminal = _decide(client, proposal.proposal_id, "approve")

    assert unknown.status_code == 404
    assert terminal.get_json()["status"] == "rejected"
    assert requests.read(request_id) == before


def test_undo_adapter_accepts_only_server_proposal_id_and_returns_a_display_only_inverse_proposal():
    app, client, request_id = _runtime()
    requests = app.extensions["request_state_store"]
    initial = requests.read(request_id)
    seeded = dict(initial.state)
    overview = dict(seeded["analysis_overview"])
    overview["request_description"] = {"value": "before undo"}
    seeded["analysis_overview"] = overview
    requests.replace(request_id, initial.version, seeded)
    original = _proposal(app, request_id, "after undo")
    assert _decide(client, original.proposal_id, "approve").get_json()["status"] == "approved"
    before_undo = requests.read(request_id)

    invalid = client.post("/api/orchestrator/proposals/undo", json={"proposal_id": original.proposal_id, "state": {}})
    created = client.post("/api/orchestrator/proposals/undo", json={"proposal_id": original.proposal_id})
    duplicate = client.post("/api/orchestrator/proposals/undo", json={"proposal_id": original.proposal_id})

    assert invalid.status_code == 400
    assert invalid.get_json()["error"] == "invalid_undo_payload"
    assert created.status_code == 200
    body = created.get_json()
    assert body["kind"] == "undo_proposal_created"
    assert body["proposal"]["status"] == "pending"
    assert set(body["proposal"]) == {"proposal_id", "status", "diff"}
    assert duplicate.get_json() == {"ok": True, "kind": "undo_unavailable", "code": "undo_duplicate", "read_only": True}
    assert requests.read(request_id) == before_undo
