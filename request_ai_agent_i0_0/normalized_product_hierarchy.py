"""Normalized product hierarchy backed by the canonical taxonomy master."""

from __future__ import annotations

from .product_taxonomy import build_taxonomy_tree


def normalized_product_hierarchy() -> dict[str, dict[str, dict[str, list[dict[str, object]]]]]:
    return build_taxonomy_tree()


NORMALIZED_PRODUCT_HIERARCHY = build_taxonomy_tree()
