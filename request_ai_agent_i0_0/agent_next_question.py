"""Read-only selection of the next question from current validation blockers."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal, Mapping, TypedDict

from .agent_context import _build_instance_context
from .agent_write_contract import build_agent_write_contract
from .condition_fieldsets import CARD_TEMPLATES
from .field_registry import FieldRegistryDTO, get_field_registry
from .form_context import FormFieldContext, build_form_context
from .request_state_store import RequestStateSnapshot
from .validator import validate_state


class NextQuestion(TypedDict):
    kind: Literal["field_question", "ui_guidance", "complete"]
    message: str
    active_field_id: str | None
    blocking_code: str | None


@dataclass(frozen=True)
class _QuestionTarget:
    active_field_id: str
    label: str
    reference: str
    example: str
    parent_group_key: str = ""
    allowed_values: tuple[str, ...] = ()
    allow_custom_input: bool = False


_GEOMETRY_PATH_RE = re.compile(
    r"^geometry\.(base_product|comparison_products\[(\d+)\])\.([A-Za-z0-9_]+)$"
)


def plan_next_question(
    request_snapshot: RequestStateSnapshot,
    previous_active_field_id: str | None = None,
) -> NextQuestion:
    """Choose one next question without changing Request or conversation state."""

    state = request_snapshot.state
    validation = validate_state(state)
    summary = _mapping(validation.get("summary"))
    if summary.get("can_submit") is True:
        return {
            "kind": "complete",
            "message": "필수 입력이 완료되었습니다. 다음으로 Case Matrix에서 실제 해석할 Case와 조건 매핑을 확인해 주세요.",
            "active_field_id": None,
            "blocking_code": None,
        }

    blockers = [item for item in _list(validation.get("blocking")) if isinstance(item, Mapping)]
    form = build_form_context(state)
    form_fields = {field.field_id: field for field in form.fields}
    registry = get_field_registry(state)
    contract = build_agent_write_contract(state)
    instance_context = _build_instance_context(state)

    for issue in blockers:
        target = _resolve_writable_target(
            issue,
            state=state,
            form_fields=form_fields,
            registry=registry,
            contract=contract,
            instance_context=instance_context,
        )
        if target is None:
            continue
        return {
            "kind": "field_question",
            "message": _question_message(
                target,
                previous_group_key=_condition_group_for_active(state, previous_active_field_id),
                analysis_type=_text(_mapping(state.get("request_context")).get("analysis_type")),
            ),
            "active_field_id": target.active_field_id,
            "blocking_code": _text(issue.get("code")) or None,
        }

    issue = next((item for item in blockers if _text(item.get("code")) or _text(item.get("message"))), None)
    blocking_code = _text(issue.get("code")) if issue is not None else ""
    return {
        "kind": "ui_guidance",
        "message": _ui_guidance(issue),
        "active_field_id": None,
        "blocking_code": blocking_code or None,
    }


def _resolve_writable_target(
    issue: Mapping[str, Any],
    *,
    state: Mapping[str, Any],
    form_fields: Mapping[str, FormFieldContext],
    registry: tuple[FieldRegistryDTO, ...],
    contract: Mapping[str, Any],
    instance_context: Mapping[str, Mapping[str, Any]],
) -> _QuestionTarget | None:
    section = _text(issue.get("section"))
    if section in {"basic_info", "analysis_overview"}:
        return _general_target(issue, form_fields, registry, contract)
    if section == "geometry":
        return _geometry_target(issue, state, form_fields, contract, instance_context)
    if section == "conditions":
        return _condition_target(issue, state, form_fields, registry, contract, instance_context)
    return None


def _general_target(
    issue: Mapping[str, Any],
    form_fields: Mapping[str, FormFieldContext],
    registry: tuple[FieldRegistryDTO, ...],
    contract: Mapping[str, Any],
) -> _QuestionTarget | None:
    path = _text(issue.get("path"))
    field = next((row for row in registry if row.field_id == path and row.active), None)
    context = form_fields.get(field.field_id) if field is not None else None
    writable_paths = {
        _text(target.get("path"))
        for target in _targets(contract, "set")
        if isinstance(target, Mapping)
    }
    if field is None or context is None or context.system_generated or context.read_only:
        return None
    if field.operation_path not in writable_paths:
        return None
    return _QuestionTarget(field.field_id, context.label, "", context.example)


def _geometry_target(
    issue: Mapping[str, Any],
    state: Mapping[str, Any],
    form_fields: Mapping[str, FormFieldContext],
    contract: Mapping[str, Any],
    instance_context: Mapping[str, Mapping[str, Any]],
) -> _QuestionTarget | None:
    path = _text(issue.get("path"))
    matched = _GEOMETRY_PATH_RE.fullmatch(path)
    if matched is None:
        return None
    collection, raw_index, field_key = matched.groups()
    geometry = _mapping(state.get("geometry"))
    if collection == "base_product":
        product = _mapping(geometry.get("base_product"))
        form_id = path
    else:
        comparisons = _list(geometry.get("comparison_products"))
        index = int(raw_index)
        product = _mapping(comparisons[index]) if index < len(comparisons) else {}
        form_id = f"geometry.comparison_products[].{field_key}"
    geometry_id = _text(product.get("geometry_id"))
    context = form_fields.get(form_id)
    target = next(
        (
            row
            for row in _targets(contract, "set_geometry_field")
            if isinstance(row, Mapping) and _text(row.get("geometry_id")) == geometry_id
        ),
        None,
    )
    fields = _list(target.get("fields")) if isinstance(target, Mapping) else []
    writable_field = next(
        (row for row in fields if isinstance(row, Mapping) and _text(row.get("field_key")) == field_key),
        None,
    )
    reference = _reference_for(instance_context.get("geometry"), geometry_id)
    if context is None or context.system_generated or context.read_only or writable_field is None or not reference:
        return None
    return _QuestionTarget(
        active_field_id=path,
        label=_text(writable_field.get("label")) or context.label,
        reference=reference,
        example=context.example,
    )


def _condition_target(
    issue: Mapping[str, Any],
    state: Mapping[str, Any],
    form_fields: Mapping[str, FormFieldContext],
    registry: tuple[FieldRegistryDTO, ...],
    contract: Mapping[str, Any],
    instance_context: Mapping[str, Mapping[str, Any]],
) -> _QuestionTarget | None:
    instance_key = _text(issue.get("field_key"))
    field_id = f"conditions.{instance_key}" if instance_key else ""
    field = next((row for row in registry if row.field_id == field_id and row.active), None)
    context = form_fields.get(field_id)
    if field is None or context is None or context.system_generated or context.read_only:
        return None

    target = next(
        (
            row
            for row in _targets(contract, "set_condition_field")
            if isinstance(row, Mapping)
            and _text(row.get("card_id")) == field.card_id
            and _text(row.get("field_key")) == field.field_key
        ),
        None,
    )
    if not isinstance(target, Mapping):
        return None

    card_type = _text(target.get("card_type"))
    reference = _condition_reference(instance_context, field.card_id)
    if _same_type_card_count(state, card_type) <= 1:
        reference = ""
    label = _condition_field_label(card_type, field.field_key) or context.label
    if target.get("requires_fan_id") is True:
        fans = [fan for fan in _list(target.get("fans")) if isinstance(fan, Mapping)]
        if card_type == "operating" and field.field_key == "fan_rpm" and _text(target.get("fan_rpm_mode")) == "individual":
            incomplete_index = next(
                (
                    index
                    for index, fan in enumerate(fans)
                    if not _text(fan.get("location")) or not _text(fan.get("current_value"))
                ),
                None,
            )
            if incomplete_index is None:
                return None
            incomplete_fan = fans[incomplete_index]
            if not _text(incomplete_fan.get("location")):
                location_target = next(
                    (
                        row
                        for row in _targets(contract, "set_condition_field")
                        if isinstance(row, Mapping)
                        and _text(row.get("card_id")) == field.card_id
                        and _text(row.get("field_key")) == "fan_location"
                    ),
                    None,
                )
                writable_fans = _list(location_target.get("fans")) if isinstance(location_target, Mapping) else []
                fan_id = _text(incomplete_fan.get("fan_id"))
                if not any(isinstance(fan, Mapping) and _text(fan.get("fan_id")) == fan_id for fan in writable_fans):
                    return None
                return _QuestionTarget(
                    active_field_id=f"conditions.{field.card_id}.fan_location",
                    label=f"{_ordinal(incomplete_index + 1)} 팬의 위치",
                    reference=reference,
                    example="",
                    parent_group_key=card_type,
                )
        missing_index = next(
            (index for index, fan in enumerate(fans) if not _text(fan.get("current_value"))),
            None,
        )
        if missing_index is None:
            return None
        if len(fans) > 1:
            label = f"{_ordinal(missing_index + 1)} 팬의 회전수(RPM)"
            location = _text(fans[missing_index].get("location"))
            if location:
                label = f"{label} (위치: {location})"
    elif not reference and _same_type_card_count(state, _text(target.get("card_type"))) > 1:
        return None

    return _QuestionTarget(
        field.field_id,
        label,
        reference,
        context.example,
        parent_group_key=card_type,
        allowed_values=context.allowed_values,
        allow_custom_input=context.allow_custom_input,
    )


def _condition_reference(
    instance_context: Mapping[str, Mapping[str, Any]],
    card_id: str,
) -> str:
    for group in (
        "operating_conditions",
        "heat_exchangers",
        "space_environments",
        "supply_air_conditions",
    ):
        reference = _reference_for(instance_context.get(group), card_id)
        if reference:
            return reference
    return ""


def _same_type_card_count(state: Mapping[str, Any], card_type: str) -> int:
    conditions = _mapping(state.get("conditions"))
    return sum(
        1
        for card in _list(conditions.get("condition_sets"))
        if isinstance(card, Mapping) and _text(card.get("type")) == card_type
    )


def _targets(contract: Mapping[str, Any], operation: str) -> list[Any]:
    operations = _mapping(contract.get("operations"))
    definition = _mapping(operations.get(operation))
    return _list(definition.get("targets"))


def _reference_for(references: Mapping[str, Any] | None, instance_id: str) -> str:
    if not isinstance(references, Mapping):
        return ""
    return next((str(label) for label, value in references.items() if _text(value) == instance_id), "")


def _question_message(
    target: _QuestionTarget,
    *,
    previous_group_key: str = "",
    analysis_type: str = "",
) -> str:
    if target.allow_custom_input and "없음" in target.allowed_values:
        return "온도 조건에 따라 해석 결과가 달라질 수 있으므로, 확인된 온도 조건이 있다면 입력해 주세요. 별도 온도 조건이 없는 경우에만 ‘없음’을 선택해 주세요."
    subject = f"{target.reference}의 {target.label}" if target.reference else target.label
    if target.parent_group_key:
        message = f"{subject}{_object_particle(subject)} 알려주세요."
        if previous_group_key != target.parent_group_key:
            message = f"{_group_transition_message(target.parent_group_key)} {message}"
    else:
        message = f"{subject}{_object_particle(subject)} 입력해 주세요."
    example = _text(target.example)
    return f"{message} {example}" if example else message


def _condition_field_label(card_type: str, field_key: str) -> str:
    if card_type == "heat_exchanger" and field_key == "tube_diameter":
        return "관 직경"
    template = next((item for item in CARD_TEMPLATES if item["key"] == card_type), None)
    if not isinstance(template, Mapping):
        return ""
    return next((label for key, label, _unit in template["fields"] if key == field_key), "")


def _condition_group_label(card_type: str) -> str:
    template = next((item for item in CARD_TEMPLATES if item["key"] == card_type), None)
    return _text(template.get("label")) if isinstance(template, Mapping) else card_type


def _group_transition_message(card_type: str) -> str:
    return {
        "operating": "먼저 운전 조건을 확인하겠습니다.",
        "heat_exchanger": "이제는 열교환기 사양 정보가 필요합니다.",
        "space_environment": "다음은 공간 환경 조건을 확인하겠습니다.",
        "supply_air": "이제는 취출 공기 조건이 필요합니다.",
    }.get(card_type, f"이제는 {_condition_group_label(card_type)} 정보가 필요합니다.")


def _condition_group_for_active(state: Mapping[str, Any], active_field_id: str | None) -> str:
    active = _text(active_field_id)
    if not active.startswith("conditions."):
        return ""
    parts = active.split(".")
    if len(parts) != 3:
        return ""
    card_id = parts[1]
    conditions = _mapping(state.get("conditions"))
    card = next(
        (
            item
            for item in _list(conditions.get("condition_sets"))
            if isinstance(item, Mapping) and _text(item.get("id")) == card_id
        ),
        None,
    )
    return _text(card.get("type")) if isinstance(card, Mapping) else ""


def _ordinal(index: int) -> str:
    return {1: "첫 번째", 2: "두 번째", 3: "세 번째"}.get(index, f"{index}번째")


def _object_particle(value: str) -> str:
    for suffix, particle in (("Fin type", "을"), ("FPI", "를")):
        if value.endswith(suffix):
            return particle
    for character in reversed(value):
        codepoint = ord(character)
        if 0xAC00 <= codepoint <= 0xD7A3:
            return "을" if (codepoint - 0xAC00) % 28 else "를"
        if character.isalnum():
            return "를"
    return "을"


def _ui_guidance(issue: Mapping[str, Any] | None) -> str:
    if issue is None:
        return "검증 결과를 화면에서 확인해 주세요."
    section = _text(issue.get("section"))
    path = _text(issue.get("path"))
    if path.startswith("request_context."):
        return "의뢰 대상과 해석유형을 화면에서 확정해 주세요."
    if section == "case_matrix":
        return "Case Matrix에서 실제 해석할 Case와 조건 매핑을 확인해 주세요."
    section_label = {
        "geometry": "해석 제품",
        "conditions": "해석 조건",
        "basic_info": "의뢰자 정보",
        "analysis_overview": "요청 내용",
    }.get(section, section or "검증 결과")
    field_label = _text(issue.get("field_label"))
    detail = f" {field_label}" if field_label else " 필요한"
    return f"{section_label} 화면에서{detail} 항목을 확인해 주세요."


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str("" if value is None else value).replace("\x00", "").strip()
