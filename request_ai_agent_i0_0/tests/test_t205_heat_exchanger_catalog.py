from __future__ import annotations

import request_ai_agent_i0_0.heat_exchanger_catalog as catalog_module
from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.condition_fieldsets import default_condition_sets, sanitize_condition_sets
from request_ai_agent_i0_0.heat_exchanger_catalog import (
    EMBEDDED_STANDARD_SPECS,
    HeatExchangerCatalogError,
    build_heat_exchanger_catalog_payload,
    embedded_heat_exchanger_catalog,
    load_heat_exchanger_catalog,
    resolve_heat_exchanger_workbook,
    validate_heat_exchanger_proposal,
)
from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def test_pressure_loss_workbook_loads_only_standard_heat_exchanger_rows():
    workbook = resolve_heat_exchanger_workbook()
    rows = load_heat_exchanger_catalog(workbook)

    assert workbook.name == "열교환기압력손실DB_Final.xlsx"
    assert len(rows) == 53
    assert rows[0] == {"tube_diameter": "5", "fin_type": "Slit(Half)", "row_count": "1", "fpi": "21"}
    assert {row["tube_diameter"] for row in rows} == {"5", "7", "W10.5", "W14.5", "W16"}
    assert {"tube_diameter": "5", "fin_type": "Slit(Half)", "row_count": "1", "fpi": "22"} not in rows


def test_embedded_catalog_matches_the_canonical_workbook():
    workbook_rows = load_heat_exchanger_catalog(resolve_heat_exchanger_workbook())

    assert len(EMBEDDED_STANDARD_SPECS) == 53
    assert embedded_heat_exchanger_catalog() == workbook_rows


def test_default_catalog_does_not_resolve_or_read_an_external_workbook(monkeypatch):
    monkeypatch.setattr(
        catalog_module,
        "resolve_heat_exchanger_workbook",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("external workbook must not be resolved")),
    )

    rows = load_heat_exchanger_catalog()
    payload = build_heat_exchanger_catalog_payload()

    assert len(rows) == 53
    assert payload["status"] == "loaded"
    assert payload["source"] == "embedded"
    assert payload["rows"] == rows


def test_heat_exchanger_catalog_is_available_from_bootstrap_and_its_api():
    client = create_app().test_client()

    bootstrap = client.get("/api/bootstrap").get_json()["heat_exchanger_catalog"]
    response = client.get("/api/heat-exchanger-catalog")
    catalog = response.get_json()

    assert response.status_code == 200
    assert bootstrap["status"] == catalog["status"] == "loaded"
    assert bootstrap["row_count"] == catalog["row_count"] == 53
    assert bootstrap["source"] == catalog["source"] == "embedded"
    assert catalog["sheet"] == "압손DB_과제결과"
    assert catalog["standard_marker"] == "O"


def test_missing_workbook_has_a_non_fatal_catalog_payload(tmp_path):
    payload = build_heat_exchanger_catalog_payload(tmp_path / "missing.xlsx")

    assert payload["status"] == "unavailable"
    assert payload["rows"] == []
    assert payload["row_count"] == 0


def test_heat_exchanger_fields_are_cascading_selects_in_database_order():
    assert 'const heatExchangerCascadeKeys = ["tube_diameter", "fin_type", "row_count", "fpi"]' in HTML_TEMPLATE
    assert 'data-heat-exchanger-field="${esc(key)}"' in HTML_TEMPLATE
    assert 'heatExchangerCascadeKeys.slice(changedIndex + 1)' in HTML_TEMPLATE
    assert 'select[data-heat-exchanger-field]' in HTML_TEMPLATE
    assert 'row_count:"열 수"' in HTML_TEMPLATE
    assert 'row_count:"행 수"' not in HTML_TEMPLATE


def test_heat_exchanger_type_is_persisted_and_micro_channel_forces_flat_fin():
    context = {"analysis_type": "일반 유동 해석", "context_locked": True}
    default_card = next(card for card in default_condition_sets(context) if card["type"] == "heat_exchanger")
    assert default_card["heat_exchanger_type"] == "Fin&Tube"

    default_card["heat_exchanger_type"] = "Micro-Channel"
    default_card["fields"].update({"tube_diameter": "W16", "fin_type": "Flat(MCC)", "row_count": "2", "fpi": "75"})
    cleaned = next(card for card in sanitize_condition_sets([default_card], context) if card["type"] == "heat_exchanger")

    assert cleaned["heat_exchanger_type"] == "Micro-Channel"
    assert cleaned["fields"]["fin_type"]["value"] == "Flat"


def test_heat_exchanger_type_selector_switches_labels_and_catalog_partitions():
    assert 'const heatExchangerTypes = ["Fin&Tube", "Micro-Channel"]' in HTML_TEMPLATE
    assert 'select data-card-id="${esc(cardId)}" data-heat-exchanger-type aria-label="HEX type"' in HTML_TEMPLATE
    assert 'return showLabel ? `<label>HEX type${select}</label>` : select;' in HTML_TEMPLATE
    assert 'const card = cards.find(item => contextText(asObj(item).id) === select.dataset.cardId);' in HTML_TEMPLATE
    assert 'cards.filter(card => contextText(asObj(card).type) === "heat_exchanger").forEach' not in HTML_TEMPLATE
    assert 'tube_diameter:"관 직경(Pi)"' in HTML_TEMPLATE
    assert 'tube_diameter:"채널 폭 (Witdth)"' in HTML_TEMPLATE
    assert 'fpi:"FPDM"' in HTML_TEMPLATE
    assert 'if (type === "Micro-Channel" && key === "fin_type") return "Flat";' in HTML_TEMPLATE
    assert 'contextText(asObj(row).tube_diameter).toUpperCase().startsWith("W")' in HTML_TEMPLATE
    assert 'card.fields.fin_type = selectedType === "Micro-Channel" ? "Flat" : "";' in HTML_TEMPLATE


def test_heat_exchanger_dropdowns_offer_the_same_custom_input_pattern_as_request_target():
    assert 'const customOption = customAllowed && !disabled ? `<option value="__custom__">직접 입력</option>` : "";' in HTML_TEMPLATE
    assert 'class="prep-custom-control heat-exchanger-custom-control"' in HTML_TEMPLATE
    assert 'data-heat-exchanger-custom-field="${esc(key)}"' in HTML_TEMPLATE
    assert 'data-heat-exchanger-restore="${esc(key)}"' in HTML_TEMPLATE
    assert 'input[data-heat-exchanger-custom-field]' in HTML_TEMPLATE
    assert 'button[data-heat-exchanger-restore]' in HTML_TEMPLATE
    assert 'const customAllowed = !(key === "fin_type" && type === "Micro-Channel")' in HTML_TEMPLATE


def test_custom_heat_exchanger_values_survive_normalization_except_micro_channel_fin():
    context = {"analysis_type": "일반 유동 해석", "context_locked": True}
    fin_tube = next(card for card in default_condition_sets(context) if card["type"] == "heat_exchanger")
    fin_tube["fields"].update({"tube_diameter": "6.35", "fin_type": "Custom Fin", "row_count": "5", "fpi": "23"})
    cleaned_fin_tube = next(card for card in sanitize_condition_sets([fin_tube], context) if card["type"] == "heat_exchanger")
    assert {key: cleaned_fin_tube["fields"][key]["value"] for key in ("tube_diameter", "fin_type", "row_count", "fpi")} == {
        "tube_diameter": "6.35",
        "fin_type": "Custom Fin",
        "row_count": "5",
        "fpi": "23",
    }

    micro_channel = next(card for card in default_condition_sets(context) if card["type"] == "heat_exchanger")
    micro_channel["heat_exchanger_type"] = "Micro-Channel"
    micro_channel["fields"].update({"tube_diameter": "W12", "fin_type": "Custom Fin", "row_count": "4", "fpi": "80"})
    cleaned_micro = next(card for card in sanitize_condition_sets([micro_channel], context) if card["type"] == "heat_exchanger")
    assert cleaned_micro["fields"]["tube_diameter"]["value"] == "W12"
    assert cleaned_micro["fields"]["fin_type"]["value"] == "Flat"
    assert cleaned_micro["fields"]["row_count"]["value"] == "4"
    assert cleaned_micro["fields"]["fpi"]["value"] == "80"


def test_catalog_mismatch_and_unavailable_allow_direct_input_but_series_shape_still_blocks(monkeypatch):
    state = {
        "conditions": {
            "condition_sets": [
                {
                    "id": "heat_exchanger_1",
                    "type": "heat_exchanger",
                    "fields": {
                        "tube_diameter": "custom diameter",
                        "fin_type": "custom fin",
                        "row_count": "custom rows",
                        "fpi": "custom fpi",
                    },
                }
            ]
        }
    }
    single_field_operation = [
        {
            "op": "set_condition_field",
            "card_id": "heat_exchanger_1",
            "field_key": "fpi",
            "value": "custom fpi",
        }
    ]

    mismatch = validate_heat_exchanger_proposal(state, single_field_operation, catalog_rows=[])
    assert mismatch["valid"] is True
    assert mismatch["alternatives"] == []

    monkeypatch.setattr(
        catalog_module,
        "load_heat_exchanger_catalog",
        lambda: (_ for _ in ()).throw(HeatExchangerCatalogError("unavailable")),
    )
    unavailable = validate_heat_exchanger_proposal(state, single_field_operation)
    assert unavailable["valid"] is True
    assert unavailable["alternatives"] == []

    mismatched_series = validate_heat_exchanger_proposal(
        state,
        [
            {
                "op": "set_condition_card_series",
                "card_type": "heat_exchanger",
                "field_key": "row_count",
                "values": ["first"],
            },
            {
                "op": "set_condition_card_series",
                "card_type": "heat_exchanger",
                "field_key": "fpi",
                "values": ["first", "second"],
            },
        ],
    )
    assert mismatched_series["valid"] is False
    assert mismatched_series["alternatives"] == []
