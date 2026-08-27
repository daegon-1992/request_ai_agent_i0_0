"""Compatibility names for clients still calling the hierarchy endpoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .product_taxonomy import (
    build_product_taxonomy_payload,
    find_product_taxonomy_matches,
    product_taxonomy_answer,
)


def build_product_hierarchy_payload(root: Path | None = None) -> dict[str, Any]:
    return build_product_taxonomy_payload()


def find_product_hierarchy_matches(
    criteria: Mapping[str, Any], root: Path | None = None
) -> list[dict[str, Any]]:
    return find_product_taxonomy_matches(criteria)


def product_hierarchy_answer(
    criteria: Mapping[str, Any], matches: list[dict[str, Any]]
) -> str:
    return product_taxonomy_answer(criteria, matches)
