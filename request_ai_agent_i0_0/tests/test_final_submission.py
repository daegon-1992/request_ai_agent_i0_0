from __future__ import annotations

from copy import deepcopy
import importlib

from request_ai_agent_i0_0 import create_app
from request_ai_agent_i0_0.state import create_initial_state
from request_ai_agent_i0_0.submission_service import DuplicateSubmissionError
from request_ai_agent_i0_0.ui import HTML_TEMPLATE


app_module = importlib.import_module("request_ai_agent_i0_0.app")


def _validated_state(*, can_submit: bool) -> dict[str, object]:
    state = create_initial_state()
    state["metadata"]["request_no"] = "REQ-2026-000001"
    blocking = [] if can_submit else [{"code": "basic_info.requester_name.missing", "message": "요청자 이름이 필요합니다."}]
    state["review"]["validator"] = {
        "summary": {"can_submit": can_submit},
        "blocking": blocking,
        "warning": [],
    }
    return state


def test_submit_requires_json_boolean_true_before_any_db_write(monkeypatch):
    called = []
    monkeypatch.setattr(app_module, "save_initial_submission", lambda **kwargs: called.append(kwargs))
    client = create_app().test_client()

    missing = client.post("/api/submit", json={"state": _validated_state(can_submit=True)})
    truthy_integer = client.post(
        "/api/submit",
        json={"state": _validated_state(can_submit=True), "submission_consent": 1},
    )

    assert missing.status_code == 400
    assert missing.get_json()["error"] == "submission_consent_required"
    assert truthy_integer.status_code == 400
    assert called == []


def test_submit_returns_422_without_db_write_when_validation_blocks(monkeypatch):
    state = _validated_state(can_submit=False)
    monkeypatch.setattr(app_module, "state_with_validation", lambda _state: deepcopy(state))
    monkeypatch.setattr(
        app_module,
        "save_initial_submission",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("blocked submission must not write")),
    )

    response = create_app().test_client().post(
        "/api/submit",
        json={"state": state, "submission_consent": True},
    )

    assert response.status_code == 422
    payload = response.get_json()
    assert payload["error"] == "submission_validation_failed"
    assert payload["state_changed"] is False
    assert payload["blocking"][0]["code"] == "basic_info.requester_name.missing"


def test_submit_persists_consent_metadata_and_returns_saved_ids(monkeypatch):
    state = _validated_state(can_submit=True)
    captured = {}

    def save_submission(**kwargs):
        captured.update(kwargs)
        return {
            "request_id": 11,
            "request_no": "REQ-2026-000001",
            "revision_id": 12,
            "revision_no": 0,
            "workflow_event_id": 13,
            "condition_instance_count": 4,
            "condition_value_count": 10,
            "status": "SUBMITTED",
        }

    monkeypatch.setattr(app_module, "state_with_validation", lambda _state: deepcopy(state))
    monkeypatch.setattr(app_module, "_submission_user_id", lambda: 7)
    monkeypatch.setattr(app_module, "save_initial_submission", save_submission)

    response = create_app().test_client().post(
        "/api/submit",
        json={"state": state, "submission_consent": True},
    )

    assert response.status_code == 200
    payload = response.get_json()
    consent = captured["state"]["metadata"]["submission_consent"]
    assert captured["submitted_by_user_id"] == 7
    assert consent["accepted"] is True
    assert consent["submitted_by_user_id"] == 7
    assert consent["statement"] == app_module.SUBMISSION_CONSENT_STATEMENT
    assert consent["accepted_at"].endswith("+00:00")
    assert payload["submission_result"]["request_id"] == 11
    assert payload["submission"]["status"] == "SUBMITTED"
    assert payload["state_changed"] is True


def test_submit_maps_duplicate_request_number_to_409(monkeypatch):
    state = _validated_state(can_submit=True)
    monkeypatch.setattr(app_module, "state_with_validation", lambda _state: deepcopy(state))
    monkeypatch.setattr(app_module, "_submission_user_id", lambda: 7)
    monkeypatch.setattr(
        app_module,
        "save_initial_submission",
        lambda **_kwargs: (_ for _ in ()).throw(DuplicateSubmissionError("duplicate")),
    )

    response = create_app().test_client().post(
        "/api/submit",
        json={"state": state, "submission_consent": True},
    )

    assert response.status_code == 409
    assert response.get_json()["error"] == "duplicate_submission"


def test_word_export_stays_disabled_by_default():
    response = create_app().test_client().post("/api/export/word", json={})

    assert response.status_code == 403
    assert response.get_json()["feature"] == "word_export"


def test_final_submit_modal_requires_consent_and_blocks_repeat_actions():
    assert 'id="finalSubmitBtn" type="button">제출</button>' in HTML_TEMPLATE
    assert "해석 의뢰를 최종 제출하시겠습니까?" in HTML_TEMPLATE
    assert "현재 입력한 의뢰 내용으로 해석을 진행하는 것에 동의합니다." in HTML_TEMPLATE
    assert 'id="finalSubmitConfirm" type="button" disabled' in HTML_TEMPLATE
    assert 'submission_consent: true' in HTML_TEMPLATE
    assert "if (submissionInProgress || submissionCompleted || consent?.checked !== true) return false;" in HTML_TEMPLATE
    assert 'if (cancel) cancel.disabled = true;' in HTML_TEMPLATE
    assert 'if (event.key === "Escape")' in HTML_TEMPLATE
    assert "hideFinalSubmitModal();" in HTML_TEMPLATE
    assert 'submitButton.textContent = submissionCompleted ? "제출 완료" : "제출";' in HTML_TEMPLATE
