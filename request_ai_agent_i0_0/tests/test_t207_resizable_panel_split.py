from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def test_desktop_panels_default_to_reference_image_ratio_without_changing_total_layout_width():
    assert "grid-template-columns:minmax(0,2.285fr) 16px minmax(0,1fr)" in HTML_TEMPLATE
    assert 'grid-template-areas:"workspace-bar workspace-bar workspace-bar" "workspace-content panel-resizer agent"' in HTML_TEMPLATE


def test_panel_separator_supports_pointer_drag_between_one_to_one_and_three_to_one():
    assert 'id="panelResizer" role="separator"' in HTML_TEMPLATE
    assert 'aria-valuemin="1" aria-valuenow="2.29" aria-valuemax="3"' in HTML_TEMPLATE
    assert "function initPanelResizer()" in HTML_TEMPLATE
    assert "Math.min(drag.totalWidth * .75, Math.max(drag.totalWidth * .5" in HTML_TEMPLATE
    assert "setPanelRatio(nextLeft / (drag.totalWidth - nextLeft))" in HTML_TEMPLATE
    assert "layout.style.gridTemplateColumns = `minmax(0,${clamped}fr) 16px minmax(0,1fr)`" in HTML_TEMPLATE


def test_resizer_hit_area_overlaps_both_panel_edges():
    assert "justify-self:center;width:20px;min-width:20px;height:100%;margin:0 -4px" in HTML_TEMPLATE
    assert "cursor:col-resize;touch-action:none;user-select:none" in HTML_TEMPLATE


def test_resizer_stays_out_of_overlay_and_hidden_agent_layouts():
    assert ".panel-resizer{display:none}" in HTML_TEMPLATE
    assert ".layout.agent-hidden .panel-resizer{display:none}" in HTML_TEMPLATE
    assert "if (event.button !== 0 || isAgentOverlay() || !agentOpen) return" in HTML_TEMPLATE


def test_agent_hide_expands_workspace_and_reopen_restores_default_ratio():
    assert '.layout.agent-hidden{grid-template-columns:minmax(0,1fr);grid-template-areas:"workspace-bar" "workspace-content"}' in HTML_TEMPLATE
    assert 'document.querySelector(".layout")?.style.removeProperty("grid-template-columns")' in HTML_TEMPLATE
    assert '$("panelResizer")?.setAttribute("aria-valuenow", "2.29")' in HTML_TEMPLATE
    set_agent_open = HTML_TEMPLATE[HTML_TEMPLATE.index("function setAgentOpen"):HTML_TEMPLATE.index("function syncChatMetadata")]
    assert "agentOpen = nextOpen;\n      resetPanelRatio();\n      renderAgentDock();" in set_agent_open
