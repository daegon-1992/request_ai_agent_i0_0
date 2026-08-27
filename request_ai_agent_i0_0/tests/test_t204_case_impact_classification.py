from pathlib import Path


UI_PATH = Path(__file__).resolve().parents[1] / "ui.py"


def test_t204_case_impact_hook_is_client_side_and_preserves_case_rows():
    ui = UI_PATH.read_text(encoding="utf-8")

    assert 'const CASE_REVIEW_REQUIRED = "CASE_REVIEW_REQUIRED";' in ui
    assert 'const CASE_REBUILD_REQUIRED = "CASE_REBUILD_REQUIRED";' in ui
    assert "function classifyCaseImpact(state)" in ui
    assert "function resetCaseImpactBaseline()" in ui
    assert "data-case-impact-status" in ui
    assert "classifyCaseImpact(collectState());" in ui
    assert "previewRefreshTimer = window.setTimeout(() => {" in ui
    assert "refreshPreview(scheduledRevision);" in ui
    assert "Case 행은 자동으로 변경하지 않았습니다." in ui
    assert "새 소스가 추가되었거나 비참조 소스가 변경되었습니다. Case 행을 검토해 주세요." not in ui
    assert "if (caseImpactSideState.status === CASE_REBUILD_REQUIRED)" in ui


def test_t204_classifies_added_and_referenced_source_changes():
    ui = UI_PATH.read_text(encoding="utf-8")

    assert 'reviewReasons.push(`geometry:${id}:added`)' in ui
    assert 'rebuildReasons.push(`geometry:${id}:required_value_invalid`)' in ui
    assert 'rebuildReasons.push(`condition:${key}:required_value_invalid`)' in ui
    assert 'status:CASE_REBUILD_REQUIRED' in ui
    assert 'status:CASE_REVIEW_REQUIRED' in ui


def test_case_configuration_confirmation_revalidates_before_entering_preview():
    ui = UI_PATH.read_text(encoding="utf-8")

    assert '이전: 요청 내용' in ui
    assert '다음: 해석 조건' in ui
    assert '이전: 해석 제품' in ui
    assert '다음: Case Matrix' in ui
    assert 'id="caseConfirmNextBtn"' in ui
    assert 'function confirmCaseConfiguration()' in ui
    assert 'await refreshPreview();' in ui
    assert 'resetCaseImpactBaseline();' in ui
    assert 'const blockingIssues = caseConfigurationIssues();' in ui
    assert 'focusCaseValidationIssue(blockingIssues[0]);' in ui
    assert 'navigateScreen("SCREEN-06");' in ui
    assert 'function caseConfigurationMessageHtml(issues, state=requestState, includeReviewAction=false)' in ui
    assert '오류 · Case 구성을 확인해 주세요.' in ui
    assert 'case_matrix.duplicate' in ui


def test_case_matrix_dropdown_changes_refresh_validator_feedback_without_rebuilding_active_select():
    ui = UI_PATH.read_text(encoding="utf-8")
    preserve_start = ui.index("function preserveCaseSelections()")
    preserve_end = ui.index("function collectState()", preserve_start)
    preserve = ui[preserve_start:preserve_end]

    assert '!event.target.matches("select[data-case-field]")' in ui
    assert 'if (event.target.matches("select[data-case-field]")) preserveCaseSelections();' in ui
    assert 'const activeCaseSelect = document.activeElement?.matches?.("select[data-case-field]");' in ui
    assert 'if (!activeCaseSelect) $("caseMatrix").innerHTML' in ui
    assert 'lastCaseDeleteNoticeVisible = false;' in preserve
    assert 'schedulePreviewRefresh();' in preserve
    assert 'else if (event.target.matches("select[data-case-field]")) refreshPreview();' not in ui
