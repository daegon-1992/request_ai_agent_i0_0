from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.state import create_initial_state, sanitize_state

from test_orchestrator_chat_panel import UI_PATH, _panel_source, _run_panel_runtime


def _coverage_complete_state():
    state = create_initial_state()
    state["request_context"].update(
        {
            "business_unit": "RAC",
            "product_group": "벽걸이",
            "platform": "SK",
            "analysis_type": "풍량",
            "context_locked": True,
        }
    )
    state["geometry"]["base_product"]["drawing_no"] = "DRAW-A"
    return sanitize_state(state)


def test_existing_word_endpoint_keeps_the_preview_dom_payload_and_docx_output():
    response = create_app().test_client().post(
        "/api/export/word",
        json={"state": _coverage_complete_state(), "sections": [{"title": "Preview", "blocks": [{"type": "field", "label": "PMS", "value": "SERVER"}]}]},
    )

    assert response.status_code == 200
    assert response.mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert response.data.startswith(b"PK")
    assert "analysis_request.docx" in response.headers["Content-Disposition"]


def test_word_panel_boundary_uses_only_the_existing_preview_serializer_and_endpoint():
    source = UI_PATH.read_text(encoding="utf-8")
    panel = _panel_source()
    action_start = panel.index("async function runOrchestratorWordExportAction")
    word_action = panel[action_start : panel.index("    async function runOrchestratorRagGuidanceAction", action_start)]

    assert 'id="orchestratorWordExportAction"' not in source
    assert "await exportWordFromPreview({useExistingPreviewDom:true})" in word_action
    assert "collectState()" not in word_action
    assert "renderDocumentPreviewPanel(" not in word_action
    assert "fetch('/api/export/word'" in source
    assert "if (!useExistingPreviewDom)" in source
    assert "previewDomForWord()" in source


def test_panel_word_export_requires_matching_fenced_preview_dom_and_is_double_click_safe():
    _run_panel_runtime(
        """
const calls = [];
const renderedDocument = {dataset:{orchestratorPreviewRequestId:"request_server", orchestratorPreviewRequestVersion:"4"}};
document.querySelector = () => renderedDocument;
exportWordFromPreview = async options => { calls.push(options); };
orchestratorPanelState.requestId = "request_server";
orchestratorPanelState.requestVersion = 4;
orchestratorPanelState.latestApprovedState = {metadata:{request_no:"RECEIPT"}};
orchestratorPanelState.caseMatrixSyncedRequestId = "request_server";
orchestratorPanelState.caseMatrixSyncedRequestVersion = 4;
await runOrchestratorWordExportAction();
if (calls.length || elements.orchestratorWordExportAction.disabled) throw new Error("Word action entered without Preview receipt");
orchestratorPanelState.previewRenderedRequestId = "request_server";
orchestratorPanelState.previewRenderedRequestVersion = 4;
const first = runOrchestratorWordExportAction();
const second = runOrchestratorWordExportAction();
await first; await second;
if (JSON.stringify(calls) !== JSON.stringify([{useExistingPreviewDom:true}])) throw new Error("Word action was not Preview-DOM-only or double-click safe");
if (editorSyncs || derivedRenders || elements.chatLog.children.length || elements.chatInput.value !== "legacy" || elements.formView.value !== "unchanged") throw new Error("Word action changed legacy UI");
"""
    )


def test_panel_word_export_rejects_stale_dom_and_export_failure_without_state_changes():
    _run_panel_runtime(
        """
const renderedDocument = {dataset:{orchestratorPreviewRequestId:"request_server", orchestratorPreviewRequestVersion:"3"}};
document.querySelector = () => renderedDocument;
let calls = 0;
exportWordFromPreview = async () => { calls += 1; throw new Error("network"); };
orchestratorPanelState.requestId = "request_server";
orchestratorPanelState.requestVersion = 4;
orchestratorPanelState.latestApprovedState = {metadata:{request_no:"RECEIPT"}};
orchestratorPanelState.caseMatrixSyncedRequestId = "request_server";
orchestratorPanelState.caseMatrixSyncedRequestVersion = 4;
orchestratorPanelState.previewRenderedRequestId = "request_server";
orchestratorPanelState.previewRenderedRequestVersion = 4;
await runOrchestratorWordExportAction();
if (calls) throw new Error("stale Preview DOM entered Word export");
renderedDocument.dataset.orchestratorPreviewRequestVersion = "4";
await runOrchestratorWordExportAction();
if (calls !== 1 || elements.orchestratorWordExportAction.disabled) throw new Error("export failure did not remain recoverable");
if (editorSyncs || derivedRenders || elements.chatLog.children.length || elements.chatInput.value !== "legacy" || elements.formView.value !== "unchanged") throw new Error("failed Word action changed legacy UI");
"""
    )
