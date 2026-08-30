from __future__ import annotations

import pytest

import request_ai_agent_i0_0.app as app_module
from request_ai_agent_i0_0.app import (
    STAGE_WRITING_GUIDES,
    _field_help_answer,
    _missing_items_answer,
    _stage_key_from_writing_question,
    _stage_progress,
)
from request_ai_agent_i0_0.schema import ANALYSIS_OVERVIEW_SPECS, BASIC_INFO_SPECS, get_public_schema
from request_ai_agent_i0_0.state import normalize_state
from request_ai_agent_i0_0.ui import HTML_TEMPLATE
from request_ai_agent_i0_0.validator import validate_state


REQUEST_DETAIL_PATHS = {
    "analysis_overview.request_description",
    "analysis_overview.additional_result_request",
}


def _request_detail_issue_paths(state: dict) -> set[str]:
    validation = validate_state(state)
    return {
        item["path"]
        for item in validation["blocking"]
        if item.get("path") in REQUEST_DETAIL_PATHS
    }


def test_two_request_detail_fields_are_required_and_drive_stage_progress():
    empty = normalize_state({})
    assert _request_detail_issue_paths(empty) == REQUEST_DETAIL_PATHS

    completed = normalize_state({"analysis_overview": {
        "request_description": "토출부 이슬맺힘이 반복되어 원인 확인이 필요합니다.",
        "additional_result_request": "발생 원인과 개선안별 차이를 확인하고 싶습니다.",
    }})
    assert not _request_detail_issue_paths(completed)
    assert _stage_progress(completed)["stages"]["analysis_overview"]["is_complete"] is True
    assert _stage_progress(completed)["stages"]["geometry"]["label"] == "해석 제품"


@pytest.mark.parametrize(
    "question",
    [
        "해석 제품은 어떻게 작성해?",
        "총 조립 형상 작성법을 알려줘.",
        "총조립도는 어떻게 입력하나요?",
        "형상/모델 정보는 어떻게 작성해?",
    ],
)
def test_geometry_writing_guide_recognizes_current_and_legacy_terms(question):
    assert _stage_key_from_writing_question(question) == "geometry"


def test_geometry_writing_guide_and_field_help_use_current_screen_contract():
    guide = STAGE_WRITING_GUIDES["geometry"]

    assert guide == {
        "description": "해석 제품은 해석에 사용할 총 조립 형상과 비교 제품의 Base 대비 변경점을 입력하는 단계입니다.",
        "examples": [
            ("Base 제품 · 총조립도 도면번호 (NPDM MCAD)", "예: AJT000123 또는 TEMP-BASE-01"),
            ("비교 제품 · 총조립도 도면번호 (NPDM MCAD)", "예: AJT000234 또는 TEMP-COMP-01"),
            ("비교 제품 · Base 대비 변경점", "예: 베인 각도 30° 적용, Fan 위치 상향 20 mm"),
        ],
    }
    assert "기존 부품(Base)" not in str(guide)
    assert "변경 부품(Variant)" not in str(guide)
    assert _field_help_answer("해석 제품이 뭐야?") == (
        "해석 제품은 CFD에 사용할 총 조립 형상을 의미합니다. Base 제품의 총조립도 도면번호를 입력하고, "
        "비교 제품이 있으면 변경 사항이 반영된 별도 총조립도 도면번호와 Base 대비 변경점을 입력합니다."
    )
    assert _field_help_answer("변경 부품은 뭐야?") == (
        "현재 해석 제품 화면에서는 변경 부품을 별도 부품 항목으로 입력하지 않습니다. "
        "비교 제품의 변경 사항이 반영된 총 조립 형상과 Base 대비 변경점을 입력합니다."
    )
    assert _field_help_answer("Case Matrix가 뭐야?") == (
        "Case Matrix는 해석 제품과 해석 조건을 선택해 실제 계산할 Case를 구성하는 표입니다. "
        "각 Case에서 사용할 해석 제품과 조건을 직접 매핑합니다."
    )


def test_geometry_completion_message_and_public_schema_use_current_label(monkeypatch):
    monkeypatch.setattr(app_module, "_derive_state", lambda state: state)
    monkeypatch.setattr(app_module, "_stage_progress", lambda state: {"all_complete": True})

    assert _missing_items_answer({}) == (
        "현재 요청 내용, 해석 제품, 해석 조건, Case Matrix의 필요한 항목이 모두 채워졌습니다. "
        "전체 확인·최종 제출에서 최종 내용을 확인해 주세요."
    )
    geometry = next(section for section in get_public_schema()["sections"] if section["key"] == "geometry")
    assert geometry["label"] == "해석 제품"


def test_canonical_request_content_ui_has_only_the_two_requested_fields():
    start = HTML_TEMPLATE.index('id="section-overview"')
    end = HTML_TEMPLATE.index('</section>', start)
    section = HTML_TEMPLATE[start:end]

    assert section.count('<textarea') == 2
    assert '해석을 요청하게 된 배경' in section
    assert '해석으로 확인하고 싶은 내용' in section
    assert '결과 활용 목적' not in section
    assert '해석 결과 안내' not in section
    assert 'navigateScreen("SCREEN-02");' in HTML_TEMPLATE
    assert 'id="nextRequestContentBtn"' in HTML_TEMPLATE
    assert 'overflow-x:hidden;overflow-y:auto;' in HTML_TEMPLATE
    assert '.workspace{min-height:0;overflow:visible;padding:12px}' in HTML_TEMPLATE
    assert '.workspace-content{grid-area:workspace-content;min-width:0;min-height:0;display:grid;grid-template-rows:auto auto;gap:10px;overflow:visible}' in HTML_TEMPLATE
    assert '.workspace-shell .main{overflow:visible}' in HTML_TEMPLATE
    assert '.chat-log{min-height:0;overflow:auto;padding:12px;background:var(--soft)}' in HTML_TEMPLATE
    assert 'max-width:1120px;' in HTML_TEMPLATE


def test_screen_two_required_policy_matches_the_two_request_detail_fields():
    assert {spec.key for spec in BASIC_INFO_SPECS if spec.required} >= {
        "division", "department", "requester_name", "requester_role",
    }
    assert {spec.key for spec in ANALYSIS_OVERVIEW_SPECS if spec.required} >= {
        "project_name", "development_grade", "npi_stage", "model_suffix", "request_date",
        "desired_completion_date", "request_description", "additional_result_request",
    }
    assert "decision_use" not in {spec.key for spec in ANALYSIS_OVERVIEW_SPECS if spec.required}
    assert 'if (activeScreen === "SCREEN-02" && screen.id === "SCREEN-03")' not in HTML_TEMPLATE
    assert 'position:static;display:flex' in HTML_TEMPLATE
    assert 'class="request-detail-grid"' in HTML_TEMPLATE


def test_later_screen_navigation_gate_checks_both_request_detail_fields():
    start = HTML_TEMPLATE.index('if (screenId === "SCREEN-02")')
    end = HTML_TEMPLATE.index('if (screenId === "SCREEN-03")', start)
    gate = HTML_TEMPLATE[start:end]

    assert '"analysis_overview.request_description", "analysis_overview.additional_result_request"' in gate
    assert 'return paths.map(requiredPathControl).find(control => !contextText(control?.value)) || null;' in gate
    assert 'const first = firstIncompleteScreenBefore(screen);' in HTML_TEMPLATE
    assert 'focusRequiredControl(first.screen, first.control);' in HTML_TEMPLATE
