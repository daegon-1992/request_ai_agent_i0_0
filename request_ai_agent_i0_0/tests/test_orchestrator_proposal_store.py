from copy import deepcopy

import pytest

from request_ai_agent_i0_0.chat_patch import apply_patch_operations
from request_ai_agent_i0_0.request_state_store import RequestNotFoundError, RequestStateStore, RequestVersionConflictError
from request_ai_agent_i0_0.proposal_store import (
    PendingProposalExistsError,
    ProposalCapacityError,
    ProposalNotFoundError,
    ProposalService,
    ProposalStore,
    ProposalValidationError,
)
from request_ai_agent_i0_0.state import create_initial_state
from request_ai_agent_i0_0.validator import state_with_validation


def _service() -> tuple[RequestStateStore, ProposalService]:
    requests = RequestStateStore(state_with_validation)
    return requests, ProposalService(requests)


def test_proposal_creation_reads_server_request_and_keeps_request_state_and_version_unchanged():
    requests, service = _service()
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)

    proposal = service.create_proposal(
        created.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "Proposal candidate"}],
        source="llm_structured_output",
        message="update description",
        client_base_version=created.version,
    )
    fetched = service.read_proposal(proposal.proposal_id)

    assert proposal.request_id == created.request_id
    assert proposal.base_version == created.version
    assert proposal.status == "pending"
    assert proposal.operations[0]["source"] == "llm_structured_output"
    assert proposal.diff_summary["changed_paths"]
    assert proposal.created_at
    assert fetched == proposal
    fetched.operations[0]["value"] = "forged local copy"
    assert service.read_proposal(proposal.proposal_id).operations[0]["value"] == "Proposal candidate"
    assert requests.read(created.request_id) == before


@pytest.mark.parametrize(
    "operations",
    [
        "not an operation list",
        [{"op": "delete", "path": "analysis_overview.request_description"}],
        [{"op": "set", "path": "analysis_overview.request_description", "value": ""}],
    ],
)
def test_invalid_or_unsupported_proposals_do_not_mutate_request_or_ledger(operations):
    requests, service = _service()
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)

    with pytest.raises(ProposalValidationError):
        service.create_proposal(created.request_id, operations, source="llm_structured_output")

    assert requests.read(created.request_id) == before
    assert service.proposal_count() == 0


def test_unknown_request_and_stale_client_base_version_do_not_create_proposals():
    requests, service = _service()
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)
    operation = [{"op": "set", "path": "analysis_overview.request_description", "value": "candidate"}]

    with pytest.raises(RequestNotFoundError):
        service.create_proposal("missing-request", operation, source="llm_structured_output")
    with pytest.raises(RequestVersionConflictError):
        service.create_proposal(created.request_id, operation, source="llm_structured_output", client_base_version=1)

    assert requests.read(created.request_id) == before
    assert service.proposal_count() == 0


def test_proposal_storage_failure_keeps_request_and_existing_ledger_unchanged():
    requests = RequestStateStore(state_with_validation)
    service = ProposalService(requests, ProposalStore(max_proposals=1))
    created = requests.create(create_initial_state())
    first = service.create_proposal(
        created.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "first candidate"}],
        source="llm_structured_output",
    )
    before_request = requests.read(created.request_id)
    before_proposal = service.read_proposal(first.proposal_id)
    other = requests.create(create_initial_state())

    with pytest.raises(ProposalCapacityError):
        service.create_proposal(
            other.request_id,
            [{"op": "set", "path": "analysis_overview.project_name", "value": "second candidate"}],
            source="llm_structured_output",
        )

    assert requests.read(created.request_id) == before_request
    assert service.proposal_count() == 1
    assert service.read_proposal(first.proposal_id) == before_proposal


def test_request_allows_only_one_pending_proposal_until_the_first_is_terminal():
    requests, service = _service()
    created = requests.create(create_initial_state())
    first = service.create_proposal(
        created.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "first"}],
        source="llm_structured_output",
    )

    with pytest.raises(PendingProposalExistsError) as exc_info:
        service.create_proposal(
            created.request_id,
            [{"op": "set", "path": "analysis_overview.project_name", "value": "second"}],
            source="llm_structured_output",
        )

    assert exc_info.value.proposal_id == first.proposal_id
    assert service.proposal_count() == 1
    assert service.pending_proposal_for_request(created.request_id) == first


def test_proposal_dry_run_reuses_geometry_adapter_and_canonical_finalization():
    requests, service = _service()
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
    created = requests.create(initial)
    operations = [
        {"op": "list_values", "path": "geometry.products", "values": ["A100", "B200"]},
        {"op": "condition_values", "field_key": "room_temp", "values": ["25"]},
    ]
    expected = apply_patch_operations(deepcopy(created.state), operations)

    proposal = service.create_proposal(created.request_id, operations, source="llm_structured_output")

    assert proposal.operations[0]["adapter"] == "geometry_products_to_complete_product_cards"
    assert expected["geometry"]["base_product"]["drawing_no"]["value"] == "A100"
    assert "products" not in expected["geometry"]
    assert all(card["type"] != "space_environment" for card in expected["conditions"]["condition_sets"])
    assert proposal.validation == expected["review"]
    assert requests.read(created.request_id) == created


def test_approve_uses_only_server_record_and_applies_once_through_cas(monkeypatch):
    requests, service = _service()
    created = requests.create(create_initial_state())
    proposal = service.create_proposal(
        created.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "server proposal"}],
        source="llm_structured_output",
    )
    calls = 0
    original_apply = apply_patch_operations

    def tracked_apply(state, operations):
        nonlocal calls
        calls += 1
        return original_apply(state, operations)

    monkeypatch.setattr("request_ai_agent_i0_0.proposal_store.apply_patch_operations", tracked_apply)

    approved = service.approve_proposal(proposal.proposal_id)
    replay = service.approve_proposal(proposal.proposal_id)
    latest = requests.read(created.request_id)

    assert approved.status == replay.status == "approved"
    assert approved.result["state_changed"] is True
    assert approved.result["request_version"] == 1
    assert calls == 1
    assert latest.version == 1
    assert latest.state["analysis_overview"]["request_description"]["value"] == "server proposal"


@pytest.mark.parametrize("decision, status", [("reject_proposal", "rejected"), ("expire_proposal", "expired")])
def test_reject_and_expire_are_terminal_without_request_mutation(decision, status):
    requests, service = _service()
    created = requests.create(create_initial_state())
    proposal = service.create_proposal(
        created.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "not applied"}],
        source="llm_structured_output",
    )
    before = requests.read(created.request_id)

    terminal = getattr(service, decision)(proposal.proposal_id)
    replay = service.approve_proposal(proposal.proposal_id)

    assert terminal.status == replay.status == status
    assert terminal.result["state_changed"] is False
    assert terminal.resolved_at
    assert requests.read(created.request_id) == before


@pytest.mark.parametrize("decision", ["approve_proposal", "reject_proposal", "expire_proposal"])
def test_unknown_proposal_cannot_change_request(decision):
    requests, service = _service()
    created = requests.create(create_initial_state())
    before = requests.read(created.request_id)

    with pytest.raises(ProposalNotFoundError):
        getattr(service, decision)("proposal_missing")

    assert requests.read(created.request_id) == before


def test_stale_approval_records_conflict_without_request_mutation():
    requests, service = _service()
    created = requests.create(create_initial_state())
    proposal = service.create_proposal(
        created.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "stale"}],
        source="llm_structured_output",
    )
    current = requests.replace(created.request_id, created.version, created.state)
    before = requests.read(created.request_id)

    terminal = service.approve_proposal(proposal.proposal_id)

    assert terminal.status == "conflicted"
    assert terminal.result["state_changed"] is False
    assert terminal.result["outcome"] == "conflicted"
    assert requests.read(created.request_id) == before
    assert current.version == before.version == 1


def test_apply_failure_is_terminal_and_preserves_request(monkeypatch):
    requests, service = _service()
    created = requests.create(create_initial_state())
    proposal = service.create_proposal(
        created.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "fails"}],
        source="llm_structured_output",
    )
    before = requests.read(created.request_id)

    def fail_apply(_state, _operations):
        raise ValueError("apply failed")

    monkeypatch.setattr("request_ai_agent_i0_0.proposal_store.apply_patch_operations", fail_apply)
    terminal = service.approve_proposal(proposal.proposal_id)
    replay = service.approve_proposal(proposal.proposal_id)

    assert terminal.status == replay.status == "failed"
    assert terminal.result["state_changed"] is False
    assert terminal.result["error"] == "apply failed"
    assert requests.read(created.request_id) == before


def test_validation_failure_is_terminal_and_preserves_request():
    fail_validation = False

    def normalizer(state):
        if fail_validation:
            raise ValueError("validation failed")
        return state_with_validation(state)

    requests = RequestStateStore(normalizer)
    service = ProposalService(requests)
    created = requests.create(create_initial_state())
    proposal = service.create_proposal(
        created.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "validation fails"}],
        source="llm_structured_output",
    )
    before = requests.read(created.request_id)
    fail_validation = True

    terminal = service.approve_proposal(proposal.proposal_id)

    assert terminal.status == "failed"
    assert terminal.result["state_changed"] is False
    assert terminal.result["error"] == "validation failed"
    assert requests.read(created.request_id) == before


def test_approved_apply_preserves_geometry_adapter_conditional_cleanup_and_validation():
    requests, service = _service()
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
    created = requests.create(initial)
    operations = [
        {"op": "list_values", "path": "geometry.products", "values": ["A100", "B200"]},
        {"op": "condition_values", "field_key": "room_temp", "values": ["25"]},
    ]
    expected = apply_patch_operations(deepcopy(created.state), operations)
    proposal = service.create_proposal(
        created.request_id,
        operations,
        source="llm_structured_output",
    )

    approved = service.approve_proposal(proposal.proposal_id)
    latest = requests.read(created.request_id)

    assert approved.status == "approved"
    assert latest.version == 1
    assert latest.state["geometry"]["base_product"]["drawing_no"]["value"] == "A100"
    assert [card["drawing_no"]["value"] for card in latest.state["geometry"]["comparison_products"]] == ["B200"]
    assert "products" not in latest.state["geometry"]
    assert all(card["type"] != "space_environment" for card in latest.state["conditions"]["condition_sets"])
    assert latest.state == expected
    assert latest.state["review"]["submission"]["blocking_reasons"] == [
        issue["code"] for issue in latest.state["review"]["validator"]["blocking"]
    ]
