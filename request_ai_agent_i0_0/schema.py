"""Public schema descriptors for request assistant state."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .constants import (
    ANALYSIS_OVERVIEW_FIELD_DEFS,
    BASIC_INFO_FIELD_DEFS,
    CONDITION_FIELD_DEFS,
    DROPDOWN_OPTION_DEFS,
    FIELD_STATUSES,
    GEOMETRY_INPUT_KEYS,
    LEGACY_INTERNAL_FIELD_DEFS,
    REQUEST_CONTEXT_FIELD_DEFS,
    SECTION_ANALYSIS_OVERVIEW,
    SECTION_BASIC_INFO,
    SECTION_CASE_MATRIX,
    SECTION_CONDITIONS,
    SECTION_GEOMETRY,
    SECTION_LEGACY_INTERNAL,
    SECTION_METADATA,
    SECTION_REQUEST_CONTEXT,
    SECTION_REVIEW,
    STATE_SCHEMA_VERSION,
    REMOVED_PUBLIC_FIELD_PATHS,
)


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    section: str
    required: bool = False
    value_type: str = "text"
    unit: str = ""
    binding: str = ""
    legacy_key: str = ""
    derived: bool = False
    track_progress: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SectionSpec:
    key: str
    label: str
    fields: tuple[FieldSpec, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["fields"] = [field.to_dict() for field in self.fields]
        return row


def _build_field_specs(section: str, defs: tuple[Mapping[str, Any], ...]) -> tuple[FieldSpec, ...]:
    specs: list[FieldSpec] = []
    for item in defs:
        specs.append(
            FieldSpec(
                key=str(item.get("key", "")).strip(),
                label=str(item.get("label", "")).strip(),
                section=section,
                required=bool(item.get("required", False)),
                value_type=str(item.get("value_type", "text")).strip() or "text",
                unit=str(item.get("unit", "")).strip(),
                binding=str(item.get("binding", "")).strip(),
                legacy_key=str(item.get("legacy_key", "")).strip(),
                derived=bool(item.get("derived", False)),
                track_progress=bool(item.get("track_progress", False)),
            )
        )
    return tuple(specs)


BASIC_INFO_SPECS = _build_field_specs(SECTION_BASIC_INFO, BASIC_INFO_FIELD_DEFS)
REQUEST_CONTEXT_SPECS = _build_field_specs(SECTION_REQUEST_CONTEXT, REQUEST_CONTEXT_FIELD_DEFS)
ANALYSIS_OVERVIEW_SPECS = _build_field_specs(SECTION_ANALYSIS_OVERVIEW, ANALYSIS_OVERVIEW_FIELD_DEFS)
CONDITION_FIELD_SPECS = _build_field_specs(SECTION_CONDITIONS, CONDITION_FIELD_DEFS)
LEGACY_INTERNAL_SPECS = _build_field_specs(SECTION_LEGACY_INTERNAL, LEGACY_INTERNAL_FIELD_DEFS)

SECTION_SPECS = (
    SectionSpec(SECTION_METADATA, "메타데이터"),
    SectionSpec(SECTION_REQUEST_CONTEXT, "의뢰 컨텍스트", REQUEST_CONTEXT_SPECS),
    SectionSpec(SECTION_BASIC_INFO, "기본 정보", BASIC_INFO_SPECS),
    SectionSpec(SECTION_ANALYSIS_OVERVIEW, "해석 개요", ANALYSIS_OVERVIEW_SPECS),
    SectionSpec(SECTION_GEOMETRY, "해석 제품"),
    SectionSpec(SECTION_CONDITIONS, "해석조건", CONDITION_FIELD_SPECS),
    SectionSpec(SECTION_CASE_MATRIX, "Case Matrix"),
    SectionSpec(SECTION_REVIEW, "검토 상태"),
    SectionSpec(SECTION_LEGACY_INTERNAL, "Legacy/Internal", LEGACY_INTERNAL_SPECS),
)

FIELD_SPECS_BY_PATH = {
    f"{spec.section}.{spec.key}": spec
    for section in SECTION_SPECS
    for spec in section.fields
}

CONDITION_FIELD_SPECS_BY_KEY = {spec.key: spec for spec in CONDITION_FIELD_SPECS}


def get_condition_field_spec(key: str) -> FieldSpec | None:
    return CONDITION_FIELD_SPECS_BY_KEY.get(str(key or "").strip())


def get_public_schema() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "field_statuses": list(FIELD_STATUSES),
        "geometry_input_keys": list(GEOMETRY_INPUT_KEYS),
        "ui_options": {path: list(options) for path, options in DROPDOWN_OPTION_DEFS.items()},
        "removed_public_field_paths": list(REMOVED_PUBLIC_FIELD_PATHS),
        "sections": [section.to_dict() for section in SECTION_SPECS],
    }
