from __future__ import annotations

from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def test_step_navigation_stays_in_the_main_workspace_and_keeps_all_six_labels():
    workspace_start = HTML_TEMPLATE.index('<div class="workspace-shell"')
    navigation_start = HTML_TEMPLATE.index('<nav class="step-navigation"', workspace_start)
    agent_start = HTML_TEMPLATE.index('<aside class="panel chat agent-dock"')

    assert navigation_start < agent_start
    for label in (
        "의뢰 대상·시작",
        "요청 내용",
        "해석 제품",
        "해석 조건",
        "Case Matrix",
        "전체 확인·Preview·Word",
    ):
        assert label in HTML_TEMPLATE


def test_step_navigation_uses_chevrons_and_preserves_desktop_and_overlay_width_rules():
    assert 'grid-template-columns:repeat(6,minmax(0,1fr))' in HTML_TEMPLATE
    assert 'clip-path:polygon(0 0,calc(100% - 18px) 0,100% 50%,calc(100% - 18px) 100%,0 100%)' in HTML_TEMPLATE
    assert 'clip-path:polygon(0 0,calc(100% - 18px) 0,100% 50%,calc(100% - 18px) 100%,0 100%,18px 50%)' in HTML_TEMPLATE
    assert 'clip-path:polygon(0 0,100% 0,100% 100%,0 100%,18px 50%)' in HTML_TEMPLATE
    assert '.workspace-shell .screen-map{gap:0}' in HTML_TEMPLATE
    assert '.workspace-shell .screen-map-item:not(:first-child){margin-left:-18px}' in HTML_TEMPLATE
    assert '.screen-map-item:nth-child(n+2):not(:last-child)::after{' in HTML_TEMPLATE
    assert 'content:"›"' in HTML_TEMPLATE
    assert '.workspace-shell .screen-map-item{background:var(--paper);color:var(--request-workspace-muted)}' in HTML_TEMPLATE
    assert '.screen-map-item[aria-current="page"]{background:var(--accent);color:#fff}' in HTML_TEMPLATE
    assert '@media (max-width:1039px)' in HTML_TEMPLATE
    assert 'position:fixed' in HTML_TEMPLATE


def test_locked_steps_keep_the_existing_surface_and_show_only_a_leading_lock_icon():
    navigation_start = HTML_TEMPLATE.index('<nav class="step-navigation"')
    navigation_end = HTML_TEMPLATE.index('</nav>', navigation_start)
    navigation = HTML_TEMPLATE[navigation_start:navigation_end]
    item_lines = {
        screen_id: next(line for line in navigation.splitlines() if f'data-screen="{screen_id}"' in line)
        for screen_id in ("SCREEN-01", "SCREEN-02", "SCREEN-03", "SCREEN-04", "SCREEN-05", "SCREEN-06")
    }

    for screen_id in ("SCREEN-02", "SCREEN-03", "SCREEN-04", "SCREEN-05"):
        assert 'class="screen-map-lock"' in item_lines[screen_id]
    for screen_id in ("SCREEN-01", "SCREEN-06"):
        assert 'class="screen-map-lock"' not in item_lines[screen_id]

    assert '.screen-map-item[aria-disabled="true"]{cursor:not-allowed}' in HTML_TEMPLATE
    assert '.screen-map-item[aria-disabled="true"] :is(.screen-map-number,.screen-map-label){color:var(--muted);opacity:.55}' in HTML_TEMPLATE
    assert '.screen-map-item[aria-disabled="true"] .screen-map-lock{display:grid}' in HTML_TEMPLATE


def test_requested_headings_omit_icons_while_agent_keeps_its_identity_icon():
    assert 'class="screen-heading title-with-icon" id="screen01Heading"' not in HTML_TEMPLATE
    assert 'class="screen-heading title-with-icon" id="screen02Heading"' not in HTML_TEMPLATE
    assert 'id="agentDockHeading" class="title-with-icon"' in HTML_TEMPLATE
    assert 'aria-hidden="true"><svg viewBox="0 0 24 24">' in HTML_TEMPLATE
