"""Runtime Request State identity and compare-and-swap boundary.

This intentionally small store is process-local.  It gives later Proposal
work a server-authoritative latest-read/CAS contract without changing the
legacy client-held-state endpoints or introducing persistence prematurely.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Mapping
from uuid import uuid4

from .deferred_input import deferred_fact_key, normalize_deferred_fact


class RequestNotFoundError(KeyError):
    """Raised when a Request identity is not present in this runtime store."""


class RequestVersionConflictError(RuntimeError):
    """Raised when a write's expected version is not the current version."""

    def __init__(self, request_id: str, expected_version: int, current_version: int) -> None:
        super().__init__("request_version_conflict")
        self.request_id = request_id
        self.expected_version = expected_version
        self.current_version = current_version


@dataclass(frozen=True)
class RequestStateSnapshot:
    request_id: str
    version: int
    state: dict[str, Any]


NormalizeState = Callable[[Mapping[str, Any]], dict[str, Any]]
Mutation = Callable[[dict[str, Any]], Mapping[str, Any]]
MAX_DEFERRED_INPUT_FACTS = 64


class RequestStateStore:
    """In-memory latest-read and atomic CAS store for canonical Request State."""

    def __init__(self, normalize_state: NormalizeState) -> None:
        self._normalize_state = normalize_state
        self._records: dict[str, RequestStateSnapshot] = {}
        self._deferred_input_facts: dict[str, list[dict[str, Any]]] = {}
        self._lock = RLock()

    def create(self, raw_state: Mapping[str, Any]) -> RequestStateSnapshot:
        normalized = self._normalized_copy(raw_state)
        snapshot = RequestStateSnapshot(request_id=str(uuid4()), version=0, state=normalized)
        with self._lock:
            self._records[snapshot.request_id] = snapshot
            self._deferred_input_facts[snapshot.request_id] = []
        return self._copy_snapshot(snapshot)

    def read(self, request_id: str) -> RequestStateSnapshot:
        with self._lock:
            return self._copy_snapshot(self._get(request_id))

    def replace(self, request_id: str, expected_version: int, raw_state: Mapping[str, Any]) -> RequestStateSnapshot:
        return self.compare_and_swap(request_id, expected_version, lambda _current: raw_state)

    def compare_and_swap(self, request_id: str, expected_version: int, mutation: Mutation) -> RequestStateSnapshot:
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0:
            raise ValueError("expected_version must be a non-negative integer")
        if not callable(mutation):
            raise ValueError("mutation must be callable")

        with self._lock:
            current = self._get(request_id)
            if expected_version != current.version:
                raise RequestVersionConflictError(request_id, expected_version, current.version)

            # Nothing is committed until both mutation and canonical finalization
            # complete.  A failed mutation therefore cannot advance the version.
            candidate = mutation(deepcopy(current.state))
            if not isinstance(candidate, Mapping):
                raise ValueError("mutation must return a state mapping")
            normalized = self._normalized_copy(candidate)
            next_snapshot = RequestStateSnapshot(
                request_id=request_id,
                version=current.version + 1,
                state=normalized,
            )
            self._records[request_id] = next_snapshot
            return self._copy_snapshot(next_snapshot)

    def at_version(self, request_id: str, expected_version: int, reader: Callable[[RequestStateSnapshot], Any]) -> Any:
        """Run one internal read-only/ledger action while a version stays fenced.

        The callback cannot mutate Request State through this API.  It is used
        when a server-side ledger record must be tied to a particular latest
        Request version without admitting a read-then-record race.
        """

        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0:
            raise ValueError("expected_version must be a non-negative integer")
        if not callable(reader):
            raise ValueError("reader must be callable")
        with self._lock:
            current = self._get(request_id)
            if expected_version != current.version:
                raise RequestVersionConflictError(request_id, expected_version, current.version)
            return reader(self._copy_snapshot(current))

    def read_deferred_input_facts(self, request_id: str) -> list[dict[str, Any]]:
        """Read Request-scoped auxiliary facts without projecting them into State."""

        with self._lock:
            self._get(request_id)
            return deepcopy(self._deferred_input_facts.get(request_id, []))

    def add_deferred_input_facts(
        self,
        request_id: str,
        facts: list[Mapping[str, Any]],
        *,
        captured_request_version: int,
    ) -> list[dict[str, Any]]:
        """Add or replace semantic facts by target; the latest Agent input wins."""

        if isinstance(captured_request_version, bool) or not isinstance(captured_request_version, int):
            raise ValueError("captured_request_version must be an integer")
        normalized: list[dict[str, Any]] = []
        for raw in facts:
            fact = normalize_deferred_fact(raw)
            if fact is None:
                raise ValueError("invalid deferred input fact")
            fact["fact_id"] = f"deferred_{uuid4().hex}"
            fact["captured_request_version"] = captured_request_version
            fact["resolution"] = "waiting_target"
            fact["last_checked_version"] = captured_request_version
            normalized.append(fact)
        with self._lock:
            current_snapshot = self._get(request_id)
            if current_snapshot.version != captured_request_version:
                raise RequestVersionConflictError(
                    request_id,
                    captured_request_version,
                    current_snapshot.version,
                )
            current = deepcopy(self._deferred_input_facts.get(request_id, []))
            indexes = {deferred_fact_key(fact): index for index, fact in enumerate(current)}
            for fact in normalized:
                key = deferred_fact_key(fact)
                if key in indexes:
                    current[indexes[key]] = fact
                else:
                    indexes[key] = len(current)
                    current.append(fact)
            if len(current) > MAX_DEFERRED_INPUT_FACTS:
                current = current[-MAX_DEFERRED_INPUT_FACTS:]
            self._deferred_input_facts[request_id] = current
            return deepcopy(current)

    def replace_deferred_input_facts(
        self,
        request_id: str,
        facts: list[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        with self._lock:
            self._get(request_id)
            copied = [deepcopy(dict(fact)) for fact in facts if isinstance(fact, Mapping)]
            if len(copied) > MAX_DEFERRED_INPUT_FACTS:
                raise ValueError("too many deferred input facts")
            self._deferred_input_facts[request_id] = copied
            return deepcopy(copied)

    def remove_deferred_input_facts(self, request_id: str, fact_ids: set[str]) -> list[dict[str, Any]]:
        with self._lock:
            self._get(request_id)
            current = self._deferred_input_facts.get(request_id, [])
            retained = [fact for fact in current if str(fact.get("fact_id", "")) not in fact_ids]
            self._deferred_input_facts[request_id] = retained
            return deepcopy(retained)

    def _get(self, request_id: str) -> RequestStateSnapshot:
        snapshot = self._records.get(request_id)
        if snapshot is None:
            raise RequestNotFoundError(request_id)
        return snapshot

    def _normalized_copy(self, raw_state: Mapping[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_state(deepcopy(dict(raw_state)))
        if not isinstance(normalized, Mapping):
            raise ValueError("normalizer must return a state mapping")
        return deepcopy(dict(normalized))

    @staticmethod
    def _copy_snapshot(snapshot: RequestStateSnapshot) -> RequestStateSnapshot:
        return RequestStateSnapshot(
            request_id=snapshot.request_id,
            version=snapshot.version,
            state=deepcopy(snapshot.state),
        )
