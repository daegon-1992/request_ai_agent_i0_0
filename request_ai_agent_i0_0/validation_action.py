"""Read-only bridge from a server Request to the canonical Validator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .request_state_store import (
    RequestNotFoundError,
    RequestStateSnapshot,
    RequestStateStore,
    RequestVersionConflictError,
)
from .validator import validate_state


@dataclass(frozen=True)
class ValidationActionResult:
    """Display-only result of one explicit, fenced validation action."""

    code: str
    request_id: str
    request_version: int | None = None
    validation: dict[str, Any] | None = None


class ValidationActionService:
    """Run the existing Validator against a server latest Request only.

    The service deliberately has no Request write, Proposal, workflow, Matrix,
    or Undo dependency.  It fences the latest read so a concurrent write is a
    stable read-only result rather than a validation response for an obsolete
    snapshot.
    """

    def __init__(self, requests: RequestStateStore) -> None:
        self._requests = requests

    def run(self, request_id: str) -> ValidationActionResult:
        try:
            latest = self._requests.read(request_id)
        except RequestNotFoundError:
            return ValidationActionResult("request_not_found", request_id)

        try:
            return self._requests.at_version(request_id, latest.version, self._run_fenced)
        except RequestNotFoundError:
            return ValidationActionResult("request_not_found", request_id)
        except RequestVersionConflictError:
            return ValidationActionResult("request_version_conflict", request_id)
        except Exception:
            # Validator or normalizer failures never become a client patch.
            return ValidationActionResult("validation_failed", request_id)

    @staticmethod
    def _run_fenced(snapshot: RequestStateSnapshot) -> ValidationActionResult:
        # validate_state() owns sanitizer entry, readiness, issue severities,
        # field/section binding, and all Matrix validation.  Its raw result is
        # intentionally returned without adapter-side filtering or translation.
        validation = validate_state(snapshot.state)
        blocking = validation.get("blocking", []) if isinstance(validation, dict) else []
        code = "validation_blocked" if blocking else "validation_ready"
        return ValidationActionResult(
            code,
            snapshot.request_id,
            request_version=snapshot.version,
            validation=validation,
        )
