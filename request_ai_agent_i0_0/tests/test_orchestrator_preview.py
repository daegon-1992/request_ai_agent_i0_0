from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.preview_action import PreviewActionService
from request_ai_agent_i0_0.request_state_store import RequestStateStore
from request_ai_agent_i0_0.state import create_initial_state, sanitize_state

from test_orchestrator_chat_panel import _run_panel_runtime


def _service():
    requests = RequestStateStore(sanitize_state)
    return requests, PreviewActionService(requests)


def test_explicit_preview_reads_only_the_fenced_server_latest_snapshot_without_rendering_or_write(monkeypatch):
    requests, service = _service()
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)

    result = service.run(created.request_id)

    assert result.code == "preview_ready"
    assert result.request_id == created.request_id
    assert result.request_version == created.version
    assert result.state == before.state
    assert result.state is not before.state
    assert requests.read(created.request_id) == before

    def unexpected_renderer(_state):
        raise AssertionError("server Preview action must not select a renderer")

    monkeypatch.setattr("request_ai_agent_i0_0.preview_document.build_request_preview", unexpected_renderer)
    assert service.run(created.request_id).code == "preview_ready"


def test_preview_unknown_stale_duplicate_and_read_failure_are_stable_read_only(monkeypatch):
    requests, service = _service()
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)

    assert service.run(created.request_id).code == "preview_ready"
    assert service.run(created.request_id).code == "preview_ready"
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
    monkeypatch.setattr(requests, "at_version", lambda *_args: (_ for _ in ()).throw(ValueError("read failed")))
    assert service.run(created.request_id).code == "preview_read_failed"
    assert requests.read(created.request_id) == current
    assert before.version == 0


def test_preview_http_accepts_only_request_id_and_never_changes_request_or_ledger():
    app = create_app()
    client = app.test_client()
    requests = app.extensions["request_state_store"]
    proposals = app.extensions["proposal_service"]
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)

    invalid = client.post("/api/orchestrator/preview/action", json={"request_id": created.request_id, "state": {}})
    latest = client.get(f"/api/request/versioned/{created.request_id}")
    ready = client.post("/api/orchestrator/preview/action", json={"request_id": created.request_id})
    replay = client.post("/api/orchestrator/preview/action", json={"request_id": created.request_id})

    assert invalid.status_code == 400
    assert ready.status_code == replay.status_code == 200
    assert ready.get_json()["kind"] == replay.get_json()["kind"] == "preview_ready"
    assert ready.get_json()["state"] == latest.get_json()["state"]
    assert ready.get_json()["state_changed"] is False
    assert requests.read(created.request_id) == before
    assert proposals.proposal_count() == 0


def test_panel_preview_is_receipt_gated_request_id_only_and_uses_only_server_response():
    _run_panel_runtime(
        """
const requests = [];
let previews = [];
renderDocumentPreviewPanel = state => { previews.push(state); };
global.fetch = async (url, options={}) => {
  requests.push({url, body:options.body || null});
  return {ok:true, json:async()=>({ok:true, kind:"preview_ready", request_id:"request_server", request_version:4, state:{metadata:{request_no:"SERVER"}, request_context:{}, basic_info:{}, analysis_overview:{}, geometry:{}, conditions:{}, case_matrix:{}, review:{validator:{blocking:[{code:"existing.blocking"}]}}, legacy_internal:{}}, read_only:true, state_changed:false})};
};
orchestratorPanelState.requestId = "request_server";
orchestratorPanelState.requestVersion = 4;
orchestratorPanelState.latestApprovedState = {metadata:{request_no:"RECEIPT"}};
orchestratorPanelState.caseMatrixSyncedRequestId = "request_server";
orchestratorPanelState.caseMatrixSyncedRequestVersion = 4;
const first = runOrchestratorPreviewAction();
const second = runOrchestratorPreviewAction();
await first; await second;
if (JSON.stringify(requests) !== JSON.stringify([{url:"/api/orchestrator/preview/action", body:'{"request_id":"request_server"}'}])) throw new Error("action was not request-id-only or double-click safe");
if (previews.length !== 1 || previews[0].metadata.request_no !== "SERVER") throw new Error("Preview used client state instead of server response");
if (editorSyncs || derivedRenders || elements.chatLog.children.length || elements.chatInput.value !== "legacy" || elements.formView.value !== "unchanged") throw new Error("action changed legacy UI");
"""
    )


def test_panel_preview_rejects_unsynced_stale_malformed_and_network_results_without_legacy_changes():
    _run_panel_runtime(
        """
const requests = [];
let previews = 0;
renderDocumentPreviewPanel = () => { previews += 1; };
const outcomes = [
  {ok:true, json:async()=>({ok:true, kind:"preview_ready", request_id:"request_server", request_version:3, state:{}})},
  {ok:false, json:async()=>{throw new Error("malformed");}},
];
global.fetch = async (url, options={}) => { requests.push({url, body:options.body || null}); return outcomes.shift(); };
orchestratorPanelState.requestId = "request_server";
await runOrchestratorPreviewAction();
if (requests.length || previews) throw new Error("unsynced Request entered Preview action");
orchestratorPanelState.requestVersion = 4;
orchestratorPanelState.latestApprovedState = {metadata:{request_no:"RECEIPT"}};
orchestratorPanelState.caseMatrixSyncedRequestId = "request_server";
orchestratorPanelState.caseMatrixSyncedRequestVersion = 4;
await runOrchestratorPreviewAction();
await runOrchestratorPreviewAction();
if (previews || requests.length !== 2) throw new Error("stale or malformed Preview changed renderer");
if (editorSyncs || derivedRenders || elements.chatLog.children.length || elements.chatInput.value !== "legacy" || elements.formView.value !== "unchanged") throw new Error("failed Preview changed legacy UI");
"""
    )
