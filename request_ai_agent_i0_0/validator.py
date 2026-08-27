"""Structured validation for the request assistant state."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping

from .condition_fields import clean_text
from .condition_fieldsets import get_active_condition_fields
from .constants import (
    FIELD_STATUS_PROVIDED,
    SECTION_ANALYSIS_OVERVIEW,
    SECTION_BASIC_INFO,
    SECTION_CASE_MATRIX,
    SECTION_CONDITIONS,
    SECTION_GEOMETRY,
    SECTION_REQUEST_CONTEXT,
    SECTION_REVIEW,
)
from .geometry_engine import state_with_geometry_axis
from .schema import ANALYSIS_OVERVIEW_SPECS, BASIC_INFO_SPECS, FieldSpec
from .state import decision_use_is_complete, field_value, normalize_decision_use_field, sanitize_state


ValidationResult = dict[str, Any]

SEVERITY_BLOCKING = "blocking"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

FORBIDDEN_PREVIEW_COLUMN_KEYS = {
    "condition",
    "condition_id",
    "condition_label",
    "product",
    "product_ref",
    "product_modeling_no",
    "product_modeling_number",
    "modeling_no",
    "part",
    "part_ref",
    "changed_part",
    "changed_from_part",
    "changed_part_modeling_no",
}

MODELING_NO_RE = re.compile(r"^[A-Za-z0-9-]+$")


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _new_result() -> ValidationResult:
    return {SEVERITY_BLOCKING: [], SEVERITY_WARNING: [], SEVERITY_INFO: []}


def _add_issue(
    result: ValidationResult,
    severity: str,
    *,
    code: str,
    section: str,
    message: str,
    path: str = "",
    field_key: str = "",
    field_label: str = "",
    action: str = "",
) -> None:
    issue = {
        "severity": severity,
        "code": code,
        "section": section,
        "sectionId": section,
        "message": message,
        "evidence": "structured_state",
    }
    if path:
        issue["path"] = path
    if field_key:
        issue["field_key"] = field_key
        issue["fieldId"] = field_key
    if field_label:
        issue["field_label"] = field_label
    if action:
        issue["action"] = action
        issue["actionLabel"] = "이 위치 보완"
    result[severity].append(issue)


def build_issue_registry(validation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten validation issues into UI navigation records."""

    registry: list[dict[str, Any]] = []
    for severity in (SEVERITY_BLOCKING, SEVERITY_WARNING, SEVERITY_INFO):
        for item in _as_list(_as_mapping(validation).get(severity)):
            issue = _as_mapping(item)
            code = clean_text(issue.get("code"))
            if not code:
                continue
            section = clean_text(issue.get("section")) or SECTION_REVIEW
            field_key = clean_text(issue.get("field_key"))
            registry.append(
                {
                    "severity": severity,
                    "code": code,
                    "section": section,
                    "sectionId": section,
                    "field_key": field_key,
                    "fieldId": field_key,
                    "path": clean_text(issue.get("path")),
                    "message": clean_text(issue.get("message")),
                    "actionLabel": clean_text(issue.get("actionLabel")) or "이 위치 보완",
                }
            )
    return registry


def _field_status(field: Any) -> str:
    return clean_text(_as_mapping(field).get("status"))


def _field_is_provided(field: Any) -> bool:
    return _field_status(field) == FIELD_STATUS_PROVIDED and clean_text(field_value(field)) != ""


def _provided_value_count(rows: Any) -> int:
    return sum(1 for row in _as_list(rows) if _field_is_provided(row))


def _condition_required_level(field: Mapping[str, Any]) -> str:
    """Return the active-fieldset requirement level with legacy fallback."""

    level = clean_text(field.get("required_level"))
    if level in {"required", "conditional_required", "optional_non_blocking"}:
        return level
    return "required" if bool(field.get("required", False)) else "optional_non_blocking"


def _validate_modeling_no(
    result: ValidationResult,
    *,
    value: Any,
    code: str,
    path: str,
    field_key: str,
    field_label: str,
) -> None:
    text = clean_text(value)
    if not text or MODELING_NO_RE.fullmatch(text):
        return
    _add_issue(
        result,
        SEVERITY_BLOCKING,
        code=code,
        section=SECTION_GEOMETRY,
        path=path,
        field_key=field_key,
        field_label=field_label,
        message=f"{field_label} must use only English letters, numbers, and hyphen (-).",
        action="Revise the modeling number format.",
    )


def _prepare_state_and_case_payload(source: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    state = state_with_geometry_axis(sanitize_state(source))
    return state, dict(_as_mapping(state.get(SECTION_CASE_MATRIX)))


def _validate_required_field_section(
    result: ValidationResult,
    *,
    state: Mapping[str, Any],
    section_key: str,
    specs: tuple[FieldSpec, ...],
    section_label: str,
) -> None:
    section = _as_mapping(state.get(section_key))
    for spec in specs:
        if not spec.required:
            continue
        field = section.get(spec.key)
        if section_key == SECTION_ANALYSIS_OVERVIEW and spec.key == "decision_use":
            if decision_use_is_complete(field):
                continue
            decision = normalize_decision_use_field(field)
            primary_code = decision["value"]["primary_code"]
            message = "Select a primary result-use purpose."
            if primary_code == "other":
                message = "Provide the custom result-use purpose for 기타."
            elif primary_code == "undecided":
                message = "Confirm the primary result-use purpose before submission."
            _add_issue(
                result,
                SEVERITY_BLOCKING,
                code=f"{section_key}.{spec.key}.required_missing",
                section=section_key,
                path=f"{section_key}.{spec.key}",
                field_key=spec.key,
                field_label=spec.label,
                message=message,
                action="Select one result-use purpose and complete 기타 when selected.",
            )
            continue
        if _field_is_provided(field):
            continue
        code = f"{section_key}.{spec.key}.required_missing"
        _add_issue(
            result,
            SEVERITY_BLOCKING,
            code=code,
            section=section_key,
            path=f"{section_key}.{spec.key}",
            field_key=spec.key,
            field_label=spec.label,
            message=f"Required {section_label} field is missing: {spec.label}.",
            action="Provide a value or explicitly revise the request scope.",
        )


def _validate_geometry(result: ValidationResult, state: Mapping[str, Any]) -> None:
    geometry = _as_mapping(state.get(SECTION_GEOMETRY))
    axis = _as_mapping(geometry.get("axis"))
    variants = _as_list(axis.get("geometry_variants"))

    if not variants:
        _add_issue(
            result,
            SEVERITY_BLOCKING,
            code="geometry.axis_missing",
            section=SECTION_GEOMETRY,
            path="geometry.axis.geometry_variants",
            message="At least one geometry variant is required.",
            action="Add a product modeling number or valid changed-part information.",
        )

    base_product = _as_mapping(geometry.get("base_product"))
    comparisons = _as_list(geometry.get("comparison_products"))
    if base_product.get("role") != "base":
        _add_issue(
            result,
            SEVERITY_BLOCKING,
            code="geometry.base_product.role_invalid",
            section=SECTION_GEOMETRY,
            path="geometry.base_product.role",
            message="Exactly one base product is required.",
            action="Keep the base product card as the only base product.",
        )
    products = [("base_product", base_product), *[(f"comparison_products[{index}]", _as_mapping(item)) for index, item in enumerate(comparisons)]]
    seen_drawings: set[str] = set()
    for path, product in products:
        drawing = product.get("drawing_no")
        if not _field_is_provided(drawing):
            _add_issue(result, SEVERITY_BLOCKING, code="geometry.product.drawing_no.required_missing", section=SECTION_GEOMETRY, path=f"geometry.{path}.drawing_no", message="Each product needs a drawing number.", action="Enter the product drawing number.")
        else:
            drawing_value = clean_text(field_value(drawing))
            _validate_modeling_no(
                result,
                value=drawing_value, code="geometry.product.drawing_no.invalid", path=f"geometry.{path}.drawing_no", field_key="drawing_no", field_label="Drawing number",
            )
            if drawing_value in seen_drawings:
                _add_issue(result, SEVERITY_BLOCKING, code="geometry.product.drawing_no.duplicate", section=SECTION_GEOMETRY, path=f"geometry.{path}.drawing_no", field_key="drawing_no", field_label="Drawing number", message="Each product needs a distinct drawing number.", action="Use a different drawing number.")
            seen_drawings.add(drawing_value)
        if path != "base_product":
            if product.get("role") != "comparison":
                _add_issue(result, SEVERITY_BLOCKING, code="geometry.comparison.role_invalid", section=SECTION_GEOMETRY, path=f"geometry.{path}.role", message="Comparison products must have the comparison role.", action="Keep the comparison product role.")
            if not _field_is_provided(product.get("difference_from_base")):
                _add_issue(result, SEVERITY_BLOCKING, code="geometry.comparison.difference.required_missing", section=SECTION_GEOMETRY, path=f"geometry.{path}.difference_from_base", message="Each comparison product needs its difference from the base product.", action="Describe the geometry difference.")

    if not variants:
        _add_issue(
            result,
            SEVERITY_BLOCKING,
            code="geometry.base_product.required_missing",
            section=SECTION_GEOMETRY,
            path="geometry.base_product.drawing_no",
            message="A base product drawing number is required.",
            action="Enter the base product drawing number.",
        )


def _validate_conditions(result: ValidationResult, state: Mapping[str, Any]) -> None:
    request_context = _as_mapping(state.get(SECTION_REQUEST_CONTEXT))
    if request_context.get("context_locked") is not True:
        _add_issue(
            result,
            SEVERITY_BLOCKING,
            code="request_context.not_locked",
            section=SECTION_CONDITIONS,
            path="request_context.context_locked",
            message="Request context must be confirmed before condition validation.",
            action="Confirm business unit, product group, platform, and analysis type first.",
        )
        return

    conditions = _as_mapping(state.get(SECTION_CONDITIONS))
    fields = get_active_condition_fields(state)

    if not fields:
        _add_issue(
            result,
            SEVERITY_BLOCKING,
            code="conditions.no_active_fieldset_fields",
            section=SECTION_CONDITIONS,
            path="request_context.condition_fieldset_snapshot",
            message="No active condition fields are available from the confirmed fieldset.",
            action="Reconfirm the request context to rebuild the condition fieldset.",
        )
        return

    conditional_groups: dict[str, list[dict[str, Any]]] = {}
    for field in fields:
        required_level = _condition_required_level(field)
        if required_level == "conditional_required":
            key = clean_text(field.get("key"))
            group_key = clean_text(field.get("conditional_group")) or key
            conditional_groups.setdefault(group_key, []).append(field)
            continue
        if required_level != "required":
            continue
        if _provided_value_count(field.get("values")) > 0:
            continue
        key = clean_text(field.get("key"))
        label = clean_text(field.get("label")) or key
        _add_issue(
            result,
            SEVERITY_BLOCKING,
            code=f"conditions.{key}.required_missing",
            section=SECTION_CONDITIONS,
            path=f"conditions.fields.{key}.values",
            field_key=key,
            field_label=label,
            message=f"Required analysis condition is missing: {label}.",
            action="Add at least one provided condition value.",
        )


    for group_key, group_fields in conditional_groups.items():
        if any(_provided_value_count(field.get("values")) > 0 for field in group_fields):
            continue
        representative = group_fields[0]
        key = clean_text(representative.get("key"))
        label = clean_text(representative.get("label")) or key
        _add_issue(
            result,
            SEVERITY_BLOCKING,
            code=f"conditions.{group_key}.conditional_required_missing",
            section=SECTION_CONDITIONS,
            path=f"conditions.fields.{key}.values",
            field_key=key,
            field_label=label,
            message=f"A conditionally required analysis condition is missing: {label}.",
            action="Add at least one provided condition value from this conditional group.",
        )

    if not any(_provided_value_count(field.get("values")) for field in fields):
        _add_issue(
            result,
            SEVERITY_BLOCKING,
            code="conditions.no_values",
            section=SECTION_CONDITIONS,
            path="conditions.fields",
            message="No provided analysis condition values are available.",
            action="Add condition values for the analysis request.",
        )


def _validate_case_matrix(result: ValidationResult, state: Mapping[str, Any]) -> None:
    """Validate the current user-maintained Case Matrix rows."""

    matrix = _as_mapping(state.get(SECTION_CASE_MATRIX))
    rows = _as_list(matrix.get("rows"))
    options = _as_mapping(matrix.get("dropdown_options"))
    columns = _as_list(matrix.get("visible_columns"))
    condition_keys = [
        clean_text(column.get("key"))
        for column in columns
        if _as_mapping(column).get("kind") == "condition" and clean_text(_as_mapping(column).get("key"))
    ]
    geometry_ids = {clean_text(item.get("value")) for item in _as_list(options.get("geometry_id")) if isinstance(item, Mapping)}
    option_values = {
        key: {clean_text(item.get("value")) for item in _as_list(options.get(key)) if isinstance(item, Mapping)}
        for key in condition_keys
    }

    if not rows:
        _add_issue(
            result,
            SEVERITY_BLOCKING,
            code="case_matrix.rows_missing",
            section=SECTION_CASE_MATRIX,
            path="case_matrix.rows",
            message="At least one Case is required.",
            action="Add a Case and map its geometry and active conditions.",
        )
        return

    seen_signatures: dict[tuple[str, ...], int] = {}
    for index, raw_row in enumerate(rows, start=1):
        row = _as_mapping(raw_row)
        geometry_id = clean_text(row.get("geometry_id"))
        case_is_valid = geometry_id in geometry_ids
        if geometry_id not in geometry_ids:
            _add_issue(
                result,
                SEVERITY_BLOCKING,
                code="case_matrix.geometry_missing",
                section=SECTION_CASE_MATRIX,
                path=f"case_matrix.rows[{index - 1}].geometry_id",
                field_key="geometry_id",
                message=f"Case {index} needs a valid geometry selection.",
                action="Select a geometry from the current geometry list.",
            )
        values = _as_mapping(row.get("condition_values"))
        for key in condition_keys:
            value = clean_text(values.get(key))
            if value in option_values.get(key, set()):
                continue
            case_is_valid = False
            _add_issue(
                result,
                SEVERITY_BLOCKING,
                code=f"case_matrix.{key}.missing",
                section=SECTION_CASE_MATRIX,
                path=f"case_matrix.rows[{index - 1}].condition_values.{key}",
                field_key=key,
                message=f"Case {index} needs a valid {key} selection.",
                action="Select one of the latest active condition values.",
            )
        if not case_is_valid:
            continue
        signature = (geometry_id, *(clean_text(values.get(key)) for key in condition_keys))
        matching_case_no = seen_signatures.get(signature)
        if matching_case_no is not None:
            _add_issue(
                result,
                SEVERITY_BLOCKING,
                code="case_matrix.duplicate",
                section=SECTION_CASE_MATRIX,
                path=f"case_matrix.rows[{index - 1}].geometry_id",
                field_key="geometry_id",
                message=f"Case {index} duplicates an existing Case.",
                action="Change the geometry or condition selection, or remove the duplicate Case.",
            )
            result[SEVERITY_BLOCKING][-1]["case_no"] = index
            result[SEVERITY_BLOCKING][-1]["duplicate_of_case_no"] = matching_case_no
            continue
        seen_signatures[signature] = index


def case_matrix_coverage(matrix: Mapping[str, Any]) -> dict[str, Any]:
    """Report unused current Matrix options without changing blocking readiness."""

    source = _as_mapping(matrix)
    columns = [_as_mapping(column) for column in _as_list(source.get("visible_columns"))]
    options = _as_mapping(source.get("dropdown_options"))
    rows = [_as_mapping(row) for row in _as_list(source.get("rows"))]
    geometry_column = next(
        (column for column in columns if clean_text(column.get("key")) == "geometry_id"),
        {},
    )
    condition_columns = [
        column
        for column in columns
        if column.get("kind") == "condition" and clean_text(column.get("key"))
    ]
    used_geometry = {clean_text(row.get("geometry_id")) for row in rows if clean_text(row.get("geometry_id"))}
    used_conditions = {
        clean_text(column.get("key")): {
            clean_text(_as_mapping(row.get("condition_values")).get(clean_text(column.get("key"))))
            for row in rows
            if clean_text(_as_mapping(row.get("condition_values")).get(clean_text(column.get("key"))))
        }
        for column in condition_columns
    }
    unused_items: list[dict[str, str]] = []

    def add_unused(kind: str, column: Mapping[str, Any], raw_options: Any, used: set[str]) -> None:
        column_key = clean_text(column.get("key"))
        column_label = clean_text(column.get("label"))
        seen_values: set[str] = set()
        for raw_option in _as_list(raw_options):
            option = _as_mapping(raw_option)
            value = clean_text(option.get("value"))
            if not value or value in seen_values:
                continue
            seen_values.add(value)
            if value in used:
                continue
            option_label = clean_text(option.get("label")) or value
            display_label = option_label
            if column_label and column_label not in option_label:
                display_label = f"{column_label} {option_label}"
            unused_items.append(
                {
                    "kind": kind,
                    "column_key": column_key,
                    "column_label": column_label,
                    "value": value,
                    "option_label": option_label,
                    "display_label": display_label,
                }
            )

    add_unused("geometry", geometry_column, options.get("geometry_id"), used_geometry)
    for column in condition_columns:
        key = clean_text(column.get("key"))
        add_unused("condition", column, options.get(key), used_conditions.get(key, set()))

    return {"complete": not unused_items, "unused_items": unused_items}


def validate_state(source: Mapping[str, Any]) -> ValidationResult:
    """Validate structured state and derived axes without using chat logs."""

    raw_source = source if isinstance(source, Mapping) else {}
    state, case_payload = _prepare_state_and_case_payload(raw_source)
    result = _new_result()

    _add_issue(
        result,
        SEVERITY_INFO,
        code="validator.structured_state_only",
        section="validator",
        message="Validation uses structured state, axes, and case matrix only.",
    )

    _validate_required_field_section(
        result,
        state=state,
        section_key=SECTION_BASIC_INFO,
        specs=BASIC_INFO_SPECS,
        section_label="basic information",
    )
    _validate_required_field_section(
        result,
        state=state,
        section_key=SECTION_ANALYSIS_OVERVIEW,
        specs=ANALYSIS_OVERVIEW_SPECS,
        section_label="analysis overview",
    )
    _validate_geometry(result, state)
    _validate_conditions(result, state)
    _validate_case_matrix(result, state)
    matrix = _as_mapping(state.get(SECTION_CASE_MATRIX))
    result["coverage"] = case_matrix_coverage(matrix)
    case_count = len(_as_list(matrix.get("rows")))
    can_submit = len(result[SEVERITY_BLOCKING]) == 0 and case_count > 0

    result["summary"] = {
        "can_generate_case_matrix": case_count > 0,
        "can_submit": can_submit,
        "blocking_count": len(result[SEVERITY_BLOCKING]),
        "warning_count": len(result[SEVERITY_WARNING]),
        "info_count": len(result[SEVERITY_INFO]),
    }
    return result


def state_with_validation(raw_state: Mapping[str, Any]) -> dict[str, Any]:
    """Return a state copy with review.validator and submission status populated."""

    state, case_payload = _prepare_state_and_case_payload(raw_state if isinstance(raw_state, Mapping) else {})
    validation = validate_state(state)

    state[SECTION_REVIEW]["validator"] = deepcopy(validation)
    state.setdefault("metadata", {})
    state["metadata"]["issue_registry"] = build_issue_registry(validation)
    state[SECTION_REVIEW]["submission"] = {
        "status": "ready" if validation["summary"]["can_submit"] else "not_ready",
        "can_submit": validation["summary"]["can_submit"],
        "blocking_reasons": [item["code"] for item in validation[SEVERITY_BLOCKING]],
        "warning_reasons": [item["code"] for item in validation[SEVERITY_WARNING]],
    }
    return state
