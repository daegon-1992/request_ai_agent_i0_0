"""Read-only canonical field bindings for orchestrator consumers.

This module intentionally adapts existing schema and Fieldset results.  It is
not a second rules engine and has no Request State mutation entry point.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .condition_fieldsets import get_active_condition_fields
from .schema import (
    ANALYSIS_OVERVIEW_SPECS,
    BASIC_INFO_SPECS,
    REQUEST_CONTEXT_SPECS,
    FieldSpec,
)
from .constants import SECTION_REQUEST_CONTEXT


@dataclass(frozen=True)
class FieldRegistryDTO:
    """A stable field identity and its existing canonical/validation bindings."""

    field_id: str
    canonical_path: str
    value_path: str
    label: str
    value_type: str
    unit: str
    active: bool
    required: bool
    required_level: str
    dependencies: tuple[str, ...]
    validation_binding: str
    priority: str
    operation_path: str = ""
    field_key: str = ""
    card_id: str = ""
    binding: str = ""

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["dependencies"] = list(self.dependencies)
        return row


@dataclass(frozen=True)
class GeometryProductsAdapterDTO:
    """The transport-only legacy geometry DTO; it is not Request State."""

    adapter_id: str
    transport_path: str
    canonical_paths: tuple[str, ...]
    state_path: None = None
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["canonical_paths"] = list(self.canonical_paths)
        return row


_GENERAL_SPECS: tuple[FieldSpec, ...] = (
    *REQUEST_CONTEXT_SPECS,
    *BASIC_INFO_SPECS,
    *ANALYSIS_OVERVIEW_SPECS,
)


def _priority(required_level: str) -> str:
    if required_level == "required":
        return "blocking_required"
    if required_level == "conditional_required":
        return "blocking_conditional_group"
    return "optional"


def _general_field(spec: FieldSpec) -> FieldRegistryDTO:
    path = f"{spec.section}.{spec.key}"
    required_level = "required" if spec.required else "optional_non_blocking"
    value_path = path if spec.section == SECTION_REQUEST_CONTEXT else f"{path}.value"
    return FieldRegistryDTO(
        field_id=path,
        canonical_path=path,
        value_path=value_path,
        label=spec.label,
        value_type=spec.value_type,
        unit=spec.unit,
        active=True,
        required=spec.required,
        required_level=required_level,
        dependencies=(),
        validation_binding="validator._validate_required_field_section",
        priority=_priority(required_level),
        operation_path=path,
        field_key=spec.key,
        binding=spec.binding,
    )


def _condition_binding(field: Mapping[str, Any]) -> tuple[str, str]:
    card_id = str(field.get("card_id") or "").strip()
    field_key = str(field.get("field_key") or field.get("key") or "").strip()
    if field_key == "fan_rpm":
        return (
            f"conditions.condition_sets[card_id={card_id}].fans[*].values.{field_key}",
            f"conditions.fields.{field_key}.values",
        )
    return (
        f"conditions.condition_sets[card_id={card_id}].fields.{field_key}.value",
        f"conditions.fields.{field_key}.values",
    )


def _condition_field(field: Mapping[str, Any]) -> FieldRegistryDTO:
    instance_key = str(field.get("key") or "").strip()
    card_id = str(field.get("card_id") or "").strip()
    field_key = str(field.get("field_key") or instance_key.rsplit(".", 1)[-1]).strip()
    required_level = str(field.get("required_level") or "").strip()
    if required_level not in {"required", "conditional_required", "optional_non_blocking"}:
        required_level = "required" if field.get("required") is True else "optional_non_blocking"
    canonical_path, validation_path = _condition_binding(field)
    group = str(field.get("conditional_group") or "").strip()
    dependencies = (f"conditions.conditional_group.{group}",) if group else ("request_context.analysis_type",)
    return FieldRegistryDTO(
        field_id=f"conditions.{instance_key}",
        canonical_path=canonical_path,
        value_path=canonical_path,
        label=str(field.get("label") or field_key),
        value_type=str(field.get("value_type") or "text"),
        unit=str(field.get("unit") or ""),
        active=field.get("active") is True,
        required=required_level in {"required", "conditional_required"},
        required_level=required_level,
        dependencies=dependencies,
        validation_binding="validator._validate_conditions",
        priority=_priority(required_level),
        operation_path=validation_path,
        field_key=field_key,
        card_id=card_id,
        binding=str(field.get("binding") or "condition_card"),
    )


def get_field_registry(state: Mapping[str, Any] | None = None) -> tuple[FieldRegistryDTO, ...]:
    """Return a snapshot without normalizing or otherwise mutating ``state``.

    Active/required condition metadata is deliberately delegated to the live
    Fieldset helper.  Callers that write a proposed value must still route it
    through the existing sanitizer and validator boundary.
    """

    source = state or {}
    general = tuple(_general_field(spec) for spec in _GENERAL_SPECS)
    request_context = source.get("request_context", {}) if isinstance(source, Mapping) else {}
    analysis_type = request_context.get("analysis_type", "") if isinstance(request_context, Mapping) else ""
    if isinstance(analysis_type, Mapping):
        analysis_type = analysis_type.get("value", "")
    active_conditions = (
        tuple(_condition_field(field) for field in get_active_condition_fields(source))
        if str(analysis_type or "").strip()
        else ()
    )
    return (*general, *active_conditions)


def get_geometry_products_adapter() -> GeometryProductsAdapterDTO:
    """Describe the LLM-facing geometry transport DTO without registering state."""

    return GeometryProductsAdapterDTO(
        adapter_id="geometry_products_to_complete_product_cards",
        transport_path="geometry.products",
        canonical_paths=(
            "geometry.base_product.drawing_no",
            "geometry.comparison_products[].drawing_no",
        ),
    )
