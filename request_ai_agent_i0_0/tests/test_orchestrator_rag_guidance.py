from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.rag_guidance_action import RagGuidanceActionService
from request_ai_agent_i0_0.request_state_store import RequestStateStore
from request_ai_agent_i0_0.state import create_initial_state, sanitize_state

from test_orchestrator_chat_panel import UI_PATH, _panel_source, _run_panel_runtime


def _qa(*, sources=None, question_type="general", ok=True):
    return {"ok": ok, "question": "document question", "question_type": question_type,
            "sources": [] if sources is None else sources, "hit_count": len(sources or []),
            "confidence": "low", "limitations": ["existing limitation"], "answer_text": "existing RAG answer",
            "read_only": True, "state_changed": False}


def test_rag_guidance_calls_existing_runner_without_request_snapshot_or_client_authority():
    requests = RequestStateStore(sanitize_state)
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)
    seen = []

    def runner(question, *, state):
        seen.append((question, state))
        return _qa(sources=[{"source_name": "existing", "score": 0.8}])

    result = RagGuidanceActionService(requests, rag_runner=runner).run(created.request_id, "document question")
    assert result.code == "rag_guidance_ready"
    assert result.qa["sources"][0]["score"] == 0.8
    assert seen == [("document question", None)]
    assert requests.read(created.request_id) == before


def test_rag_guidance_stable_no_result_disabled_error_malformed_unknown_race_and_replay(monkeypatch):
    requests = RequestStateStore(sanitize_state)
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)
    service = RagGuidanceActionService(requests, rag_runner=lambda *_args, **_kwargs: _qa())
    assert service.run(created.request_id, "document question").code == "rag_guidance_no_result"
    assert service.run(created.request_id, "document question").code == "rag_guidance_no_result"
    service._rag_runner = lambda *_args, **_kwargs: _qa(question_type="rag_disabled")
    assert service.run(created.request_id, "document question").code == "rag_guidance_disabled"
    service._rag_runner = lambda *_args, **_kwargs: _qa(question_type="rag_error", ok=False)
    assert service.run(created.request_id, "document question").code == "rag_guidance_error"
    service._rag_runner = lambda *_args, **_kwargs: {"not": "existing qa"}
    assert service.run(created.request_id, "document question").code == "rag_guidance_malformed"
    assert service.run("missing", "document question").code == "request_not_found"
    assert service.run(created.request_id, "").code == "invalid_rag_guidance_question"
    assert service.run(created.request_id, "current input").code == "rag_guidance_requires_document_question"
    original_read = requests.read
    def stale_read(request_id):
        snapshot = original_read(request_id)
        requests.replace(request_id, snapshot.version, snapshot.state)
        return snapshot
    monkeypatch.setattr(requests, "read", stale_read)
    assert service.run(created.request_id, "document question").code == "request_version_conflict"
    assert before.version == 0


def test_rag_guidance_http_accepts_only_id_and_question_and_preserves_request_and_ledger():
    app = create_app()
    client = app.test_client()
    requests = app.extensions["request_state_store"]
    proposals = app.extensions["proposal_service"]
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)
    app.extensions["rag_guidance_action_service"]._rag_runner = lambda *_args, **_kwargs: _qa()
    invalid = client.post("/api/orchestrator/rag-guidance/action", json={"request_id": created.request_id, "question": "q", "state": {}})
    no_result = client.post("/api/orchestrator/rag-guidance/action", json={"request_id": created.request_id, "question": "q"})
    replay = client.post("/api/orchestrator/rag-guidance/action", json={"request_id": created.request_id, "question": "q"})
    assert invalid.status_code == 400
    assert no_result.status_code == replay.status_code == 200
    assert no_result.get_json()["kind"] == replay.get_json()["kind"] == "rag_guidance_no_result"
    assert no_result.get_json()["qa"]["answer_text"] == "existing RAG answer"
    assert requests.read(created.request_id) == before
    assert proposals.proposal_count() == 0


def test_panel_rag_action_is_id_and_question_only_and_isolates_legacy_state():
    source = _panel_source()
    action_source = source[source.index("async function runOrchestratorRagGuidanceAction"):source.index("async function createOrchestratorConversation")]
    assert 'id="orchestratorRagGuidanceAction"' not in UI_PATH.read_text(encoding="utf-8")
    assert 'fetch("/api/orchestrator/rag-guidance/action"' in action_source
    assert "JSON.stringify({request_id:orchestratorPanelState.requestId, question})" in action_source
    assert 'const question = $("chatInput").value.trim()' in action_source
    for forbidden in ("requestState =", "syncEditorFromState()", "renderDerivedPanels()", "renderDocumentPreviewPanel", "exportWordFromPreview", "JSON.stringify({sources:"):
        assert forbidden not in action_source
    _run_panel_runtime("""
const requests = [];
global.fetch = async (url, options={}) => {
  requests.push({url, body:options.body || null});
  return {ok:true, json:async()=>({ok:true, kind:"rag_guidance_no_result", request_id:"request_server", qa:{answer_text:"existing answer", sources:[], confidence:"low", limitations:["existing"], hit_count:0, source_types_searched:[]}, read_only:true, state_changed:false})};
};
orchestratorPanelState.requestId = "request_server";
$("orchestratorInput").value = "document question";
await runOrchestratorRagGuidanceAction();
if (requests.length !== 1 || requests[0].url !== "/api/orchestrator/rag-guidance/action") throw new Error("wrong action request");
const body = JSON.parse(requests[0].body);
if (Object.keys(body).sort().join(",") !== "question,request_id" || body.request_id !== "request_server") throw new Error("authority leak");
if (editorSyncs !== 0 || derivedRenders !== 0 || orchestratorPanelState.requestVersion !== null) throw new Error("legacy state changed");
""")
