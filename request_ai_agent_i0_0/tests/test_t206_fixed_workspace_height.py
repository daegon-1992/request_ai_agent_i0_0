from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def test_desktop_workspace_uses_geometry_three_comparison_reference_height():
    assert "--stage-panel-reference-height:810px" in HTML_TEMPLATE
    assert "height:100%;max-height:calc(var(--stage-panel-reference-height) + 100px);min-height:0;" in HTML_TEMPLATE
    assert "body{display:grid;grid-template-rows:auto minmax(0,1fr) auto;overflow:hidden}" in HTML_TEMPLATE
    assert "minmax(908px,1fr)" not in HTML_TEMPLATE


def test_form_and_agent_keep_equal_height_with_independent_scroll_regions():
    assert ".workspace-content{height:100%;grid-template-rows:auto minmax(0,1fr);overflow:hidden}" in HTML_TEMPLATE
    assert ".workspace-shell .main{min-height:0;overflow:hidden}" in HTML_TEMPLATE
    assert ".workspace-shell .workspace{height:100%;min-height:0;overflow-y:auto;overscroll-behavior:contain}" in HTML_TEMPLATE
    assert ".agent-dock{height:100%;min-height:0}" in HTML_TEMPLATE
    assert ".chat-log{min-height:0;overflow-y:auto;overscroll-behavior:contain}" in HTML_TEMPLATE
    assert ".chat-input{position:relative;z-index:1}" in HTML_TEMPLATE


def test_existing_mobile_page_scroll_fallback_is_preserved():
    assert "@media (max-width:1039px)" in HTML_TEMPLATE
    assert "body{overflow:auto;overflow-x:hidden}" in HTML_TEMPLATE


def test_desktop_screen_one_uses_compact_workspace_spacing():
    assert '.workspace-shell .workspace{padding:10px 18px}' in HTML_TEMPLATE
    assert '.screen-group[data-screen="SCREEN-01"] > .screen-heading{margin-bottom:8px}' in HTML_TEMPLATE
    assert '.screen-group[data-screen="SCREEN-01"] .prep-body{padding-top:14px;gap:14px}' in HTML_TEMPLATE
