from __future__ import annotations

from copy import deepcopy
import subprocess

import pytest

from request_ai_agent_i0_0.chat_patch import apply_patch_operations
from request_ai_agent_i0_0.condition_fieldsets import (
    default_condition_sets,
    get_active_condition_fields,
    sanitize_condition_sets,
)
from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def _context() -> dict[str, object]:
    return {"analysis_type": "일반 유동 해석", "context_locked": True}


def _operating_card() -> dict[str, object]:
    return next(card for card in default_condition_sets(_context()) if card["type"] == "operating")


def _fans(*rows: tuple[str, str]) -> list[dict[str, object]]:
    return [
        {
            "id": f"fan_{index}",
            "name": "",
            "location": location,
            "running": True,
            "values": {"fan_rpm": rpm},
        }
        for index, (location, rpm) in enumerate(rows, 1)
    ]


def _fan_field(card: dict[str, object]) -> dict[str, object]:
    state = {"request_context": _context(), "conditions": {"condition_sets": [card]}}
    return next(field for field in get_active_condition_fields(state) if field["card_id"] == card["id"])


def test_fan_rpm_mode_round_trips_without_changing_the_card_id():
    for mode in ("", "common", "individual"):
        card = _operating_card()
        card["id"] = "operating_opaque123"
        card["fans"] = _fans(("상", "1000"), ("하", "1000"))
        card["fan_rpm_mode"] = mode

        cleaned = sanitize_condition_sets([card], _context())[0]

        assert cleaned["id"] == "operating_opaque123"
        assert cleaned["fan_rpm_mode"] == mode
        assert cleaned["fan_locations"] == ["상", "하"]
        assert cleaned["fan_rpms"] == ["1000", "1000"]


def test_legacy_multi_fan_values_are_preserved_without_inferring_a_mode():
    card = _operating_card()
    card.pop("fan_rpm_mode")
    card["fans"] = _fans(("상", "1000"), ("하", "1000"))

    cleaned = sanitize_condition_sets([card], _context())[0]

    assert cleaned["fan_rpm_mode"] == ""
    assert cleaned["fan_locations"] == ["상", "하"]
    assert cleaned["fan_rpms"] == ["1000", "1000"]
    assert _fan_field(cleaned)["values"][0]["status"] == "missing"


@pytest.mark.parametrize(
    ("mode", "rows", "expected"),
    [
        ("", (("", "780"),), "provided"),
        ("", (("상", "1000"), ("하", "1000")), "missing"),
        ("common", (("", "1600"), ("", "1600")), "provided"),
        ("common", (("", "1600"), ("", "1500")), "missing"),
        ("individual", (("상", "1000"), ("하", "700")), "provided"),
        ("individual", (("상", "1000"), ("", "700")), "missing"),
        ("individual", (("상", "1000"), ("하", "")), "missing"),
    ],
)
def test_fan_completeness_is_mode_aware(mode, rows, expected):
    card = _operating_card()
    card["fan_rpm_mode"] = mode
    card["fans"] = _fans(*rows)

    assert _fan_field(card)["values"][0]["status"] == expected


def test_single_fan_forces_an_empty_mode_and_common_ignores_locations():
    single = _operating_card()
    single["fan_rpm_mode"] = "common"
    single["fans"] = _fans(("상", "780"))
    cleaned = sanitize_condition_sets([single], _context())[0]
    assert cleaned["fan_rpm_mode"] == ""

    common = deepcopy(cleaned)
    common["fans"] = _fans(("", "1600"), ("", "1600"), ("", "1600"))
    common["fan_rpm_mode"] = "common"
    assert _fan_field(common)["values"][0]["status"] == "provided"
    assert _fan_field(common)["values"][0]["value"] == "모든 팬 1600"


def test_existing_agent_fan_write_preserves_the_mode():
    card = _operating_card()
    card["fan_rpm_mode"] = "individual"
    card["fans"] = _fans(("상", "900"), ("하", "800"))
    state = {"request_context": _context(), "conditions": {"condition_sets": [card]}}

    updated = apply_patch_operations(
        state,
        [{"op": "set_condition_field", "card_id": card["id"], "field_key": "fan_rpm", "fan_id": "fan_1", "value": "950"}],
    )
    operating = next(item for item in updated["conditions"]["condition_sets"] if item["type"] == "operating")

    assert operating["fan_rpm_mode"] == "individual"
    assert operating["fans"][0]["values"]["fan_rpm"] == "950"


def test_screen04_renders_the_three_fan_input_structures_and_one_inline_detail():
    renderer = HTML_TEMPLATE.split("function renderConditionFields()", 1)[1].split("function syncEditorFromState()", 1)[0]

    assert 'class="fan-rpm-editor single"' in renderer
    assert 'data-fan-rpm-mode' in renderer
    assert 'value="common"' in renderer and '모든 팬 동일' in renderer
    assert 'value="individual"' in renderer and '팬별 입력' in renderer
    assert 'data-fan-common-rpm' in renderer
    assert 'data-fan-detail-card' in renderer
    assert 'expandedFanCardId === cardId' in renderer
    assert 'fan-summary' not in renderer
    assert 'fanCompactText' not in renderer
    assert '${modeSelect}<button class="ghost fan-detail-toggle"' in renderer
    assert 'aria-controls="fan-detail-${esc(cardId)}"' in renderer
    assert '<span>팬별 설정</span><svg viewBox="0 0 24 24" aria-hidden="true">' in renderer
    assert 'id="fan-detail-${esc(cardId)}"' in renderer
    assert '팬별 설정 ${expanded ? "▲" : "▼"}' not in renderer
    assert renderer.count('class="condition-card-row"') == 1
    assert 'operatingExtraWidth' not in renderer


def test_missing_individual_fan_control_reopens_its_card_and_focuses_the_rerendered_field():
    reveal = HTML_TEMPLATE.split("function revealMissingFanControl", 1)[1].split("function firstIncompleteScreenBefore", 1)[0]
    renderer = HTML_TEMPLATE.split("function renderConditionFields()", 1)[1].split("function syncEditorFromState()", 1)[0]

    remember = reveal.index("const cardId = contextText(control.dataset.cardId);")
    expand = reveal.index("expandedFanCardId = cardId;")
    rerender = reveal.index("renderConditionFields();")
    refind = reveal.index("return document.querySelector")
    focus = reveal.index("target?.focus?.({preventScroll:true});")
    assert remember < expand < rerender < refind < focus
    assert 'control?.closest?.("[data-fan-detail-card]")' in reveal
    assert 'preserveEditorDraftBeforeRerender();' in reveal
    assert '[data-fan-index="${CSS.escape(fanIndex)}"]' in reveal
    assert '[data-card-field="${CSS.escape(fieldKey)}"]' in reveal
    assert 'const target = screen.id === "SCREEN-04" ? revealMissingFanControl(control)' in reveal

    # 하나의 전역 card id와 card별 일치 여부만으로 hidden을 결정하므로 다른 상세영역은 닫힌다.
    assert "const expanded = expandedFanCardId === cardId;" in renderer
    assert '${expanded ? "" : "hidden"}' in renderer


def test_hidden_fan_values_are_preserved_and_common_input_updates_every_fan():
    collector = HTML_TEMPLATE.split("function collectConditionSets()", 1)[1].split("async function refreshAnalysisResultGuidance", 1)[0]

    assert 'if (locationInput) fan.location = locationInput.value.trim();' in collector
    assert 'fan.location = locationInput ? locationInput.value.trim() : "";' not in collector
    assert 'if (commonRpmInput)' in collector
    assert 'asArray(card.fans).forEach(fan => { fan.values = {fan_rpm: commonRpmInput.value.trim()}; });' in collector


def test_fan_count_limit_uses_the_existing_blocking_modal_style_without_mutating_state():
    resize = HTML_TEMPLATE.split("function resizeFanRpmInputs", 1)[1].split("function handleFanCountChange", 1)[0]

    assert 'if (count > 10)' in resize
    assert resize.index('if (count > 10)') < resize.index('card.fans = Array.from({length:count}')
    assert 'showFanLimitModal(cardId);' in resize
    assert 'max="10"' in HTML_TEMPLATE
    assert 'id="fanLimitModal"' in HTML_TEMPLATE
    assert 'aria-modal="true"' in HTML_TEMPLATE
    assert 'Fan 개수를 확인해 주세요.' in HTML_TEMPLATE
    assert HTML_TEMPLATE.count("sedo.hong@lge.com") == 2  # link text and href, one modal only
    assert 'if (count === 1 || current.length === 1) card.fan_rpm_mode = "";' in resize


def test_case_matrix_and_preview_use_mode_aware_full_fan_details():
    helper = HTML_TEMPLATE.split("function operatingFanDisplay", 1)[1].split("function caseSourceReferenceHtml", 1)[0]
    script = f'''function asObj(value){{ return value && typeof value === "object" && !Array.isArray(value) ? value : {{}}; }}
function asArray(value){{ return Array.isArray(value) ? value : []; }}
function contextText(value){{ return String(value ?? "").trim(); }}
function operatingFanDisplay{helper}
const common = operatingFanDisplay({{fan_rpm_mode:"common", fans:[{{values:{{fan_rpm:"1600"}}}},{{values:{{fan_rpm:"1600"}}}}]}});
const individual = operatingFanDisplay({{fan_rpm_mode:"individual", fans:[{{location:"상",values:{{fan_rpm:"1000"}}}},{{location:"중",values:{{fan_rpm:"700"}}}},{{location:"하",values:{{fan_rpm:"640"}}}}]}});
if (common.text !== "모든 팬 1600" || common.missing) throw new Error(JSON.stringify(common));
if (individual.text !== "상 1000 / 중 700 / 하 640" || individual.missing) throw new Error(JSON.stringify(individual));
'''
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    case_reference = HTML_TEMPLATE.split("function caseSourceReferenceHtml()", 1)[1].split("function caseTableHtml()", 1)[0]
    preview = HTML_TEMPLATE.split("function renderDocumentPreviewPanel", 1)[1].split("function renderCandidateNotice", 1)[0]
    assert '팬 개수: ${display.count} · 회전수(RPM): ${display.text}' in case_reference
    assert 'const fanDisplay = operatingFanDisplay(row);' in preview
    assert '+N' not in helper + case_reference + preview
