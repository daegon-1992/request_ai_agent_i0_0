from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.request_state_store import RequestStateStore
from request_ai_agent_i0_0.state import create_initial_state, sanitize_state
from request_ai_agent_i0_0.validation_action import ValidationActionService

from test_orchestrator_chat_panel import _run_panel_runtime


def _service():
    requests = RequestStateStore(sanitize_state)
    return requests, ValidationActionService(requests)


def test_explicit_server_latest_action_returns_raw_canonical_validator_result_without_write(monkeypatch):
    requests, service = _service()
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)
    canonical = {
        "blocking": [],
        "warning": [{"code": "existing.warning", "section": "conditions", "path": "conditions.x"}],
        "info": [{"code": "existing.info", "section": "case_matrix", "path": "case_matrix.rows"}],
        "summary": {"can_submit": True},
    }
    seen = []

    def validator(source):
        seen.append(source)
        return canonical

    monkeypatch.setattr("request_ai_agent_i0_0.validation_action.validate_state", validator)
    result = service.run(created.request_id)

    assert result.code == "validation_ready"
    assert result.request_id == created.request_id
    assert result.request_version == created.version
    assert result.validation is canonical
    assert seen == [before.state]
    assert requests.read(created.request_id) == before


def test_unknown_stale_duplicate_and_validator_failure_are_stable_read_only(monkeypatch):
    requests, service = _service()
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)

    blocked = service.run(created.request_id)
    assert blocked.code == "validation_blocked"
    assert blocked.validation["blocking"]
    assert service.run(created.request_id).code == "validation_blocked"
    assert service.run("missing-request").code == "request_not_found"

    original_read = requests.read

    def stale_read(request_id):
        snapshot = original_read(request_id)
        requests.replace(request_id, snapshot.version, snapshot.state)
        return snapshot

    monkeypatch.setattr(requests, "read", stale_read)
    assert service.run(created.request_id).code == "request_version_conflict"
    monkeypatch.setattr(requests, "read", original_read)
    current = requests.read(created.request_id)
    monkeypatch.setattr(
        "request_ai_agent_i0_0.validation_action.validate_state",
        lambda _state: (_ for _ in ()).throw(ValueError("validator failed")),
    )
    assert service.run(created.request_id).code == "validation_failed"
    assert requests.read(created.request_id) == current
    assert before.version == 0


def test_http_action_accepts_only_panel_request_id_and_never_changes_request_or_ledger():
    app = create_app()
    client = app.test_client()
    requests = app.extensions["request_state_store"]
    proposals = app.extensions["proposal_service"]
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)

    invalid = client.post("/api/orchestrator/validation/action", json={"request_id": created.request_id, "state": {}})
    blocked = client.post("/api/orchestrator/validation/action", json={"request_id": created.request_id})
    replay = client.post("/api/orchestrator/validation/action", json={"request_id": created.request_id})

    assert invalid.status_code == 400
    assert blocked.status_code == replay.status_code == 200
    assert blocked.get_json()["kind"] == replay.get_json()["kind"] == "validation_blocked"
    assert blocked.get_json()["state_changed"] is False
    assert requests.read(created.request_id) == before
    assert proposals.proposal_count() == 0


def test_panel_validation_action_is_receipt_gated_request_id_only_and_isolates_legacy_ui():
    _run_panel_runtime(
        """
const requests = [];
global.fetch = async (url, options={}) => {
  requests.push({url, body:options.body || null});
  return {ok:true, json:async()=>({ok:true, kind:"validation_ready", request_id:"request_server", request_version:4, validation:{blocking:[], warning:[{code:"existing.warning", section:"conditions"}], info:[], summary:{can_submit:true}}, read_only:true, state_changed:false})};
};
orchestratorPanelState.requestId = "request_server";
orchestratorPanelState.requestVersion = 4;
orchestratorPanelState.latestApprovedState = {metadata:{request_no:"SERVER"}};
orchestratorPanelState.caseMatrixSyncedRequestId = "request_server";
orchestratorPanelState.caseMatrixSyncedRequestVersion = 4;
const first = runOrchestratorValidationAction();
const second = runOrchestratorValidationAction();
await first; await second;
if (JSON.stringify(requests) !== JSON.stringify([{url:"/api/orchestrator/validation/action", body:'{"request_id":"request_server"}'}])) throw new Error("action was not request-id-only or double-click safe");
if (editorSyncs || derivedRenders || elements.chatLog.children.length || elements.chatInput.value !== "legacy" || elements.formView.value !== "unchanged") throw new Error("action changed legacy UI");
"""
    )


def test_panel_validation_action_rejects_unsynced_and_failed_latest_get_without_legacy_changes():
    _run_panel_runtime(
        """
const requests = [];
global.fetch = async (url, options={}) => {
  requests.push({url, body:options.body || null});
  return {ok:false, json:async()=>({error:"request_read_failed"})};
};
orchestratorPanelState.requestId = "request_server";
await runOrchestratorValidationAction();
if (requests.length) throw new Error("unsynced Request entered Validation action");
await refreshApprovedOrchestratorRequest("proposal_server").catch(() => {});
if (hasSyncedCaseMatrixRequest()) throw new Error("failed latest GET left Validation eligibility");
await runOrchestratorValidationAction();
if (requests.length !== 1 || requests[0].url !== "/api/request/versioned/request_server") throw new Error("failed GET allowed Validation action");
if (editorSyncs || derivedRenders || elements.chatLog.children.length || elements.chatInput.value !== "legacy" || elements.formView.value !== "unchanged") throw new Error("unsynced action changed legacy UI");
"""
    )
