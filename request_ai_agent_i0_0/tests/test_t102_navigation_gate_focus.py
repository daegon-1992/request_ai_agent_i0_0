from __future__ import annotations

from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def test_six_screen_navigation_has_gate_focus_and_screen_six_for_review():
    assert 'const screenOrder = [' in HTML_TEMPLATE
    assert 'function navigateScreen(screenId, options={})' in HTML_TEMPLATE
    assert 'function renderScreenNavigation()' in HTML_TEMPLATE
    assert 'function focusScreenHeading(screen)' in HTML_TEMPLATE
    assert 'aria-current' in HTML_TEMPLATE
    assert HTML_TEMPLATE.count('id="previewSlotBtn"') == 0
    assert 'data-screen="SCREEN-06"' in HTML_TEMPLATE


def test_navigation_blocks_incomplete_required_inputs_without_collecting_or_refreshing_state():
    start = HTML_TEMPLATE.index('function navigateScreen(screenId, options={})')
    end = HTML_TEMPLATE.index('function valuesFromRows(selector)', start)
    navigation = HTML_TEMPLATE[start:end]
    assert 'screen.requiresContext && !isContextLocked()' in navigation
    assert 'screen.id !== "SCREEN-06"' in navigation
    assert 'targetIndex > currentIndex' in navigation
    assert 'focusRequiredControl(first.screen, first.control)' in navigation
    assert 'SCREEN-01' in navigation
    assert 'collectState(' not in navigation
    assert 'refreshPreview(' not in navigation
    assert 'postState(' not in navigation


def test_navigation_locks_only_steps_after_the_first_incomplete_screen():
    start = HTML_TEMPLATE.index('function renderScreenNavigation()')
    end = HTML_TEMPLATE.index('function focusScreenHeading(screen)', start)
    navigation = HTML_TEMPLATE[start:end]

    assert 'const firstIncomplete = firstIncompleteScreenBefore(reviewScreen)' in navigation
    assert 'screenIndex > firstIncompleteIndex' in navigation
    assert '!!screen?.requiresContext' in navigation
    assert '{id:"SCREEN-06", headingId:"screen06Heading", tab:"preview", requiresContext:false}' in HTML_TEMPLATE
    assert 'renderScreenNavigation();\n      orchestratorPanelState.dirty = true;' in HTML_TEMPLATE


def test_screen_six_remains_clickable_even_when_earlier_required_inputs_are_incomplete():
    start = HTML_TEMPLATE.index('function navigateScreen(screenId, options={})')
    end = HTML_TEMPLATE.index('function valuesFromRows(selector)', start)
    navigation = HTML_TEMPLATE[start:end]

    assert 'screen.id !== "SCREEN-06"' in navigation
    assert '{id:"SCREEN-06", headingId:"screen06Heading", tab:"preview", requiresContext:false}' in HTML_TEMPLATE


def test_navigation_required_gate_lists_each_screen_and_focuses_first_missing_control():
    assert 'function missingRequiredControl(screenId)' in HTML_TEMPLATE
    assert 'function blockingScreenError(screenId)' in HTML_TEMPLATE
    assert 'function firstIncompleteScreenBefore(targetScreen)' in HTML_TEMPLATE
    for screen_id in ("SCREEN-01", "SCREEN-02", "SCREEN-03", "SCREEN-04", "SCREEN-05"):
        assert f'screenId === "{screen_id}"' in HTML_TEMPLATE
    assert 'target?.focus?.({preventScroll:true});' in HTML_TEMPLATE
    assert 'missingRequiredControl(screen.id) || blockingScreenError(screen.id)' in HTML_TEMPLATE
    assert 'screenId === "SCREEN-03" && geometryDrawingDuplicateIssues().length' in HTML_TEMPLATE
    assert 'screenId === "SCREEN-05" && caseConfigurationIssues().length' in HTML_TEMPLATE
    assert '의 오류를 수정한 뒤 다음 단계로 이동할 수 있습니다.' in HTML_TEMPLATE


def test_screen_navigation_marks_current_screen_and_supports_keyboard_activation():
    assert '.screen-map-item[data-screen]' in HTML_TEMPLATE
    assert 'item.setAttribute("aria-current", screen?.id === active.id ? "page" : "false")' in HTML_TEMPLATE
    assert 'event.key !== "Enter" && event.key !== " "' in HTML_TEMPLATE


def test_submission_is_disabled_and_guarded_while_required_inputs_are_incomplete():
    assert 'submitButton.disabled = submissionCompleted || submissionInProgress || firstIncompleteIndex >= 0' in HTML_TEMPLATE
    assert '필수 입력을 완료하면 제출할 수 있습니다.' in HTML_TEMPLATE
    submit_start = HTML_TEMPLATE.index('function showFinalSubmitModal()')
    submit_end = HTML_TEMPLATE.index('function hideFinalSubmitModal', submit_start)
    submit_action = HTML_TEMPLATE[submit_start:submit_end]
    assert 'const firstIncomplete = firstIncompleteScreenBefore(reviewScreen)' in submit_action
    assert 'focusRequiredControl(firstIncomplete.screen, firstIncomplete.control)' in submit_action
    assert 'return false;' in submit_action
