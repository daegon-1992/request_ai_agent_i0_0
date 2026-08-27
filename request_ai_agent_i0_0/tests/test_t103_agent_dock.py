from __future__ import annotations

import re

from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def test_agent_dock_has_explicit_open_hide_controls_and_preserved_chat_anchors():
    assert 'id="agentDock"' in HTML_TEMPLATE
    assert 'id="agentClearBtn"' in HTML_TEMPLATE
    assert 'id="agentHideBtn"' in HTML_TEMPLATE
    assert 'id="agentOpenBtn"' in HTML_TEMPLATE
    assert 'id="chatLog"' in HTML_TEMPLATE
    assert 'id="chatInput"' in HTML_TEMPLATE
    assert 'let chatHistory = []' in HTML_TEMPLATE
    assert 'const pendingChatProposals = new Map()' not in HTML_TEMPLATE
    assert 'body:JSON.stringify({proposal_id:proposalId, decision})' in HTML_TEMPLATE
    assert 'function restoreChatHistoryFromState()' in HTML_TEMPLATE
    assert 'function syncChatMetadata()' in HTML_TEMPLATE


def test_agent_first_entry_guidance_prioritizes_product_selection_and_start_action():
    guidance = (
        "먼저 해석 대상 제품을 정해 주세요. 이 의뢰 대상·시작에서 사업부 → 제품 분류 → "
        "해석유형을 선택한 다음, 의뢰서 작성 시작 버튼을 누르면 작성을 시작할 수 있습니다. "
        "해석유형을 모르겠다면 해석유형 선택 가이드를 확인하고 Agent에게 물어봐 주세요."
    )
    placeholder = re.search(r'<textarea id="chatInput" placeholder="([^"]+)">', HTML_TEMPLATE)

    assert HTML_TEMPLATE.count(guidance) == 2
    assert placeholder is not None
    assert placeholder.group(1) == "예: 에어컨에서 소음이 발생하는 원인을 확인하고 싶어요."
    assert "Fan RPM" not in placeholder.group(1)


def test_agent_clear_control_precedes_hide_and_resets_chat_and_conversation():
    assert HTML_TEMPLATE.index('id="agentClearBtn"') < HTML_TEMPLATE.index('id="agentHideBtn"')
    assert 'async function clearAgentConversation()' in HTML_TEMPLATE
    assert 'orchestratorPanelState.conversationId = ""' in HTML_TEMPLATE
    assert 'chatHistory = []' in HTML_TEMPLATE
    assert '$("chatLog").replaceChildren()' in HTML_TEMPLATE
    assert '/close`' in HTML_TEMPLATE
    assert '$("agentClearBtn").addEventListener("click", clearAgentConversation)' in HTML_TEMPLATE
    assert '$("agentClearBtn").disabled = loading' in HTML_TEMPLATE


def test_agent_open_hide_restores_agent_focus_without_touching_orchestrator_state():
    assert 'let agentOpen = true' in HTML_TEMPLATE
    assert 'function renderAgentDock()' in HTML_TEMPLATE
    assert 'function setAgentOpen(open, options={})' in HTML_TEMPLATE
    assert 'function agentRestoreFocusTarget()' in HTML_TEMPLATE
    assert 'lastAgentFocus' in HTML_TEMPLATE
    assert '$("agentOpenBtn")?.focus()' in HTML_TEMPLATE
    assert 'window.requestAnimationFrame(() => agentRestoreFocusTarget()?.focus())' in HTML_TEMPLATE
    assert 'orchestratorPanelState' in HTML_TEMPLATE


def test_agent_dock_switches_between_340_320_dock_and_sub_1040_overlay_with_escape():
    assert 'grid-template-columns:minmax(0,1fr) 340px' in HTML_TEMPLATE
    assert '@media (max-width:1280px) and (min-width:1040px)' in HTML_TEMPLATE
    assert 'grid-template-columns:minmax(0,1fr) 320px' in HTML_TEMPLATE
    assert '@media (max-width:1039px)' in HTML_TEMPLATE
    assert 'position:fixed' in HTML_TEMPLATE
    assert 'function isAgentOverlay()' in HTML_TEMPLATE
    assert 'event.key === "Escape" && agentOpen && isAgentOverlay()' in HTML_TEMPLATE
