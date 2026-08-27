from copy import deepcopy

from request_ai_agent_i0_0.app import _derive_state, _stamp_proposal, create_app
from request_ai_agent_i0_0.state import create_initial_state
from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def test_direct_form_endpoints_keep_state_without_chat_notifications():
    app = create_app()
    app.config.update(TESTING=True)
    client = app.test_client()
    state = create_initial_state()
    state["analysis_overview"]["project_name"] = "TASK6"

    saved = client.post("/api/input/save", json={"state": state})
    refreshed = client.post("/api/preview", json={"state": state})

    assert saved.status_code == refreshed.status_code == 200
    assert saved.get_json()["state"]["analysis_overview"]["project_name"]["value"] == "TASK6"
    assert refreshed.get_json()["state"]["analysis_overview"]["project_name"]["value"] == "TASK6"
    assert "chat_notifications" not in saved.get_json()
    assert "chat_notifications" not in refreshed.get_json()


def test_form_save_does_not_add_a_recent_turn():
    app = create_app()
    app.config.update(TESTING=True)
    client = app.test_client()
    conversations = app.extensions["conversation_store"]
    created = client.post("/api/request/versioned", json={"state": create_initial_state()}).get_json()
    conversation = client.post("/api/conversations", json={"request_id": created["request_id"]}).get_json()
    before = deepcopy(conversations.read(conversation["conversation_id"]).recent_turns)

    state = deepcopy(created["state"])
    state["analysis_overview"]["project_name"] = "DIRECT-FORM"
    saved = client.put(
        f"/api/request/versioned/{created['request_id']}",
        json={"expected_version": created["request_version"], "state": state},
    )

    assert saved.status_code == 200
    assert saved.get_json()["state"]["analysis_overview"]["project_name"]["value"] == "DIRECT-FORM"
    assert conversations.read(conversation["conversation_id"]).recent_turns == before


def test_legacy_proposal_status_response_has_no_duplicate_success_message():
    app = create_app()
    app.config.update(TESTING=True)
    client = app.test_client()
    state = _derive_state(create_initial_state())
    proposal = {
        "proposal_id": "task6-proposal",
        "status": "pending",
        "operations": [
            {
                "op": "set",
                "path": "analysis_overview.project_name",
                "value": "TASK6",
            }
        ],
    }

    proposal = _stamp_proposal(proposal, state)
    applied = client.post("/api/chat/apply", json={"state": state, "proposal": proposal})
    rejected = client.post("/api/chat/reject", json={"proposal": proposal})

    assert applied.status_code == rejected.status_code == 200
    assert applied.get_json()["proposal"]["status"] == "applied"
    assert rejected.get_json()["proposal"]["status"] == "rejected"
    assert "assistant" not in applied.get_json()
    assert "assistant" not in rejected.get_json()
    assert "chat_notifications" not in applied.get_json()


def test_ui_keeps_next_questions_and_errors_but_drops_system_success_appends():
    source = HTML_TEMPLATE

    assert 'let displayedMessage = String(nextQuestion.message || "");' in source
    assert 'if (nextQuestion.message) pushMessage("assistant", displayedMessage);' in source
    assert 'statusNode.textContent = "상태: 승인됨 · 최신 의뢰서 동기화 오류";' in source
    assert 'pushMessage("assistant", errorMessage === "LLM이 정상 작동하지 않습니다."' in source
    assert "handleChatNotifications" not in source
    for message in (
        "선택한 조합 기준으로 입력항목이 준비됐습니다.",
        "운전 구분 기준으로 해석조건 입력항목을 갱신했습니다.",
        "Case Matrix 확인 완료",
        "Preview 확인 완료",
        "Word 출력 완료",
        "변경 내용을 의뢰서에 반영했습니다.",
        "변경 내용을 반영하지 않았습니다.",
    ):
        assert message not in source
