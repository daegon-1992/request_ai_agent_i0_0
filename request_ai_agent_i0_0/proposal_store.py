"""Runtime Proposal ledger and lifecycle on the server-owned Request boundary.

The ledger is process-local like ``RequestStateStore``.  Its lifecycle lock
keeps a terminal decision and its optional CAS apply in one runtime-critical
section, so one server-issued Proposal cannot apply twice in this process.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Iterable, Mapping
from uuid import uuid4

from .chat_patch import apply_patch_operations, proposal_from_operations, sanitize_external_operations
from .request_state_store import RequestStateSnapshot, RequestStateStore, RequestVersionConflictError
from .state import field_value


MAX_PROPOSALS = 256
MAX_OPERATIONS = 32
MAX_DIFF_PATHS = 64


class ProposalNotFoundError(KeyError):
    """Raised when a server-issued Proposal id is absent from this runtime ledger."""


class ProposalValidationError(ValueError):
    """Raised before a Proposal is recorded when its candidate is unsafe."""


class PendingProposalExistsError(RuntimeError):
    """Raised when a Request already owns a pending Proposal."""

    def __init__(self, request_id: str, proposal_id: str) -> None:
        super().__init__("request_pending_proposal_exists")
        self.request_id = request_id
        self.proposal_id = proposal_id


class ProposalCapacityError(RuntimeError):
    """Raised when the bounded process-local ledger is full."""


@dataclass(frozen=True)
class ProposalSnapshot:
    proposal_id: str
    request_id: str
    base_version: int
    operations: list[dict[str, Any]]
    diff_summary: dict[str, Any]
    source: str
    status: str
    validation: dict[str, Any]
    result: dict[str, Any]
    created_at: str
    resolved_at: str | None = None
    # Server-only evidence captured at dry-run time.  It is intentionally not
    # a Request snapshot and is present only when a canonical inverse can be
    # proven without interpreting values, targets, or units.
    inverse_evidence: dict[str, Any] = field(default_factory=dict)
    # A server-issued inverse Proposal records its original ledger reference.
    undo_of: str | None = None


@dataclass(frozen=True)
class UndoProposalResult:
    """Read-only result of an explicit server-ledger Undo request."""

    code: str
    proposal: ProposalSnapshot | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _copy_snapshot(snapshot: ProposalSnapshot) -> ProposalSnapshot:
    return ProposalSnapshot(**deepcopy(asdict(snapshot)))


def _changed_paths(before: Any, after: Any, prefix: str = "") -> list[str]:
    """Bounded structural diff of the existing canonical and dry-run states."""

    if isinstance(before, Mapping) and isinstance(after, Mapping):
        paths: list[str] = []
        for key in sorted(set(before) | set(after)):
            child = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_changed_paths(before.get(key), after.get(key), child))
            if len(paths) >= MAX_DIFF_PATHS:
                return paths[:MAX_DIFF_PATHS]
        return paths
    if isinstance(before, list) and isinstance(after, list):
        if before == after:
            return []
        return [prefix or "$list"]
    return [] if before == after else [prefix or "$state"]


def _canonical_set_value(state: Mapping[str, Any], path: str) -> Any:
    """Read one allowed set target without turning it into a State snapshot."""

    section_key, field_key = path.split(".", 1)
    section = state.get(section_key)
    if not isinstance(section, Mapping) or field_key not in section:
        return None
    return field_value(section.get(field_key), None)


def _inverse_evidence(
    before_state: Mapping[str, Any],
    after_state: Mapping[str, Any],
    operations: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Capture only fully proven inverse operations for canonical set fields.

    List/condition adapters can change canonical structures and normalizer
    outputs, so they deliberately receive no Undo evidence in this stage.
    """

    inverse_operations: list[dict[str, Any]] = []
    expected_current: dict[str, Any] = {}
    seen_paths: set[str] = set()
    for operation in operations:
        if operation.get("op") != "set" or not isinstance(operation.get("path"), str):
            return {}
        path = operation["path"]
        if path in seen_paths:
            return {}
        seen_paths.add(path)
        before = _canonical_set_value(before_state, path)
        after = _canonical_set_value(after_state, path)
        # Empty prior values cannot be safely expressed by the existing patch
        # contract, which intentionally rejects empty set operations.
        if before is None or after is None or not str(before).strip() or before == after:
            return {}
        inverse_operations.append(
            {
                "op": "set",
                "path": path,
                "value": deepcopy(before),
                "label": f"Undo {path}",
                "confidence": "high",
                "source": "server_inverse",
            }
        )
        expected_current[path] = deepcopy(after)
    if not inverse_operations:
        return {}
    return {
        "kind": "canonical_set_inverse_v1",
        "inverse_operations": inverse_operations,
        "expected_current_values": expected_current,
    }


def _inverse_evidence_matches(state: Mapping[str, Any], evidence: Mapping[str, Any]) -> bool:
    expected = evidence.get("expected_current_values")
    if not isinstance(expected, Mapping) or not expected:
        return False
    return all(isinstance(path, str) and _canonical_set_value(state, path) == value for path, value in expected.items())


class ProposalStore:
    """Small server-side Proposal ledger; writes are service-internal only."""

    def __init__(self, *, max_proposals: int = MAX_PROPOSALS) -> None:
        if isinstance(max_proposals, bool) or not isinstance(max_proposals, int) or max_proposals < 1:
            raise ValueError("max_proposals must be a positive integer")
        self._max_proposals = max_proposals
        self._records: dict[str, ProposalSnapshot] = {}
        self._lock = RLock()
        # Shared by every service using this ledger.  It deliberately spans
        # the Request CAS so replay cannot observe a still-pending record.
        self._lifecycle_lock = RLock()

    def _record(self, snapshot: ProposalSnapshot) -> ProposalSnapshot:
        with self._lock:
            if len(self._records) >= self._max_proposals:
                raise ProposalCapacityError("proposal_ledger_full")
            self._records[snapshot.proposal_id] = _copy_snapshot(snapshot)
            return _copy_snapshot(snapshot)

    def _read(self, proposal_id: str) -> ProposalSnapshot:
        with self._lock:
            snapshot = self._records.get(proposal_id)
            if snapshot is None:
                raise ProposalNotFoundError(proposal_id)
            return _copy_snapshot(snapshot)

    def _count(self) -> int:
        with self._lock:
            return len(self._records)

    def _replace(self, snapshot: ProposalSnapshot) -> ProposalSnapshot:
        with self._lock:
            if snapshot.proposal_id not in self._records:
                raise ProposalNotFoundError(snapshot.proposal_id)
            self._records[snapshot.proposal_id] = _copy_snapshot(snapshot)
            return _copy_snapshot(snapshot)

    def _find_inverse(self, original_proposal_id: str) -> ProposalSnapshot | None:
        with self._lock:
            for snapshot in self._records.values():
                if snapshot.undo_of == original_proposal_id:
                    return _copy_snapshot(snapshot)
        return None

    def _pending_for_request(self, request_id: str) -> ProposalSnapshot | None:
        with self._lock:
            for snapshot in self._records.values():
                if snapshot.request_id == request_id and snapshot.status == "pending":
                    return _copy_snapshot(snapshot)
        return None


class ProposalService:
    """Creates and resolves server-recorded Proposals without public HTTP surface."""

    def __init__(self, request_store: RequestStateStore, proposal_store: ProposalStore | None = None) -> None:
        self._request_store = request_store
        self._proposal_store = proposal_store or ProposalStore()

    def create_proposal(
        self,
        request_id: str,
        operations: Iterable[Mapping[str, Any]],
        *,
        source: str,
        message: str = "",
        client_base_version: int | None = None,
    ) -> ProposalSnapshot:
        with self._proposal_store._lifecycle_lock:
            request = self._request_store.read(request_id)
            self._validate_client_version(client_base_version, request.version, request_id)
            self._raise_if_request_pending(request_id)
            return self._create_proposal_from_request(request, operations, source=source, message=message)

    def _create_proposal_from_request(
        self,
        request: RequestStateSnapshot,
        operations: Iterable[Mapping[str, Any]],
        *,
        source: str,
        message: str,
    ) -> ProposalSnapshot:
        supplied_operations = self._validate_operations(operations, source, request.state)

        # This existing helper owns normalized operation construction and keeps
        # the legacy geometry.products DTO on the canonical Adapter path.
        patch_proposal = proposal_from_operations(message, supplied_operations, source=source, state=request.state)
        normalized = patch_proposal["operations"]
        dry_run_state = apply_patch_operations(request.state, normalized)
        paths = _changed_paths(request.state, dry_run_state)
        if not paths:
            raise ProposalValidationError("operations do not change canonical Request State")
        validation = deepcopy(dry_run_state.get("review", {})) if isinstance(dry_run_state.get("review"), Mapping) else {}
        snapshot = ProposalSnapshot(
            proposal_id=f"proposal_{uuid4().hex}",
            request_id=request.request_id,
            base_version=request.version,
            operations=deepcopy(normalized),
            diff_summary={"changed_paths": paths, "changed_path_count": len(paths), "truncated": len(paths) >= MAX_DIFF_PATHS},
            source=source.strip(),
            status="pending",
            validation=validation,
            result={"state_changed": False, "dry_run_state_changed": bool(paths), "read_only": True},
            created_at=_utc_now(),
            inverse_evidence=_inverse_evidence(request.state, dry_run_state, normalized),
        )
        return self._proposal_store._record(snapshot)

    def read_proposal(self, proposal_id: str) -> ProposalSnapshot:
        return self._proposal_store._read(proposal_id)

    def proposal_count(self) -> int:
        """Return the server ledger size without exposing its write surface."""

        return self._proposal_store._count()

    def pending_proposal_for_request(self, request_id: str) -> ProposalSnapshot | None:
        """Read the single pending ledger entry, if any, without creating one."""

        with self._proposal_store._lifecycle_lock:
            return self._proposal_store._pending_for_request(request_id)

    def _raise_if_request_pending(self, request_id: str) -> None:
        pending = self._proposal_store._pending_for_request(request_id)
        if pending is not None:
            raise PendingProposalExistsError(request_id, pending.proposal_id)

    def create_undo_proposal(self, proposal_id: str) -> UndoProposalResult:
        """Create one inverse dry-run from server-recorded approved evidence.

        This is deliberately narrower than a rollback: the original approval
        must still be the latest Request write, and only evidence recorded by
        this server at original dry-run time may supply inverse values.
        """

        with self._proposal_store._lifecycle_lock:
            try:
                original = self._proposal_store._read(proposal_id)
            except ProposalNotFoundError:
                return UndoProposalResult("undo_proposal_not_found")
            if original.status != "approved" or original.undo_of is not None:
                return UndoProposalResult("undo_not_approved")
            existing = self._proposal_store._find_inverse(original.proposal_id)
            if existing is not None:
                return UndoProposalResult("undo_duplicate" if existing.status == "pending" else "undo_already_resolved")
            evidence = original.inverse_evidence
            inverse_operations = evidence.get("inverse_operations") if isinstance(evidence, Mapping) else None
            approved_version = original.result.get("request_version") if isinstance(original.result, Mapping) else None
            if (
                not isinstance(evidence, Mapping)
                or evidence.get("kind") != "canonical_set_inverse_v1"
                or not isinstance(inverse_operations, list)
                or not inverse_operations
                or isinstance(approved_version, bool)
                or not isinstance(approved_version, int)
            ):
                return UndoProposalResult("undo_inverse_evidence_unavailable")
            try:
                latest = self._request_store.read(original.request_id)
            except Exception:
                return UndoProposalResult("undo_request_unavailable")
            if latest.version != approved_version:
                return UndoProposalResult("undo_stale")
            if not _inverse_evidence_matches(latest.state, evidence):
                return UndoProposalResult("undo_conflicted")
            try:
                self._raise_if_request_pending(original.request_id)
                inverse = self._request_store.at_version(
                    original.request_id,
                    latest.version,
                    lambda current: self._create_proposal_from_request(
                        current,
                        inverse_operations,
                        source="server_inverse",
                        message=f"Undo of server Proposal {original.proposal_id}",
                    ),
                )
            except RequestVersionConflictError:
                return UndoProposalResult("undo_stale")
            except Exception:
                return UndoProposalResult("undo_creation_failed")
            linked = self._proposal_store._replace(
                ProposalSnapshot(
                    proposal_id=inverse.proposal_id,
                    request_id=inverse.request_id,
                    base_version=inverse.base_version,
                    operations=deepcopy(inverse.operations),
                    diff_summary=deepcopy(inverse.diff_summary),
                    source=inverse.source,
                    status=inverse.status,
                    validation=deepcopy(inverse.validation),
                    result=deepcopy(inverse.result),
                    created_at=inverse.created_at,
                    resolved_at=inverse.resolved_at,
                    inverse_evidence=deepcopy(inverse.inverse_evidence),
                    undo_of=original.proposal_id,
                )
            )
            return UndoProposalResult("undo_proposal_created", linked)

    def approve_proposal(self, proposal_id: str) -> ProposalSnapshot:
        """Apply one pending server Proposal through its recorded Request CAS.

        No caller-provided Request, version, Proposal, or operations participate
        in this path.  A replay returns the already-terminal server record.
        """

        with self._proposal_store._lifecycle_lock:
            proposal = self._proposal_store._read(proposal_id)
            if proposal.status != "pending":
                return proposal
            try:
                updated = self._request_store.compare_and_swap(
                    proposal.request_id,
                    proposal.base_version,
                    lambda current: apply_patch_operations(current, proposal.operations),
                )
            except RequestVersionConflictError as exc:
                return self._terminal(proposal, "conflicted", error=str(exc))
            except Exception as exc:
                return self._terminal(proposal, "failed", error=str(exc))
            return self._terminal(proposal, "approved", request_version=updated.version)

    def reject_proposal(self, proposal_id: str) -> ProposalSnapshot:
        """Record rejection for one pending server Proposal without Request mutation."""

        return self._resolve_without_apply(proposal_id, "rejected")

    def expire_proposal(self, proposal_id: str) -> ProposalSnapshot:
        """Record expiration for one pending server Proposal without Request mutation."""

        return self._resolve_without_apply(proposal_id, "expired")

    def _resolve_without_apply(self, proposal_id: str, status: str) -> ProposalSnapshot:
        with self._proposal_store._lifecycle_lock:
            proposal = self._proposal_store._read(proposal_id)
            if proposal.status != "pending":
                return proposal
            return self._terminal(proposal, status)

    def _terminal(
        self,
        proposal: ProposalSnapshot,
        status: str,
        *,
        request_version: int | None = None,
        error: str | None = None,
    ) -> ProposalSnapshot:
        """Persist one immutable terminal record while the lifecycle lock is held."""

        result = deepcopy(proposal.result)
        result.update(
            {
                "state_changed": status == "approved",
                "read_only": status != "approved",
                "outcome": status,
            }
        )
        if request_version is not None:
            result["request_version"] = request_version
        if error is not None:
            result["error"] = error
        return self._proposal_store._replace(
            ProposalSnapshot(
                proposal_id=proposal.proposal_id,
                request_id=proposal.request_id,
                base_version=proposal.base_version,
                operations=deepcopy(proposal.operations),
                diff_summary=deepcopy(proposal.diff_summary),
                source=proposal.source,
                status=status,
                validation=deepcopy(proposal.validation),
                result=result,
                created_at=proposal.created_at,
                resolved_at=_utc_now(),
                inverse_evidence=deepcopy(proposal.inverse_evidence),
                undo_of=proposal.undo_of,
            )
        )

    @staticmethod
    def _validate_client_version(client_version: int | None, latest_version: int, request_id: str) -> None:
        if client_version is None:
            return
        if isinstance(client_version, bool) or not isinstance(client_version, int) or client_version < 0:
            raise ProposalValidationError("client_base_version must be a non-negative integer")
        if client_version != latest_version:
            raise RequestVersionConflictError(request_id, client_version, latest_version)

    @staticmethod
    def _validate_operations(
        operations: Iterable[Mapping[str, Any]],
        source: str,
        state: Mapping[str, Any],
    ) -> list[Mapping[str, Any]]:
        if not isinstance(source, str) or not source.strip():
            raise ProposalValidationError("source must be a non-empty string")
        if isinstance(operations, (str, bytes, Mapping)):
            raise ProposalValidationError("operations must be a sequence of operation mappings")
        try:
            supplied = list(operations)
        except TypeError as exc:
            raise ProposalValidationError("operations must be iterable") from exc
        if not supplied or len(supplied) > MAX_OPERATIONS:
            raise ProposalValidationError("operations must contain between 1 and 32 items")
        for operation in supplied:
            if not isinstance(operation, Mapping) or not sanitize_external_operations(
                [operation],
                source=source,
                state=state,
            ):
                raise ProposalValidationError("operation is invalid or unsupported")
        return supplied
