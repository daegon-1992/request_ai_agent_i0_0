from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def _preview_renderer() -> str:
    return HTML_TEMPLATE.split("function renderDocumentPreviewPanel", 1)[1].split(
        "function renderCandidateNotice", 1
    )[0]


def test_preview_marks_missing_field_labels_with_a_red_warning_icon():
    preview = _preview_renderer()

    assert ".preview-missing-icon" in HTML_TEMPLATE
    assert "color:#c62828" in HTML_TEMPLATE
    assert 'data-preview-missing="${missing}"' in preview
    assert "previewFieldLabel(label, missing" in preview
    assert 'previewFieldLabel("도면번호 (NPDM MCAD)", productDrawingMissing)' in preview
    assert 'previewFieldLabel("팬 회전수(RPM)", fanDisplay.missing)' in preview


def test_submit_button_shows_required_input_warning_only_for_missing_required_input():
    navigation = HTML_TEMPLATE.split("function renderScreenNavigation", 1)[1].split(
        "function focusScreenHeading", 1
    )[0]

    assert 'id="wordExportRequiredWarning"' in HTML_TEMPLATE
    assert "필수 입력 누락" in HTML_TEMPLATE
    assert "wordRequiredWarning.hidden = firstIncompleteIndex < 0" in navigation
    assert (
        "submitButton.disabled = submissionCompleted || submissionInProgress || "
        "firstIncompleteIndex >= 0"
    ) in navigation


def test_screen_six_uses_canonical_preview_card_read_only_and_action_contracts():
    screen_start = HTML_TEMPLATE.index('class="workspace-form screen-group" data-screen="SCREEN-06"')
    screen_end = HTML_TEMPLATE.index('data-shell="AgentDock"', screen_start)
    screen = HTML_TEMPLATE[screen_start:screen_end]

    assert '<div class="section-title"><h3>의뢰서 미리보기</h3></div>' in screen
    assert 'class="section-title-icon"' not in screen
    assert 'class="title-icon"' in HTML_TEMPLATE[screen_end:]
    assert (
        '.workspace-shell .workspace-form[data-screen="SCREEN-06"] > #section-preview{'
        'margin-bottom:var(--request-workspace-card-section-gap);border:1px solid #DCDDDE;'
        'border-radius:10px;background:var(--paper);box-shadow:none;overflow:visible}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .workspace-form[data-screen="SCREEN-06"] > #section-preview '
        '> .section-head{min-height:0;padding:16px 16px 0;border-bottom:0;'
        'background:transparent}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .workspace-form[data-screen="SCREEN-06"] > #section-preview '
        '> .section-body{padding:16px;border-top:0}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .workspace-form[data-screen="SCREEN-06"] > #section-preview '
        '> .section-head h3{font-size:16px;font-weight:600;color:var(--ink)}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .workspace-form[data-screen="SCREEN-06"] .preview-table th{'
        'font-size:13px;font-weight:500;line-height:1.45}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .workspace-form[data-screen="SCREEN-06"] .preview-table td{'
        'font-size:14px;font-weight:400;line-height:1.45}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .workspace-form[data-screen="SCREEN-06"] #finalSubmitBtn{'
        'min-height:44px;padding:0 18px;border-radius:8px;font-size:15px;font-weight:600}'
    ) in HTML_TEMPLATE


def test_screen_six_keeps_missing_markers_inline_at_semantic_icon_size():
    assert (
        '.workspace-shell .workspace-form[data-screen="SCREEN-06"] '
        ':is(.preview-missing-icon,.preview-missing-icon svg){width:14px;height:14px}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .workspace-form[data-screen="SCREEN-06"] .preview-missing-icon{'
        'flex:0 0 14px;color:#C62828}'
    ) in HTML_TEMPLATE
    assert '<span class="preview-missing-icon" aria-hidden="true"><svg' in HTML_TEMPLATE
    assert 'word-export-required-warning' in HTML_TEMPLATE
