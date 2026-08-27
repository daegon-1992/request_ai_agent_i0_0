"""Minimal, process-local observer for existing orchestrator results.

The audit log intentionally receives only server-derived identifiers and result
codes after an existing authority has completed.  It is not a lifecycle,
Request, workflow, or evidence store.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Literal
from uuid import uuid4


AuditStatus = Literal["success", "failure"]


@dataclass(frozen=True)
class RuntimeAuditEvent:
    """A bounded redacted event safe for runtime observation only."""

    event_id: str
    timestamp: str
    sequence: int
    action: str
    result_code: str
    status: AuditStatus
    request_id: str | None = None
    proposal_id: str | None = None
    conversation_id: str | None = None

    def dto(self) -> dict[str, object]:
        return asdict(self)


class RuntimeAuditLog:
    """Append-only, bounded in-memory observer with no business authority."""

    def __init__(self, *, max_events: int = 256) -> None:
        if isinstance(max_events, bool) or not isinstance(max_events, int) or max_events < 1:
            raise ValueError("max_events must be a positive integer")
        self._max_events = max_events
        self._events: list[RuntimeAuditEvent] = []
        self._sequence = 0
        self._lock = RLock()

    def append(
        self,
        *,
        action: str,
        result_code: str,
        status: AuditStatus,
        request_id: str | None = None,
        conversation_id: str | None = None,
        proposal_id: str | None = None,
    ) -> RuntimeAuditEvent:
        """Record one already-determined server result and nothing else."""

        if not isinstance(action, str) or not action or not isinstance(result_code, str) or not result_code:
            raise ValueError("audit action and result_code must be non-empty strings")
        if status not in {"success", "failure"}:
            raise ValueError("audit status is invalid")
        ids = (request_id, conversation_id, proposal_id)
        if any(value is not None and (not isinstance(value, str) or not value) for value in ids):
            raise ValueError("audit identifiers must be server-issued non-empty strings")
        with self._lock:
            self._sequence += 1
            event = RuntimeAuditEvent(
                event_id=f"audit_{uuid4().hex}",
                timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                sequence=self._sequence,
                action=action,
                result_code=result_code,
                status=status,
                request_id=request_id,
                conversation_id=conversation_id,
                proposal_id=proposal_id,
            )
            self._events.append(event)
            if len(self._events) > self._max_events:
                del self._events[: len(self._events) - self._max_events]
            return event

    def events(self) -> tuple[RuntimeAuditEvent, ...]:
        """Return immutable redacted DTO sources; this read has no authority."""

        with self._lock:
            return tuple(self._events)
