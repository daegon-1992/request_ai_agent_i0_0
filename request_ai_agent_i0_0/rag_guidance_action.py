"""Read-only bridge from an explicit panel action to the existing RAG Q&A entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .rag_qa import looks_like_current_input_question, run_rag_qa
from .request_state_store import (
    RequestNotFoundError,
    RequestStateSnapshot,
    RequestStateStore,
    RequestVersionConflictError,
)


RagRunner = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class RagGuidanceActionResult:
    """Display-only result; ``qa`` is the unmodified existing RAG DTO."""

    code: str
    request_id: str
    qa: dict[str, Any] | None = None


class RagGuidanceActionService:
    """Call the established RAG entry without making Request state RAG input.

    The Request store is used only to verify the server-issued panel-local id
    and fence a concurrent write.  Its snapshot is deliberately never read or
    passed to RAG: question text is the sole RAG input for this Action.
    """

    def __init__(self, requests: RequestStateStore, *, rag_runner: RagRunner = run_rag_qa) -> None:
        self._requests = requests
        self._rag_runner = rag_runner

    def run(self, request_id: str, question: str) -> RagGuidanceActionResult:
        if not question.strip():
            return RagGuidanceActionResult("invalid_rag_guidance_question", request_id)
        if looks_like_current_input_question(question):
            return RagGuidanceActionResult("rag_guidance_requires_document_question", request_id)
        try:
            latest = self._requests.read(request_id)
        except RequestNotFoundError:
            return RagGuidanceActionResult("request_not_found", request_id)
        try:
            return self._requests.at_version(
                request_id,
                latest.version,
                lambda snapshot: self._run_fenced(snapshot, question),
            )
        except RequestNotFoundError:
            return RagGuidanceActionResult("request_not_found", request_id)
        except RequestVersionConflictError:
            return RagGuidanceActionResult("request_version_conflict", request_id)
        except Exception:
            return RagGuidanceActionResult("rag_guidance_failed", request_id)

    def _run_fenced(self, snapshot: RequestStateSnapshot, question: str) -> RagGuidanceActionResult:
        # Do not inspect snapshot.state: it is an identity/race fence only.
        try:
            qa = self._rag_runner(question, state=None)
        except Exception:
            return RagGuidanceActionResult("rag_guidance_error", snapshot.request_id)
        if not self._is_existing_qa_dto(qa):
            return RagGuidanceActionResult("rag_guidance_malformed", snapshot.request_id)
        question_type = str(qa.get("question_type", ""))
        sources = qa.get("sources", [])
        if question_type == "rag_disabled":
            code = "rag_guidance_disabled"
        elif question_type == "rag_error" or qa.get("ok") is False:
            code = "rag_guidance_error"
        elif not sources:
            code = "rag_guidance_no_result"
        else:
            code = "rag_guidance_ready"
        return RagGuidanceActionResult(code, snapshot.request_id, qa=qa)

    @staticmethod
    def _is_existing_qa_dto(qa: Any) -> bool:
        if not isinstance(qa, dict) or qa.get("read_only") is not True or qa.get("state_changed") is not False:
            return False
        if not isinstance(qa.get("question_type"), str) or not isinstance(qa.get("sources"), list):
            return False
        return all(isinstance(source, Mapping) for source in qa["sources"])
