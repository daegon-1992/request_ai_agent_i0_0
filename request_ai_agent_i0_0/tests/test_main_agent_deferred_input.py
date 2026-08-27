from copy import deepcopy

import request_ai_agent_i0_0.app as app_module
from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.condition_fieldsets import default_condition_sets


def _decision(action, reply, operations=None, *, deferred_facts=None, continues=False):
    return {
        "action": action,
        "reply": reply,
        "operations": operations or [],
        "active_field_id": None,
        "resume_workflow": False,
        "product_hierarchy_query": None,
        "continues_pending_clarification": continues,
        "deferred_facts": deferred_facts or [],
    }


def _runtime(monkeypatch, decider, *, locked=False):
    monkeypatch.setattr(app_module, "decide_agent_action", decider)
    app = create_app()
    client = app.test_client()
    state = client.get("/api/bootstrap").get_json()["state"]
    if locked:
        state["request_context"].update(
            {
                "taxonomy_id": "PTX-ADA7A057CA62",
                "analysis_type": "이슬맺힘",
                "context_locked": True,
            }
        )
        state["conditions"]["condition_sets"] = default_condition_sets(state["request_context"])
    created = client.post("/api/request/versioned", json={"state": state}).get_json()
    conversation = client.post("/api/conversations", json={"request_id": created["request_id"]}).get_json()
    return app, client, created["request_id"], conversation["conversation_id"]


def _approve(client, proposal_id):
    response = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": proposal_id, "decision": "approve"},
    )
    assert response.status_code == 200
    return response.get_json()


def _fan_rpm(state):
    operating = next(card for card in state["conditions"]["condition_sets"] if card["type"] == "operating")
    return operating["fans"][0]["values"]["fan_rpm"]


def test_initial_context_and_future_fan_value_are_preserved_then_proposed(monkeypatch):
    seen = []

    def decider(context, contract):
        seen.append(deepcopy(context))
        assert len(seen) == 1
        assert contract["operations"]["confirm_request_context"]["available"] is True
        return _decision(
            "propose",
            "의뢰 대상과 함께 입력 가능한 내용을 제안합니다.",
            [
                {
                    "op": "confirm_request_context",
                    "context": {
                "taxonomy_id": "PTX-ADA7A057CA62",
                        "analysis_type": "이슬맺힘",
                    },
                },
                {"op": "set", "path": "analysis_overview.project_name", "value": "ABC"},
                {"op": "set", "path": "analysis_overview.development_grade", "value": "B"},
                {"op": "list_values", "path": "geometry.products", "values": ["A100", "B200"]},
            ],
            deferred_facts=[
                {
                    "kind": "condition_field",
                    "target": {"card_type": "operating"},
                    "field_key": "fan_rpm",
                    "value": "780",
                    "source_summary": "Fan RPM 780",
                }
            ],
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    first = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "RAC 벽걸이 SK 이슬맺힘이고 프로젝트명 ABC, 개발등급 B, Base A100, 비교 B200, Fan 780 RPM이야."},
    ).get_json()

    assert first["proposal"]["status"] == "pending"
    context_changes = first["proposal"]["changes"]
    assert any(change["label"] == "Division" and change["new_value"] == "RAC" for change in context_changes)
    assert "아직 준비되지 않아 보관" in first["assistant"]
    before_approval = app.extensions["request_state_store"].read(request_id).state
    assert before_approval["request_context"]["context_locked"] is False
    assert len(app.extensions["request_state_store"].read_deferred_input_facts(request_id)) == 1

    approved = _approve(client, first["proposal"]["proposal_id"])
    after_context = app.extensions["request_state_store"].read(request_id)
    assert after_context.state["request_context"]["context_locked"] is True
    assert after_context.state["analysis_overview"]["project_name"]["value"] == "ABC"
    assert after_context.state["analysis_overview"]["development_grade"]["value"] == "B"
    assert after_context.state["geometry"]["base_product"]["drawing_no"]["value"] == "A100"
    assert after_context.state["geometry"]["comparison_products"][0]["drawing_no"]["value"] == "B200"
    assert _fan_rpm(after_context.state) == ""
    facts = app.extensions["request_state_store"].read_deferred_input_facts(request_id)
    assert facts[0]["resolution"] == "ready"
    assert "next_question" not in approved
    assert approved["proposal"]["status"] == "pending"
    pending = app.extensions["proposal_service"].pending_proposal_for_request(request_id)
    assert pending is not None and pending.proposal_id == approved["proposal"]["proposal_id"]
    assert "앞서 Fan RPM 780" in approved["assistant"]
    assert "당시에는 팬 회전수(RPM)" in approved["assistant"]
    assert "현재 팬 회전수(RPM)" in approved["assistant"]
    assert all(token not in approved["assistant"] for token in ("deferred", "card_id", "fan_id", "operation"))
    assert len(seen) == 1
    _approve(client, approved["proposal"]["proposal_id"])
    assert _fan_rpm(app.extensions["request_state_store"].read(request_id).state) == "780"
    assert app.extensions["request_state_store"].read_deferred_input_facts(request_id) == []
    assert app.extensions["proposal_service"].pending_proposal_for_request(request_id) is None


def test_comparison_difference_maps_only_after_product_card_creation(monkeypatch):
    calls = 0

    def decider(_context, _contract):
        nonlocal calls
        calls += 1
        return _decision(
            "propose",
            "Base와 비교제품 생성을 제안합니다.",
            [{"op": "list_values", "path": "geometry.products", "values": ["A100", "B200"]}],
            deferred_facts=[
                {
                    "kind": "geometry_field",
                    "target": {"role": "comparison", "product_reference": "B200"},
                    "field_key": "difference_from_base",
                    "value": "토출 그릴 변경",
                    "source_summary": "비교제품 B200의 Base 대비 토출 그릴 변경",
                }
            ],
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider, locked=True)
    first = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "Base A100, 비교 B200이고 B200은 토출 그릴 변경"},
    ).get_json()
    fact = app.extensions["request_state_store"].read_deferred_input_facts(request_id)[0]
    assert fact["target"] == {"role": "comparison", "product_reference": "B200"}
    assert "geometry_id" not in fact["target"]
    approved = _approve(client, first["proposal"]["proposal_id"])
    assert approved["proposal"]["status"] == "pending"
    assert "비교제품 B200" in approved["assistant"]
    assert "당시에는 B200 비교제품" in approved["assistant"]
    assert "현재 B200 비교제품" in approved["assistant"]
    assert calls == 1
    _approve(client, approved["proposal"]["proposal_id"])
    comparison = app.extensions["request_state_store"].read(request_id).state["geometry"]["comparison_products"][0]
    assert comparison["drawing_no"]["value"] == "B200"
    assert comparison["difference_from_base"]["value"] == "토출 그릴 변경"


def test_newer_form_value_supersedes_old_deferred_value(monkeypatch):
    def decider(_context, contract):
        return _decision(
            "propose",
            "Context 확정을 제안합니다.",
            [
                {
                    "op": "confirm_request_context",
                    "context": {
                "taxonomy_id": "PTX-ADA7A057CA62",
                        "analysis_type": "이슬맺힘",
                    },
                }
            ],
            deferred_facts=[
                {
                    "kind": "condition_field",
                    "target": {"card_type": "operating"},
                    "field_key": "fan_rpm",
                    "value": "780",
                    "source_summary": "Fan RPM 780",
                }
            ],
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    proposed = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "Context와 Fan 780 RPM"},
    ).get_json()
    followup = _approve(client, proposed["proposal"]["proposal_id"])["proposal"]
    latest = app.extensions["request_state_store"].read(request_id)

    unrelated_edit = deepcopy(latest.state)
    unrelated_edit["analysis_overview"]["project_name"] = {"value": "FORM-PROJECT", "source": "user"}
    unrelated = client.put(
        f"/api/request/versioned/{request_id}",
        json={"expected_version": latest.version, "state": unrelated_edit},
    )
    assert unrelated.status_code == 200
    retained = app.extensions["request_state_store"].read_deferred_input_facts(request_id)
    assert len(retained) == 1 and retained[0]["value"] == "780"

    latest = app.extensions["request_state_store"].read(request_id)
    edited = deepcopy(latest.state)
    operating = next(card for card in edited["conditions"]["condition_sets"] if card["type"] == "operating")
    operating["fans"][0]["values"]["fan_rpm"] = "900"
    replaced = client.put(
        f"/api/request/versioned/{request_id}",
        json={"expected_version": latest.version, "state": edited},
    )
    assert replaced.status_code == 200
    assert app.extensions["request_state_store"].read_deferred_input_facts(request_id) == []
    assert _fan_rpm(app.extensions["request_state_store"].read(request_id).state) == "900"
    conflicted = _approve(client, followup["proposal_id"])
    assert conflicted["status"] == "conflicted"
    assert _fan_rpm(app.extensions["request_state_store"].read(request_id).state) == "900"


def test_newer_agent_value_replaces_ready_deferred_value_without_old_value_message(monkeypatch):
    calls = 0

    def decider(context, contract):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _decision(
                "propose",
                "Context 확정을 제안합니다.",
                [
                    {
                        "op": "confirm_request_context",
                        "context": {
                "taxonomy_id": "PTX-ADA7A057CA62",
                            "analysis_type": "이슬맺힘",
                        },
                    }
                ],
                deferred_facts=[
                    {
                        "kind": "condition_field",
                        "target": {"card_type": "operating"},
                        "field_key": "fan_rpm",
                        "value": "780",
                        "source_summary": "Fan RPM 780",
                    }
                ],
            )
        assert context["request_deferred_input"]["ready"] == []
        target = next(
            item
            for item in contract["operations"]["set_condition_field"]["targets"]
            if item["card_type"] == "operating" and item["field_key"] == "fan_rpm"
        )
        operation = {
            "op": "set_condition_field",
            "card_id": target["card_id"],
            "fan_id": target["fans"][0]["fan_id"],
            "field_key": "fan_rpm",
            "value": "900",
        }
        return _decision("propose", "최신 Fan RPM 900 반영을 제안합니다.", [operation])

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    first = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "Context와 Fan 780 RPM"},
    ).get_json()
    automatic = _approve(client, first["proposal"]["proposal_id"])["proposal"]
    rejected = client.post(
        "/api/orchestrator/proposals/decision",
        json={"proposal_id": automatic["proposal_id"], "decision": "reject"},
    )
    assert rejected.status_code == 200

    second = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "Fan은 900 RPM으로 수정할게."},
    ).get_json()
    assert "최신 Fan RPM 900" in second["assistant"]
    assert "앞선 대화" not in second["assistant"]
    assert app.extensions["request_state_store"].read_deferred_input_facts(request_id) == []
    _approve(client, second["proposal"]["proposal_id"])
    assert _fan_rpm(app.extensions["request_state_store"].read(request_id).state) == "900"


def test_clear_fact_survives_partial_clarification(monkeypatch):
    def decider(_context, _contract):
        return _decision(
            "clarify",
            "어느 운전 조건인지 관계만 확인해 주세요.",
            deferred_facts=[
                {
                    "kind": "geometry_field",
                    "target": {"role": "comparison", "product_reference": "C300"},
                    "field_key": "difference_from_base",
                    "value": "흡입 그릴 변경",
                    "source_summary": "비교제품 C300의 흡입 그릴 변경",
                }
            ],
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider, locked=True)
    response = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "C300은 흡입 그릴 변경이고 Fan 값은 어느 조건인지 애매해."},
    ).get_json()
    assert response["action"] == "clarify"
    assert "관계만 확인" in response["assistant"]
    assert "보관" in response["assistant"]
    facts = app.extensions["request_state_store"].read_deferred_input_facts(request_id)
    assert len(facts) == 1
    assert facts[0]["value"] == "흡입 그릴 변경"


def test_form_version_change_invalidates_pending_clarification_candidates(monkeypatch):
    def decider(_context, _contract):
        return _decision(
            "clarify",
            "프로젝트명만 확인해 주세요.",
            [{"op": "set", "path": "analysis_overview.project_name", "value": "OLD"}],
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider, locked=True)
    response = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "프로젝트명 OLD가 맞는지 확인이 필요해."},
    )
    assert response.status_code == 200
    assert app.extensions["conversation_store"].read(conversation_id).pending_write_candidates

    latest = app.extensions["request_state_store"].read(request_id)
    edited = deepcopy(latest.state)
    edited["analysis_overview"]["project_name"] = {"value": "NEW", "source": "user"}
    replaced = client.put(
        f"/api/request/versioned/{request_id}",
        json={"expected_version": latest.version, "state": edited},
    )
    assert replaced.status_code == 200
    assert app.extensions["conversation_store"].read(conversation_id).pending_write_candidates == []


def test_second_conversation_reuses_request_pending_proposal_instead_of_creating_another(monkeypatch):
    def decider(context, _contract):
        value = "FIRST" if "첫" in context["current_message"] else "SECOND"
        return _decision(
            "propose",
            "프로젝트명 변경을 제안합니다.",
            [{"op": "set", "path": "analysis_overview.project_name", "value": value}],
        )

    app, client, request_id, conversation_a = _runtime(monkeypatch, decider, locked=True)
    conversation_b = client.post("/api/conversations", json={"request_id": request_id}).get_json()["conversation_id"]
    first = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_a, "message": "첫 번째 변경"},
    ).get_json()
    second = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_b, "message": "두 번째 변경"},
    ).get_json()

    assert first["proposal"]["status"] == "pending"
    assert second["kind"] == "pending_proposal_wait"
    assert second["pending_proposal_id"] == first["proposal"]["proposal_id"]
    assert "먼저 반영하거나 반영하지 않음으로 결정" in second["assistant"]
    assert app.extensions["proposal_service"].proposal_count() == 1
    pending = app.extensions["proposal_service"].pending_proposal_for_request(request_id)
    assert pending is not None and pending.proposal_id == first["proposal"]["proposal_id"]


def test_deferred_heat_exchanger_catalog_message_is_preserved_without_followup_proposal(monkeypatch):
    catalog_message = "현재 등록된 열교환기 Catalog에서 해당 조합을 찾을 수 없습니다."

    def validate_catalog(_state, operations):
        touched = any(
            operation.get("op") == "set_condition_field"
            and operation.get("field_key") in {"tube_diameter", "fin_type", "row_count", "fpi"}
            for operation in operations
        )
        return {"valid": not touched, "message": catalog_message if touched else ""}

    monkeypatch.setattr(app_module, "validate_heat_exchanger_proposal", validate_catalog)

    def decider(_context, _contract):
        facts = [
            {
                "kind": "condition_field",
                "target": {"card_type": "heat_exchanger"},
                "field_key": field_key,
                "value": value,
                "source_summary": f"열교환기 {field_key} {value}",
            }
            for field_key, value in (
                ("tube_diameter", "9.99"),
                ("fin_type", "TEST-FIN"),
                ("row_count", "99"),
                ("fpi", "99"),
            )
        ]
        return _decision(
            "propose",
            "Context 확정을 제안합니다.",
            [
                {
                    "op": "confirm_request_context",
                    "context": {
                "taxonomy_id": "PTX-ADA7A057CA62",
                        "analysis_type": "이슬맺힘",
                    },
                }
            ],
            deferred_facts=facts,
        )

    app, client, request_id, conversation_id = _runtime(monkeypatch, decider)
    first = client.post(
        "/api/chat/send",
        json={"conversation_id": conversation_id, "message": "Context와 열교환기 사양을 함께 입력"},
    ).get_json()
    before_approval = app.extensions["request_state_store"].read(request_id)

    approved = _approve(client, first["proposal"]["proposal_id"])
    latest = app.extensions["request_state_store"].read(request_id)

    assert approved["assistant"] == catalog_message
    assert "proposal" not in approved
    assert "next_question" in approved
    assert latest.version == before_approval.version + 1
    heat_exchanger = next(
        card for card in latest.state["conditions"]["condition_sets"] if card["type"] == "heat_exchanger"
    )
    assert all(not heat_exchanger["fields"][key]["value"] for key in ("tube_diameter", "fin_type", "row_count", "fpi"))
    assert len(app.extensions["request_state_store"].read_deferred_input_facts(request_id)) == 4
    assert app.extensions["proposal_service"].proposal_count() == 1
    assert app.extensions["proposal_service"].pending_proposal_for_request(request_id) is None
