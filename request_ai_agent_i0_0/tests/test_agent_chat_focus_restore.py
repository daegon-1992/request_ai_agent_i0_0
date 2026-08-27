from __future__ import annotations

import subprocess

from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def _focus_helpers() -> str:
    start = HTML_TEMPLATE.index("    function beginChatFocusRestore()")
    end = HTML_TEMPLATE.index("    function agentRestoreFocusTarget()", start)
    return HTML_TEMPLATE[start:end]


def test_chat_focus_helpers_restore_only_while_chat_intent_is_pending():
    helpers = _focus_helpers()
    script = f"""
let chatFocusRestorePending = false;
let agentOpen = true;
const frames = [];
const input = {{
  value:"복구된 질문",
  disabled:false,
  focusCalls:[],
  selection:null,
  focus(options) {{ this.focusCalls.push(options); }},
  setSelectionRange(start, end) {{ this.selection = [start, end]; }},
}};
const otherControl = {{}};
const $ = id => id === "chatInput" ? input : null;
const document = {{hidden:false, contains:node => node === input}};
const window = {{requestAnimationFrame(callback) {{ frames.push(callback); }}}};
{helpers}

beginChatFocusRestore();
restoreChatInputFocusAfterReply();
if (frames.length !== 1) throw new Error("focus restoration was not scheduled");
frames.shift()();
if (input.focusCalls.length !== 1 || input.focusCalls[0].preventScroll !== true) throw new Error("input was not focused without scrolling");
if (JSON.stringify(input.selection) !== JSON.stringify([input.value.length, input.value.length])) throw new Error("caret was not moved to the restored text end");
if (chatFocusRestorePending) throw new Error("completed restoration remained pending");

beginChatFocusRestore();
handlePendingChatFocusPointerDown({{target:otherControl}});
restoreChatInputFocusAfterReply();
if (frames.length !== 0 || input.focusCalls.length !== 1) throw new Error("external pointer interaction did not cancel restoration");

beginChatFocusRestore();
handlePendingChatFocusPointerDown({{target:input}});
restoreChatInputFocusAfterReply();
if (frames.length !== 1) throw new Error("chat input interaction incorrectly cancelled restoration");
frames.shift()();
if (input.focusCalls.length !== 2) throw new Error("chat input restoration did not run");

beginChatFocusRestore();
handlePendingChatFocusKeyDown({{key:"Tab"}});
restoreChatInputFocusAfterReply();
if (frames.length !== 0 || input.focusCalls.length !== 2) throw new Error("Tab did not cancel restoration");

beginChatFocusRestore();
restoreChatInputFocusAfterReply();
document.hidden = true;
frames.shift()();
if (input.focusCalls.length !== 2) throw new Error("hidden page stole focus");
"""

    completed = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=False
    )

    assert completed.returncode == 0, completed.stderr


def test_chat_send_and_lifecycle_events_apply_the_conditional_focus_policy():
    send_start = HTML_TEMPLATE.index("    async function sendChatMessage()")
    send_end = HTML_TEMPLATE.index("    function triggerDownload", send_start)
    send_source = HTML_TEMPLATE[send_start:send_end]
    open_start = HTML_TEMPLATE.index("    function setAgentOpen(open, options={})")
    open_end = HTML_TEMPLATE.index("    function syncChatMetadata()", open_start)
    open_source = HTML_TEMPLATE[open_start:open_end]

    assert send_source.index("beginChatFocusRestore();") < send_source.index('$("chatInput").value = ""')
    assert send_source.index('$("chatInput").value = text;') < send_source.index("restoreChatInputFocusAfterReply();")
    assert send_source.index("setOrchestratorLoading(false);") < send_source.index("restoreChatInputFocusAfterReply();")
    assert 'renderOrchestratorProposal(data.proposal, String(data.assistant || ""));' in send_source
    assert '$("sendBtn").addEventListener("click", sendChatMessage);' in HTML_TEMPLATE
    assert 'event.key === "Enter" && !event.shiftKey && !event.isComposing' in HTML_TEMPLATE
    assert "sendChatMessage();" in HTML_TEMPLATE
    assert 'document.addEventListener("pointerdown", handlePendingChatFocusPointerDown, true);' in HTML_TEMPLATE
    assert 'document.addEventListener("keydown", handlePendingChatFocusKeyDown, true);' in HTML_TEMPLATE
    assert 'window.addEventListener("blur", cancelChatFocusRestore);' in HTML_TEMPLATE
    assert 'document.addEventListener("visibilitychange"' in HTML_TEMPLATE
    assert "if (!nextOpen) cancelChatFocusRestore();" in open_source
