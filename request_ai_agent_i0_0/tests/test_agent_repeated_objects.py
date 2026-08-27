from copy import deepcopy

import pytest

from request_ai_agent_i0_0.condition_fieldsets import default_condition_sets
from request_ai_agent_i0_0.proposal_store import ProposalService
from request_ai_agent_i0_0.request_state_store import RequestStateStore
from request_ai_agent_i0_0.state import create_initial_state, field_value
from request_ai_agent_i0_0.validator import state_with_validation


def _service(analysis_type="열교환기 유속 프로파일"):
    state = create_initial_state()
    state["request_context"].update(
        {
            "business_unit": "RAC",
            "product_group": "벽걸이",
            "platform": "SK",
            "analysis_type": analysis_type,
            "context_locked": True,
        }
    )
    state["conditions"]["condition_sets"] = default_condition_sets(state["request_context"])
    requests = RequestStateStore(state_with_validation)
    created = requests.create(state)
    return requests, ProposalService(requests), created


def _cards(state, card_type):
    return [card for card in state["conditions"]["condition_sets"] if card["type"] == card_type]


def test_multiple_products_use_existing_base_and_comparison_product_adapter():
    requests, service, created = _service()
    before = deepcopy(requests.read(created.request_id))

    proposal = service.create_proposal(
        created.request_id,
        [{"op": "list_values", "path": "geometry.products", "values": ["A100", "B200"]}],
        source="main_agent_decision",
        message="A100하고 B200 두 제품을 비교할 거야",
    )

    assert requests.read(created.request_id) == before
    assert proposal.status == "pending"
    latest = service.approve_proposal(proposal.proposal_id)
    state = requests.read(created.request_id).state
    assert latest.status == "approved"
    assert field_value(state["geometry"]["base_product"]["drawing_no"]) == "A100"
    assert [field_value(card["drawing_no"]) for card in state["geometry"]["comparison_products"]] == ["B200"]


@pytest.mark.parametrize(
    ("analysis_type", "message", "card_type", "field_key", "values"),
    [
        ("열교환기 유속 프로파일", "RPM이 두 케이스이다. 800, 1000", "operating", "fan_rpm", ["800", "1000"]),
        ("열교환기 유속 프로파일", "관 직경 7, 9.52 두 조건", "heat_exchanger", "tube_diameter", ["7", "9.52"]),
        ("기류 패턴", "공간 온도 27, 30 두 개", "space_environment", "room_temp", ["27", "30"]),
        ("기류 패턴", "취출 온도 12, 14 두 건", "supply_air", "heat_exchanger_temp", ["12", "14"]),
    ],
)
def test_multiple_alternatives_are_scalar_values_on_repeated_condition_cards(
    analysis_type,
    message,
    card_type,
    field_key,
    values,
):
    requests, service, created = _service(analysis_type)
    proposal = service.create_proposal(
        created.request_id,
        [
            {
                "op": "set_condition_card_series",
                "card_type": card_type,
                "field_key": field_key,
                "values": values,
            }
        ],
        source="main_agent_decision",
        message=message,
    )
    service.approve_proposal(proposal.proposal_id)

    cards = _cards(requests.read(created.request_id).state, card_type)
    assert len(cards) == 2
    if card_type == "operating":
        actual = [card["fans"][0]["values"]["fan_rpm"] for card in cards]
        assert all(len(card["fans"]) == 1 for card in cards)
    else:
        actual = [field_value(card["fields"][field_key]) for card in cards]
    assert actual == values
    assert all(not isinstance(value, list) for value in actual)


def test_agent_condition_series_preserves_existing_ids_and_allocates_only_new_ids():
    requests, service, created = _service()
    original_id = _cards(created.state, "operating")[0]["id"]

    expanded = service.create_proposal(
        created.request_id,
        [{"op": "set_condition_card_series", "card_type": "operating", "field_key": "fan_rpm", "values": ["800", "1000", "1200"]}],
        source="main_agent_decision",
        message="운전 조건을 세 개로 설정",
    )
    service.approve_proposal(expanded.proposal_id)
    expanded_ids = [card["id"] for card in _cards(requests.read(created.request_id).state, "operating")]

    assert expanded_ids[0] == original_id
    assert len(set(expanded_ids)) == 3
    assert all(card_id.startswith("operating_") for card_id in expanded_ids)
    assert all(len(card_id) == len("operating_") + 32 for card_id in expanded_ids[1:])

    shrunk = service.create_proposal(
        created.request_id,
        [{"op": "set_condition_card_series", "card_type": "operating", "field_key": "fan_rpm", "values": ["900", "1100"]}],
        source="main_agent_decision",
        message="운전 조건을 두 개로 축소",
    )
    service.approve_proposal(shrunk.proposal_id)

    assert [card["id"] for card in _cards(requests.read(created.request_id).state, "operating")] == expanded_ids[:2]


def test_multiple_fans_stay_in_one_operating_condition():
    requests, service, created = _service()
    proposal = service.create_proposal(
        created.request_id,
        [{"op": "set_operating_fans", "card_id": "operating_1", "values": ["800", "1000"]}],
        source="main_agent_decision",
        message="팬이 2개이고 각각 800, 1000 RPM이야",
    )
    service.approve_proposal(proposal.proposal_id)

    operating = _cards(requests.read(created.request_id).state, "operating")
    assert len(operating) == 1
    assert [fan["values"]["fan_rpm"] for fan in operating[0]["fans"]] == ["800", "1000"]
