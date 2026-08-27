from copy import deepcopy
from threading import Event, Thread

import pytest

from request_ai_agent_i0_0.chat_patch import apply_patch_operations
from request_ai_agent_i0_0.proposal_store import ProposalService
from request_ai_agent_i0_0.request_state_store import RequestStateStore
from request_ai_agent_i0_0.state import create_initial_state
from request_ai_agent_i0_0.validator import state_with_validation


def _service_with_prior_value():
    requests = RequestStateStore(state_with_validation)
    initial = apply_patch_operations(
        create_initial_state(),
        [{"op": "set", "path": "analysis_overview.request_description", "value": "before undo"}],
    )
    request = requests.create(initial)
    service = ProposalService(requests)
    original = service.create_proposal(
        request.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "after approval"}],
        source="orchestrator_llm",
    )
    return requests, service, request, original


def test_undo_creates_server_evidenced_pending_inverse_at_latest_version_without_mutating_request():
    requests, service, request, original = _service_with_prior_value()
    approved = service.approve_proposal(original.proposal_id)
    before_undo = requests.read(request.request_id)

    result = service.create_undo_proposal(original.proposal_id)

    assert approved.status == "approved"
    assert result.code == "undo_proposal_created"
    assert result.proposal is not None
    inverse = result.proposal
    assert inverse.status == "pending"
    assert inverse.undo_of == original.proposal_id
    assert inverse.source == "server_inverse"
    assert inverse.base_version == before_undo.version == approved.result["request_version"]
    assert inverse.operations[0]["value"] == "before undo"
    assert inverse.diff_summary["changed_path_count"] > 0
    assert requests.read(request.request_id) == before_undo
    assert service.proposal_count() == 2

    inverse_approved = service.approve_proposal(inverse.proposal_id)
    latest = requests.read(request.request_id)
    assert inverse_approved.status == "approved"
    assert latest.version == before_undo.version + 1
    assert latest.state["analysis_overview"]["request_description"]["value"] == "before undo"


def test_undo_rejects_unknown_nonapproved_missing_evidence_stale_and_duplicate_without_new_mutation():
    requests, service, request, original = _service_with_prior_value()
    before = requests.read(request.request_id)
    assert service.create_undo_proposal("proposal_missing").code == "undo_proposal_not_found"
    assert service.create_undo_proposal(original.proposal_id).code == "undo_not_approved"
    assert requests.read(request.request_id) == before
    assert service.proposal_count() == 1
    service.reject_proposal(original.proposal_id)

    no_evidence = service.create_proposal(
        request.request_id,
        [{"op": "list_values", "path": "geometry.products", "values": ["DRAW-A"]}],
        source="orchestrator_llm",
    )
    service.approve_proposal(no_evidence.proposal_id)
    after_no_evidence = requests.read(request.request_id)
    assert service.create_undo_proposal(no_evidence.proposal_id).code == "undo_inverse_evidence_unavailable"
    assert requests.read(request.request_id) == after_no_evidence

    # A later Request write is never overwritten by an old approved Proposal.
    stale_original = service.create_proposal(
        request.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "newer original"}],
        source="orchestrator_llm",
    )
    service.approve_proposal(stale_original.proposal_id)
    current = requests.read(request.request_id)
    requests.replace(request.request_id, current.version, current.state)
    stale_before = requests.read(request.request_id)
    assert service.create_undo_proposal(stale_original.proposal_id).code == "undo_stale"
    assert requests.read(request.request_id) == stale_before

    fresh = service.create_proposal(
        request.request_id,
        [{"op": "set", "path": "analysis_overview.request_description", "value": "duplicate original"}],
        source="orchestrator_llm",
    )
    service.approve_proposal(fresh.proposal_id)
    first = service.create_undo_proposal(fresh.proposal_id)
    assert first.proposal is not None
    count = service.proposal_count()
    assert service.create_undo_proposal(fresh.proposal_id).code == "undo_duplicate"
    assert service.proposal_count() == count


def test_undo_version_fence_blocks_a_queued_request_write_until_inverse_ledger_record(monkeypatch):
    requests, service, request, original = _service_with_prior_value()
    service.approve_proposal(original.proposal_id)
    store = service._proposal_store
    original_record = store._record
    write_started = Event()
    write_finished = Event()
    writer: Thread | None = None

    def queued_write():
        write_started.set()
        current = requests.read(request.request_id)
        requests.replace(request.request_id, current.version, current.state)
        write_finished.set()

    def record_after_writer_is_queued(snapshot):
        nonlocal writer
        writer = Thread(target=queued_write)
        writer.start()
        assert write_started.wait(1)
        assert not write_finished.wait(0.05)  # Request lock is the Undo version fence.
        return original_record(snapshot)

    monkeypatch.setattr(store, "_record", record_after_writer_is_queued)
    result = service.create_undo_proposal(original.proposal_id)
    assert result.code == "undo_proposal_created"
    assert result.proposal is not None
    assert result.proposal.base_version == 1
    assert writer is not None
    writer.join(timeout=1)
    assert write_finished.is_set()
    # The queued write is later than the inverse ledger record and may make its
    # approval stale, but it cannot create the old read-then-record race.
    assert requests.read(request.request_id).version == 2


@pytest.mark.parametrize("failure", ["apply", "validation"])
def test_inverse_approval_failures_remain_terminal_and_preserve_request(monkeypatch, failure):
    requests, service, request, original = _service_with_prior_value()
    service.approve_proposal(original.proposal_id)
    inverse = service.create_undo_proposal(original.proposal_id).proposal
    assert inverse is not None
    before = deepcopy(requests.read(request.request_id))
    if failure == "apply":
        monkeypatch.setattr(
            "request_ai_agent_i0_0.proposal_store.apply_patch_operations",
            lambda _state, _operations: (_ for _ in ()).throw(ValueError("inverse apply failed")),
        )
    else:
        requests._normalize_state = lambda _state: (_ for _ in ()).throw(ValueError("inverse validation failed"))

    terminal = service.approve_proposal(inverse.proposal_id)
    assert terminal.status == "failed"
    assert requests.read(request.request_id) == before
    assert service.create_undo_proposal(original.proposal_id).code == "undo_already_resolved"
