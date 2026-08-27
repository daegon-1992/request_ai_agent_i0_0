"""Manual Case Matrix normalization helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .state import sanitize_state


CaseMatrixPayload = dict[str, Any]


def generate_case_matrix(source: Mapping[str, Any]) -> CaseMatrixPayload:
    """Return the synchronized manual mapping table without generating combinations.

    The historical public function name is retained for API compatibility only.
    It no longer expands product/condition combinations into Cases.
    """

    state = sanitize_state(source)
    return deepcopy(state["case_matrix"])


def state_with_case_matrix_generation(raw_state: Mapping[str, Any]) -> dict[str, Any]:
    """Return state with current manual Matrix options and selections normalized."""

    return sanitize_state(deepcopy(raw_state))
