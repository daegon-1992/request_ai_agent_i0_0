from __future__ import annotations

from copy import deepcopy
import subprocess

from request_ai_agent_i0_0.condition_engine import generate_condition_axis
from request_ai_agent_i0_0.condition_fieldsets import default_condition_sets, get_active_condition_fields, sanitize_condition_sets
from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def _context(analysis_type: str = "열유동 해석") -> dict[str, object]:
    return {"analysis_type": analysis_type, "context_locked": True}


def test_active_condition_cards_are_canonical_and_extra_cards_are_preserved():
    cards = default_condition_sets(_context("일반 유동 해석"))
    assert {card["type"] for card in cards} == {"operating", "heat_exchanger"}
    extra = {**cards[0], "id": "operating_2", "is_default": False}
    cleaned = sanitize_condition_sets([*cards, extra], _context("일반 유동 해석"))
    assert [card["id"] for card in cleaned if card["type"] == "operating"] == ["operating_1", "operating_2"]


def test_condition_card_ids_survive_middle_row_deletion_and_normalization():
    context = _context("일반 유동 해석")
    first = next(card for card in default_condition_sets(context) if card["type"] == "operating")
    cards = [deepcopy(first) for _ in range(4)]
    for card, card_id in zip(cards, ("operating_1", "operating_2", "operating_3", "operating_4")):
        card.update({"id": card_id, "is_default": card_id == "operating_1"})

    cleaned = sanitize_condition_sets([cards[0], cards[2], cards[3]], context)

    assert [card["id"] for card in cleaned if card["type"] == "operating"] == [
        "operating_1",
        "operating_3",
        "operating_4",
    ]
    assert [card["name"] for card in cleaned if card["type"] == "operating"] == ["운전 1", "운전 2", "운전 3"]


def test_condition_card_sanitizer_repairs_only_missing_duplicate_or_cross_type_ids():
    context = _context("일반 유동 해석")
    first = next(card for card in default_condition_sets(context) if card["type"] == "operating")
    rows = [deepcopy(first) for _ in range(4)]
    rows[0]["id"] = "operating_1"
    rows[1]["id"] = "operating_1"
    rows[2]["id"] = ""
    rows[3]["id"] = "heat_exchanger_9"

    cleaned = [card for card in sanitize_condition_sets(rows, context) if card["type"] == "operating"]
    ids = [card["id"] for card in cleaned]

    assert ids[0] == "operating_1"
    assert len(set(ids)) == 4
    assert all(card_id.startswith("operating_") for card_id in ids)
    assert all(len(card_id) == len("operating_") + 32 for card_id in ids[1:])


def test_condition_card_ui_adds_and_removes_rows_inside_each_condition_box():
    assert 'data-action="add-condition-card"' in HTML_TEMPLATE
    assert 'data-action="remove-condition-card"' in HTML_TEMPLATE
    assert 'class="primary condition-row-action"' in HTML_TEMPLATE
    assert 'class="condition-row-action remove"' in HTML_TEMPLATE
    assert 'const environment = ["space_environment", "supply_air"]' in HTML_TEMPLATE
    assert 'condition-primary-grid' in HTML_TEMPLATE
    assert 'condition-environment-grid' in HTML_TEMPLATE
    assert '.condition-primary-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}' in HTML_TEMPLATE
    assert '.condition-primary-grid .condition-card-type-heat_exchanger{grid-column:1/-1}' in HTML_TEMPLATE
    assert '.condition-environment-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}' in HTML_TEMPLATE
    assert 'const cards = collectConditionSets();' in HTML_TEMPLATE
    assert 'const card = JSON.parse(JSON.stringify(base));' in HTML_TEMPLATE
    assert 'card.is_default = false;' in HTML_TEMPLATE
    assert 'CSS.escape(card.id)' in HTML_TEMPLATE
    assert 'CSS.escape(focusCard.id)' in HTML_TEMPLATE


def test_condition_row_rerender_preserves_the_latest_geometry_draft():
    helper = HTML_TEMPLATE.split('function preserveEditorDraftBeforeRerender()', 1)[1].split('async function postJson', 1)[0]
    assert 'requestState = collectState();' in helper

    fan_count_action = HTML_TEMPLATE.split('function resizeFanRpmInputs', 1)[1].split('function handleFanCountChange', 1)[0]
    add_action = HTML_TEMPLATE.split('if (action === "add-condition-card")', 1)[1]
    remove_action = HTML_TEMPLATE.split('if (action === "remove-condition-card")', 1)[1]
    assert fan_count_action.index('preserveEditorDraftBeforeRerender();') < fan_count_action.index('renderConditionFields();')
    for action_block in (add_action, remove_action):
        assert action_block.index('preserveEditorDraftBeforeRerender();') < action_block.index('syncEditorFromState();')


def test_case_matrix_uses_live_values_after_any_condition_row_is_removed():
    helper = HTML_TEMPLATE.split('function liveCaseDropdownOptions()', 1)[1].split('function caseSourceReferenceHtml()', 1)[0]
    source_reference = HTML_TEMPLATE.split('function caseSourceReferenceHtml()', 1)[1].split('function caseTableHtml()', 1)[0]
    case_table = HTML_TEMPLATE.split('function caseTableHtml()', 1)[1].split('function caseCoverageState', 1)[0]

    assert 'add("fan", card.id, `운전 ${++operatingIndex}`);' in helper
    assert 'add("heat_exchanger", card.id, `사양 ${++heatExchangerIndex}`);' in helper
    assert 'Object.prototype.hasOwnProperty.call(fields, key)' in helper
    assert 'const options = liveCaseDropdownOptions();' in source_reference
    assert '.map(card => [contextText(asObj(card).id), asObj(card)]));' in source_reference
    assert 'const optionMap = liveCaseDropdownOptions();' in case_table


def test_late_preview_response_cannot_restore_a_removed_condition_row():
    schedule = HTML_TEMPLATE.split('function invalidatePendingPreviewRefresh()', 1)[1].split('const CASE_REVIEW_REQUIRED', 1)[0]

    assert schedule.index('previewStateRevision += 1;') < schedule.index('previewRefreshTimer = window.setTimeout(() => {')
    assert 'window.clearTimeout(previewRefreshTimer);' in schedule
    assert 'const scheduledRevision = previewStateRevision;' in schedule
    assert 'refreshPreview(scheduledRevision);' in schedule
    assert 'async function refreshPreview(requestedRevision=previewStateRevision)' in schedule
    assert schedule.index('if (requestedRevision !== previewStateRevision) return false;') < schedule.index('adoptStateFromResponse(data);')
    assert 'const previousConditionIdentity = conditionCardIdentity();' in schedule
    assert 'if (previousConditionIdentity !== conditionCardIdentity()) renderConditionFields();' in schedule


def test_context_confirmation_invalidates_an_inflight_preview_before_adopting_locked_state():
    confirm_start = HTML_TEMPLATE.index('async function confirmRequestContext()')
    confirm_end = HTML_TEMPLATE.index('async function updateOperationMode', confirm_start)
    confirm_function = HTML_TEMPLATE[confirm_start:confirm_end]
    preview_start = HTML_TEMPLATE.index('function invalidatePendingPreviewRefresh()')
    preview_end = HTML_TEMPLATE.index('const CASE_REVIEW_REQUIRED', preview_start)
    preview_functions = HTML_TEMPLATE[preview_start:preview_end]
    navigation_start = HTML_TEMPLATE.index('function navigateScreen(screenId, options={})')
    navigation_end = HTML_TEMPLATE.index('function updateGate()', navigation_start)
    navigation_function = HTML_TEMPLATE[navigation_start:navigation_end]

    assert confirm_function.index('invalidatePendingPreviewRefresh();') < confirm_function.index('adoptStateFromResponse(data);')

    script = '''
(async () => {
  let requestState = {request_context:{context_locked:false}};
  let previewStateRevision = 0;
  let previewRefreshTimer = null;
  let prepAssistStarted = false;
  let previewResolve;
  let activeScreen = "SCREEN-02";
  let activeTopTab = "write";
  const confirmedContext = {
    division:"H&A", product_lineup:"SAC", platform:"Applied",
    taxonomy_id:"DOAS", analysis_type:"DB", context_locked:true
  };
  const window = {clearTimeout:() => {}, setTimeout:() => 1};
  const syncQuickPrepSelectionsToDraft = () => confirmedContext;
  const missingContextFields = () => [];
  const collectContextConfirmState = () => requestState;
  const postJson = async () => ({state:{request_context:confirmedContext}});
  const postState = () => new Promise(resolve => { previewResolve = resolve; });
  const adoptStateFromResponse = data => { requestState = data.state || requestState; };
  const syncEditorFromState = () => {};
  const pushMessage = () => {};
  const renderRequestPrepCard = () => {};
  const conditionCardIdentity = () => "";
  const renderConditionFields = () => {};
  const renderDerivedPanels = () => {};
  const screenOrder = [
    {id:"SCREEN-01", tab:"write", requiresContext:false},
    {id:"SCREEN-02", tab:"write", requiresContext:true},
    {id:"SCREEN-03", tab:"write", requiresContext:true}
  ];
  const isContextLocked = () => requestState.request_context.context_locked === true;
  const firstIncompleteScreenBefore = () => null;
  const missingRequiredControl = () => null;
  const focusRequiredControl = () => { activeScreen = "SCREEN-01"; };
  const renderScreenNavigation = () => {};
  const focusScreenHeading = () => {};
''' + preview_functions + navigation_function + confirm_function + '''
  const pendingPreview = refreshPreview();
  await Promise.resolve();
  await confirmRequestContext();
  previewResolve({state:{request_context:{context_locked:false}}});
  const stalePreviewAccepted = await pendingPreview;
  const screenThreeAccepted = navigateScreen("SCREEN-03", {bypassRequiredGate:true, focus:false});
  process.stdout.write(JSON.stringify({
    stalePreviewAccepted,
    contextLocked:requestState.request_context.context_locked,
    screenThreeAccepted,
    activeScreen
  }));
})().catch(error => { console.error(error); process.exit(1); });
'''
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        '{"stalePreviewAccepted":false,"contextLocked":true,'
        '"screenThreeAccepted":true,"activeScreen":"SCREEN-03"}'
    )


def test_new_condition_rows_use_opaque_ids_instead_of_reusing_the_row_count():
    helper = HTML_TEMPLATE.split('function newConditionCardId(type)', 1)[1].split('function conditionValuesMap()', 1)[0]
    add_action = HTML_TEMPLATE.split('if (action === "add-condition-card")', 1)[1].split('if (action === "remove-condition-card")', 1)[0]

    assert 'window.crypto.getRandomValues(bytes);' in helper
    assert 'return `${contextText(type)}_${suffix}`;' in helper
    assert 'card.id = newConditionCardId(type);' in add_action
    assert 'card.id = `${type}_${number}`' not in add_action


def test_condition_row_rerender_reads_unsaved_product_strings_without_resetting_them():
    helper_block = HTML_TEMPLATE.split('function asObj(value)', 1)[1].split('function isProvided(field)', 1)[0]
    script = f'''function asObj(value){helper_block}
const draft = {{drawing_no:"DRAW-NEW", difference_from_base:"토출부 변경"}};
const saved = {{drawing_no:{{value:"DRAW-SAVED", status:"provided", display_value:"DRAW-SAVED"}}}};
if (productText(draft, "drawing_no") !== "DRAW-NEW") throw new Error("draft drawing reset");
if (productText(draft, "difference_from_base") !== "토출부 변경") throw new Error("draft description reset");
if (productText(saved, "drawing_no") !== "DRAW-SAVED") throw new Error("saved drawing reset");
'''
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    assert 'function productField(product, key){ return asObj(product)[key]; }' in HTML_TEMPLATE


def test_condition_boxes_share_the_requester_info_shadow():
    assert (
        '.workspace-shell .condition-group{border-color:var(--request-workspace-border);'
        'background:var(--request-workspace-surface);box-shadow:none}'
    ) in HTML_TEMPLATE


def test_condition_boxes_use_screen_four_i0_0_control_density():
    assert '.workspace-shell .condition-input-screen .condition-group{border-radius:10px}' in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen .condition-group-head{min-height:0;'
        'padding:16px 16px 0;border-bottom:0;background:transparent}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen .condition-group-head h3{'
        'font-size:16px;font-weight:600;color:var(--ink)}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen .condition-card-row :is(input,select){'
        'min-height:46px;padding:10px 12px;font-size:14px;font-weight:400;'
        'border:1px solid var(--line-strong);border-radius:8px;background:var(--paper)}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen .condition-spec-name{min-height:46px;'
        'padding-block:10px;font-size:14px;font-weight:400;line-height:1.45}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen .condition-temperature-combobox{'
        'height:46px;min-height:46px;grid-template-columns:minmax(0,1fr) 42px;'
        'border:1px solid var(--line-strong);'
        'border-radius:8px;background:var(--paper)}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen .condition-temperature-combobox input{'
        'height:44px;min-height:44px;padding:10px 12px;border:0;'
        'border-radius:7px 0 0 7px;background:transparent}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen .condition-temperature-combobox '
        '.undecided-combobox-toggle{width:42px;height:44px;min-height:44px;'
        'border:0;border-radius:0 7px 7px 0;background:transparent}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen .condition-temperature-guidance{'
        'margin:-10px 0 0;color:#55585B;font-size:13px;font-weight:400;line-height:1.55}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen .heat-exchanger-custom-control{'
        'grid-template-columns:minmax(0,1fr) 42px}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen '
        ':is(.heat-exchanger-custom-control,.fan-count-custom-control) > button{'
        'width:42px;min-width:42px;height:46px;min-height:46px}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen .fan-count-custom-control input{padding-inline:6px}'
    ) in HTML_TEMPLATE
    assert '.condition-row-action{width:34px;min-width:34px;height:34px;' in HTML_TEMPLATE


def test_all_condition_boxes_use_the_shared_content_spacing():
    assert '.condition-card-rows{display:grid;gap:8px;padding:16px}' in HTML_TEMPLATE
    assert '.fan-input-column{display:flex;flex-direction:column;gap:6px;min-width:0}' in HTML_TEMPLATE
    assert 'const primary = types.filter(type => type !== "supply_air" && type !== "space_environment").map(groupHtml).join("");' in HTML_TEMPLATE
    assert '${primary ? `<div class="condition-primary-grid">${primary}</div>` : ""}' in HTML_TEMPLATE
    assert 'const environment = ["space_environment", "supply_air"]' in HTML_TEMPLATE


def test_fan_detail_uses_the_screen_four_local_action_and_subsurface_standard():
    assert (
        '.workspace-shell .condition-input-screen .fan-detail-toggle{min-height:36px;'
        'justify-self:start;padding:0 11px;display:inline-flex;align-items:center;'
        'justify-content:center;gap:6px;border:1px solid var(--line-strong);border-radius:8px;'
        'background:var(--paper);color:var(--ink);font-size:14px;font-weight:500;line-height:1.2}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen .fan-detail-toggle svg{width:16px;height:16px;'
        'fill:none;stroke:currentColor;stroke-linecap:round;stroke-linejoin:round;stroke-width:2;'
        'transition:transform .16s ease}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen .fan-detail{margin-top:6px;padding:16px;'
        'border:1px solid var(--line-strong);border-radius:10px;background:#F7F7F7;box-shadow:none}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen .fan-detail-title{margin:0 0 12px;'
        'padding:0;border:0;color:var(--ink);font-size:15px;font-weight:600;line-height:1.55}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .condition-input-screen .fan-input-set{padding:12px;'
        'border:1px solid var(--line);border-radius:8px;background:var(--paper)}'
    ) in HTML_TEMPLATE


def test_heat_exchanger_spec_is_narrow_and_remaining_columns_share_equal_widths():
    assert '.condition-card-type-heat_exchanger .condition-card-row{grid-template-columns:64px repeat(5,minmax(0,1fr)) max-content;gap:9px}' in HTML_TEMPLATE
    assert '.condition-card-type-heat_exchanger .condition-card-row>label{min-width:0;white-space:nowrap}' in HTML_TEMPLATE
    assert '.condition-card-type-heat_exchanger .condition-spec-name{padding-inline:4px;white-space:nowrap}' in HTML_TEMPLATE


def test_fan_count_controls_replace_the_legacy_multiple_fan_mode():
    assert 'data-fan-running="${index}"' not in HTML_TEMPLATE
    assert 'fan.running === false ? "disabled" : ""' not in HTML_TEMPLATE
    assert 'enable-multiple-fans' not in HTML_TEMPLATE
    assert 'add-fan' not in HTML_TEMPLATE
    assert 'convert-single-fan' not in HTML_TEMPLATE
    assert 'data-fan-count' in HTML_TEMPLATE
    assert '<option value="__custom__">직접 입력</option>' in HTML_TEMPLATE
    assert 'const options = [1,2,3,4].map' in HTML_TEMPLATE
    assert 'count > 4' in HTML_TEMPLATE
    assert 'Array.from({length:count}' in HTML_TEMPLATE
    assert 'data-fan-index="${fanIndex}"' in HTML_TEMPLATE


def test_condition_rows_render_only_inputs_after_the_first_row():
    rows = HTML_TEMPLATE.split('const rowHtml =', 1)[1].split('const groupHtml =', 1)[0]
    assert 'fixedTextHtml(key, `사양 ${rowIndex}`, isFirst)}${heatExchangerTypeSelectHtml(cardId, row, isFirst)' in rows
    assert 'fixedTextHtml("fan", `운전 ${rowIndex}`, isFirst)' in rows
    assert 'class="product-geometry-name condition-spec-name"' in HTML_TEMPLATE
    assert 'data-spec-name' in HTML_TEMPLATE
    assert '.condition-fixed-value' not in HTML_TEMPLATE
    assert 'aria-readonly="true"' in HTML_TEMPLATE
    assert 'data-action="add-condition-card"' in rows
    assert 'data-action="remove-condition-card"' in rows


def test_operating_rows_use_fan_names_and_heat_exchanger_numeric_inputs_share_width():
    cards = default_condition_sets(_context("일반 유동 해석"))
    operating = next(card for card in cards if card["type"] == "operating")
    second = {**operating, "id": "operating_2", "is_default": False}

    cleaned = sanitize_condition_sets([operating, second], _context("일반 유동 해석"))

    assert [card["name"] for card in cleaned if card["type"] == "operating"] == ["운전 1", "운전 2"]
    assert 'fan_count:"팬 개수"' in HTML_TEMPLATE
    assert 'fan_location:"위치"' in HTML_TEMPLATE
    assert 'fan_rpm:"팬 회전수(RPM)"' in HTML_TEMPLATE
    assert '.condition-card-type-operating .condition-card-row{grid-template-columns:64px 100px minmax(260px,1fr) max-content;align-items:end}' in HTML_TEMPLATE
    assert '.condition-card-type-operating .condition-row-actions{grid-column:4;grid-row:1}' in HTML_TEMPLATE
    assert '.condition-card-type-operating .condition-spec-name{padding-inline:3px;white-space:nowrap}' in HTML_TEMPLATE
    assert '.fan-count-custom-control{grid-template-columns:minmax(0,1fr) 42px;gap:4px;width:90px}' in HTML_TEMPLATE
    assert 'repeat(5,minmax(0,1fr))' in HTML_TEMPLATE
    assert '.fan-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))' in HTML_TEMPLATE
    assert '.fan-input-set{display:grid;grid-template-columns:30px minmax(100px,1fr) minmax(90px,120px)' in HTML_TEMPLATE
    assert 'const multiple = fans.length >= 2;' in HTML_TEMPLATE
    assert 'data-card-field="fan_location"' in HTML_TEMPLATE


def test_operating_card_width_is_independent_of_fan_count():
    assert '.condition-primary-grid .condition-card-type-operating{' in HTML_TEMPLATE
    assert 'grid-column:1/-1;width:100%' in HTML_TEMPLATE
    assert '.condition-primary-grid .condition-card-type-operating{width:100%}' in HTML_TEMPLATE
    assert 'operatingExtraWidth' not in HTML_TEMPLATE


def test_fan_location_inputs_show_upper_middle_lower_example():
    assert 'placeholder="예 : 상/중/하"' in HTML_TEMPLATE
    assert 'placeholder="예: 상"' not in HTML_TEMPLATE


def test_one_operating_row_is_one_fan_configuration_not_multiple_rpm_cases():
    context = _context("일반 유동 해석")
    cards = default_condition_sets(context)
    operating = next(card for card in cards if card["type"] == "operating")
    operating["fans"] = [
        {"id": "fan_1", "name": "", "location": "상", "running": True, "values": {"fan_rpm": "900"}},
        {"id": "fan_2", "name": "", "location": "중", "running": True, "values": {"fan_rpm": "1100"}},
        {"id": "fan_3", "name": "", "location": "하", "running": True, "values": {"fan_rpm": "1200"}},
    ]
    operating["fan_rpm_mode"] = "individual"
    state = {"request_context": context, "conditions": {"condition_sets": cards}}

    cleaned = sanitize_condition_sets(cards, context)
    cleaned_operating = next(card for card in cleaned if card["type"] == "operating")
    fan_field = next(field for field in get_active_condition_fields(state) if field["card_id"] == "operating_1")
    axis = generate_condition_axis(state)

    assert cleaned_operating["fan_count"] == 3
    assert cleaned_operating["fan_locations"] == ["상", "중", "하"]
    assert cleaned_operating["fan_rpms"] == ["900", "1100", "1200"]
    assert fan_field["value_semantics"] == "fan_configuration"
    assert fan_field["fan_configuration"] == {
        "name": "운전 1",
        "fan_count": 3,
        "fan_rpm_mode": "individual",
        "fan_locations": ["상", "중", "하"],
        "fan_rpms": ["900", "1100", "1200"],
    }
    assert len(fan_field["values"]) == 1
    assert fan_field["values"][0]["value"] == "상 900 / 중 1100 / 하 1200"
    assert "operating_1.fan_rpm" in axis["common_conditions"]
    assert "operating_1.fan_rpm" not in axis["variable_conditions"]
    assert len(axis["condition_variants"]) == 1


def test_incomplete_rpm_inside_a_fan_configuration_remains_missing():
    context = _context("일반 유동 해석")
    cards = default_condition_sets(context)
    operating = next(card for card in cards if card["type"] == "operating")
    operating["fans"] = [
        {"id": "fan_1", "name": "", "running": True, "values": {"fan_rpm": "900"}},
        {"id": "fan_2", "name": "", "running": True, "values": {"fan_rpm": ""}},
    ]

    fan_field = next(
        field
        for field in get_active_condition_fields({"request_context": context, "conditions": {"condition_sets": cards}})
        if field["card_id"] == "operating_1"
    )

    assert len(fan_field["values"]) == 1
    assert fan_field["values"][0]["status"] == "missing"
    assert fan_field["values"][0]["display_value"] == "900 / -"


def test_full_preview_uses_condition_names_as_row_titles_without_repeating_them_in_values():
    preview = HTML_TEMPLATE.split("function renderDocumentPreviewPanel", 1)[1].split("function renderCandidateNotice", 1)[0]

    assert 'operating: []' in preview
    assert 'heat_exchanger: ["tube_diameter", "fin_type", "row_count", "fpi"]' in preview
    assert 'if (cardType === "operating") return contextText(row.name);' in preview
    assert 'if (cardType === "heat_exchanger") return contextText(fieldDisplayValue(asObj(row.fields).name));' in preview
    assert 'return name ? `${title} (${name})` : title;' in preview
    assert 'const fanDisplay = operatingFanDisplay(row);' in preview
    assert '`\ud32c ${fanDisplay.count}\uac1c \u00b7 ${fanDisplay.text}' in preview
    assert 'previewFieldLabel("팬 회전수(RPM)", fanDisplay.missing)' in preview
    assert '? [`${row.name || "Fan"}' not in preview
    assert '${esc(previewConditionTitle(row, cardType))}' in preview


def test_heat_exchanger_spec_is_system_generated_for_each_row():
    cards = default_condition_sets(_context("일반 유동 해석"))
    heat_exchanger = next(card for card in cards if card["type"] == "heat_exchanger")
    second = {**heat_exchanger, "id": "heat_exchanger_2", "is_default": False}
    second["fields"] = {**heat_exchanger["fields"], "name": "사용자 입력값"}

    cleaned = sanitize_condition_sets([heat_exchanger, second], _context("일반 유동 해석"))
    heat_exchangers = [card for card in cleaned if card["type"] == "heat_exchanger"]

    assert [card["fields"]["name"]["value"] for card in heat_exchangers] == ["사양 1", "사양 2"]
    assert all(card["fields"]["name"]["source"] == "system" for card in heat_exchangers)
    assert 'const fieldLabels = {name:"사양",fan:"운전"' in HTML_TEMPLATE


def test_legacy_stopped_fan_without_rpm_restores_to_zero_and_preserves_explicit_zero():
    cards = sanitize_condition_sets(
        [{"id": "operating_1", "type": "operating", "fans": [
            {"id": "fan_1", "name": "Indoor", "running": False, "values": {"fan_rpm": ""}},
            {"id": "fan_2", "name": "Aux", "values": {"fan_rpm": 0}},
        ]}],
        _context(),
    )
    assert [fan["values"]["fan_rpm"] for fan in cards[0]["fans"]] == ["0", "0"]
    assert [fan["name"] for fan in cards[0]["fans"]] == ["Indoor", "Aux"]
