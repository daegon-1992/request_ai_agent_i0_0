from __future__ import annotations

from request_ai_agent_i0_0.state import field_value, normalize_state
from request_ai_agent_i0_0.ui import HTML_TEMPLATE
from request_ai_agent_i0_0.validator import validate_state


EDITABLE_UNDECIDED_FIELDS = (
    ("analysis_overview.project_name", "projectNameInput", "projectNameMenu"),
    ("analysis_overview.model_suffix", "modelSuffixInput", "modelSuffixMenu"),
)


def _request_basic_section() -> str:
    start = HTML_TEMPLATE.index('id="section-request-basic"')
    end = HTML_TEMPLATE.index('</section>', start)
    return HTML_TEMPLATE[start:end]


def test_project_name_and_model_suffix_use_the_same_custom_combobox():
    section = _request_basic_section()

    assert section.count('data-undecided-combobox') == 2
    for path, input_id, menu_id in EDITABLE_UNDECIDED_FIELDS:
        assert section.count(f'data-path="{path}"') == 1
        assert (
            f'id="{input_id}" data-path="{path}" data-undecided-input role="combobox"'
            in section
        )
        assert f'id="{menu_id}" data-undecided-menu role="listbox"' in section
        assert f'data-dropdown-path="{path}"' not in section
        assert f'class="custom-input" data-path="{path}"' not in section
    assert section.count('data-undecided-mode="custom"') == 2
    assert section.count('data-undecided-mode="undecided"') == 2
    assert section.count('>직접 입력</button>') == 2
    assert section.count('>미정</button>') == 2
    assert '<datalist' not in section


def test_shared_combobox_switches_modes_in_the_same_input():
    assert 'input.readOnly = selectedMode === "undecided";' in HTML_TEMPLATE
    assert 'if (previousMode === "undecided") input.value = "";' in HTML_TEMPLATE
    assert 'input.value = "미정";' in HTML_TEMPLATE
    assert 'syncUndecidedCombobox(`analysis_overview.${key}`, value);' in HTML_TEMPLATE
    assert 'touchedFields.add(input.dataset.path || "");' in HTML_TEMPLATE
    assert 'setUndecidedComboboxOpen(combobox, false);' in HTML_TEMPLATE


def test_custom_listbox_uses_a_native_select_like_square_flat_menu():
    assert '.request-basic-grid select[data-dropdown-path]{' in HTML_TEMPLATE
    assert 'appearance:none;padding-right:42px;background-image:url(' in HTML_TEMPLATE
    assert "d='m7 9 5 5 5-5'" in HTML_TEMPLATE
    assert 'border:1px solid var(--line);border-radius:7px;background:var(--paper)' in HTML_TEMPLATE
    assert '.undecided-combobox:focus-within{outline:3px solid var(--accent);outline-offset:2px}' in HTML_TEMPLATE
    assert 'display:grid;place-items:center;border:0;border-radius:0 6px 6px 0;' in HTML_TEMPLATE
    assert '<path d="m7 9 5 5 5-5"></path>' in HTML_TEMPLATE
    assert 'top:calc(100% + 4px);left:-1px;right:-1px;padding:0;' in HTML_TEMPLATE
    assert 'border:1px solid var(--line);border-radius:0;background:var(--paper);box-shadow:none' in HTML_TEMPLATE
    assert 'border:0;border-radius:0;background:transparent;padding:5px 8px;text-align:left;cursor:default' in HTML_TEMPLATE
    assert 'undecided-combobox-check' not in HTML_TEMPLATE


def test_mouse_hover_and_keyboard_focus_share_the_native_highlight():
    assert (
        '.undecided-combobox-option:hover,\n'
        '    .undecided-combobox-option:focus,\n'
        '    .undecided-combobox-option[data-undecided-active="true"]{'
        in HTML_TEMPLATE
    )
    assert 'background-color:var(--brand)!important;color:#ffffff!important;outline:0' in HTML_TEMPLATE
    assert 'option.addEventListener("mouseenter", () => setUndecidedActiveOption(combobox, option, {focus:true}));' in HTML_TEMPLATE
    assert 'option.addEventListener("focus", () => setUndecidedActiveOption(combobox, option));' in HTML_TEMPLATE
    assert 'setUndecidedActiveOption(combobox, options[(index + direction + options.length) % options.length], {focus:true});' in HTML_TEMPLATE
    assert 'event.key === "ArrowDown" || event.key === "ArrowUp"' in HTML_TEMPLATE


def test_both_fields_accept_custom_text_and_undecided_as_completed_values():
    values_by_key = {
        "project_name": ("2026 신모델 냉방 검토", "미정"),
        "model_suffix": ("MODEL-A", "미정"),
    }
    for key, values in values_by_key.items():
        path = f"analysis_overview.{key}"
        for value in values:
            state = normalize_state({"analysis_overview": {key: value}})
            assert field_value(state["analysis_overview"][key]) == value
            assert path not in {
                issue.get("path") for issue in validate_state(state)["blocking"]
            }
