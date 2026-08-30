from __future__ import annotations

from copy import deepcopy
import json
import subprocess

import request_ai_agent_i0_0.app as app_module
from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.condition_fieldsets import default_condition_sets
from request_ai_agent_i0_0.state import create_initial_state, sanitize_state
from request_ai_agent_i0_0.ui import HTML_TEMPLATE
from request_ai_agent_i0_0.validator import case_matrix_coverage, validate_state


def _matrix() -> dict[str, object]:
    return {
        "visible_columns": [
            {"key": "case_no", "label": "No.", "kind": "number"},
            {"key": "geometry_id", "label": "형상", "kind": "geometry"},
            {"key": "operation", "label": "운전", "kind": "condition"},
            {"key": "specification", "label": "사양", "kind": "condition"},
        ],
        "dropdown_options": {
            "geometry_id": [
                {"value": "g1", "label": "형상 1"},
                {"value": "g2", "label": "형상 2"},
                {"value": "g3", "label": "형상 3"},
                {"value": "", "label": "빈 형상"},
            ],
            "operation": [
                {"value": "o1", "label": "운전 1"},
                {"value": "o2", "label": "운전 2"},
            ],
            "specification": [
                {"value": "s1", "label": "사양 1"},
                {"value": "s2", "label": "사양 2"},
            ],
            "not_visible": [{"value": "ignored", "label": "무시"}],
        },
        "rows": [
            {"geometry_id": "g1", "condition_values": {"operation": "o1", "specification": "s1"}},
            {"geometry_id": "g2", "condition_values": {"operation": "o2", "specification": "s2"}},
        ],
    }


def _complete_state() -> dict[str, object]:
    state = create_initial_state()
    state["request_context"].update(
        {
            "business_unit": "RAC",
            "product_group": "벽걸이",
            "platform": "SK",
            "analysis_type": "풍량",
            "context_locked": True,
        }
    )
    state["basic_info"].update(
        {"division": "RAC", "department": "개발팀", "requester_name": "테스터", "requester_role": "책임"}
    )
    state["analysis_overview"].update(
        {
            "project_name": "COVERAGE",
            "development_grade": "A",
            "npi_stage": "DV",
            "model_suffix": "MODEL-A",
            "desired_completion_date": "2026-08-25",
            "request_description": "설계 변경 검토",
            "additional_result_request": "기존안과 변경안 비교",
        }
    )
    state["geometry"]["base_product"]["drawing_no"] = "DRAW-A"
    cards = default_condition_sets(state["request_context"])
    for card in cards:
        if card["type"] == "operating":
            card["fans"][0]["values"]["fan_rpm"] = "700"
        else:
            for key, field in card["fields"].items():
                if key != "name":
                    field["value"] = "1"
    state["conditions"]["condition_sets"] = cards
    return sanitize_state(state)


def _state_with_unused_operation() -> dict[str, object]:
    state = _complete_state()
    operating = next(card for card in state["conditions"]["condition_sets"] if card["type"] == "operating")
    second = deepcopy(operating)
    second["id"] = "operating_2"
    second["is_default"] = False
    second["fans"][0]["values"]["fan_rpm"] = "900"
    state["conditions"]["condition_sets"].append(second)
    return sanitize_state(state)


def _state_with_duplicate_case() -> dict[str, object]:
    state = _complete_state()
    duplicate = deepcopy(state["case_matrix"]["rows"][0])
    duplicate["case_id"] = "case_002"
    state["case_matrix"]["rows"].append(duplicate)
    return state


def test_coverage_reports_only_unused_geometry_and_visible_condition_options():
    coverage = case_matrix_coverage(_matrix())

    assert coverage["complete"] is False
    assert [(item["kind"], item["column_label"], item["option_label"]) for item in coverage["unused_items"]] == [
        ("geometry", "형상", "형상 3"),
    ]


def test_coverage_is_complete_without_a_cartesian_product_when_every_value_is_used():
    matrix = _matrix()
    matrix["rows"].append(
        {"geometry_id": "g3", "condition_values": {"operation": "o1", "specification": "s1"}}
    )

    assert case_matrix_coverage(matrix) == {"complete": True, "unused_items": []}
    assert len(matrix["rows"]) == 3


def test_coverage_does_not_change_existing_blocking_or_can_submit_meaning():
    state = _state_with_unused_operation()
    validation = validate_state(state)

    assert validation["coverage"]["complete"] is False
    assert [item["option_label"] for item in validation["coverage"]["unused_items"]] == ["운전 2"]
    assert validation["blocking"] == []
    assert validation["summary"]["can_submit"] is True
    assert validation["summary"]["warning_count"] == 0


def test_case_and_preview_status_ui_unifies_case_errors_and_keeps_coverage_separate():
    case_common = HTML_TEMPLATE.index('<div id="caseCommon"></div>')
    case_table = HTML_TEMPLATE.index('<div id="caseMatrix"></div>', case_common)
    duplicate_warning = HTML_TEMPLATE.index('id="caseDuplicateWarning"', case_table)
    case_status = HTML_TEMPLATE.index('id="caseCoverageStatus"', duplicate_warning)
    preview = HTML_TEMPLATE.index('<div id="documentPreviewPanel"></div>')
    preview_warning = HTML_TEMPLATE.index('id="previewCoverageWarning"', preview)
    submit_button = HTML_TEMPLATE.index('id="finalSubmitBtn"', preview_warning)
    confirm_start = HTML_TEMPLATE.index("async function confirmCaseConfiguration()")
    confirm_end = HTML_TEMPLATE.index("function renderDerivedPanels()", confirm_start)
    confirmation = HTML_TEMPLATE[confirm_start:confirm_end]

    assert case_common < case_table < duplicate_warning < case_status
    feedback_scope = (
        '.workspace-shell :is(.geometry-screen,.stage-static-screen[data-screen="SCREEN-05"],'
        '.workspace-form[data-screen="SCREEN-06"]) '
    )
    case_review_css = HTML_TEMPLATE.split(f"{feedback_scope}.case-review-message{{", 1)[1].split("}", 1)[0]
    assert "gap:12px" in case_review_css
    assert "padding:16px" in case_review_css
    assert "border-radius:10px" in case_review_css
    assert "box-shadow:none" in case_review_css
    assert "min-height" not in case_review_css
    assert '.case-duplicate-warning:empty,.case-coverage-status:empty,#previewCoverageWarning:empty{display:none}' in HTML_TEMPLATE
    assert f'{feedback_scope}.case-review-message:empty{{display:none}}' in HTML_TEMPLATE
    assert preview < preview_warning < submit_button
    assert f'{feedback_scope}.case-review-message.error{{border:1px solid #E8B4B0;background:#FFF2F1}}' in HTML_TEMPLATE
    assert f'{feedback_scope}.case-review-message.warning{{border:1px solid #E4D3AD;background:#FFF9ED}}' in HTML_TEMPLATE
    assert '.case-review-message.error{border:1px solid #E8B4B0;background:#FFF2F1}' in HTML_TEMPLATE
    assert '.case-review-message.warning{border:1px solid #E4D3AD;background:#FFF9ED}' in HTML_TEMPLATE
    assert "border-left:3px" not in HTML_TEMPLATE.split(f"{feedback_scope}.case-review-message.error{{", 1)[1].split("}", 1)[0]
    assert "border-left:3px" not in HTML_TEMPLATE.split(f"{feedback_scope}.case-review-message.warning{{", 1)[1].split("}", 1)[0]
    assert f'{feedback_scope}.coverage-warning-icon{{display:inline-grid;flex:0 0 20px;width:20px;height:20px;' in HTML_TEMPLATE
    assert f'{feedback_scope}.coverage-warning-title{{color:var(--ink);font-size:15px;font-weight:600;line-height:1.55}}' in HTML_TEMPLATE
    assert f'{feedback_scope}.coverage-warning-copy{{margin:0;color:#55585B;font-size:13px;font-weight:400;line-height:1.55}}' in HTML_TEMPLATE
    assert '<strong class="coverage-warning-title">오류 · Case 구성을 확인해 주세요.</strong>' in HTML_TEMPLATE
    assert '<strong class="coverage-warning-title">확인 필요 · Case에 사용되지 않은 항목이 있습니다.</strong>' in HTML_TEMPLATE
    assert '<circle cx="12" cy="12" r="9"></circle><path d="m9 9 6 6M15 9l-6 6"></path>' in HTML_TEMPLATE
    assert '<span class="coverage-warning-icon" aria-hidden="true">⚠</span><strong class="coverage-warning-title">' in HTML_TEMPLATE
    assert 'data-action="review-case-coverage"' in HTML_TEMPLATE
    assert 'navigateScreen("SCREEN-05")' in HTML_TEMPLATE
    assert "const blockingIssues = caseConfigurationIssues();" in confirmation
    assert "if (blockingIssues.length)" in confirmation
    assert "focusCaseValidationIssue(blockingIssues[0]);" in confirmation
    assert 'navigateScreen("SCREEN-06")' in confirmation
    assert "coverage" not in confirmation
    assert "wordButton.disabled = wordExportInProgress || firstIncompleteIndex >= 0 || caseMatrixExportBlocked" in HTML_TEMPLATE
    assert "const caseMatrixExportBlocked = caseMatrixBlocksWordExport();" in HTML_TEMPLATE
    assert 'screen.id !== "SCREEN-06"' in HTML_TEMPLATE


def test_screen_five_uses_the_canonical_card_action_and_matrix_header_contracts():
    assert (
        '.workspace-shell .stage-static-screen[data-screen="SCREEN-05"] .screen-heading{'
        'margin-bottom:8px;padding:3px 0;font-size:24px;font-weight:600;line-height:1.3;'
        'letter-spacing:-.02em;color:var(--ink)}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .stage-static-screen[data-screen="SCREEN-05"] > #section-case{'
        'margin-bottom:var(--request-workspace-card-section-gap);border:1px solid #DCDDDE;'
        'border-radius:10px;background:var(--paper);box-shadow:none;overflow:visible}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .stage-static-screen[data-screen="SCREEN-05"] > #section-case '
        '> .section-head{min-height:0;padding:16px 16px 0;border-bottom:0;background:transparent}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .stage-static-screen[data-screen="SCREEN-05"] > #section-case '
        '> .section-body{padding:16px;border-top:0}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .stage-static-screen[data-screen="SCREEN-05"] > #section-case '
        '> .section-head h3{font-size:16px;font-weight:600;color:var(--ink)}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .stage-static-screen[data-screen="SCREEN-05"] > #section-case '
        '> .section-head > .case-section-actions button{height:auto;min-height:36px;'
        'padding:7px 11px;border-radius:8px;font-size:14px;font-weight:500}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .stage-static-screen[data-screen="SCREEN-05"] '
        '> .screen-action-bar button{min-height:44px;padding:0 18px;border-radius:8px}'
    ) in HTML_TEMPLATE
    assert (
        '.workspace-shell .stage-static-screen[data-screen="SCREEN-05"] #section-case '
        '.matrix-wrap th{font-size:13px;font-weight:500;line-height:1.45}'
    ) in HTML_TEMPLATE


def test_case_error_warning_groups_missing_fields_uses_visible_labels_and_clears_when_resolved():
    start = HTML_TEMPLATE.index("function caseValidatorState(state=requestState)")
    end = HTML_TEMPLATE.index("function renderCaseCoverageStatus()", start)
    renderer = HTML_TEMPLATE[start:end]
    script = f"""
const target = {{innerHTML:""}};
const $ = id => id === "caseDuplicateWarning" ? target : null;
const asObj = value => value && typeof value === "object" && !Array.isArray(value) ? value : {{}};
const asArray = value => Array.isArray(value) ? value : [];
const contextText = value => String(value ?? "").trim();
const esc = value => String(value ?? "");
let requestState = {{
  case_matrix:{{visible_columns:[
    {{key:"case_no", label:"No.", kind:"number"}},
    {{key:"geometry_id", label:"형상", kind:"geometry"}},
    {{key:"axis_a", label:"운전", kind:"condition"}},
    {{key:"axis_b", label:"사양", kind:"condition"}}
  ]}},
  review:{{validator:{{blocking:[
    {{code:"case_matrix.geometry_missing", path:"case_matrix.rows[0].geometry_id", field_key:"geometry_id"}},
    {{code:"case_matrix.axis_a.missing", path:"case_matrix.rows[0].condition_values.axis_a", field_key:"axis_a"}},
    {{code:"case_matrix.axis_b.missing", path:"case_matrix.rows[0].condition_values.axis_b", field_key:"axis_b"}},
    {{code:"case_matrix.duplicate", case_no:2, duplicate_of_case_no:1}}
  ]}}}}
}};
{renderer}
renderCaseDuplicateWarning();
const emptyHtml = target.innerHTML;
requestState.review.validator.blocking = [
  {{code:"case_matrix.axis_b.missing", path:"case_matrix.rows[0].condition_values.axis_b", field_key:"axis_b"}}
];
renderCaseDuplicateWarning();
const partialHtml = target.innerHTML;
requestState.review.validator.blocking = [];
renderCaseDuplicateWarning();
process.stdout.write(JSON.stringify({{emptyHtml, partialHtml, resolvedHtml:target.innerHTML}}));
"""
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=False
    )

    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    assert "오류 · Case 구성을 확인해 주세요." in rendered["emptyHtml"]
    assert "Case 1: 형상, 운전, 사양을 선택해 주세요." in rendered["emptyHtml"]
    assert "Case 2: Case 1과 동일합니다." in rendered["emptyHtml"]
    assert "Case 1: 사양을 선택해 주세요." in rendered["partialHtml"]
    assert "형상, 운전" not in rendered["partialHtml"]
    assert rendered["resolvedHtml"] == ""


def test_preview_shows_same_case_errors_and_separate_coverage_together():
    start = HTML_TEMPLATE.index("function caseValidatorState(state=requestState)")
    end = HTML_TEMPLATE.index("function renderCasePreview()", start)
    renderer = HTML_TEMPLATE[start:end]
    script = f"""
const target = {{innerHTML:""}};
const $ = id => id === "previewCoverageWarning" ? target : null;
const asObj = value => value && typeof value === "object" && !Array.isArray(value) ? value : {{}};
const asArray = value => Array.isArray(value) ? value : [];
const contextText = value => String(value ?? "").trim();
const esc = value => String(value ?? "");
let requestState = {{case_matrix:{{visible_columns:[
  {{key:"geometry_id", label:"형상", kind:"geometry"}},
  {{key:"axis_a", label:"운전", kind:"condition"}}
]}}, review:{{validator:{{
  blocking:[
    {{code:"case_matrix.geometry_missing", path:"case_matrix.rows[0].geometry_id", field_key:"geometry_id"}},
    {{code:"case_matrix.axis_a.missing", path:"case_matrix.rows[0].condition_values.axis_a", field_key:"axis_a"}},
    {{code:"case_matrix.duplicate", case_no:3, duplicate_of_case_no:2}}
  ],
  coverage:{{complete:false, unused_items:[{{column_key:"fan", column_label:"운전", option_label:"운전 2"}}]}}
}}}}}};
{renderer}
renderPreviewCaseMatrixStatus();
const bothHtml = target.innerHTML;
requestState = {{review:{{validator:{{blocking:[], coverage:{{}}}}}}}};
renderPreviewCaseMatrixStatus();
process.stdout.write(JSON.stringify({{bothHtml, missingHtml:target.innerHTML}}));
"""
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=False
    )

    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    assert rendered["bothHtml"].count('class="case-review-message') == 2
    assert "오류 · Case 구성을 확인해 주세요." in rendered["bothHtml"]
    assert "Case 1: 형상, 운전을 선택해 주세요." in rendered["bothHtml"]
    assert "Case 3: Case 2과 동일합니다." in rendered["bothHtml"]
    assert "확인 필요 · Case에 사용되지 않은 항목이 있습니다." in rendered["bothHtml"]
    assert "05 Case Matrix에서 확인" in rendered["bothHtml"]
    assert rendered["missingHtml"] == ""


def test_duplicate_and_coverage_block_word_without_duplicating_selection_missing_gate():
    start = HTML_TEMPLATE.index("function caseValidatorState(state=requestState)")
    end = HTML_TEMPLATE.index("function coverageUnusedGroups(coverage)", start)
    helpers = HTML_TEMPLATE[start:end]
    script = f"""
const asObj = value => value && typeof value === "object" && !Array.isArray(value) ? value : {{}};
const asArray = value => Array.isArray(value) ? value : [];
const contextText = value => String(value ?? "").trim();
let requestState = {{}};
{helpers}
const duplicate = caseMatrixBlocksWordExport({{review:{{validator:{{blocking:[{{code:"case_matrix.duplicate"}}], coverage:{{complete:true}}}}}}}});
const coverage = caseMatrixBlocksWordExport({{review:{{validator:{{blocking:[], coverage:{{complete:false}}}}}}}});
const missing = caseMatrixBlocksWordExport({{review:{{validator:{{blocking:[], coverage:{{}}}}}}}});
const selectionMissing = caseMatrixBlocksWordExport({{review:{{validator:{{blocking:[{{code:"case_matrix.geometry_missing"}}], coverage:{{complete:true}}}}}}}});
process.stdout.write(JSON.stringify({{duplicate, coverage, missing, selectionMissing}}));
"""
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=False
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "duplicate": True,
        "coverage": True,
        "missing": False,
        "selectionMissing": False,
    }


def test_case_next_blocks_configuration_errors_but_allows_coverage_warning_review():
    start = HTML_TEMPLATE.index("async function confirmCaseConfiguration()")
    end = HTML_TEMPLATE.index("function renderDerivedPanels()", start)
    confirmation = HTML_TEMPLATE[start:end]
    script = f"""
(async () => {{
  const action = {{disabled:false}};
  const $ = id => id === "caseConfirmNextBtn" ? action : null;
  const asObj = value => value && typeof value === "object" && !Array.isArray(value) ? value : {{}};
  const asArray = value => Array.isArray(value) ? value : [];
  const contextText = value => String(value ?? "").trim();
  let requestState = {{review:{{validator:{{blocking:[]}}}}}};
  let nextScreen = "";
  let focusedIssues = 0;
  const refreshPreview = async () => true;
  const renderCasePreview = () => {{}};
  const resetCaseImpactBaseline = () => {{}};
  const caseConfigurationIssues = () => requestState.review.validator.blocking;
  const focusCaseValidationIssue = () => {{ focusedIssues += 1; }};
  const navigateScreen = screen => {{ nextScreen = screen; }};
  {confirmation}
  requestState.review.validator.blocking = [{{section:"case_matrix", code:"case_matrix.duplicate", case_no:2, duplicate_of_case_no:1}}];
  await confirmCaseConfiguration();
  const duplicateScreen = nextScreen;
  nextScreen = "";
  requestState.review.validator.blocking = [{{section:"case_matrix", code:"case_matrix.geometry_missing"}}];
  await confirmCaseConfiguration();
  const missingScreen = nextScreen;
  nextScreen = "";
  requestState.review.validator = {{blocking:[], coverage:{{complete:false}}}};
  await confirmCaseConfiguration();
  process.stdout.write(JSON.stringify({{duplicateScreen, missingScreen, warningScreen:nextScreen, focusedIssues}}));
}})().catch(error => {{ console.error(error); process.exit(1); }});
"""
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=False
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "duplicateScreen": "",
        "missingScreen": "",
        "warningScreen": "SCREEN-06",
        "focusedIssues": 2,
    }


def test_last_case_delete_uses_local_notice_and_case_manipulations_clear_it():
    mutate_start = HTML_TEMPLATE.index('function mutateCaseRows(action, caseId="")')
    mutate_end = HTML_TEMPLATE.index("function jumpToIssue", mutate_start)
    mutate = HTML_TEMPLATE[mutate_start:mutate_end]
    preserve_start = HTML_TEMPLATE.index("function preserveCaseSelections()")
    preserve_end = HTML_TEMPLATE.index("function collectState()", preserve_start)
    preserve = HTML_TEMPLATE[preserve_start:preserve_end]
    script = f"""
const asObj = value => value && typeof value === "object" && !Array.isArray(value) ? value : {{}};
const asArray = value => Array.isArray(value) ? value : [];
const contextText = value => String(value ?? "").trim();
let requestState = {{case_matrix:{{rows:[{{case_id:"case_1", geometry_id:"g1", condition_values:{{}}}}]}}}};
let lastCaseDeleteNoticeVisible = false;
let removedNotices = 0;
let scheduled = 0;
const rendered = [];
const document = {{querySelector:() => ({{remove:() => {{ removedNotices += 1; }}}})}};
const collectState = () => requestState;
const collectCaseRows = () => asArray(asObj(requestState.case_matrix).rows);
const renderCasePreview = () => {{ rendered.push(lastCaseDeleteNoticeVisible); }};
const schedulePreviewRefresh = () => {{ scheduled += 1; }};
Date.now = () => 123;
{preserve}
{mutate}
mutateCaseRows("remove", "case_1");
const blocked = {{rowCount:requestState.case_matrix.rows.length, notice:lastCaseDeleteNoticeVisible}};
mutateCaseRows("add");
const added = {{rowCount:requestState.case_matrix.rows.length, notice:lastCaseDeleteNoticeVisible}};
mutateCaseRows("remove", "case_1");
const removed = {{rowCount:requestState.case_matrix.rows.length, notice:lastCaseDeleteNoticeVisible}};
mutateCaseRows("remove", "case_123");
preserveCaseSelections();
process.stdout.write(JSON.stringify({{blocked, added, removed, selectedNotice:lastCaseDeleteNoticeVisible, removedNotices, scheduled, rendered}}));
"""
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=False
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "blocked": {"rowCount": 1, "notice": True},
        "added": {"rowCount": 2, "notice": False},
        "removed": {"rowCount": 1, "notice": False},
        "selectedNotice": False,
        "removedNotices": 1,
        "scheduled": 3,
        "rendered": [True, False, False, True],
    }
    assert 'notify("최소 1개 Case는 유지해야 합니다.")' not in mutate
    assert "마지막 Case는 삭제할 수 없습니다." in HTML_TEMPLATE
    assert "해석을 위해 최소 1개의 Case가 필요합니다." in HTML_TEMPLATE


def test_coverage_ui_groups_multiple_unused_options_by_column_key():
    start = HTML_TEMPLATE.index("function coverageUnusedGroups(coverage)")
    end = HTML_TEMPLATE.index("function coverageUnusedItemsHtml(coverage)", start)
    grouping_function = HTML_TEMPLATE[start:end]
    script = f"""
const asObj = value => value && typeof value === "object" && !Array.isArray(value) ? value : {{}};
const asArray = value => Array.isArray(value) ? value : [];
const contextText = value => String(value ?? "").trim();
{grouping_function}
const coverage = {{unused_items:[
  {{column_key:"geometry_axis", column_label:"형상", option_label:"형상 3"}},
  {{column_key:"operation_axis", column_label:"운전", option_label:"운전 2"}},
  {{column_key:"operation_axis", column_label:"운전", option_label:"운전 3"}},
  {{column_key:"spec_axis", column_label:"사양", option_label:"사양 2"}}
]}};
process.stdout.write(JSON.stringify(coverageUnusedGroups(coverage)));
"""
    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        {"label": "형상", "options": ["형상 3"]},
        {"label": "운전", "options": ["운전 2", "운전 3"]},
        {"label": "사양", "options": ["사양 2"]},
    ]
    assert 'labels.join(", ")' in HTML_TEMPLATE
    assert "가 어떤 Case에도 선택되지 않았습니다." in HTML_TEMPLATE
    assert all(key not in grouping_function for key in ("geometry_id", "fan", "heat_exchanger"))


def test_word_preview_state_keeps_coverage_and_missing_coverage_is_safe():
    collect_start = HTML_TEMPLATE.index("function collectState()")
    collect_end = HTML_TEMPLATE.index("function preserveEditorDraftBeforeRerender()", collect_start)
    collect_state = HTML_TEMPLATE[collect_start:collect_end]
    coverage_start = HTML_TEMPLATE.index("function caseValidatorState(state=requestState)")
    coverage_end = HTML_TEMPLATE.index("function coverageUnusedGroups(coverage)", coverage_start)
    coverage_function = HTML_TEMPLATE[coverage_start:coverage_end]

    assert "review: asObj(requestState.review)" in collect_state

    script = f"""
const asObj = value => value && typeof value === "object" && !Array.isArray(value) ? value : {{}};
const asArray = value => Array.isArray(value) ? value : [];
const contextText = value => String(value ?? "").trim();
let requestState = {{}};
{coverage_function}
const missing = caseCoverageState();
const present = caseCoverageState({{review:{{validator:{{coverage:{{complete:true}}}}}}}});
if (JSON.stringify(missing) !== "{{}}") throw new Error("missing coverage was not normalized");
if (present.complete !== true) throw new Error("existing coverage was not preserved");
"""
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=False
    )

    assert result.returncode == 0, result.stderr


def test_word_case_matrix_failure_updates_status_without_automatic_screen_change():
    export_start = HTML_TEMPLATE.index("async function exportWordFromPreview({useExistingPreviewDom=false}={})")
    export_end = HTML_TEMPLATE.index("function mutateRows(listName, action, index)", export_start)
    export_action = HTML_TEMPLATE[export_start:export_end]
    failure_start = export_action.index('if (asObj(error).error === "case_matrix_coverage_incomplete")')
    failure_end = export_action.index("throw new Error('Word export failed')", failure_start)
    coverage_failure = export_action[failure_start:failure_end]
    event_start = HTML_TEMPLATE.index("const action = button.dataset.action;")
    event_end = HTML_TEMPLATE.index('if (action === "add-case")', event_start)
    review_action = HTML_TEMPLATE[event_start:event_end]

    assert 'renderPreviewCaseMatrixStatus(requestState, {coverage:asObj(error).coverage})' in coverage_failure
    assert 'renderPreviewCaseMatrixStatus(requestState, {configurationIssues:asArray(error.issues)})' in coverage_failure
    assert "return false;" in coverage_failure
    assert "navigateScreen" not in coverage_failure
    assert "renderDocumentPreviewPanel" not in coverage_failure
    assert "collectState" not in coverage_failure
    assert 'if (action === "review-case-coverage") { navigateScreen("SCREEN-05"); return; }' in review_action
    assert "사용할 항목은 05 Case Matrix에서 선택하고, 필요하지 않은 항목은 입력 화면에서 삭제해 주세요." in HTML_TEMPLATE


def test_word_button_shows_progress_blocks_duplicates_and_restores_navigation_policy():
    start = HTML_TEMPLATE.index("async function runWordExportFromPreview()")
    end = HTML_TEMPLATE.index("function mutateRows(listName, action, index)", start)
    action_function = HTML_TEMPLATE[start:end]
    script = f"""
(async () => {{
  const action = {{disabled:false, textContent:"의뢰서 생성(Word)"}};
  const $ = id => id === "wordExportSlotBtn" ? action : null;
  let wordExportInProgress = false;
  let exportCalls = 0;
  let finishExport;
  const exportWordFromPreview = () => {{
    exportCalls += 1;
    return new Promise(resolve => {{ finishExport = resolve; }});
  }};
  let policyRestored = false;
  const renderScreenNavigation = () => {{ policyRestored = true; action.disabled = true; }};
  {action_function}
  const first = runWordExportFromPreview();
  const second = await runWordExportFromPreview();
  if (action.textContent !== "확인 중..." || action.disabled !== true) throw new Error("missing progress state");
  if (exportCalls !== 1 || second !== false) throw new Error("duplicate export was not blocked");
  finishExport(false);
  await first;
  if (action.textContent !== "의뢰서 생성(Word)") throw new Error("label was not restored");
  if (!policyRestored || action.disabled !== true) throw new Error("navigation disabled policy was not restored");
}})().catch(error => {{ console.error(error); process.exit(1); }});
"""
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=False
    )

    assert result.returncode == 0, result.stderr


def test_word_api_blocks_unused_coverage_before_docx_generation(monkeypatch):
    called = False
    monkeypatch.setitem(app_module.FEATURE_LOCKS, "word_export", True)

    def forbidden_docx(_preview):
        nonlocal called
        called = True
        raise AssertionError("DOCX generation must not run")

    monkeypatch.setattr(app_module, "build_word_docx", forbidden_docx)
    response = create_app().test_client().post(
        "/api/export/word",
        json={"state": _state_with_unused_operation(), "sections": []},
    )

    assert response.status_code == 409
    assert response.get_json()["error"] == "case_matrix_coverage_incomplete"
    assert response.get_json()["coverage"]["complete"] is False
    assert called is False


def test_word_api_blocks_duplicate_case_before_docx_generation(monkeypatch):
    called = False
    monkeypatch.setitem(app_module.FEATURE_LOCKS, "word_export", True)

    def forbidden_docx(_preview):
        nonlocal called
        called = True
        raise AssertionError("DOCX generation must not run")

    monkeypatch.setattr(app_module, "build_word_docx", forbidden_docx)
    response = create_app().test_client().post(
        "/api/export/word",
        json={"state": _state_with_duplicate_case(), "sections": []},
    )

    assert response.status_code == 409
    assert response.get_json()["error"] == "case_matrix_duplicate"
    assert response.get_json()["duplicate"]["case_no"] == 2
    assert response.get_json()["duplicate"]["duplicate_of_case_no"] == 1
    assert called is False


def test_word_api_blocks_missing_case_selections_before_docx_generation(monkeypatch):
    called = False
    monkeypatch.setitem(app_module.FEATURE_LOCKS, "word_export", True)

    def forbidden_docx(_preview):
        nonlocal called
        called = True
        raise AssertionError("DOCX generation must not run")

    state = _complete_state()
    condition_key = next(
        column["key"]
        for column in state["case_matrix"]["visible_columns"]
        if column.get("kind") == "condition"
    )
    row = state["case_matrix"]["rows"][0]
    row["geometry_id"] = ""
    row["auto_geometry_id"] = ""
    row["condition_values"][condition_key] = ""
    monkeypatch.setattr(app_module, "build_word_docx", forbidden_docx)

    response = create_app().test_client().post(
        "/api/export/word",
        json={"state": state, "sections": []},
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["error"] == "case_matrix_selection_missing"
    assert {issue["code"] for issue in payload["issues"]} >= {
        "case_matrix.geometry_missing",
        f"case_matrix.{condition_key}.missing",
    }

    rows_missing_state = _complete_state()
    rows_missing_state["case_matrix"]["rows"] = []
    rows_missing_response = create_app().test_client().post(
        "/api/export/word",
        json={"state": rows_missing_state, "sections": []},
    )
    assert rows_missing_response.status_code == 409
    assert {issue["code"] for issue in rows_missing_response.get_json()["issues"]} == {
        "case_matrix.rows_missing"
    }
    assert called is False


def test_word_api_keeps_existing_docx_generation_when_coverage_is_complete(monkeypatch):
    calls = []
    monkeypatch.setitem(app_module.FEATURE_LOCKS, "word_export", True)
    monkeypatch.setattr(app_module, "build_word_docx", lambda preview: calls.append(preview) or b"PK-docx")

    response = create_app().test_client().post(
        "/api/export/word",
        json={"state": _complete_state(), "sections": [{"title": "Preview", "blocks": []}]},
    )

    assert response.status_code == 200
    assert response.data == b"PK-docx"
    assert calls == [{"request_title": "", "request_no": "", "sections": [{"title": "Preview", "blocks": []}]}]
