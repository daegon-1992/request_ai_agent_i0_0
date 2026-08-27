"""Read-only bridge from a server Request to the active browser Preview."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .request_state_store import (
    RequestNotFoundError,
    RequestStateSnapshot,
    RequestStateStore,
    RequestVersionConflictError,
)


@dataclass(frozen=True)
class PreviewActionResult:
    """One fenced server snapshot for the existing browser Preview entry."""

    code: str
    request_id: str
    request_version: int | None = None
    state: dict[str, Any] | None = None


class PreviewActionService:
    """Read the canonical latest snapshot without rendering or mutating it.

    The active Preview renderer is ``ui.py:renderDocumentPreviewPanel()``, not
    the disabled legacy document-preview endpoint.  This adapter deliberately
    supplies that renderer with a fenced server snapshot only; it does not run
    a second renderer, normalizer, Validator, readiness policy, or write.
    """

    def __init__(self, requests: RequestStateStore) -> None:
        self._requests = requests

    def run(self, request_id: str) -> PreviewActionResult:
        try:
            latest = self._requests.read(request_id)
        except RequestNotFoundError:
            return PreviewActionResult("request_not_found", request_id)

        try:
            return self._requests.at_version(request_id, latest.version, self._read_fenced)
        except RequestNotFoundError:
            return PreviewActionResult("request_not_found", request_id)
        except RequestVersionConflictError:
            return PreviewActionResult("request_version_conflict", request_id)
        except Exception:
            return PreviewActionResult("preview_read_failed", request_id)

    @staticmethod
    def _read_fenced(snapshot: RequestStateSnapshot) -> PreviewActionResult:
        return PreviewActionResult(
            "preview_ready",
            snapshot.request_id,
            request_version=snapshot.version,
            state=snapshot.state,
        )
