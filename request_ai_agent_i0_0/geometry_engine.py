"""Geometry axis generation for request assistant state."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .constants import (
    FIELD_STATUS_MISSING,
    FIELD_STATUS_PROVIDED,
    SECTION_GEOMETRY,
)
from .state import field_value, sanitize_state


GeometryPayload = dict[str, Any]


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _geometry_section(source: Mapping[str, Any]) -> Mapping[str, Any]:
    geometry = source.get(SECTION_GEOMETRY)
    if isinstance(geometry, Mapping):
        return geometry
    return source


def generate_geometry_axis(source: Mapping[str, Any]) -> GeometryPayload:
    """Return a geometry-axis payload from a state or geometry section.

    Each registered complete product is one geometry.  No part assembly or
    unregistered product combinations are generated.
    """

    geometry = _geometry_section(source)
    products = [geometry.get("base_product"), *(geometry.get("comparison_products") or [])]
    variants = []
    for index, product in enumerate(products, start=1):
        if not isinstance(product, Mapping) or product.get("drawing_no", {}).get("status") != FIELD_STATUS_PROVIDED:
            continue
        drawing_no = _clean_text(field_value(product.get("drawing_no")))
        if not drawing_no:
            continue
        display_name = _clean_text(field_value(product.get("display_name"))) or drawing_no
        variants.append({
            "geometry_id": _clean_text(product.get("geometry_id")),
            "geometry_label": f"형상 {index}",
            "drawing_no": drawing_no,
            "display_name": display_name,
            "role": _clean_text(product.get("role")),
            "difference_from_base": _clean_text(field_value(product.get("difference_from_base"))),
            "is_baseline": product.get("role") == "base",
        })

    return {
        "axis_type": "geometry",
        "generation_status": FIELD_STATUS_PROVIDED if variants else FIELD_STATUS_MISSING,
        "geometry_variants": variants,
        "source_inputs": {"product_count": len(products), "baseline_count": sum(1 for item in variants if item.get("is_baseline"))},
        "warnings": [],
    }


def state_with_geometry_axis(raw_state: Mapping[str, Any]) -> dict[str, Any]:
    """Return a sanitized state copy with geometry.axis populated."""

    state = sanitize_state(deepcopy(raw_state))
    state[SECTION_GEOMETRY]["axis"] = generate_geometry_axis(state)
    return state
