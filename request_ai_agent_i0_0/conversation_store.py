"""Bounded, process-local Conversation State references.

Conversation State contains workflow progress/references, bounded recent
conversation context, an active field reference, and temporary write
candidates awaiting clarification.  It never contains a Request State
snapshot, a client-supplied State, or Proposal operations/base versions.
Request and Proposal authority remain with their respective server stores.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from threading import RLock
from typing import Any, Mapping, Sequence
from uuid import uuid4


MAX_CONVERSATIONS = 256
MAX_QUESTION_HISTORY = 32
MAX_RECENT_TURNS = 10
MAX_IDENTIFIER_LENGTH = 256
MAX_WORKFLOW_STATUS_LENGTH = 128
MAX_QUESTION_LENGTH = 2_000
MAX_TURN_CONTENT_LENGTH = 4_000
MAX_SUMMARY_LENGTH = 8_000
MAX_PENDING_WRITE_CANDIDATES = 32
ALLOWED_TURN_ROLES = frozenset({"user", "assistant"})


class ConversationNotFoundError(KeyError):
    """Raised when a server-issued conversation id is not in this runtime."""


class ConversationCapacityError(RuntimeError):
    """Raised when the bounded process-local conversation store is full."""


class ConversationStateError(RuntimeError):
    """Raised when a lifecycle transition or active-state mutation is invalid."""


@dataclass(frozen=True)
class ConversationSnapshot:
    """A deep-copy-only local conversation record linked by server references."""

    conversation_id: str
    request_id: str
    workflow_status: str
    pending_proposal_id: str | None
    question_history: list[str]
    paused: bool
    summary: str
    version: int
    status: str
    recent_turns: list[dict[str, str]] = field(default_factory=list)
    active_field_id: str | None = None
    pending_write_candidates: list[dict[str, Any]] = field(default_factory=list)


def _copy_snapshot(snapshot: ConversationSnapshot) -> ConversationSnapshot:
    return ConversationSnapshot(**deepcopy(asdict(snapshot)))


class ConversationStore:
    """Small process-local store for independent Conversation state."""

    def __init__(
        self,
        *,
        max_conversations: int = MAX_CONVERSATIONS,
        max_question_history: int = MAX_QUESTION_HISTORY,
    ) -> None:
        if isinstance(max_conversations, bool) or not isinstance(max_conversations, int) or max_conversations < 1:
            raise ValueError("max_conversations must be a positive integer")
        if isinstance(max_question_history, bool) or not isinstance(max_question_history, int) or max_question_history < 1:
            raise ValueError("max_question_history must be a positive integer")
        self._max_conversations = max_conversations
        self._max_question_history = max_question_history
        self._records: dict[str, ConversationSnapshot] = {}
        self._lock = RLock()

    def create(self, request_id: str, *, workflow_status: str = "started") -> ConversationSnapshot:
        """Create a server-issued conversation/session id for one Request id."""

        request_id = self._required_identifier(request_id, "request_id")
        workflow_status = self._workflow_status(workflow_status)
        with self._lock:
            if len(self._records) >= self._max_conversations:
                raise ConversationCapacityError("conversation_store_full")
            snapshot = ConversationSnapshot(
                conversation_id=f"conversation_{uuid4().hex}",
                request_id=request_id,
                workflow_status=workflow_status,
                pending_proposal_id=None,
                question_history=[],
                paused=False,
                summary="",
                version=0,
                status="active",
            )
            self._records[snapshot.conversation_id] = snapshot
            return _copy_snapshot(snapshot)

    def read(self, conversation_id: str) -> ConversationSnapshot:
        with self._lock:
            return _copy_snapshot(self._get(conversation_id))

    def set_workflow_status(self, conversation_id: str, workflow_status: str) -> ConversationSnapshot:
        workflow_status = self._workflow_status(workflow_status)
        return self._update_active(conversation_id, workflow_status=workflow_status)

    def append_question(self, conversation_id: str, question: str) -> ConversationSnapshot:
        question = self._bounded_text(question, "question", MAX_QUESTION_LENGTH)
        with self._lock:
            current = self._require_active(self._get(conversation_id))
            history = [*current.question_history, question]
            return self._replace(current, question_history=history[-self._max_question_history :])

    def append_turn(self, conversation_id: str, role: str, content: str) -> ConversationSnapshot:
        if not isinstance(role, str) or role not in ALLOWED_TURN_ROLES:
            raise ValueError("role must be 'user' or 'assistant'")
        if not isinstance(content, str):
            raise ValueError("content must be a string")
        content = self._bounded_text(content.strip(), "content", MAX_TURN_CONTENT_LENGTH)
        with self._lock:
            current = self._require_active(self._get(conversation_id))
            recent_turns = [*current.recent_turns, {"role": role, "content": content}]
            return self._replace(current, recent_turns=recent_turns[-MAX_RECENT_TURNS:])

    def append_exchange(
        self,
        conversation_id: str,
        user_content: str,
        assistant_content: str,
        *,
        active_field_id: str | None = None,
    ) -> ConversationSnapshot:
        """Record one successfully displayed user/assistant exchange atomically."""

        user_content = self._bounded_text(user_content.strip(), "user_content", MAX_TURN_CONTENT_LENGTH)
        assistant_content = self._bounded_text(assistant_content.strip(), "assistant_content", MAX_TURN_CONTENT_LENGTH)
        if active_field_id is not None:
            active_field_id = self._required_identifier(active_field_id, "field_id")
        with self._lock:
            current = self._require_active(self._get(conversation_id))
            recent_turns = [
                *current.recent_turns,
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": assistant_content},
            ]
            return self._replace(
                current,
                recent_turns=recent_turns[-MAX_RECENT_TURNS:],
                active_field_id=current.active_field_id if active_field_id is None else active_field_id,
            )

    def apply_planner_message(
        self,
        conversation_id: str,
        message: str,
        *,
        active_field_id: str | None,
        record_question: bool,
        workflow_status: str,
        pending_proposal_id: str | None,
        expected_version: int,
    ) -> ConversationSnapshot:
        """Atomically record one displayed Planner result and workflow outcome."""

        message = self._bounded_text(message.strip(), "message", MAX_TURN_CONTENT_LENGTH)
        workflow_status = self._workflow_status(workflow_status)
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0:
            raise ValueError("expected_version must be a non-negative integer")
        if record_question:
            if active_field_id is None:
                raise ValueError("a Planner question requires an active field")
            active_field_id = self._required_identifier(active_field_id, "field_id")
        elif active_field_id is not None:
            raise ValueError("Planner guidance cannot set an active field")
        if pending_proposal_id is not None:
            pending_proposal_id = self._required_identifier(pending_proposal_id, "proposal_id")

        with self._lock:
            current = self._require_active(self._get(conversation_id))
            if current.version != expected_version:
                raise ConversationStateError("conversation_version_conflict")
            recent_turns = [*current.recent_turns, {"role": "assistant", "content": message}]
            question_history = current.question_history
            if record_question:
                question_history = [*question_history, message][-self._max_question_history :]
            return self._replace(
                current,
                workflow_status=workflow_status,
                pending_proposal_id=pending_proposal_id,
                question_history=question_history,
                recent_turns=recent_turns[-MAX_RECENT_TURNS:],
                active_field_id=active_field_id,
            )

    def set_active_field(self, conversation_id: str, field_id: str) -> ConversationSnapshot:
        return self._update_active(conversation_id, active_field_id=self._required_identifier(field_id, "field_id"))

    def clear_active_field(self, conversation_id: str) -> ConversationSnapshot:
        return self._update_active(conversation_id, active_field_id=None)

    def set_pending_proposal(self, conversation_id: str, proposal_id: str | None) -> ConversationSnapshot:
        if proposal_id is not None:
            proposal_id = self._required_identifier(proposal_id, "proposal_id")
        return self._update_active(conversation_id, pending_proposal_id=proposal_id)

    def set_pending_write_candidates(
        self,
        conversation_id: str,
        candidates: Sequence[Mapping[str, Any]],
    ) -> ConversationSnapshot:
        """Store bounded, non-authoritative candidates across clarification turns."""

        if not isinstance(candidates, (list, tuple)) or len(candidates) > MAX_PENDING_WRITE_CANDIDATES:
            raise ValueError("invalid pending write candidates")
        copied: list[dict[str, Any]] = []
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                raise ValueError("invalid pending write candidate")
            copied.append(deepcopy(dict(candidate)))
        return self._update_active(conversation_id, pending_write_candidates=copied)

    def clear_pending_write_candidates(self, conversation_id: str) -> ConversationSnapshot:
        return self._update_active(conversation_id, pending_write_candidates=[])

    def clear_pending_write_candidates_for_request(self, request_id: str) -> None:
        """Invalidate clarification candidates after any canonical Request write."""

        request_id = self._required_identifier(request_id, "request_id")
        with self._lock:
            for conversation_id, current in list(self._records.items()):
                if current.request_id == request_id and current.pending_write_candidates:
                    self._records[conversation_id] = self._replace(
                        current,
                        pending_write_candidates=[],
                    )

    def apply_workflow_transition(
        self,
        conversation_id: str,
        *,
        workflow_status: str,
        pending_proposal_id: str | None,
    ) -> ConversationSnapshot:
        """Atomically persist a validated local workflow outcome.

        This does not interpret workflow events or extend lifecycle authority;
        it only prevents a partial status/reference write after a valid caller
        has already selected both values.
        """

        workflow_status = self._workflow_status(workflow_status)
        if pending_proposal_id is not None:
            pending_proposal_id = self._required_identifier(pending_proposal_id, "proposal_id")
        with self._lock:
            current = self._require_active(self._get(conversation_id))
            return self._replace(
                current,
                workflow_status=workflow_status,
                pending_proposal_id=pending_proposal_id,
            )

    def set_summary(self, conversation_id: str, summary: str) -> ConversationSnapshot:
        return self._update_active(conversation_id, summary=self._bounded_text(summary, "summary", MAX_SUMMARY_LENGTH, allow_empty=True))

    def pause(self, conversation_id: str) -> ConversationSnapshot:
        with self._lock:
            current = self._require_active(self._get(conversation_id))
            return self._replace(current, paused=True, status="paused")

    def resume(self, conversation_id: str) -> ConversationSnapshot:
        with self._lock:
            current = self._get(conversation_id)
            if current.status != "paused":
                raise ConversationStateError("conversation is not paused")
            return self._replace(current, paused=False, status="active")

    def close(self, conversation_id: str) -> ConversationSnapshot:
        with self._lock:
            current = self._get(conversation_id)
            if current.status == "closed":
                raise ConversationStateError("conversation is closed")
            return self._replace(current, paused=False, status="closed")

    def _update_active(self, conversation_id: str, **changes: Any) -> ConversationSnapshot:
        with self._lock:
            current = self._require_active(self._get(conversation_id))
            return self._replace(current, **changes)

    def _replace(self, current: ConversationSnapshot, **changes: Any) -> ConversationSnapshot:
        next_snapshot = ConversationSnapshot(
            conversation_id=current.conversation_id,
            request_id=current.request_id,
            workflow_status=changes.get("workflow_status", current.workflow_status),
            pending_proposal_id=changes.get("pending_proposal_id", current.pending_proposal_id),
            question_history=changes.get("question_history", current.question_history),
            paused=changes.get("paused", current.paused),
            summary=changes.get("summary", current.summary),
            version=current.version + 1,
            status=changes.get("status", current.status),
            recent_turns=changes.get("recent_turns", current.recent_turns),
            active_field_id=changes.get("active_field_id", current.active_field_id),
            pending_write_candidates=changes.get(
                "pending_write_candidates",
                current.pending_write_candidates,
            ),
        )
        self._records[current.conversation_id] = next_snapshot
        return _copy_snapshot(next_snapshot)

    def _get(self, conversation_id: str) -> ConversationSnapshot:
        snapshot = self._records.get(conversation_id)
        if snapshot is None:
            raise ConversationNotFoundError(conversation_id)
        return snapshot

    @staticmethod
    def _require_active(snapshot: ConversationSnapshot) -> ConversationSnapshot:
        if snapshot.status == "closed":
            raise ConversationStateError("conversation is closed")
        if snapshot.status == "paused":
            raise ConversationStateError("conversation is paused")
        return snapshot

    @staticmethod
    def _required_identifier(value: str, name: str) -> str:
        return ConversationStore._bounded_text(value, name, MAX_IDENTIFIER_LENGTH)

    @staticmethod
    def _workflow_status(value: str) -> str:
        return ConversationStore._bounded_text(value, "workflow_status", MAX_WORKFLOW_STATUS_LENGTH)

    @staticmethod
    def _bounded_text(value: str, name: str, maximum: int, *, allow_empty: bool = False) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        if not value and not allow_empty:
            raise ValueError(f"{name} must not be empty")
        if len(value) > maximum:
            raise ValueError(f"{name} exceeds maximum length")
        return value
