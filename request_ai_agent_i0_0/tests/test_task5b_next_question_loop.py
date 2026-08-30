from copy import deepcopy
import subprocess

import pytest

import request_ai_agent_i0_0.app as app_module
from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.condition_fieldsets import default_condition_sets
from request_ai_agent_i0_0.state import create_initial_state, field_value, infer_field_status, make_field, sanitize_state
from request_ai_agent_i0_0.ui import HTML_TEMPLATE
from request_ai_agent_i0_0.validator import validate_state


def _decision(
    action,
    reply,
    operations=None,
    active_field_id=None,
    *,
    resume_workflow=None,
    product_hierarchy_query=None,
):
    decision = {
        "action": action,
        "reply": reply,
        "operations": operations or [],
        "active_field_id": active_field_id,
    }
    if resume_workflow is not None or product_hierarchy_query is not None:
        decision["resume_workflow"] = bool(resume_workflow)
        decision["product_hierarchy_query"] = product_hierarchy_query
    return decision


def _complete_state():
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
    for key, value in {
        "project_name": "PROJECT",
        "development_grade": "A",
        "npi_stage": "DV",
        "model_suffix": "MODEL-A",
        "desired_completion_date": "2026-08-25",
        "request_description": "설계 변경 검토",
        "additional_result_request": "기존안과 변경안 비교",
    }.items():
        state["analysis_overview"][key] = value
    state["geometry"]["base_product"]["drawing_no"] = "DRAW-A"
    cards = default_condition_sets(state["request_context"])
    for card in cards:
        if card["type"] == "operating":
            card["fans"][0]["values"]["fan_rpm"] = "700"
        else:
            for key, field in card["fields"].items():
                if key != "name":
                    field["value"] = "1"
    state["conditions"]["condition_sets"] = cards
    state = sanitize_state(state)
    assert validate_state(state)["summary"]["can_submit"] is True
    return state


def _runtime(monkeypatch, state, decider):
    monkeypatch.setattr(app_module, "decide_agent_action", decider)
    app = create_app()
    client = app.test_client()
    created = client.post("/api/request/versioned", json={"state": state}).get_json()
    conversation = client.post("/api/conversations", json={"request_id": created["request_id"]}).get_json()
    return app, client, created["request_id"], conversation["conversation_id"]


def _missing_overview(*keys):
    state = _complete_state()
    for key in keys:
        state["analysis_overview"][key] = make_field("")
    return state


def _start_question(client, conversation_id):
    return client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "현재 입력 상태를 알려줘."},
    ).get_json()


def test_approve_applies_latest_state_then_records_exactly_one_next_question(monkeypatch):
    def decider(context, _contract):
        if context["current_message"] == "PROJECT-A":
            return _decision(
                "propose",
                "프로젝트명 변경을 제안합니다.",
                [{"op": "set", "path": "analysis_overview.project_name", "value": "PROJECT-A"}],
            )
        return _decision("answer", "현재 입력 상태를 확인했습니다.")

    app, client, request_id, conversation_id = _runtime(
        monkeypatch,
        _missing_overview("project_name", "development_grade"),
        decider,
    )
    first = _start_question(client, conversation_id)
    assert first["next_question"]["active_field_id"] == "analysis_overview.project_name"

    proposed = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "PROJECT-A"},
    ).get_json()
    proposal_id = proposed["proposal"]["proposal_id"]
    assert "next_question" not in proposed

    approved = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal_id, "decision": "approve"},
    ).get_json()
    conversation = app.extensions["conversation_store"].read(conversation_id)

    assert approved["status"] == "approved"
    assert field_value(app.extensions["request_state_store"].read(request_id).state["analysis_overview"]["project_name"]) == "PROJECT-A"
    assert approved["next_question"]["active_field_id"] == "analysis_overview.development_grade"
    assert conversation.active_field_id == "analysis_overview.development_grade"
    assert conversation.question_history == [first["next_question"]["message"], approved["next_question"]["message"]]
    assert conversation.recent_turns[-1] == {"role": "assistant", "content": approved["next_question"]["message"]}


def test_reject_keeps_state_and_reasks_the_same_blocking_field(monkeypatch):
    def decider(context, _contract):
        if context["current_message"] == "PROJECT-A":
            return _decision(
                "propose",
                "프로젝트명 변경을 제안합니다.",
                [{"op": "set", "path": "analysis_overview.project_name", "value": "PROJECT-A"}],
            )
        return _decision("answer", "현재 입력 상태를 확인했습니다.")

    app, client, request_id, conversation_id = _runtime(monkeypatch, _missing_overview("project_name"), decider)
    first = _start_question(client, conversation_id)
    before = app.extensions["request_state_store"].read(request_id)
    proposal_id = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "PROJECT-A"},
    ).get_json()["proposal"]["proposal_id"]

    rejected = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal_id, "decision": "reject"},
    ).get_json()

    assert rejected["status"] == "rejected"
    assert rejected["next_question"]["active_field_id"] == "analysis_overview.project_name"
    assert app.extensions["request_state_store"].read(request_id) == before
    conversation = app.extensions["conversation_store"].read(conversation_id)
    assert conversation.active_field_id == "analysis_overview.project_name"
    assert conversation.question_history == [first["next_question"]["message"], rejected["next_question"]["message"]]


def test_active_project_name_interprets_no_decided_value_as_undecided_proposal(monkeypatch):
    operation = {"op": "set", "path": "analysis_overview.project_name", "value": "미정"}

    def decider(context, _contract):
        if context["current_message"] == "없어.":
            field = next(
                row
                for row in context["form_context"]["fields"]
                if row["field_id"] == operation["path"]
            )
            assert context["conversation"]["active_field_id"] == operation["path"]
            assert field["allowed_values"] == ["미정"]
            return _decision("propose", "프로젝트명(PMS)은 '미정'으로 처리하겠습니다.", [operation])
        return _decision("answer", "현재 입력 상태를 확인했습니다.")

    app, client, request_id, conversation_id = _runtime(
        monkeypatch,
        _missing_overview("project_name", "development_grade"),
        decider,
    )
    first = _start_question(client, conversation_id)
    assert first["next_question"]["active_field_id"] == operation["path"]
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)

    proposed = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "없어."},
    ).get_json()

    assert proposed["action"] == "propose"
    assert proposed["assistant"] == "프로젝트명(PMS)은 '미정'으로 처리하겠습니다."
    assert proposed["proposal"]["status"] == "pending"
    assert requests.read(request_id) == before

    approved = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposed["proposal"]["proposal_id"], "decision": "approve"},
    ).get_json()

    assert field_value(requests.read(request_id).state["analysis_overview"]["project_name"]) == "미정"
    assert approved["next_question"]["active_field_id"] == "analysis_overview.development_grade"


def test_active_free_text_geometry_value_proposes_on_first_input_then_asks_next_field_once(monkeypatch):
    operation = {
        "op": "set_geometry_field",
        "geometry_id": "base_001",
        "field_key": "drawing_no",
        "value": "T-251186671",
    }

    def decider(context, _contract):
        if context["current_message"] == operation["value"]:
            assert context["conversation"]["active_field_id"] == "geometry.base_product.drawing_no"
            return _decision("propose", "형상 1의 도면번호 입력을 제안합니다.", [operation])
        return _decision("answer", "현재 입력 상태를 확인했습니다.")

    state = _complete_state()
    state["geometry"]["base_product"]["drawing_no"] = make_field("")
    operating = next(card for card in state["conditions"]["condition_sets"] if card["type"] == "operating")
    operating["fans"][0]["values"]["fan_rpm"] = ""
    app, client, request_id, conversation_id = _runtime(monkeypatch, state, decider)
    requests = app.extensions["request_state_store"]

    first = _start_question(client, conversation_id)
    before = requests.read(request_id)
    proposed = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": operation["value"]},
    ).get_json()

    assert first["next_question"]["active_field_id"] == "geometry.base_product.drawing_no"
    assert proposed["action"] == "propose"
    assert proposed["proposal"]["status"] == "pending"
    assert "next_question" not in proposed
    assert app.extensions["proposal_service"].proposal_count() == 1
    assert requests.read(request_id) == before

    approved = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposed["proposal"]["proposal_id"], "decision": "approve"},
    ).get_json()
    conversation = app.extensions["conversation_store"].read(conversation_id)
    next_question = approved["next_question"]

    assert approved["status"] == "approved"
    assert field_value(requests.read(request_id).state["geometry"]["base_product"]["drawing_no"]) == operation["value"]
    assert next_question["active_field_id"] == "conditions.operating_1.fan_rpm"
    assert conversation.question_history.count(next_question["message"]) == 1
    assert conversation.recent_turns.count({"role": "assistant", "content": next_question["message"]}) == 1


def test_side_question_returns_to_fpi_then_short_answer_still_proposes(monkeypatch):
    seen_active_fields = []

    def decider(context, _contract):
        seen_active_fields.append(context["conversation"]["active_field_id"])
        if context["current_message"] == "20":
            return _decision(
                "propose",
                "사양 1의 FPI 변경을 제안합니다.",
                [{"op": "set_condition_field", "card_id": "heat_exchanger_1", "field_key": "fpi", "value": "20"}],
            )
        if context["current_message"] == "현재 입력 상태를 알려줘.":
            return _decision("answer", "작성할 항목을 확인합니다.", resume_workflow=True)
        return _decision("answer", "FPI는 인치당 Fin 수입니다.", resume_workflow=False)

    state = _complete_state()
    heat_exchanger = next(card for card in state["conditions"]["condition_sets"] if card["id"] == "heat_exchanger_1")
    heat_exchanger["fields"]["tube_diameter"] = make_field("5")
    heat_exchanger["fields"]["fin_type"] = make_field("Slit(Half)")
    heat_exchanger["fields"]["row_count"] = make_field("2")
    heat_exchanger["fields"]["fpi"] = make_field("")
    app, client, _request_id, conversation_id = _runtime(monkeypatch, state, decider)

    first = _start_question(client, conversation_id)
    side = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "FPI가 뭔가요?"},
    ).get_json()
    conversation_after_side = app.extensions["conversation_store"].read(conversation_id)
    proposed = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "20"},
    ).get_json()

    assert first["next_question"]["active_field_id"] == "conditions.heat_exchanger_1.fpi"
    assert side["action"] == "answer"
    assert "next_question" not in side
    assert conversation_after_side.active_field_id == "conditions.heat_exchanger_1.fpi"
    assert conversation_after_side.workflow_status == "awaiting_answer"
    assert seen_active_fields[-2:] == ["conditions.heat_exchanger_1.fpi", "conditions.heat_exchanger_1.fpi"]
    assert proposed["proposal"]["status"] == "pending"
    assert "next_question" not in proposed
    assert app.extensions["proposal_service"].proposal_count() == 1


def test_clarify_and_pending_answer_do_not_add_planner_questions(monkeypatch):
    def decider(context, _contract):
        if context["current_message"] == "모호한 변경":
            return _decision("clarify", "변경할 값을 알려주세요.", active_field_id="analysis_overview.project_name")
        if context["current_message"] == "왜?":
            return _decision("answer", "요청한 변경을 반영하기 위한 제안입니다.")
        return _decision(
            "propose",
            "프로젝트명 변경을 제안합니다.",
            [{"op": "set", "path": "analysis_overview.project_name", "value": "PROJECT-A"}],
        )

    app, client, _request_id, conversation_id = _runtime(monkeypatch, _missing_overview("project_name"), decider)
    clarified = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "모호한 변경"},
    ).get_json()
    assert clarified["action"] == "clarify" and "next_question" not in clarified

    proposed = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "PROJECT-A"},
    ).get_json()
    pending_answer = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "왜?"},
    ).get_json()
    assert proposed["proposal"]["status"] == "pending"
    assert pending_answer["action"] == "answer" and "next_question" not in pending_answer
    assert app.extensions["proposal_service"].proposal_count() == 1


def test_server_form_save_resynchronizes_stale_active_field_on_next_chat_only(monkeypatch):
    seen_contexts = []

    def decider(context, _contract):
        seen_contexts.append(deepcopy(context))
        return _decision("answer", "최신 입력 상태를 확인했습니다.")

    state = _missing_overview("project_name", "development_grade", "npi_stage")
    app, client, request_id, conversation_id = _runtime(monkeypatch, state, decider)
    first = _start_question(client, conversation_id)
    conversations = app.extensions["conversation_store"]
    requests = app.extensions["request_state_store"]
    before_form_turns = deepcopy(conversations.read(conversation_id).recent_turns)

    current = requests.read(request_id)
    form_state = deepcopy(current.state)
    form_state["analysis_overview"]["project_name"] = make_field("PROJECT-A")
    form_state["analysis_overview"]["development_grade"] = make_field("A")
    requests.replace(request_id, current.version, form_state)

    assert conversations.read(conversation_id).recent_turns == before_form_turns
    next_chat = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "다음 입력은 뭐야?"},
    ).get_json()

    assert first["next_question"]["active_field_id"] == "analysis_overview.project_name"
    assert seen_contexts[-1]["conversation"]["active_field_id"] is None
    assert next_chat["next_question"]["active_field_id"] == "analysis_overview.npi_stage"
    assert conversations.read(conversation_id).active_field_id == "analysis_overview.npi_stage"
    assert not any(turn["content"] in {"PROJECT-A", "A"} for turn in conversations.read(conversation_id).recent_turns)


def test_stale_proposal_conflicts_after_server_form_save_without_next_question(monkeypatch):
    def decider(_context, _contract):
        return _decision(
            "propose",
            "프로젝트명 변경을 제안합니다.",
            [{"op": "set", "path": "analysis_overview.project_name", "value": "OLD-PROPOSAL"}],
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, _complete_state(), decider)
    proposal_id = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "프로젝트명을 바꿔줘."},
    ).get_json()["proposal"]["proposal_id"]
    conversations = app.extensions["conversation_store"]
    before_terminal_turns = deepcopy(conversations.read(conversation_id).recent_turns)
    requests = app.extensions["request_state_store"]
    current = requests.read(request_id)
    form_state = deepcopy(current.state)
    form_state["analysis_overview"]["development_grade"] = make_field("FORM-SAVED")
    saved = requests.replace(request_id, current.version, form_state)

    conflicted = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal_id, "decision": "approve"},
    ).get_json()
    latest = requests.read(request_id)

    assert conflicted["status"] == "conflicted" and "next_question" not in conflicted
    assert latest.version == saved.version
    assert field_value(latest.state["analysis_overview"]["project_name"]) == "PROJECT"
    assert field_value(latest.state["analysis_overview"]["development_grade"]) == "FORM-SAVED"
    assert conversations.read(conversation_id).recent_turns == before_terminal_turns
    assert conversations.read(conversation_id).workflow_status == "proposal_completed"


def test_complete_clears_focus_without_submit_close_or_terminal_workflow(monkeypatch):
    app, client, request_id, conversation_id = _runtime(
        monkeypatch,
        _complete_state(),
        lambda _context, _contract: _decision("answer", "현재 상태를 확인했습니다."),
    )
    conversations = app.extensions["conversation_store"]
    conversations.set_active_field(conversation_id, "analysis_overview.project_name")
    before = app.extensions["request_state_store"].read(request_id)

    response = _start_question(client, conversation_id)
    conversation = conversations.read(conversation_id)

    assert response["next_question"]["kind"] == "complete"
    assert conversation.active_field_id is None
    assert conversation.question_history == []
    assert conversation.recent_turns[-1]["content"] == response["next_question"]["message"]
    assert conversation.status == "active"
    assert conversation.workflow_status == "planning_next_question"
    assert app.extensions["request_state_store"].read(request_id) == before


def test_complete_request_exposes_canonical_next_steps_and_direct_submission_to_agent(monkeypatch):
    seen_processes = []

    def decider(context, _contract):
        process = deepcopy(context["submission_process"])
        seen_processes.append(process)
        if len(seen_processes) == 1:
            return _decision(
                "answer",
                "필수 입력 다음에는 Case Matrix를 확인하고, 전체 확인 화면의 미리보기를 검토한 뒤 제출 동의해 주세요.",
                resume_workflow=False,
            )
        return _decision(
            "answer",
            "전체 확인 화면에서 동의한 뒤 최종 제출 버튼을 눌러 주세요.",
            resume_workflow=False,
        )

    app, client, _request_id, conversation_id = _runtime(
        monkeypatch,
        _complete_state(),
        decider,
    )

    next_step = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "그 다음 절차를 알려주세요."},
    ).get_json()
    submission = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "완성된 파일은 어디로 전달하나요?"},
    ).get_json()

    assert all(process["required_input_complete"] is True for process in seen_processes)
    assert all(process["next_action"]["key"] == "case_matrix_review" for process in seen_processes)
    assert all(process["submission"]["direct_screen_submission_available"] is True for process in seen_processes)
    assert "Case Matrix" in next_step["assistant"]
    assert "미리보기" in next_step["assistant"]
    assert "동의" in next_step["assistant"]
    assert "최종 제출" in submission["assistant"]
    assert "next_question" not in next_step and "next_question" not in submission


def test_existing_agent_ui_displays_separate_server_planner_messages():
    helper = HTML_TEMPLATE.split("function renderNextQuestion", 1)[1].split("function setOrchestratorLoading", 1)[0]
    decision = HTML_TEMPLATE.split("async function decideOrchestratorProposal", 1)[1].split("function renderOrchestratorProposal", 1)[0]
    chat = HTML_TEMPLATE.split("async function sendChatMessage", 1)[1].split("function triggerDownload", 1)[0]

    assert 'pushMessage("assistant", displayedMessage)' in helper
    assert helper.count('pushMessage("assistant"') == 1
    assert decision.count("renderNextQuestion(data);") == 2
    assert chat.count("renderNextQuestion(data);") == 1


def test_new_planner_field_uses_existing_navigation_once_per_changed_active_field():
    helper = "function renderNextQuestion" + HTML_TEMPLATE.split("function renderNextQuestion", 1)[1].split(
        "function setOrchestratorLoading", 1
    )[0]
    script = f"""
const events = [];
let activeScreen = "SCREEN-02";
let lastPlannerActiveFieldId = "";
function asObj(value) {{ return value && typeof value === "object" && !Array.isArray(value) ? value : {{}}; }}
function screenForSection(section) {{ return ({{analysis_overview:"SCREEN-02", geometry:"SCREEN-03", conditions:"SCREEN-04"}})[section] || "SCREEN-01"; }}
const screenNames = {{"SCREEN-02":"요청 내용", "SCREEN-03":"해석 제품", "SCREEN-04":"해석 조건"}};
const failedScreens = new Set();
const document = {{querySelector(selector) {{
  const screenId = Object.keys(screenNames).find(id => selector.includes(`data-screen="${{id}}"`));
  return screenId ? {{textContent:screenNames[screenId]}} : null;
}}}};
function navigateScreen(screenId, options={{}}) {{
  events.push(["navigate", screenId, options.focus]);
  if (failedScreens.has(screenId)) return false;
  activeScreen = screenId;
  return true;
}}
function pushMessage(_role, message) {{ events.push(["message", message]); }}
{helper}
renderNextQuestion({{next_question:{{kind:"field_question", active_field_id:"analysis_overview.project_name", message:"project"}}}});
renderNextQuestion({{next_question:{{kind:"field_question", active_field_id:"geometry.base_product.drawing_no", message:"geometry"}}}});
renderNextQuestion({{next_question:{{kind:"field_question", active_field_id:"conditions.operating_1.fan_rpm", message:"condition"}}}});
activeScreen = "SCREEN-02";
renderNextQuestion({{next_question:{{kind:"field_question", active_field_id:"conditions.operating_1.fan_rpm", message:"same condition"}}}});
renderNextQuestion({{action:"answer", next_question:{{kind:"field_question", active_field_id:"geometry.base_product.drawing_no", message:"answer"}}}});
renderNextQuestion({{action:"clarify", next_question:{{kind:"field_question", active_field_id:"analysis_overview.project_name", message:"clarify"}}}});
failedScreens.add("SCREEN-03");
renderNextQuestion({{next_question:{{kind:"field_question", active_field_id:"geometry.base_product.description", message:"failed geometry"}}}});
failedScreens.clear();
renderNextQuestion({{proposal:{{status:"pending"}}, next_question:{{kind:"field_question", active_field_id:"conditions.operating_2.fan_rpm", message:"pending condition"}}}});
renderNextQuestion({{next_question:{{kind:"ui_guidance", message:"ui guidance"}}}});
const navigations = events.filter(event => event[0] === "navigate");
if (JSON.stringify(navigations) !== JSON.stringify([
  ["navigate", "SCREEN-03", false],
  ["navigate", "SCREEN-04", false],
  ["navigate", "SCREEN-03", false],
  ["navigate", "SCREEN-04", false],
])) throw new Error(JSON.stringify(events));
const messages = events.filter(event => event[0] === "message").map(event => event[1]);
if (JSON.stringify(messages) !== JSON.stringify([
  "project",
  "다음은 해석 제품 정보입니다.\\ngeometry",
  "다음은 해석 조건입니다.\\ncondition",
  "same condition",
  "answer",
  "clarify",
  "failed geometry",
  "pending condition",
  "ui guidance",
])) throw new Error(JSON.stringify(events));
"""
    completed = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=False
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("user_message", ["미정", "미정이다.", "아직 미정이야.", "아직 안 정해졌어."])
def test_active_development_grade_accepts_natural_undecided_value_then_asks_next_field_once(
    monkeypatch,
    user_message,
):
    operation = {"op": "set", "path": "analysis_overview.development_grade", "value": "미정"}

    def decider(context, _contract):
        if context["current_message"] == user_message:
            field = next(
                row
                for row in context["form_context"]["fields"]
                if row["field_id"] == "analysis_overview.development_grade"
            )
            assert context["conversation"]["active_field_id"] == operation["path"]
            assert "미정" in field["allowed_values"]
            assert field["allow_custom_input"] is True
            return _decision("propose", "개발 등급을 미정으로 입력하는 내용을 제안합니다.", [operation])
        return _decision("answer", "현재 입력 상태를 확인했습니다.")

    app, client, request_id, conversation_id = _runtime(
        monkeypatch,
        _missing_overview("development_grade", "npi_stage"),
        decider,
    )
    first = _start_question(client, conversation_id)
    assert first["next_question"]["active_field_id"] == operation["path"]
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)

    proposed = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": user_message},
    ).get_json()

    assert proposed["action"] == "propose"
    assert proposed["proposal"]["status"] == "pending"
    assert "next_question" not in proposed
    proposal_id = proposed["proposal"]["proposal_id"]
    stored_operation = app.extensions["proposal_service"].read_proposal(proposal_id).operations[0]
    assert {key: stored_operation[key] for key in operation} == operation
    assert requests.read(request_id) == before

    approved = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal_id, "decision": "approve"},
    ).get_json()
    latest = requests.read(request_id)
    grade = latest.state["analysis_overview"]["development_grade"]
    blockers = validate_state(latest.state)["blocking"]

    assert approved["status"] == "approved"
    assert field_value(grade) == "미정"
    assert grade["status"] == "provided"
    assert not any(issue.get("path") == operation["path"] for issue in blockers)
    assert approved["next_question"]["active_field_id"] == "analysis_overview.npi_stage"
    next_message = approved["next_question"]["message"]
    conversation = app.extensions["conversation_store"].read(conversation_id)
    assert conversation.question_history.count(next_message) == 1
    assert conversation.recent_turns.count({"role": "assistant", "content": next_message}) == 1


def test_active_npi_stage_accepts_undecided_as_its_canonical_choice(monkeypatch):
    operation = {"op": "set", "path": "analysis_overview.npi_stage", "value": "미정"}

    def decider(context, _contract):
        if context["current_message"] == "미정":
            field = next(
                row
                for row in context["form_context"]["fields"]
                if row["field_id"] == operation["path"]
            )
            assert context["conversation"]["active_field_id"] == operation["path"]
            assert "미정" in field["allowed_values"]
            return _decision("propose", "NPI 단계를 미정으로 입력하는 내용을 제안합니다.", [operation])
        return _decision("answer", "현재 입력 상태를 확인했습니다.")

    app, client, request_id, conversation_id = _runtime(
        monkeypatch,
        _missing_overview("npi_stage", "model_suffix"),
        decider,
    )
    first = _start_question(client, conversation_id)
    assert first["next_question"]["active_field_id"] == operation["path"]
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)

    proposed = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "미정"},
    ).get_json()
    assert requests.read(request_id) == before
    proposal_id = proposed["proposal"]["proposal_id"]
    approved = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal_id, "decision": "approve"},
    ).get_json()
    latest = requests.read(request_id)

    assert proposed["action"] == "propose"
    assert field_value(latest.state["analysis_overview"]["npi_stage"]) == "미정"
    assert latest.state["analysis_overview"]["npi_stage"]["status"] == "provided"
    assert approved["next_question"]["active_field_id"] == "analysis_overview.model_suffix"


def test_explicit_current_value_question_keeps_answer_without_proposal(monkeypatch):
    def decider(context, _contract):
        assert context["conversation"]["active_field_id"] == "analysis_overview.development_grade"
        return _decision("answer", "현재 개발 등급 값은 입력되지 않았습니다.")

    app, client, _request_id, conversation_id = _runtime(
        monkeypatch,
        _missing_overview("development_grade"),
        decider,
    )
    app.extensions["conversation_store"].set_active_field(
        conversation_id,
        "analysis_overview.development_grade",
    )

    answered = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "현재 개발 등급 값이 뭐야?"},
    ).get_json()

    assert answered["action"] == "answer"
    assert "proposal" not in answered
    assert app.extensions["proposal_service"].proposal_count() == 0


def test_bare_undecided_without_active_field_does_not_guess_a_target(monkeypatch):
    def decider(context, _contract):
        assert context["conversation"]["active_field_id"] is None
        return _decision("answer", "어느 항목의 값인지 지정해 주세요.")

    app, client, request_id, conversation_id = _runtime(monkeypatch, _complete_state(), decider)
    before = app.extensions["request_state_store"].read(request_id)

    answered = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "미정"},
    ).get_json()

    assert answered["action"] == "answer"
    assert "proposal" not in answered
    assert app.extensions["proposal_service"].proposal_count() == 0
    assert app.extensions["request_state_store"].read(request_id) == before


def test_undecided_meaning_is_not_mapped_for_field_without_undecided_value(monkeypatch):
    path = "analysis_overview.request_description"

    def decider(context, _contract):
        if context["current_message"] == "아직 안 정해졌어.":
            field = next(
                row
                for row in context["form_context"]["fields"]
                if row["field_id"] == path
            )
            assert context["conversation"]["active_field_id"] == path
            assert "allowed_values" not in field
            return _decision("clarify", "해석 요청 배경은 입력이 필요합니다.", active_field_id=path)
        return _decision("answer", "현재 입력 상태를 확인했습니다.")

    app, client, request_id, conversation_id = _runtime(
        monkeypatch,
        _missing_overview("request_description"),
        decider,
    )
    first = _start_question(client, conversation_id)
    assert first["next_question"]["active_field_id"] == path
    before = app.extensions["request_state_store"].read(request_id)

    response = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "아직 안 정해졌어."},
    ).get_json()

    assert response["action"] == "clarify"
    assert "proposal" not in response
    assert app.extensions["proposal_service"].proposal_count() == 0
    assert app.extensions["request_state_store"].read(request_id) == before


def test_undecided_choice_does_not_change_generic_unknown_policy():
    assert infer_field_status("미정") == "provided"
    assert infer_field_status("모름") == "unknown"
    assert infer_field_status("알 수 없음") == "unknown"
    assert make_field("모름")["display_value"] == "모름"
    assert make_field("없음")["display_value"] == "없음"
    assert '{unknown:"모름", none:"없음", skipped:"skip"}' in HTML_TEMPLATE
