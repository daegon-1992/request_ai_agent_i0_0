from __future__ import annotations

import re

from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def test_visual_foundation_uses_neutral_charcoal_tokens_without_gradients():
    for token in (
        "--ink:#202124",
        "--muted:#76797D",
        "--bg:#F8F8F8",
        "--paper:#FFFFFF",
        "--soft:#FAFAFA",
        "--line:#E0E1E2",
        "--line-strong:#D4D5D6",
        "--brand:#5A5A5A",
        "--brand-strong:#545454",
        "--accent:#545454",
        "--disabled-bg:#F2F2F2",
        "--disabled-text:#A8AAAC",
        "--shadow:0 3px 14px rgba(0,0,0,.05)",
        "--shadow-soft:0 1px 4px rgba(0,0,0,.035)",
        "--global-header-height:72px",
        "--request-workspace-shadow:var(--shadow)",
    ):
        assert token in HTML_TEMPLATE
    assert "#586f8c" not in HTML_TEMPLATE
    assert "--ui-" not in HTML_TEMPLATE
    assert "linear-gradient" not in HTML_TEMPLATE
    assert '*{box-sizing:border-box;font-weight:400}' not in HTML_TEMPLATE
    assert 'font-family:"Noto Sans KR","Malgun Gothic","Segoe UI",sans-serif' in HTML_TEMPLATE
    assert 'font-weight:650' not in HTML_TEMPLATE


def test_global_shell_has_spacious_header_separate_summary_surfaces_and_charcoal_navigation():
    assert "height:var(--global-header-height);padding:12px 24px" in HTML_TEMPLATE
    assert "min-height:calc(100vh - var(--global-header-height))" in HTML_TEMPLATE
    assert ".workspace-shell .workspace-title-summary," in HTML_TEMPLATE
    assert ".workspace-shell .workspace-number-block{" in HTML_TEMPLATE
    assert "grid-template-columns:minmax(0,2.285fr) minmax(280px,1fr)" in HTML_TEMPLATE
    assert "gap:16px;width:100%" in HTML_TEMPLATE
    assert "border:1px solid var(--line);border-radius:10px" in HTML_TEMPLATE
    assert '.workspace-shell .screen-map-item[aria-current="page"]{background:var(--brand-strong);color:#fff}' in HTML_TEMPLATE
    assert "grid-template-columns:minmax(0,2.285fr) 16px minmax(0,1fr)" in HTML_TEMPLATE


def test_workspace_and_agent_are_independent_white_work_surfaces():
    assert ".workspace-shell .main{" in HTML_TEMPLATE
    assert "border:1px solid var(--line);border-radius:12px;background:var(--paper);box-shadow:var(--shadow)" in HTML_TEMPLATE
    assert ".agent-dock{" in HTML_TEMPLATE
    assert ".chat-head{padding:16px 18px;border-bottom-color:var(--line-strong);background:#F7F7F7}" in HTML_TEMPLATE
    assert ".chat-log{padding:18px 16px 20px 12px;background:var(--paper)}" in HTML_TEMPLATE
    assert ".chat-input{padding:14px;border-top-color:var(--line);background:var(--paper)}" in HTML_TEMPLATE
    assert ".panel-resizer::before{width:1px;height:46px;background:#d4d5d5}" in HTML_TEMPLATE


def test_guided_workspace_shell_preserves_the_six_screen_map_and_existing_sections():
    expected_screens = (
        ("SCREEN-01", "의뢰 대상·시작", "requestPrepCard"),
        ("SCREEN-02", "요청 내용", "section-basic"),
        ("SCREEN-03", "해석 제품", "section-geometry"),
        ("SCREEN-04", "해석 조건", "section-conditions"),
        ("SCREEN-05", "Case Matrix", "section-case"),
        ("SCREEN-06", "전체 확인", "documentPreviewPanel"),
    )

    positions = []
    for screen, label, marker in expected_screens:
        assert screen in HTML_TEMPLATE
        assert label in HTML_TEMPLATE
        positions.append(HTML_TEMPLATE.index(f'id="{marker}"'))
    assert positions == sorted(positions)

    for wrapper in ("GlobalHeader", "WorkspaceBar", "StepNavigation", "MainWorkspace", "AgentDock", "GlobalFooter"):
        assert wrapper in HTML_TEMPLATE
    assert 'class="screen-map"' in HTML_TEMPLATE
    assert 'id="stageRail"' not in HTML_TEMPLATE
    assert 'id="chatLog"' in HTML_TEMPLATE
    assert 'id="chatInput"' in HTML_TEMPLATE
    assert "width:min(100%,1536px);padding:18px 22px 22px" in HTML_TEMPLATE
    assert 'class="app-footer"' in HTML_TEMPLATE


def test_user_facing_screen_text_uses_navigation_names_without_internal_ids():
    navigation = (
        ("SCREEN-01", "01", "의뢰 대상·시작"),
        ("SCREEN-02", "02", "요청 내용"),
        ("SCREEN-03", "03", "해석 제품"),
        ("SCREEN-04", "04", "해석 조건"),
        ("SCREEN-05", "05", "Case Matrix"),
        ("SCREEN-06", "06", "전체 확인·Preview·Word"),
    )

    for screen_id, number, label in navigation:
        assert f'data-screen="{screen_id}"' in HTML_TEMPLATE
        assert f'<span class="screen-map-number">{number}</span>' in HTML_TEMPLATE
        assert label in HTML_TEMPLATE

    headings = re.findall(r'<h2 class="screen-heading"[^>]*>(.*?)</h2>', HTML_TEMPLATE, re.DOTALL)
    assert headings and all("SCREEN-" not in heading for heading in headings)
    assert "function userScreenName(screenId)" in HTML_TEMPLATE
    assert "현재 화면: ${active.id}" not in HTML_TEMPLATE
    assert "SCREEN-06 전체 확인은 항상 열 수 있습니다." not in HTML_TEMPLATE


def test_word_cta_is_only_in_the_screen_six_preview_workspace():
    assert HTML_TEMPLATE.count('id="wordExportSlotBtn"') == 1
    screen_six_start = HTML_TEMPLATE.index('data-screen="SCREEN-06"')
    word_cta = HTML_TEMPLATE.index('id="wordExportSlotBtn"')
    assert word_cta > screen_six_start


def test_screen_one_guidance_preserves_copy_and_uses_subtle_emphasis():
    expected_copy = (
        "요청자 소속이 아니라, 해석 대상 제품을 기준으로 선택합니다."
        "제품 분류를 선택한 후 수행할 해석유형을 지정합니다."
    )
    guidance = re.search(
        r'<p class="prep-guidance">(?P<content>.*?)</p>',
        HTML_TEMPLATE,
        flags=re.DOTALL,
    )
    responsive = re.search(
        r"@media \(max-width:1180px\)\{(?P<content>.*?)\n\s*\}",
        HTML_TEMPLATE,
        flags=re.DOTALL,
    )

    assert '<h3 class="visually-hidden">해석 대상 제품 선택</h3>' in HTML_TEMPLATE
    assert 'class="prep-info-icon"' in HTML_TEMPLATE
    assert guidance is not None
    assert re.sub(r"<[^>]+>", "", guidance.group("content")) == expected_copy
    assert HTML_TEMPLATE.count('class="prep-guidance-emphasis"') == 3
    assert 'class="prep-guidance-line prep-guidance-next"' in guidance.group("content")
    assert "border:1px solid var(--line-strong)" in HTML_TEMPLATE
    assert "background:#F7F7F7" in HTML_TEMPLATE
    assert "border-left:2px solid var(--line)" not in HTML_TEMPLATE
    assert ".prep-guidance-line:first-child{color:var(--ink);font-size:15px;font-weight:600;line-height:1.55}" in HTML_TEMPLATE
    assert ".prep-guidance-next{margin-top:4px;color:#55585B;font-size:13px;font-weight:400;line-height:1.55}" in HTML_TEMPLATE
    assert ".prep-guidance-next .prep-guidance-emphasis{color:#55585B;font-weight:400}" in HTML_TEMPLATE
    assert ".prep-guidance-emphasis{color:var(--ink);font-weight:600}" in HTML_TEMPLATE
    assert responsive is not None
    assert ".prep-quick-groups" in responsive.group("content")
    assert "grid-template-columns:1fr" in responsive.group("content")
    assert ".prep-actions{justify-content:flex-start}" in responsive.group("content")


def test_screen_one_separates_product_analysis_groups_and_summary_values():
    screen = HTML_TEMPLATE.split('<section class="screen-group" data-screen="SCREEN-01"', 1)[1].split(
        '<section class="screen-group request-content-screen" data-screen="SCREEN-02"', 1
    )[0]
    render = HTML_TEMPLATE.split("function renderRequestPrepCard(){", 1)[1].split(
        "function renderContextChip(){", 1
    )[0]

    assert ">제품 분류</h4>" in screen
    assert ">해석 설정</h4>" in screen
    for control_id in (
        "quickDivisionSelect",
        "quickProductLineupSelect",
        "quickPlatformSelect",
        "quickChassisSelect",
        "quickAnalysisTypeSelect",
    ):
        assert f'id="{control_id}"' in screen

    assert "<strong>선택한 내용</strong>" in screen
    assert 'class="prep-summary-value product-summary"' in screen
    assert 'class="prep-summary-value analysis-summary"' in screen
    assert 'const productSummary = [' in render
    assert 'const analysisSummary = context.analysis_type || "미선택";' in render
    assert "<strong>선택한 내용</strong>" in render
    assert 'class="prep-summary-value product-summary"' in render
    assert 'class="prep-summary-value analysis-summary"' in render
    assert 'id="prepStartBtn"' in screen
    assert "선택을 확정하면 맞춤 입력항목이 준비됩니다." not in screen
    assert "모든 항목을 선택해야 시작할 수 있습니다." not in screen
    assert "grid-template-columns:minmax(0,3.2fr) minmax(220px,1fr)" in HTML_TEMPLATE
    assert "grid-template-columns:repeat(4,minmax(0,1fr));gap:12px" in HTML_TEMPLATE
    assert "min-height:46px;padding:10px 12px;font-size:14px" in HTML_TEMPLATE
    assert "grid-template-columns:140px minmax(0,1fr)" in HTML_TEMPLATE
    assert 'class="prep-summary-label"><svg' not in screen
    assert 'class="prep-summary-label"><svg' not in render
    assert ".prep-summary-value{padding-left:24px" in HTML_TEMPLATE
    assert ".prep-summary-actions .primary{min-width:164px;min-height:44px" in HTML_TEMPLATE
