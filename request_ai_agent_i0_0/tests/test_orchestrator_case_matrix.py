from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.case_matrix_action import CaseMatrixActionService
from request_ai_agent_i0_0.request_state_store import RequestStateStore
from request_ai_agent_i0_0.state import create_initial_state, sanitize_state

from test_orchestrator_chat_panel import _run_panel_runtime


def _service():
    requests = RequestStateStore(sanitize_state)
    return requests, CaseMatrixActionService(requests)


def test_explicit_server_latest_action_uses_existing_engine_without_request_write(monkeypatch):
    requests, service = _service()
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)
    seen = []

    def ready_validator(source):
        seen.append(source)
        return {"blocking": []}

    monkeypatch.setattr("request_ai_agent_i0_0.case_matrix_action.validate_state", ready_validator)
    result = service.run(created.request_id)

    assert result.code == "case_matrix_ready"
    assert result.request_id == created.request_id
    assert result.request_version == created.version
    assert result.matrix_summary == {"row_count": 0, "column_count": 9, "generation_status": "missing", "read_only": True}
    assert seen and seen[0] == before.state
    assert requests.read(created.request_id) == before


def test_validator_blocking_unknown_stale_duplicate_and_engine_failure_are_read_only(monkeypatch):
    requests, service = _service()
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)

    blocked = service.run(created.request_id)
    assert blocked.code == "case_matrix_blocked"
    assert blocked.blocking_reasons
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
    monkeypatch.setattr("request_ai_agent_i0_0.case_matrix_action.validate_state", lambda _state: {"blocking": []})
    monkeypatch.setattr("request_ai_agent_i0_0.case_matrix_action.generate_case_matrix", lambda _state: (_ for _ in ()).throw(ValueError("engine failed")))
    assert service.run(created.request_id).code == "case_matrix_engine_failed"
    assert requests.read(created.request_id) == current
    assert before.version == 0


def test_http_action_accepts_only_panel_request_id_and_never_changes_request_or_ledger():
    app = create_app()
    client = app.test_client()
    requests = app.extensions["request_state_store"]
    proposals = app.extensions["proposal_service"]
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)

    invalid = client.post("/api/orchestrator/case-matrix/action", json={"request_id": created.request_id, "state": {}})
    blocked = client.post("/api/orchestrator/case-matrix/action", json={"request_id": created.request_id})
    replay = client.post("/api/orchestrator/case-matrix/action", json={"request_id": created.request_id})

    assert invalid.status_code == 400
    assert blocked.status_code == replay.status_code == 200
    assert blocked.get_json()["kind"] == replay.get_json()["kind"] == "case_matrix_blocked"
    assert blocked.get_json()["state_changed"] is False
    assert requests.read(created.request_id) == before
    assert proposals.proposal_count() == 0


def test_panel_case_matrix_action_is_request_id_only_double_click_safe_and_never_syncs_legacy_form():
    _run_panel_runtime(
        """
const requests = [];
global.fetch = async (url, options={}) => {
  requests.push({url, body:options.body || null});
  return {ok:true, json:async()=>({ok:true, kind:"case_matrix_ready", request_id:"request_server", request_version:4, matrix_summary:{row_count:2, column_count:5}, read_only:true, state_changed:false})};
};
orchestratorPanelState.requestId = "request_server";
orchestratorPanelState.requestVersion = 4;
orchestratorPanelState.latestApprovedState = {metadata:{request_no:"SERVER"}};
orchestratorPanelState.caseMatrixSyncedRequestId = "request_server";
orchestratorPanelState.caseMatrixSyncedRequestVersion = 4;
const first = runOrchestratorCaseMatrixAction();
const second = runOrchestratorCaseMatrixAction();
await first; await second;
if (JSON.stringify(requests) !== JSON.stringify([{url:"/api/orchestrator/case-matrix/action", body:'{"request_id":"request_server"}'}])) throw new Error("action was not request-id-only or double-click safe");
if (editorSyncs || derivedRenders || elements.chatLog.children.length || elements.chatInput.value !== "legacy" || elements.formView.value !== "unchanged") throw new Error("action changed legacy UI");
"""
    )


def test_panel_case_matrix_action_requires_successful_h5_020_latest_get_and_invalidates_on_get_failure():
    _run_panel_runtime(
        """
const requests = [];
global.fetch = async (url, options={}) => {
  requests.push({url, body:options.body || null});
  return {ok:false, json:async()=>({error:"request_read_failed"})};
};
orchestratorPanelState.requestId = "request_server";
await runOrchestratorCaseMatrixAction();
if (requests.length) throw new Error("unsynced Request entered Case Matrix action");
await refreshApprovedOrchestratorRequest("proposal_server").catch(() => {});
if (hasSyncedCaseMatrixRequest()) throw new Error("failed latest GET left Case Matrix eligibility");
await runOrchestratorCaseMatrixAction();
if (requests.length !== 1 || requests[0].url !== "/api/request/versioned/request_server") throw new Error("failed GET allowed Case Matrix action");
if (editorSyncs || derivedRenders || elements.chatLog.children.length || elements.chatInput.value !== "legacy" || elements.formView.value !== "unchanged") throw new Error("unsynced action changed legacy UI");
"""
    )
