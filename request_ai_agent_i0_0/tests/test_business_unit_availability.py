from __future__ import annotations

from request_ai_agent_i0_0.product_hierarchy import build_product_hierarchy_payload
from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def test_air_care_and_chiller_are_active_in_taxonomy_payload():
    payload = build_product_hierarchy_payload()

    assert [item["label"] for item in payload["divisions"]] == ["SAC", "RAC", "Air Care", "Chiller"]
    assert payload["division_counts"]["Air Care"] == 23
    assert payload["division_counts"]["Chiller"] == 2


def test_both_selection_modes_show_all_divisions_without_disabled_products():
    assert 'const defaultDivisions = ["SAC","RAC","Air Care","Chiller"];' in HTML_TEMPLATE
    assert 'renderPrepChoices("prepDivisionChoices", "division", divisions, context.division);' in HTML_TEMPLATE
    assert 'renderPrepSelect("quickDivisionSelect", divisions, context.division, "Division 선택");' in HTML_TEMPLATE
    assert "defaultDisabledBusinessUnits" not in HTML_TEMPLATE
