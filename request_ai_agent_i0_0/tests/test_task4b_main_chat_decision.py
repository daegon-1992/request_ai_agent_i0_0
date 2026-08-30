from copy import deepcopy
import json

import request_ai_agent_i0_0.app as app_module
import request_ai_agent_i0_0.agent_decision as decision_module
from request_ai_agent_i0_0.agent_decision import decide_agent_action
from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.chat_patch import apply_patch_operations
from request_ai_agent_i0_0.condition_fieldsets import default_condition_sets
from request_ai_agent_i0_0.heat_exchanger_catalog import validate_heat_exchanger_proposal
from request_ai_agent_i0_0.product_hierarchy import find_product_hierarchy_matches, product_hierarchy_answer
from request_ai_agent_i0_0.state import field_value


def _runtime(monkeypatch, decider, analysis_type="열교환기 유속 프로파일"):
    monkeypatch.setattr(app_module, "decide_agent_action", decider)
    app = create_app()
    client = app.test_client()
    state = client.get("/api/bootstrap").get_json()["state"]
    state["request_context"].update(
        {
            "business_unit": "RAC",
            "product_group": "벽걸이",
            "platform": "SK",
            "analysis_type": analysis_type,
            "context_locked": True,
        }
    )
    state["analysis_overview"]["project_name"] = {"value": "ABC"}
    cards = default_condition_sets(state["request_context"])
    operating = next(card for card in cards if card["type"] == "operating")
    operating["fans"][0]["values"]["fan_rpm"] = "650"
    state["conditions"]["condition_sets"] = cards
    created = client.post("/api/request/versioned", json={"state": state}).get_json()
    conversation = client.post("/api/conversations", json={"request_id": created["request_id"]}).get_json()
    return app, client, created["request_id"], conversation["conversation_id"]


def _decision(
    action,
    reply,
    operations=None,
    active_field_id=None,
    *,
    resume_workflow=False,
    product_hierarchy_query=None,
    continues_pending_clarification=False,
    deferred_facts=None,
):
    return {
        "action": action,
        "reply": reply,
        "operations": operations or [],
        "active_field_id": active_field_id,
        "resume_workflow": resume_workflow,
        "product_hierarchy_query": product_hierarchy_query,
        "continues_pending_clarification": continues_pending_clarification,
        "deferred_facts": deferred_facts or [],
    }


def _fan_rpm(state):
    operating = next(card for card in state["conditions"]["condition_sets"] if card["id"] == "operating_1")
    return operating["fans"][0]["values"]["fan_rpm"]


def test_decision_callable_makes_one_llm_call_without_duplicating_current_message(monkeypatch):
    calls = []

    def completion(messages, **kwargs):
        calls.append((deepcopy(messages), deepcopy(kwargs)))
        return {
            "content": json.dumps(
                {
                    "action": "answer",
                    "reply": "현재 값을 확인했습니다.",
                    "operations": [],
                    "active_field_id": None,
                    "resume_workflow": False,
                    "product_hierarchy_query": None,
                    "continues_pending_clarification": False,
                    "deferred_facts": [],
                },
                ensure_ascii=False,
            )
        }

    monkeypatch.setattr(decision_module, "azure_chat_completion", completion)
    context = {"current_message": "현재 값은?", "conversation": {"recent_turns": []}}
    contract = {"version": "agent_canonical_write_v1", "operations": {}}

    decision = decide_agent_action(context, contract)

    assert decision.action == "answer"
    assert len(calls) == 1
    llm_input = json.loads(calls[0][0][1]["content"])
    assert set(llm_input) == {"agent_context", "write_contract", "output_contract"}
    assert llm_input["agent_context"]["current_message"] == "현재 값은?"
    assert "message" not in llm_input
    assert llm_input["output_contract"]["resume_workflow"] is False
    assert llm_input["output_contract"]["product_hierarchy_query"] is None
    assert llm_input["output_contract"]["continues_pending_clarification"] is False
    assert llm_input["output_contract"]["deferred_facts"] == []
    instruction = calls[0][0][0]["content"]
    assert "active_field_id가 있으면 현재 대화 질문의 target Field로 사용한다." in instruction
    assert "비활성화되어 form_context와 Write Contract에 없는 조건 Field는 입력을 요구하거나 값 작성을 제안하지 않는다" in instruction
    assert "active_field_id는 현재 질문의 중심일 뿐" in instruction
    assert "Field target은 값의 형태만으로 판단하지 않고 current_message, active_question, recent_turns" in instruction
    assert "이미 사용자 결정이 기록된 다른 Field" in instruction
    assert "기존 결정을 변경·정정하려는 의미일 때만 target으로 고려" in instruction
    assert "answer나 clarify가 아니라 propose를 사용한다." in instruction
    assert "현재 active Field의 후보값 작성을 Agent에게 맡기는 것" in instruction
    assert "후보 문장을 직접 말하지 않았더라도" in instruction
    assert "특정 표현이나 키워드, 특정 Field가 아니라" in instruction
    assert "Context에 없는 사실·식별자·수치를 새로 만들지 않으며" in instruction
    assert "근거 없는 정보가 후보값 작성에 반드시 필요할 때만" in instruction
    assert "allowed_values를 canonical 값 판단 근거로 사용" in instruction
    assert "아직 값이 결정되거나 확인되지 않았다는 의미이면 canonical 값 미정으로 propose" in instruction
    assert "특정 문자열이나 키워드 목록이 아니라 active_question과 Field Context" in instruction
    assert "해당 없음 또는 적용 대상이 없다는 의미와 구분" in instruction
    assert "allowed_values에 미정이 없는 Field에는 이 규칙을 적용하지 않는다" in instruction
    assert "첫 응답부터 원문 그대로 propose한다" in instruction
    assert "입력 예시일 뿐 허용 형식이나 검증 규칙이 아니며" in instruction
    assert "form_context의 Field를 명시하여 값을 서술하면" in instruction
    assert "allow_custom_input=true인 Field는 allowed_values 외에도" in instruction
    assert "명시적으로 질문한 경우에는 active_field_id가 있더라도 기존처럼 answer" in instruction
    assert "active_field_id가 없고 사용자가 Field를 특정하지 않은 값만 답하면" in instruction
    assert "특정 단어나 숫자 개수만으로 정하지 않는다" in instruction
    assert "set_condition_card_series" in instruction
    assert "set_operating_fans" in instruction
    assert "Base 제품이나 비교 제품을 언급하지 않고" in instruction
    assert "해석 제품은 해석에 사용할 총 조립 형상을 기준" in instruction
    assert "조립 상태가 다른 해석 대상은 서로 다른 총 조립 형상이며 각각 다른 도면번호" in instruction
    assert "동일 도면번호의 비교 제품 Proposal을 만들지 않는다" in instruction
    assert "별도 도면번호 또는 현재 도면번호 입력 형식을 따르는 임시 도면번호" in instruction
    assert "Agent가 임시 도면번호를 임의로 생성하지 않는다" in instruction
    assert "이미 반영된 Base 대비 차이를 제공하면 기존 geometry operation으로 정상 propose" in instruction
    assert "단품 도면을 해석 제품으로 사용하려는 경우" in instruction
    assert "특정 단어나 키워드 분기가 아니라 current_message, recent_turns, Form Context, Request State" in instruction
    assert "앞에서 제시한 나머지 공통 속성을 후속 Instance에도 복원" in instruction
    assert "HEX 전용 확인 정책은 일반 선택형 Field의 allowed_values 규칙보다 우선" in instruction
    assert "allow_custom_input=true, active Field의 직접 값 응답을 바로 propose하는 일반 규칙보다도 우선" in instruction
    assert "하나의 Catalog 후보를 식별했다면 바로 propose하지 않고" in instruction
    assert "의미상 가능한 Catalog 후보가 둘 이상이면 임의 선택하지 않고" in instruction
    assert "Catalog에 없는 값을 스스로 생성하거나 보정하지 않으며" in instruction
    assert "실제 Catalog 조합 확인과 구조적 검증만 수행" in instruction
    assert "Catalog 검증과 대체 후보 산출" not in instruction
    assert "Write Contract에 그 입력을 처리할 기존 operation이 있으면 해당 operation으로 propose" in instruction
    assert "값의 형태상 가능한 다른 target을 새로 만들어 clarify하지 않는다" in instruction
    assert "실제로 둘 이상의 해석이 Context에 근거하고 선택에 따라 State 변경이 달라질 때만" in instruction
    assert "pairing이나 Cartesian product는 새로 추론하지 않는다" in instruction
    assert "pending_write_candidates" in instruction
    assert "특정 확인 문구에 의존하지 말고" in instruction
    assert "요청자(사용자가 요청사라고 표현한 경우 포함)" in instruction
    assert "basic_info.division은 의뢰자 소속 사업부" in instruction
    assert "request_context.division은 해석 대상 제품의 Division" in instruction
    assert "해석의뢰관리자에게 추가를 요청" in instruction
    assert "current_message, recent_turns, validation과 submission_process를 함께 보고 의미적으로 판단" in instruction
    assert "필수 입력 충족 여부일 뿐 실제 제출 또는 전체 절차 완료를 뜻하지 않는다" in instruction
    assert "첫 행동은 Case Matrix 확인" in instruction
    assert "SCREEN-xx, State key/path, Field ID" in instruction
    assert "active_field_id, workflow_status, geometry_id, card_id, fan_id" in instruction
    assert "실제 UI의 단계 번호와 화면명, 실제 UI의 Section/Field 명칭" in instruction
    assert "01 의뢰 대상·시작, 02 요청 내용, 03 해석 제품, 04 해석 조건, 05 Case Matrix, 06 전체 확인·최종 제출" in instruction
    assert "내부 식별자를 단순히 제거하거나 치환한 어색한 문장" in instruction
    assert "전체 확인 화면에서 의뢰서 미리보기를 검토하고 제출 동의 후 화면에서 최종 제출" in instruction
    assert "submission_process의 화면 제출 방식과 동의 절차" in instruction
    assert "질문과 관계없는 미정 항목이나 누락 항목을 매번 반복하지 않는다" in instruction
    assert "sedo.hong@lge.com" not in instruction
    assert "resume_workflow=false" in instruction
    assert "product_hierarchy_query" in instruction
    assert "SJ" not in instruction and "PL" not in instruction
    assert "case 1" not in instruction.casefold()
    assert "미정이다" not in instruction
    assert "아직 미정" not in instruction
    assert "알아서 작성해줘" not in instruction
    assert "만들어줘" not in instruction


def test_main_chat_calls_one_decision_and_answers_current_value_without_legacy_paths(monkeypatch):
    calls = []

    def decider(context, contract):
        calls.append((deepcopy(context), deepcopy(contract)))
        return _decision("answer", "현재 프로젝트명은 ABC입니다.")

    for name in (
        "_proposal_response_with_llm",
        "extract_form_patch_with_llm",
        "_current_input_qa",
        "_general_chat_answer",
        "_run_rag_qa_read_only",
        "synthesize_rag_answer",
    ):
        monkeypatch.setattr(app_module, name, lambda *_args, _name=name, **_kwargs: (_ for _ in ()).throw(AssertionError(_name)))
    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    app.extensions["orchestrator_service"].handle = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy intent router"))
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)

    response = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "현재 프로젝트명이 뭐야?", "mode": "rag"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["action"] == "answer"
    assert body["assistant"] == "현재 프로젝트명은 ABC입니다."
    assert "proposal" not in body and "qa" not in body
    assert requests.read(request_id) == before
    assert len(calls) == 1
    assert calls[0][0]["current_message"] == "현재 프로젝트명이 뭐야?"
    assert calls[0][0]["conversation"]["recent_turns"] == []
    assert "set_condition_field" in calls[0][1]["operations"]
    assert "next_question" not in body
    assert app.extensions["conversation_store"].read(conversation_id).recent_turns == [
        {"role": "user", "content": "현재 프로젝트명이 뭐야?"},
        {"role": "assistant", "content": "현재 프로젝트명은 ABC입니다."},
    ]


def test_active_field_short_answer_creates_exact_condition_proposal_and_side_question_keeps_focus(monkeypatch):
    seen_contexts = []

    def decider(context, _contract):
        seen_contexts.append(deepcopy(context))
        if context["current_message"] == "780 RPM":
            return _decision(
                "propose",
                "운전 1의 Fan RPM을 780으로 변경하는 내용을 제안합니다.",
                [
                    {
                        "op": "set_condition_field",
                        "card_id": "operating_1",
                        "field_key": "fan_rpm",
                        "fan_id": "fan_1",
                        "value": "780",
                    }
                ],
            )
        return _decision("answer", "Fan RPM은 팬의 분당 회전수입니다.")

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    monkeypatch.setattr(
        app_module,
        "plan_next_question",
        lambda _snapshot, **_kwargs: {
            "kind": "field_question",
            "message": "운전 1의 팬 회전수를 입력해 주세요.",
            "active_field_id": "conditions.operating_1.fan_rpm",
            "blocking_code": "conditions.operating_1.fan_rpm.required_missing",
        },
    )
    conversations = app.extensions["conversation_store"]
    conversations.set_active_field(conversation_id, "conditions.operating_1.fan_rpm")
    before = app.extensions["request_state_store"].read(request_id)

    proposed = client.post("/api/chat/send", json={"conversation_id": conversation_id, "message": "780 RPM"})

    assert proposed.status_code == 200
    proposal = proposed.get_json()["proposal"]
    assert proposal["status"] == "pending"
    assert proposal["changes"][0]["label"] == "운전 조건 · 팬 회전수(RPM)"
    assert "operating_1" not in proposal["changes"][0]["label"]
    assert app.extensions["request_state_store"].read(request_id) == before
    assert seen_contexts[0]["conversation"]["active_field_id"] == "conditions.operating_1.fan_rpm"

    answered = client.post("/api/chat/send", json={"conversation_id": conversation_id, "message": "Fan RPM이 무슨 뜻이야?"})

    assert answered.get_json()["action"] == "answer"
    assert "next_question" not in answered.get_json()
    assert conversations.read(conversation_id).active_field_id == "conditions.operating_1.fan_rpm"


def test_temperature_conditions_without_reference_values_create_none_proposal_from_form_context(monkeypatch):
    def decider(context, _contract):
        fields = {
            field["field_id"]: field
            for field in context["form_context"]["fields"]
        }
        for field_id in (
            "conditions.space_environment_1.room_temp",
            "conditions.supply_air_1.heat_exchanger_temp",
        ):
            assert fields[field_id]["allowed_values"] == ["없음"]
            assert fields[field_id]["allow_custom_input"] is True
        return _decision(
            "propose",
            "공간 온도와 취출 온도를 없음으로 제안합니다.",
            [
                {
                    "op": "set_condition_field",
                    "card_id": "space_environment_1",
                    "field_key": "room_temp",
                    "value": "없음",
                },
                {
                    "op": "set_condition_field",
                    "card_id": "supply_air_1",
                    "field_key": "heat_exchanger_temp",
                    "value": "없음",
                },
            ],
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider, "기류 패턴")
    app.extensions["conversation_store"].set_active_field(
        conversation_id,
        "conditions.space_environment_1.room_temp",
    )
    before = app.extensions["request_state_store"].read(request_id)

    response = client.post(
        "/api/chat/send",
        json={
            "conversation_id": conversation_id,
            "message": "해석에 참고할 별도 온도 조건은 없습니다.",
        },
    )

    assert response.status_code == 200
    proposal = response.get_json()["proposal"]
    assert proposal["status"] == "pending"
    assert {change["new_value"] for change in proposal["changes"]} == {"없음"}
    assert len(proposal["changes"]) == 2
    assert app.extensions["request_state_store"].read(request_id) == before


def test_non_temperature_analysis_agent_context_omits_removed_temperature_conditions(monkeypatch):
    def decider(context, contract):
        field_ids = {field["field_id"] for field in context["form_context"]["fields"]}
        condition_targets = {
            (target["card_id"], target["field_key"])
            for target in contract["operations"]["set_condition_field"]["targets"]
        }
        card_types = {
            card["type"]
            for card in context["request_state"]["conditions"]["condition_sets"]
        }
        assert "conditions.space_environment_1.room_temp" not in field_ids
        assert "conditions.supply_air_1.heat_exchanger_temp" not in field_ids
        assert ("space_environment_1", "room_temp") not in condition_targets
        assert ("supply_air_1", "heat_exchanger_temp") not in condition_targets
        assert card_types == {"operating", "heat_exchanger"}
        assert context["instance_context"]["space_environments"] == {}
        assert context["instance_context"]["supply_air_conditions"] == {}
        return _decision("answer", "풍량과 열교환기 사양 조건을 기준으로 안내하겠습니다.")

    for analysis_type in ("풍량", "열교환기 유속 프로파일"):
        _app, client, _request_id, conversation_id = _runtime(monkeypatch, decider, analysis_type)
        response = client.post(
            "/api/chat/send",
            json={"conversation_id": conversation_id, "message": "필요한 해석 조건을 알려줘."},
        )

        assert response.status_code == 200
        assert response.get_json()["action"] == "answer"
        assert "온도" not in response.get_json()["assistant"]


def test_delegated_active_field_drafting_uses_grounded_state_and_waits_for_approval(monkeypatch):
    candidate = "토출부 주변 이슬맺힘 발생 원인과 발생 영역을 확인하고 개선 방향을 검토하고 싶습니다."

    def decider(context, contract):
        assert context["conversation"]["active_field_id"] == "analysis_overview.additional_result_request"
        assert "토출부 주변 이슬맺힘" in field_value(
            context["request_state"]["analysis_overview"]["request_description"]
        )
        assert any(
            target["path"] == "analysis_overview.additional_result_request"
            for target in contract["operations"]["set"]["targets"]
        )
        return _decision(
            "propose",
            "현재 요청 배경을 바탕으로 확인 내용을 제안합니다.",
            [
                {
                    "op": "set",
                    "path": "analysis_overview.additional_result_request",
                    "value": candidate,
                }
            ],
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    requests = app.extensions["request_state_store"]
    initial = requests.read(request_id)
    grounded_state = deepcopy(initial.state)
    grounded_state["analysis_overview"]["request_description"] = {
        "value": "토출부 주변 이슬맺힘 발생으로 개선 검토가 필요합니다."
    }
    grounded_state["analysis_overview"]["additional_result_request"] = {"value": ""}
    requests.replace(request_id, initial.version, grounded_state)
    monkeypatch.setattr(
        app_module,
        "plan_next_question",
        lambda _snapshot, **_kwargs: {
            "kind": "field_question",
            "message": "해석으로 확인하고 싶은 내용을 작성해 주세요.",
            "active_field_id": "analysis_overview.additional_result_request",
            "blocking_code": "analysis_overview.additional_result_request.required_missing",
        },
    )
    app.extensions["conversation_store"].set_active_field(
        conversation_id,
        "analysis_overview.additional_result_request",
    )
    before = requests.read(request_id)

    proposed = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "현재 내용에 맞게 네가 작성해 줘."},
    )

    assert proposed.status_code == 200
    body = proposed.get_json()
    assert body["action"] == "propose"
    assert body["proposal"]["status"] == "pending"
    assert requests.read(request_id) == before

    approved = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": body["proposal"]["proposal_id"], "decision": "approve"},
    )

    assert approved.status_code == 200
    assert field_value(
        requests.read(request_id).state["analysis_overview"]["additional_result_request"]
    ) == candidate


def test_delegated_active_field_drafting_clarifies_when_required_fact_has_no_basis(monkeypatch):
    def decider(context, _contract):
        assert context["conversation"]["active_field_id"] == "analysis_overview.model_suffix"
        assert not field_value(context["request_state"]["analysis_overview"]["model_suffix"])
        return _decision(
            "clarify",
            "모델명을 확인할 근거가 없어 해당 정보를 알려주세요.",
            active_field_id="analysis_overview.model_suffix",
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    monkeypatch.setattr(
        app_module,
        "plan_next_question",
        lambda _snapshot, **_kwargs: {
            "kind": "field_question",
            "message": "모델명을 입력해 주세요.",
            "active_field_id": "analysis_overview.model_suffix",
            "blocking_code": "analysis_overview.model_suffix.required_missing",
        },
    )
    app.extensions["conversation_store"].set_active_field(
        conversation_id,
        "analysis_overview.model_suffix",
    )
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)

    response = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "필요한 값을 내가 모르니 대신 완성해 줘."},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["action"] == "clarify"
    assert "proposal" not in body
    assert app.extensions["proposal_service"].proposal_count() == 0
    assert requests.read(request_id) == before


def test_product_hierarchy_side_questions_use_canonical_matches_and_keep_workflow_focus(monkeypatch):
    seen_contexts = []

    def decider(context, _contract):
        seen_contexts.append(deepcopy(context))
        query = {"platform": "Ventilation"} if context["current_message"].startswith("Ventilation") else {"platform": "PTAC"}
        return _decision(
            "answer",
            "제품 분류 기준을 조회합니다.",
            resume_workflow=False,
            product_hierarchy_query=query,
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    conversations = app.extensions["conversation_store"]
    conversations.set_active_field(conversation_id, "analysis_overview.development_grade")
    before = app.extensions["request_state_store"].read(request_id)

    first = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "Ventilation은 어느 Product Line-up이야?"},
    ).get_json()
    second = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "그럼 PTAC은?"},
    ).get_json()

    assert "가능한 경로" in first["assistant"]
    assert "SAC > Applied > Ventilation" in first["assistant"]
    assert "RAC > PTAC > PTAC > YA" in second["assistant"]
    assert "next_question" not in first and "next_question" not in second
    assert conversations.read(conversation_id).active_field_id == "analysis_overview.development_grade"
    assert seen_contexts[1]["conversation"]["recent_turns"][-1]["content"] == first["assistant"]
    assert app.extensions["proposal_service"].proposal_count() == 0
    assert app.extensions["request_state_store"].read(request_id) == before


def test_request_context_answer_and_unknown_hierarchy_result_never_cross_fill(monkeypatch):
    def decider(context, _contract):
        if context["current_message"].startswith("현재"):
            assert context["request_state"]["request_context"]["platform"] == "SK"
            return _decision("answer", "현재 선택한 플랫폼은 SK입니다.", resume_workflow=False)
        return _decision(
            "answer",
            "제품 분류 기준을 조회합니다.",
            resume_workflow=False,
            product_hierarchy_query={"platform": "ZZ-UNKNOWN"},
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    before = app.extensions["request_state_store"].read(request_id)
    current = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "현재 내가 선택한 플랫폼이 뭐야?"},
    ).get_json()
    unknown = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "ZZ-UNKNOWN은 어느 제품군이야?"},
    ).get_json()

    assert current["assistant"] == "현재 선택한 플랫폼은 SK입니다."
    assert "찾지 못했습니다" in unknown["assistant"]
    assert "벽걸이" not in unknown["assistant"] and "SK" not in unknown["assistant"]
    assert "next_question" not in current and "next_question" not in unknown
    assert app.extensions["proposal_service"].proposal_count() == 0
    assert app.extensions["request_state_store"].read(request_id) == before


def test_explicit_semantic_resume_uses_existing_planner(monkeypatch):
    app, client, _request_id, conversation_id = _runtime(
        monkeypatch,
        lambda _context, _contract: _decision(
            "answer",
            "현재 작성 위치에서 계속하겠습니다.",
            resume_workflow=True,
        ),
    )

    resumed = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "이제 작성하던 흐름을 이어가자."},
    ).get_json()

    assert resumed["next_question"]["active_field_id"] == "analysis_overview.development_grade"


def test_product_hierarchy_read_only_lookup_handles_zero_one_and_multiple_results():
    missing = find_product_hierarchy_matches({"platform": "ZZ-UNKNOWN"})
    single = find_product_hierarchy_matches({"platform": "PTAC"})
    multiple = find_product_hierarchy_matches({"platform": "Ventilation"})
    product_lineup = find_product_hierarchy_matches({"division": "RAC", "product_lineup": "PTAC"})

    assert missing == []
    assert len(single) == 1 and single[0]["display_path"] == "RAC > PTAC > PTAC > YA"
    assert len(multiple) == 16
    assert "찾지 못했습니다" in product_hierarchy_answer({"platform": "ZZ-UNKNOWN"}, missing)
    assert "RAC > PTAC > PTAC > YA" in product_hierarchy_answer({"platform": "PTAC"}, single)
    assert "가능한 경로" in product_hierarchy_answer({"platform": "Ventilation"}, multiple)
    assert "RAC > PTAC > PTAC > YA" in product_hierarchy_answer(
        {"division": "RAC", "product_lineup": "PTAC"},
        product_lineup,
    )


def test_multiple_operations_create_one_proposal_and_apply_once_through_existing_cas(monkeypatch):
    operations = [
        {"op": "set", "path": "analysis_overview.project_name", "value": "XYZ"},
        {
            "op": "set_condition_field",
            "card_id": "operating_1",
            "field_key": "fan_rpm",
            "fan_id": "fan_1",
            "value": "900",
        },
    ]
    app, client, request_id, conversation_id = _runtime(
        monkeypatch,
        lambda _context, _contract: _decision("propose", "프로젝트명과 Fan RPM 변경을 제안합니다.", operations),
    )
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)

    proposed = client.post("/api/chat/send", json={"conversation_id": conversation_id, "message": "프로젝트명은 XYZ, Fan RPM은 900"})
    proposal_id = proposed.get_json()["proposal"]["proposal_id"]

    assert app.extensions["proposal_service"].proposal_count() == 1
    assert len(app.extensions["proposal_service"].read_proposal(proposal_id).operations) == 2
    assert requests.read(request_id) == before

    approved = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal_id, "decision": "approve"},
    )
    latest = requests.read(request_id)

    assert approved.get_json()["status"] == "approved"
    assert latest.version == before.version + 1
    assert field_value(latest.state["analysis_overview"]["project_name"]) == "XYZ"
    assert _fan_rpm(latest.state) == "900"


def test_requester_info_fields_can_be_changed_together_by_agent_after_approval(monkeypatch):
    operations = [
        {"op": "set", "path": "basic_info.division", "value": "RAC"},
        {"op": "set", "path": "basic_info.department", "value": "개발2팀"},
        {"op": "set", "path": "basic_info.requester_name", "value": "홍길동"},
        {"op": "set", "path": "basic_info.requester_role", "value": "책임연구원"},
    ]
    app, client, request_id, conversation_id = _runtime(
        monkeypatch,
        lambda _context, _contract: _decision(
            "propose",
            "의뢰자 정보 네 항목의 변경을 제안합니다.",
            operations,
        ),
    )
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)

    proposed = client.post(
        "/api/chat/send",
        json={
            "conversation_id": conversation_id,
            "message": "의뢰자 사업부는 RAC, 부서는 개발2팀, 요청사는 홍길동, 직급은 책임연구원으로 바꿔줘",
        },
    )

    assert proposed.status_code == 200
    body = proposed.get_json()
    assert body["action"] == "propose"
    proposal_id = body["proposal"]["proposal_id"]
    assert [change["label"] for change in body["proposal"]["changes"]] == [
        "사업부",
        "부서",
        "요청자",
        "직급",
    ]
    assert requests.read(request_id) == before

    approved = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal_id, "decision": "approve"},
    )
    latest = requests.read(request_id)

    assert approved.status_code == 200
    assert approved.get_json()["status"] == "approved"
    assert latest.version == before.version + 1
    assert {
        key: field_value(latest.state["basic_info"][key])
        for key in ("division", "department", "requester_name", "requester_role")
    } == {
        "division": "RAC",
        "department": "개발2팀",
        "requester_name": "홍길동",
        "requester_role": "책임연구원",
    }


def test_clarify_records_only_valid_active_field_without_proposal_or_state_change(monkeypatch):
    app, client, request_id, conversation_id = _runtime(
        monkeypatch,
        lambda _context, _contract: _decision(
            "clarify",
            "어느 운전 조건의 값을 말씀하시는지 알려주세요.",
            active_field_id="conditions.operating_1.fan_rpm",
        ),
    )
    before = app.extensions["request_state_store"].read(request_id)

    response = client.post("/api/chat/send", json={"conversation_id": conversation_id, "message": "그거 780으로 바꿔줘."})

    assert response.get_json()["action"] == "clarify"
    assert app.extensions["proposal_service"].proposal_count() == 0
    assert app.extensions["request_state_store"].read(request_id) == before
    assert app.extensions["conversation_store"].read(conversation_id).active_field_id == "conditions.operating_1.fan_rpm"


def test_clarified_comparison_values_are_preserved_in_one_multi_operation_proposal(monkeypatch):
    operations = [
        {
            "op": "set_geometry_field",
            "geometry_id": "comparison_001",
            "field_key": "difference_from_base",
            "value": "디스차지 1번",
        },
        {
            "op": "set_geometry_field",
            "geometry_id": "comparison_002",
            "field_key": "difference_from_base",
            "value": "디스차지 2번",
        },
    ]
    decisions = []

    def decider(context, contract):
        decisions.append(deepcopy(context))
        geometry_targets = contract["operations"]["set_geometry_field"]["targets"]
        assert {target["geometry_id"] for target in geometry_targets} >= {
            "comparison_001",
            "comparison_002",
        }
        if len(decisions) == 1:
            return _decision(
                "clarify",
                "두 비교 제품의 변경점을 이렇게 이해했습니다. 이대로 제안할까요?",
                operations,
                active_field_id="geometry.comparison_products[0].difference_from_base",
            )
        assert context["conversation"]["pending_write_candidates"] == operations
        # Even if the semantic decision repeats only the focused target, the
        # server must not drop the other structurally preserved candidate.
        return _decision(
            "propose",
            "확인한 두 변경점을 함께 제안합니다.",
            operations[:1],
            continues_pending_clarification=True,
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    requests = app.extensions["request_state_store"]
    current = requests.read(request_id)
    state = deepcopy(current.state)
    state["geometry"]["base_product"].update(
        {"geometry_id": "base_001", "role": "base", "drawing_no": "DRAW-A"}
    )
    state["geometry"]["comparison_products"] = [
        {
            "geometry_id": "comparison_001",
            "role": "comparison",
            "drawing_no": "DRAW-B",
            "display_name": "형상 2",
            "difference_from_base": "",
        },
        {
            "geometry_id": "comparison_002",
            "role": "comparison",
            "drawing_no": "DRAW-C",
            "display_name": "형상 3",
            "difference_from_base": "",
        },
    ]
    requests.replace(request_id, current.version, state)

    original_planner = app_module.plan_next_question

    def comparison_planner(snapshot, **kwargs):
        for index, product in enumerate(snapshot.state["geometry"]["comparison_products"]):
            if not field_value(product.get("difference_from_base")):
                return {
                    "kind": "field_question",
                    "message": "비교 제품의 Base 대비 변경점을 입력해 주세요.",
                    "active_field_id": f"geometry.comparison_products[{index}].difference_from_base",
                    "blocking_code": "geometry.comparison.difference.required_missing",
                }
        return original_planner(snapshot, **kwargs)

    monkeypatch.setattr(app_module, "plan_next_question", comparison_planner)
    app.extensions["conversation_store"].set_active_field(
        conversation_id,
        "geometry.comparison_products[0].difference_from_base",
    )
    before = requests.read(request_id)

    clarified = client.post(
        "/api/chat/send",
        json={
            "conversation_id": conversation_id,
            "message": "형상2는 디스차지 1번, 형상3은 디스차지 2번이다.",
        },
    ).get_json()

    assert clarified["action"] == "clarify"
    assert requests.read(request_id) == before
    assert app.extensions["proposal_service"].proposal_count() == 0
    assert app.extensions["conversation_store"].read(conversation_id).pending_write_candidates == operations

    proposed = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "그 이해가 정확합니다."},
    ).get_json()
    proposal_id = proposed["proposal"]["proposal_id"]
    proposal = app.extensions["proposal_service"].read_proposal(proposal_id)

    assert proposed["action"] == "propose"
    assert len(proposal.operations) == 2
    assert requests.read(request_id) == before
    assert app.extensions["conversation_store"].read(conversation_id).pending_write_candidates == []

    approved = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal_id, "decision": "approve"},
    ).get_json()
    comparisons = requests.read(request_id).state["geometry"]["comparison_products"]

    assert [field_value(product["difference_from_base"]) for product in comparisons] == [
        "디스차지 1번",
        "디스차지 2번",
    ]
    assert approved.get("next_question", {}).get("active_field_id") != (
        "geometry.comparison_products[1].difference_from_base"
    )


def test_clarified_general_field_candidates_use_the_same_preservation_mechanism(monkeypatch):
    operations = [
        {"op": "set", "path": "basic_info.division", "value": "RAC"},
        {"op": "set", "path": "basic_info.department", "value": "개발2팀"},
    ]
    call_count = 0

    def decider(context, _contract):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _decision(
                "clarify",
                "의뢰자 사업부와 부서를 확인했습니다. 함께 변경할까요?",
                operations,
                active_field_id="basic_info.division",
            )
        assert context["conversation"]["pending_write_candidates"] == operations
        return _decision(
            "propose",
            "확인한 의뢰자 정보를 함께 제안합니다.",
            operations[:1],
            continues_pending_clarification=True,
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    monkeypatch.setattr(
        app_module,
        "plan_next_question",
        lambda _snapshot, **_kwargs: {
            "kind": "field_question",
            "message": "의뢰자 사업부를 입력해 주세요.",
            "active_field_id": "basic_info.division",
            "blocking_code": "basic_info.division.required_missing",
        },
    )
    app.extensions["conversation_store"].set_active_field(conversation_id, "basic_info.division")
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)

    clarified = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "사업부는 RAC이고 부서는 개발2팀입니다."},
    ).get_json()
    proposed = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "두 항목 모두 그렇게 반영하면 됩니다."},
    ).get_json()

    assert clarified["action"] == "clarify"
    assert requests.read(request_id) == before
    proposal_id = proposed["proposal"]["proposal_id"]
    assert len(app.extensions["proposal_service"].read_proposal(proposal_id).operations) == 2

    client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal_id, "decision": "approve"},
    )
    latest = requests.read(request_id)
    assert field_value(latest.state["basic_info"]["division"]) == "RAC"
    assert field_value(latest.state["basic_info"]["department"]) == "개발2팀"


def test_unrelated_proposal_discards_stale_clarification_candidates(monkeypatch):
    pending = [
        {"op": "set", "path": "basic_info.division", "value": "RAC"},
        {"op": "set", "path": "basic_info.department", "value": "개발2팀"},
    ]
    unrelated = [
        {"op": "set", "path": "analysis_overview.project_name", "value": "NEW-PROJECT"},
    ]
    call_count = 0

    def decider(context, _contract):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _decision(
                "clarify",
                "의뢰자 정보 후보를 확인해 주세요.",
                pending,
                active_field_id="basic_info.division",
            )
        assert context["conversation"]["pending_write_candidates"] == pending
        return _decision("propose", "새 프로젝트명 변경을 제안합니다.", unrelated)

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    monkeypatch.setattr(
        app_module,
        "plan_next_question",
        lambda _snapshot, **_kwargs: {
            "kind": "field_question",
            "message": "의뢰자 사업부를 입력해 주세요.",
            "active_field_id": "basic_info.division",
            "blocking_code": "basic_info.division.required_missing",
        },
    )
    app.extensions["conversation_store"].set_active_field(conversation_id, "basic_info.division")
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)

    client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "사업부와 부서는 이 값들이 맞나요?"},
    )
    proposed = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "별개로 프로젝트명만 바꿔 주세요."},
    ).get_json()
    proposal = app.extensions["proposal_service"].read_proposal(proposed["proposal"]["proposal_id"])

    assert [(operation["path"], operation["value"]) for operation in proposal.operations] == [
        ("analysis_overview.project_name", "NEW-PROJECT")
    ]
    assert app.extensions["conversation_store"].read(conversation_id).pending_write_candidates == []
    assert requests.read(request_id) == before


def test_answer_ends_pending_clarification_without_creating_a_proposal(monkeypatch):
    pending = [{"op": "set", "path": "basic_info.division", "value": "RAC"}]
    call_count = 0

    def decider(_context, _contract):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _decision(
                "clarify",
                "의뢰자 사업부 후보를 확인해 주세요.",
                pending,
                active_field_id="basic_info.division",
            )
        return _decision("answer", "별도 질문에 답변했습니다.")

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)

    client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "사업부 후보를 확인해 줘."},
    )
    answered = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "그건 중단하고 현재 프로젝트명을 알려줘."},
    ).get_json()

    assert answered["action"] == "answer"
    assert app.extensions["conversation_store"].read(conversation_id).pending_write_candidates == []
    assert app.extensions["proposal_service"].proposal_count() == 0
    assert requests.read(request_id) == before


def test_pending_proposal_allows_answer_but_blocks_second_proposal(monkeypatch):
    def decider(context, _contract):
        if context["current_message"] == "왜 바꾸는 거야?":
            assert context["workflow"]["has_pending_proposal"] is True
            return _decision("answer", "사용자가 요청한 값으로 변경하기 위한 제안입니다.")
        value = "XYZ" if context["current_message"] == "첫 변경" else "SECOND"
        return _decision(
            "propose",
            f"프로젝트명을 {value}로 변경하는 내용을 제안합니다.",
            [{"op": "set", "path": "analysis_overview.project_name", "value": value}],
        )

    app, client, _request_id, conversation_id = _runtime(monkeypatch, decider)
    first = client.post("/api/chat/send", json={"conversation_id": conversation_id, "message": "첫 변경"}).get_json()
    proposal_id = first["proposal"]["proposal_id"]

    answer = client.post("/api/chat/send", json={"conversation_id": conversation_id, "message": "왜 바꾸는 거야?"}).get_json()
    blocked = client.post("/api/chat/send", json={"conversation_id": conversation_id, "message": "두 번째 변경"}).get_json()

    assert answer["action"] == "answer"
    assert blocked["kind"] == "pending_proposal_wait"
    assert blocked["pending_proposal_id"] == proposal_id
    assert app.extensions["proposal_service"].proposal_count() == 1
    conversation = app.extensions["conversation_store"].read(conversation_id)
    assert conversation.workflow_status == "awaiting_proposal_approval"
    assert conversation.pending_proposal_id == proposal_id


def test_stale_request_after_decision_does_not_create_proposal_or_record_turns(monkeypatch):
    holder = {}

    def decider(_context, _contract):
        requests = holder["app"].extensions["request_state_store"]
        current = requests.read(holder["request_id"])
        requests.replace(current.request_id, current.version, current.state)
        return _decision(
            "propose",
            "프로젝트명 변경을 제안합니다.",
            [{"op": "set", "path": "analysis_overview.project_name", "value": "STALE"}],
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    holder.update(app=app, request_id=request_id)
    conversation_before = app.extensions["conversation_store"].read(conversation_id)

    response = client.post("/api/chat/send", json={"conversation_id": conversation_id, "message": "STALE로 변경"})

    assert response.status_code == 409
    assert response.get_json()["error"] == "request_version_conflict"
    assert app.extensions["proposal_service"].proposal_count() == 0
    assert app.extensions["conversation_store"].read(conversation_id) == conversation_before


def test_llm_failure_has_no_fallback_and_changes_no_server_state(monkeypatch):
    def failure(_context, _contract):
        raise RuntimeError("offline")

    app, client, request_id, conversation_id = _runtime(monkeypatch, failure)
    request_before = app.extensions["request_state_store"].read(request_id)
    conversation_before = app.extensions["conversation_store"].read(conversation_id)

    response = client.post("/api/chat/send", json={"conversation_id": conversation_id, "message": "현재 값은?"})

    assert response.status_code == 503
    assert response.get_json()["assistant"] == "LLM이 정상 작동하지 않습니다."
    assert app.extensions["proposal_service"].proposal_count() == 0
    assert app.extensions["request_state_store"].read(request_id) == request_before
    assert app.extensions["conversation_store"].read(conversation_id) == conversation_before


def test_active_fan_rpm_case_values_create_two_condition_proposal_without_clarify(monkeypatch):
    operations = [
        {
            "op": "set_condition_card_series",
            "card_type": "operating",
            "field_key": "fan_rpm",
            "values": ["1500", "1800"],
        }
    ]

    def decider(context, contract):
        assert context["active_question"]["field_key"] == "fan_rpm"
        targets = contract["operations"]["set_condition_card_series"]["targets"]
        assert any(target["card_type"] == "operating" and target["field_key"] == "fan_rpm" for target in targets)
        return _decision("propose", "두 운전 조건의 Fan RPM 변경을 제안합니다.", operations)

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    monkeypatch.setattr(
        app_module,
        "plan_next_question",
        lambda _snapshot, **_kwargs: {
            "kind": "field_question",
            "message": "운전 조건의 Fan RPM을 입력해 주세요.",
            "active_field_id": "conditions.operating_1.fan_rpm",
            "blocking_code": "conditions.operating_1.fan_rpm.required_missing",
        },
    )
    app.extensions["conversation_store"].set_active_field(conversation_id, "conditions.operating_1.fan_rpm")
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)

    response = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "rpm은 case 1은 1500 / case 2는 1800이야."},
    )

    body = response.get_json()
    assert response.status_code == 200
    assert body["action"] == "propose"
    assert body["proposal"]["status"] == "pending"
    assert requests.read(request_id) == before

    client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": body["proposal"]["proposal_id"], "decision": "approve"},
    )
    operating_cards = [
        card
        for card in requests.read(request_id).state["conditions"]["condition_sets"]
        if card["type"] == "operating"
    ]
    assert [card["fans"][0]["values"]["fan_rpm"] for card in operating_cards] == ["1500", "1800"]


def test_deleted_condition_card_clears_stale_agent_active_field_before_the_next_turn(monkeypatch):
    def decider(context, _contract):
        assert context["conversation"]["active_field_id"] is None
        assert context["active_question"] is None
        return _decision("answer", "현재 조건을 기준으로 다시 확인했습니다.")

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    requests = app.extensions["request_state_store"]
    snapshot = requests.read(request_id)
    state = deepcopy(snapshot.state)
    first = next(card for card in state["conditions"]["condition_sets"] if card["type"] == "operating")
    second = deepcopy(first)
    second.update({"id": "operating_opaqueabc", "is_default": False})
    state["conditions"]["condition_sets"].append(second)
    with_second = requests.replace(request_id, snapshot.version, state)
    app.extensions["conversation_store"].set_active_field(
        conversation_id,
        "conditions.operating_opaqueabc.fan_rpm",
    )

    without_second = deepcopy(with_second.state)
    without_second["conditions"]["condition_sets"] = [
        card for card in without_second["conditions"]["condition_sets"] if card["id"] != "operating_opaqueabc"
    ]
    requests.replace(request_id, with_second.version, without_second)
    monkeypatch.setattr(
        app_module,
        "plan_next_question",
        lambda _snapshot, **_kwargs: {
            "kind": "complete",
            "message": "필수 입력이 완료되었습니다.",
            "active_field_id": None,
            "blocking_code": None,
        },
    )

    response = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "계속 진행해줘"},
    )

    assert response.status_code == 200
    assert app.extensions["conversation_store"].read(conversation_id).active_field_id is None


def test_common_heat_exchanger_attributes_are_restored_then_catalog_mismatch_can_be_proposed(monkeypatch):
    operations = [
        {
            "op": "set_condition_card_series",
            "card_type": "heat_exchanger",
            "field_key": "tube_diameter",
            "values": ["5", "5"],
        },
        {
            "op": "set_condition_card_series",
            "card_type": "heat_exchanger",
            "field_key": "fin_type",
            "values": ["Slit(Half)", "Slit(Half)"],
        },
        {
            "op": "set_condition_card_series",
            "card_type": "heat_exchanger",
            "field_key": "row_count",
            "values": ["2", "2"],
        },
        {
            "op": "set_condition_card_series",
            "card_type": "heat_exchanger",
            "field_key": "fpi",
            "values": ["17", "18"],
        },
    ]

    def decider(context, _contract):
        assert context["active_question"]["parent_group_key"] == "heat_exchanger"
        return _decision("propose", "두 열교환기 사양 변경을 제안합니다.", operations)

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    monkeypatch.setattr(
        app_module,
        "plan_next_question",
        lambda _snapshot, **_kwargs: {
            "kind": "field_question",
            "message": "열교환기 FPI를 입력해 주세요.",
            "active_field_id": "conditions.heat_exchanger_1.fpi",
            "blocking_code": "conditions.heat_exchanger_1.fpi.required_missing",
        },
    )
    app.extensions["conversation_store"].set_active_field(conversation_id, "conditions.heat_exchanger_1.fpi")
    requests = app.extensions["request_state_store"]
    before = requests.read(request_id)

    interpreted = apply_patch_operations(before.state, operations)
    heat_cards = [
        card
        for card in interpreted["conditions"]["condition_sets"]
        if card["type"] == "heat_exchanger"
    ]
    assert [
        tuple(field_value(card["fields"][key]) for key in ("tube_diameter", "fin_type", "row_count", "fpi"))
        for card in heat_cards
    ] == [
        ("5", "Slit(Half)", "2", "17"),
        ("5", "Slit(Half)", "2", "18"),
    ]
    validation = validate_heat_exchanger_proposal(interpreted, operations)
    assert validation["valid"] is True
    assert validation["alternatives"] == []

    response = client.post(
        "/api/chat/send",
        json={
            "conversation_id": conversation_id,
            "message": "하나는 5pi slit(half) 2R 17FPI이고 하나는 18FPI이다.",
        },
    )

    body = response.get_json()
    assert response.status_code == 200
    assert body["action"] == "propose"
    assert body["proposal"]["status"] == "pending"
    assert "Catalog에서 다음 조합을 찾을 수 없습니다" not in body["assistant"]
    assert "20FPI" not in body["assistant"]
    assert app.extensions["proposal_service"].proposal_count() == 1
    assert requests.read(request_id) == before
