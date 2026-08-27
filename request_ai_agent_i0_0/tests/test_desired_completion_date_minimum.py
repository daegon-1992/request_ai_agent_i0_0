from __future__ import annotations

from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def test_desired_completion_date_starts_tomorrow_in_local_time():
    assert 'function configureDesiredCompletionDateMinimum()' in HTML_TEMPLATE
    assert 'new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)' in HTML_TEMPLATE
    assert 'input.min = localDateValue(' in HTML_TEMPLATE
    assert '희망 완료일은 내일부터 선택할 수 있습니다.' in HTML_TEMPLATE
    assert 'addEventListener("focus", configureDesiredCompletionDateMinimum)' in HTML_TEMPLATE


def test_out_of_range_desired_completion_date_blocks_next_screen():
    screen_two_gate_start = HTML_TEMPLATE.index('if (screenId === "SCREEN-02")')
    screen_two_gate_end = HTML_TEMPLATE.index('if (screenId === "SCREEN-03")', screen_two_gate_start)
    screen_two_gate = HTML_TEMPLATE[screen_two_gate_start:screen_two_gate_end]

    assert 'requiredPathControl("analysis_overview.desired_completion_date")' in screen_two_gate
    assert '!desiredCompletionDate.validity.valid' in screen_two_gate
    assert 'target.reportValidity?.()' in HTML_TEMPLATE
