from copy import deepcopy

import pytest

from request_ai_agent_i0_0.app import create_app
from request_ai_agent_i0_0.chat_patch import apply_patch_operations
from request_ai_agent_i0_0.condition_fieldsets import make_condition_card
from request_ai_agent_i0_0.request_state_store import RequestStateStore, RequestVersionConflictError
from request_ai_agent_i0_0.state import create_initial_state
from request_ai_agent_i0_0.validator import state_with_validation


def _store() -> RequestStateStore:
    return RequestStateStore(state_with_validation)


def _state_with_operating_fans(count: int, *, legacy: bool = False) -> dict:
    state = create_initial_state()
    card = make_condition_card("operating", 1)
    if legacy:
        card.pop("fans", None)
        card["fan_rpms"] = [str(600 + index) for index in range(count)]
    else:
        card["fan_rpm_mode"] = "individual" if count > 1 else ""
        card["fans"] = [
            {
                "id": f"fan_{index + 1}",
                "name": "",
                "location": f"위치 {index + 1}",
                "running": True,
                "values": {"fan_rpm": str(600 + index)},
            }
            for index in range(count)
        ]
    state["conditions"]["condition_sets"] = [card]
    return state


def test_store_initializes_new_and_legacy_request_at_version_zero_and_returns_copies():
    store = _store()
    legacy = apply_patch_operations(
        create_initial_state(),
        [{"op": "set", "path": "analysis_overview.request_description", "value": "legacy client state"}],
    )

    created = store.create(legacy)
    fetched = store.read(created.request_id)

    assert created.version == fetched.version == 0
    assert fetched.state["analysis_overview"]["request_description"]["value"] == "legacy client state"
    fetched.state["metadata"]["rag_enabled"] = True
    assert store.read(created.request_id).state["metadata"]["rag_enabled"] is False


def test_store_cas_rejects_stale_and_failed_mutations_without_changing_state_or_version():
    store = _store()
    created = store.create(create_initial_state())
    updated = store.replace(
        created.request_id,
        0,
        {
            **created.state,
            "analysis_overview": {
                **created.state["analysis_overview"],
                "request_description": {**created.state["analysis_overview"]["request_description"], "value": "updated"},
            },
        },
    )
    before_failure = store.read(created.request_id)

    with pytest.raises(RequestVersionConflictError):
        store.replace(created.request_id, 0, create_initial_state())
    with pytest.raises(RuntimeError, match="mutation failed"):
        store.compare_and_swap(created.request_id, 1, lambda _state: (_ for _ in ()).throw(RuntimeError("mutation failed")))

    assert updated.version == 1
    assert store.read(created.request_id) == before_failure


def test_versioned_write_preserves_normalizer_validator_geometry_adapter_and_conditional_cleanup():
    store = _store()
    initial = create_initial_state()
    initial["request_context"].update(
        {
            "business_unit": "RAC",
            "product_group": "wall",
            "platform": "SK",
            "analysis_type": "일반 유동 해석",
            "context_locked": True,
        }
    )
    created = store.create(initial)
    before = deepcopy(created.state)

    updated = store.compare_and_swap(
        created.request_id,
        created.version,
        lambda current: apply_patch_operations(
            current,
            [
                {"op": "list_values", "path": "geometry.products", "values": ["A100", "B200"]},
                {"op": "condition_values", "field_key": "room_temp", "values": ["25"]},
            ],
        ),
    )

    assert before["geometry"]["base_product"]["drawing_no"]["value"] == ""
    assert updated.version == 1
    assert updated.state["geometry"]["base_product"]["drawing_no"]["value"] == "A100"
    assert [card["drawing_no"]["value"] for card in updated.state["geometry"]["comparison_products"]] == ["B200"]
    assert "products" not in updated.state["geometry"]
    assert all(card["type"] != "space_environment" for card in updated.state["conditions"]["condition_sets"])
    assert updated.state["review"]["submission"]["blocking_reasons"] == [
        issue["code"] for issue in updated.state["review"]["validator"]["blocking"]
    ]


def test_versioned_http_contract_is_additive_and_returns_conflict_without_mutation():
    app = create_app()
    client = app.test_client()
    created = client.post("/api/request/versioned", json={}).get_json()

    assert created["request_version"] == 0
    request_id = created["request_id"]
    payload = apply_patch_operations(
        deepcopy(created["state"]),
        [{"op": "set", "path": "analysis_overview.request_description", "value": "HTTP update"}],
    )
    updated = client.put(f"/api/request/versioned/{request_id}", json={"expected_version": 0, "state": payload})
    conflict = client.put(f"/api/request/versioned/{request_id}", json={"expected_version": 0, "state": created["state"]})
    latest = client.get(f"/api/request/versioned/{request_id}").get_json()

    assert updated.status_code == 200
    assert updated.get_json()["request_version"] == 1
    assert conflict.status_code == 409
    assert conflict.get_json()["error"] == "request_version_conflict"
    assert conflict.get_json()["current_version"] == 1
    assert latest["request_version"] == 1
    assert latest["state"]["analysis_overview"]["request_description"]["value"] == "HTTP update"


def test_versioned_requests_are_isolated_between_browser_workspaces():
    app = create_app()
    owner = app.test_client()
    other = app.test_client()

    created = owner.post("/api/request/versioned", json={}).get_json()
    request_id = created["request_id"]

    assert owner.get(f"/api/request/versioned/{request_id}").status_code == 200
    assert other.get(f"/api/request/versioned/{request_id}").status_code == 404
    assert other.post("/api/conversations", json={"request_id": request_id}).status_code == 404

    denied = other.put(
        f"/api/request/versioned/{request_id}",
        json={"expected_version": 0, "state": created["state"]},
    )
    assert denied.status_code == 404
    assert owner.get(f"/api/request/versioned/{request_id}").get_json()["request_version"] == 0


def test_versioned_api_accepts_ten_fans_and_rejects_eleven_without_state_or_version_changes():
    app = create_app()
    client = app.test_client()
    requests = app.extensions["request_state_store"]
    rejected_create = client.post("/api/request/versioned", json={"state": _state_with_operating_fans(11)})

    assert rejected_create.status_code == 400
    assert rejected_create.get_json() == {
        "ok": False,
        "error": "operating_fan_count_exceeds_limit",
        "message": "한 운전 조건에는 Fan을 최대 10개까지 설정할 수 있습니다.",
        "state_changed": False,
    }
    assert len(requests._records) == 0

    created_response = client.post("/api/request/versioned", json={"state": _state_with_operating_fans(10)})
    assert created_response.status_code == 201
    created = created_response.get_json()
    request_id = created["request_id"]
    assert created["request_version"] == 0
    assert len(created["state"]["conditions"]["condition_sets"][0]["fans"]) == 10

    accepted_state = deepcopy(created["state"])
    accepted_state["analysis_overview"]["request_description"]["value"] = "10 Fan PUT"
    accepted_put = client.put(
        f"/api/request/versioned/{request_id}",
        json={"expected_version": 0, "state": accepted_state},
    )
    assert accepted_put.status_code == 200
    assert accepted_put.get_json()["request_version"] == 1

    before_rejection = requests.read(request_id)
    rejected_put = client.put(
        f"/api/request/versioned/{request_id}",
        json={"expected_version": 1, "state": _state_with_operating_fans(11, legacy=True)},
    )
    assert rejected_put.status_code == 400
    assert rejected_put.get_json()["error"] == "operating_fan_count_exceeds_limit"
    assert rejected_put.get_json()["state_changed"] is False
    assert requests.read(request_id) == before_rejection
