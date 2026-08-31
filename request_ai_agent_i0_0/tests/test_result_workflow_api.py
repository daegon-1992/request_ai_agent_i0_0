from __future__ import annotations

import importlib

from request_ai_agent_i0_0 import create_app


app_module = importlib.import_module("request_ai_agent_i0_0.app")


def _client():
    return create_app().test_client()


def test_result_api_requires_analyst_and_summary(monkeypatch):
    monkeypatch.setattr(app_module, "save_result", lambda **_: (_ for _ in ()).throw(AssertionError("must not call service")))
    client = _client()
    missing_analyst = client.post(
        "/api/requests/REQ-001/result",
        json={"result_summary": "결과"},
    )
    missing_summary = client.post(
        "/api/requests/REQ-001/result",
        json={"analyst_user_code": "USER003"},
    )
    assert missing_analyst.status_code == 400
    assert missing_analyst.get_json()["error"] == "analyst_required"
    assert missing_summary.status_code == 400
    assert missing_summary.get_json()["error"] == "result_summary_required"


def test_result_api_dispatches_result_registration(monkeypatch):
    called = []
    monkeypatch.setattr(
        app_module,
        "save_result",
        lambda **kwargs: called.append(kwargs) or {
            "request_id": 1,
            "request_no": "REQ-001",
            "revision_id": 10,
            "revision_no": 1,
            "result_id": 20,
            "workflow_event_id": 30,
            "analyst_user_id": 3,
            "analyst_user_code": "USER003",
            "status": "RESULT_REVIEW",
        },
    )
    response = _client().post(
        "/api/requests/REQ-001/result",
        json={
            "analyst_user_code": "USER003",
            "result_summary": "유속 편차가 개선되었습니다.",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "RESULT_REVIEW"
    assert called == [{
        "request_no": "REQ-001",
        "analyst_user_code": "USER003",
        "result_summary": "유속 편차가 개선되었습니다.",
    }]


def test_result_api_maps_result_errors(monkeypatch):
    cases = [
        (app_module.ResultSummaryRequiredError(), 400, "result_summary_required"),
        (app_module.ResultPermissionError(), 403, "result_forbidden"),
        (app_module.AssignedAnalystMismatchError(), 403, "analyst_not_assigned"),
        (app_module.InvalidResultStateError(), 409, "result_not_allowed"),
        (app_module.ResultRequestNotFoundError(), 404, "result_request_not_found"),
    ]
    for error, expected_status, expected_code in cases:
        def fail(**_kwargs):
            raise error
        monkeypatch.setattr(app_module, "save_result", fail)
        response = _client().post(
            "/api/requests/REQ-001/result",
            json={"analyst_user_code": "USER003", "result_summary": "결과"},
        )
        assert response.status_code == expected_status
        assert response.get_json()["error"] == expected_code


def test_completion_api_dispatches_requester_completion(monkeypatch):
    monkeypatch.setattr(app_module, "_requester_user_code", lambda: "USER001")
    called = []
    monkeypatch.setattr(
        app_module,
        "save_completion",
        lambda **kwargs: called.append(kwargs) or {
            "request_id": 1,
            "request_no": "REQ-001",
            "revision_id": 10,
            "revision_no": 1,
            "result_id": 20,
            "workflow_event_id": 30,
            "requester_user_id": 1,
            "status": "COMPLETED",
        },
    )
    response = _client().post(
        "/api/requests/REQ-001/complete",
        json={"comment": "결과 확인했습니다."},
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "COMPLETED"
    assert called == [{
        "request_no": "REQ-001",
        "requester_user_code": "USER001",
        "comment": "결과 확인했습니다.",
    }]


def test_completion_api_maps_errors(monkeypatch):
    cases = [
        (app_module.ResultPermissionError(), 403, "completion_forbidden"),
        (app_module.InvalidResultStateError(), 409, "completion_not_allowed"),
        (app_module.ResultRequestNotFoundError(), 404, "completion_request_not_found"),
    ]
    monkeypatch.setattr(app_module, "_requester_user_code", lambda: "USER001")
    for error, expected_status, expected_code in cases:
        def fail(**_kwargs):
            raise error
        monkeypatch.setattr(app_module, "save_completion", fail)
        response = _client().post(
            "/api/requests/REQ-001/complete",
            json={},
        )
        assert response.status_code == expected_status
        assert response.get_json()["error"] == expected_code
