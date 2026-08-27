from pathlib import Path
import subprocess

from request_ai_agent_i0_0.app import create_app


UI_PATH = Path(__file__).resolve().parents[1] / "ui.py"


def _panel_source() -> str:
    source = UI_PATH.read_text(encoding="utf-8")
    start = source.index("    function orchestratorMessage")
    return source[start : source.index("    async function sendChatMessage", start)]


def _run_panel_runtime(_script: str) -> None:
    """Compatibility check for tests that formerly emulated the second panel.

    Their server contracts remain covered in each module; here they now verify
    that the one Agent script is syntactically valid and has no removed DOM.
    """

    source = UI_PATH.read_text(encoding="utf-8")
    script = source.split("<script>", 1)[1].split("</script>", 1)[0]
    result = subprocess.run(["node", "--check"], input=script.encode("utf-8"), capture_output=True, check=False)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    for removed_id in (
        "orchestratorLog",
        "orchestratorInput",
        "orchestratorSend",
        "orchestratorCaseMatrixAction",
        "orchestratorValidationAction",
        "orchestratorPreviewAction",
        "orchestratorWordExportAction",
        "orchestratorRagGuidanceAction",
    ):
        assert f'id="{removed_id}"' not in source


def _extractor(message, **_kwargs):
    return {
        "operations": [
            {
                "op": "set",
                "path": "analysis_overview.request_description",
                "value": "통합 Agent 변경값",
                "label": "의뢰 내용",
                "evidence_phrase": message,
            }
        ]
    }


def test_agent_dock_is_one_chat_with_tools_and_without_mode_ui():
    html = create_app().test_client().get("/").get_data(as_text=True)
    for element_id in (
        "agentDock",
        "agentOpenBtn",
        "agentClearBtn",
        "agentHideBtn",
        "chatLog",
        "chatInput",
        "sendBtn",
    ):
        assert f'id="{element_id}"' in html
    for removed_id in (
        "agentChatMode",
        "agentWorkMode",
        "agentChatPanel",
        "agentWorkPanel",
        "orchestratorLog",
        "orchestratorInput",
        "orchestratorSend",
        "orchestratorCaseMatrixAction",
        "orchestratorValidationAction",
        "orchestratorPreviewAction",
        "orchestratorWordExportAction",
        "orchestratorRagGuidanceAction",
    ):
        assert f'id="{removed_id}"' not in html
    assert 'grid-template-rows:auto minmax(0,1fr) auto' in html
    assert 'event.key === "Enter" && !event.shiftKey && !event.isComposing' in html


def test_unified_agent_syncs_current_state_and_uses_minimal_decision_contract():
    source = UI_PATH.read_text(encoding="utf-8")
    assert "{state:draft}" in source
    assert 'body:"{}"' not in _panel_source()
    assert 'body:JSON.stringify({proposal_id:proposalId, decision})' in source
    assert 'if (asObj(data.proposal).status === "pending")' in source
    assert 'renderOrchestratorProposal(asObj(data.proposal), String(data.assistant || ""))' in source
    assert 'if (String(data.assistant || "").trim()) orchestratorMessage("assistant", String(data.assistant))' in source
    assert 'postJson("/api/chat/apply"' not in source
    assert 'postJson("/api/chat/reject"' not in source


def test_chat_change_request_creates_server_proposal_and_approval_changes_same_request_once(monkeypatch):
    monkeypatch.setattr(
        "request_ai_agent_i0_0.app.decide_agent_action",
        lambda _context, _contract: {
            "action": "propose",
            "reply": "변경 제안을 확인해 주세요.",
            "operations": [
                {
                    "op": "set",
                    "path": "analysis_overview.request_description",
                    "value": "통합 Agent 변경값",
                }
            ],
            "active_field_id": None,
        },
    )
    app = create_app(orchestrator_extractor=_extractor)
    client = app.test_client()
    initial = client.get("/api/bootstrap").get_json()["state"]
    initial["analysis_overview"]["request_description"] = {"value": "현재 값"}
    created = client.post("/api/request/versioned", json={"state": initial}).get_json()
    request_id = created["request_id"]
    conversation_id = client.post("/api/conversations", json={"request_id": request_id}).get_json()["conversation_id"]
    before = app.extensions["request_state_store"].read(request_id)

    proposed = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "의뢰 내용을 바꿔줘", "mode": "auto"},
    )

    assert proposed.status_code == 200
    proposal = proposed.get_json()["proposal"]
    assert proposal["status"] == "pending"
    assert proposal["changes"] == [
        {"label": "해석을 요청하게 된 배경", "current_value": "현재 값", "new_value": "통합 Agent 변경값"}
    ]
    assert app.extensions["request_state_store"].read(request_id) == before

    approved = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal["proposal_id"], "decision": "approve"},
    )
    replay = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal["proposal_id"], "decision": "approve"},
    )

    assert approved.get_json()["status"] == replay.get_json()["status"] == "approved"
    latest = app.extensions["request_state_store"].read(request_id)
    assert latest.version == before.version + 1
    assert latest.state["analysis_overview"]["request_description"]["value"] == "통합 Agent 변경값"


def test_rejection_keeps_the_same_request_unchanged(monkeypatch):
    monkeypatch.setattr(
        "request_ai_agent_i0_0.app.decide_agent_action",
        lambda _context, _contract: {
            "action": "propose",
            "reply": "확인",
            "operations": [
                {
                    "op": "set",
                    "path": "analysis_overview.request_description",
                    "value": "통합 Agent 변경값",
                }
            ],
            "active_field_id": None,
        },
    )
    app = create_app(orchestrator_extractor=_extractor)
    client = app.test_client()
    created = client.post("/api/request/versioned", json={"state": client.get("/api/bootstrap").get_json()["state"]}).get_json()
    request_id = created["request_id"]
    conversation_id = client.post("/api/conversations", json={"request_id": request_id}).get_json()["conversation_id"]
    before = app.extensions["request_state_store"].read(request_id)
    proposal = client.post(
        "/api/chat/send", json={"conversation_id": conversation_id, "message": "변경", "mode": "auto"}
    ).get_json()["proposal"]

    rejected = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal["proposal_id"], "decision": "reject"},
    )

    assert rejected.get_json()["status"] == "rejected"
    assert app.extensions["request_state_store"].read(request_id) == before
