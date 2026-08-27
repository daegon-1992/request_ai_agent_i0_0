"""Read-only bridge from a server Request to the canonical Case Matrix engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .case_matrix import generate_case_matrix
from .request_state_store import (
    RequestNotFoundError,
    RequestStateSnapshot,
    RequestStateStore,
    RequestVersionConflictError,
)
from .validator import validate_state


@dataclass(frozen=True)
class CaseMatrixActionResult:
    """Display-only result of one explicit, fenced Case Matrix action."""

    code: str
    request_id: str
    request_version: int | None = None
    blocking_reasons: tuple[str, ...] = ()
    matrix_summary: dict[str, Any] | None = None


class CaseMatrixActionService:
    """Enter the existing manual Matrix engine from a server latest Request only.

    This service deliberately has no Request write, Proposal, workflow, or Undo
    dependency.  The version fence makes a concurrent latest-write a stable
    read-only result rather than returning a Matrix computed from an obsolete
    snapshot.
    """

    def __init__(self, requests: RequestStateStore) -> None:
        self._requests = requests

    def run(self, request_id: str) -> CaseMatrixActionResult:
        try:
            latest = self._requests.read(request_id)
        except RequestNotFoundError:
            return CaseMatrixActionResult("request_not_found", request_id)

        try:
            return self._requests.at_version(
                request_id,
                latest.version,
                self._run_fenced,
            )
        except RequestNotFoundError:
            return CaseMatrixActionResult("request_not_found", request_id)
        except RequestVersionConflictError:
            return CaseMatrixActionResult("request_version_conflict", request_id)
        except Exception:
            # Engine/normalizer failures are never converted into a client patch.
            return CaseMatrixActionResult("case_matrix_engine_failed", request_id)

    @staticmethod
    def _run_fenced(snapshot: RequestStateSnapshot) -> CaseMatrixActionResult:
        # Validator owns readiness and its input path reuses sanitize_state().
        validation = validate_state(snapshot.state)
        blocking_reasons = tuple(
            str(issue.get("code", ""))
            for issue in validation.get("blocking", [])
            if isinstance(issue, dict) and str(issue.get("code", ""))
        )
        if blocking_reasons:
            return CaseMatrixActionResult(
                "case_matrix_blocked",
                snapshot.request_id,
                request_version=snapshot.version,
                blocking_reasons=blocking_reasons,
            )

        # This is the sole Matrix entry: the historical engine delegates to
        # state.sanitize_state() and returns the canonical manual Matrix payload.
        matrix = generate_case_matrix(snapshot.state)
        rows = matrix.get("rows") if isinstance(matrix.get("rows"), list) else []
        columns = matrix.get("visible_columns") if isinstance(matrix.get("visible_columns"), list) else []
        return CaseMatrixActionResult(
            "case_matrix_ready",
            snapshot.request_id,
            request_version=snapshot.version,
            matrix_summary={
                "row_count": len(rows),
                "column_count": len(columns),
                "generation_status": str(matrix.get("generation_status", "")),
                "read_only": True,
            },
        )
