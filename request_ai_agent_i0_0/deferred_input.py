"""Request-scoped semantic input facts that do not yet have writable targets."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from .condition_fieldsets import CARD_TEMPLATES
from .state import field_value


ALLOWED_DEFERRED_KINDS = frozenset({"geometry_field", "condition_field"})
ALLOWED_GEOMETRY_FIELDS = frozenset({"drawing_no", "display_name", "difference_from_base"})
ALLOWED_CONDITION_FIELDS = {
    template["key"]: frozenset(key for key, _label, _unit in template["fields"] if key != "name")
    for template in CARD_TEMPLATES
}
MAX_SOURCE_SUMMARY_LENGTH = 500


def _clean(value: Any) -> str:
    return str("" if value is None else value).replace("\x00", "").strip()


def normalize_deferred_fact(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """Validate only semantic selectors; runtime instance ids are forbidden."""

    if not isinstance(raw, Mapping):
        return None
    kind = _clean(raw.get("kind"))
    target = raw.get("target")
    field_key = _clean(raw.get("field_key"))
    value = raw.get("value")
    source_summary = _clean(raw.get("source_summary"))
    if (
        kind not in ALLOWED_DEFERRED_KINDS
        or not isinstance(target, Mapping)
        or not field_key
        or not _clean(value)
        or not source_summary
        or len(source_summary) > MAX_SOURCE_SUMMARY_LENGTH
    ):
        return None
    forbidden = {"geometry_id", "card_id", "fan_id", "id"}
    if forbidden & set(target):
        return None

    if kind == "geometry_field":
        if field_key not in ALLOWED_GEOMETRY_FIELDS or not set(target) <= {"role", "product_reference"}:
            return None
        role = _clean(target.get("role"))
        reference = _clean(target.get("product_reference"))
        if (
            role not in {"base", "comparison"}
            or (role == "comparison" and not reference)
            or (role == "base" and field_key == "difference_from_base")
        ):
            return None
        normalized_target = {"role": role}
        if reference:
            normalized_target["product_reference"] = reference
    else:
        allowed = {"card_type", "card_name", "fan_name", "fan_location"}
        if not set(target) <= allowed:
            return None
        normalized_target = {key: _clean(target.get(key)) for key in allowed if _clean(target.get(key))}
        card_type = normalized_target.get("card_type", "")
        if not card_type or field_key not in ALLOWED_CONDITION_FIELDS.get(card_type, frozenset()):
            return None

    return {
        "kind": kind,
        "target": normalized_target,
        "field_key": field_key,
        "value": deepcopy(value),
        "source_summary": source_summary,
    }


def deferred_fact_key(fact: Mapping[str, Any]) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    target = fact.get("target") if isinstance(fact.get("target"), Mapping) else {}
    return (
        _clean(fact.get("kind")),
        _clean(fact.get("field_key")),
        tuple(sorted((str(key), _clean(value).casefold()) for key, value in target.items())),
    )


def _geometry_cards(state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    geometry = state.get("geometry") if isinstance(state.get("geometry"), Mapping) else {}
    comparisons = geometry.get("comparison_products")
    return [
        card
        for card in [geometry.get("base_product"), *(comparisons if isinstance(comparisons, list) else [])]
        if isinstance(card, Mapping) and _clean(card.get("geometry_id"))
    ]


def _matches_reference(card: Mapping[str, Any], reference: str) -> bool:
    expected = reference.casefold()
    return any(
        _clean(field_value(card.get(key), "")).casefold() == expected
        for key in ("drawing_no", "display_name")
    )


def _condition_cards(state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    conditions = state.get("conditions") if isinstance(state.get("conditions"), Mapping) else {}
    cards = conditions.get("condition_sets")
    return [card for card in cards if isinstance(card, Mapping)] if isinstance(cards, list) else []


def _current_value_for_geometry(card: Mapping[str, Any], field_key: str) -> Any:
    return field_value(card.get(field_key), "")


def _resolve_geometry(fact: Mapping[str, Any], state: Mapping[str, Any]) -> tuple[str, dict[str, Any] | None]:
    target = fact["target"]
    role = _clean(target.get("role"))
    reference = _clean(target.get("product_reference"))
    matches = [card for card in _geometry_cards(state) if _clean(card.get("role")) == role]
    if reference:
        matches = [card for card in matches if _matches_reference(card, reference)]
    if not matches:
        return "waiting_target", None
    if len(matches) != 1:
        return "ambiguous", None
    card = matches[0]
    current = _current_value_for_geometry(card, fact["field_key"])
    if _clean(current):
        return ("already_applied" if _clean(current) == _clean(fact["value"]) else "superseded"), None
    return "ready", {
        "op": "set_geometry_field",
        "geometry_id": _clean(card.get("geometry_id")),
        "field_key": fact["field_key"],
        "value": deepcopy(fact["value"]),
        "label": fact["source_summary"],
        "confidence": "high",
    }


def _card_matches(card: Mapping[str, Any], target: Mapping[str, Any]) -> bool:
    if _clean(card.get("type")) != _clean(target.get("card_type")):
        return False
    card_name = _clean(target.get("card_name"))
    if not card_name:
        return True
    fields = card.get("fields") if isinstance(card.get("fields"), Mapping) else {}
    names = {_clean(card.get("name")).casefold(), _clean(card.get("label")).casefold()}
    names.add(_clean(field_value(fields.get("name"), "")).casefold())
    return card_name.casefold() in names


def _resolve_condition(fact: Mapping[str, Any], state: Mapping[str, Any]) -> tuple[str, dict[str, Any] | None]:
    target = fact["target"]
    matches = [card for card in _condition_cards(state) if _card_matches(card, target)]
    if not matches:
        return "waiting_target", None
    if len(matches) != 1:
        return "ambiguous", None
    card = matches[0]
    field_key = fact["field_key"]
    operation: dict[str, Any] = {
        "op": "set_condition_field",
        "card_id": _clean(card.get("id")),
        "field_key": field_key,
        "value": deepcopy(fact["value"]),
        "label": fact["source_summary"],
        "confidence": "high",
    }
    if field_key == "fan_rpm":
        fans = [fan for fan in card.get("fans", []) if isinstance(fan, Mapping)] if isinstance(card.get("fans"), list) else []
        fan_name = _clean(target.get("fan_name"))
        fan_location = _clean(target.get("fan_location"))
        if fan_name:
            fans = [fan for fan in fans if _clean(fan.get("name")).casefold() == fan_name.casefold()]
        if fan_location:
            fans = [fan for fan in fans if _clean(fan.get("location")).casefold() == fan_location.casefold()]
        if not fans:
            return "waiting_target", None
        if len(fans) != 1:
            return "ambiguous", None
        fan = fans[0]
        current = (fan.get("values") if isinstance(fan.get("values"), Mapping) else {}).get(field_key, "")
        if _clean(current):
            return ("already_applied" if _clean(current) == _clean(fact["value"]) else "superseded"), None
        operation["fan_id"] = _clean(fan.get("id"))
    else:
        fields = card.get("fields") if isinstance(card.get("fields"), Mapping) else {}
        if field_key not in fields:
            return "waiting_target", None
        current = field_value(fields.get(field_key), "")
        if _clean(current):
            return ("already_applied" if _clean(current) == _clean(fact["value"]) else "superseded"), None
    return "ready", operation


def reconcile_deferred_facts(
    facts: Sequence[Mapping[str, Any]],
    state: Mapping[str, Any],
    *,
    request_version: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return retained facts and current deterministic operation candidates."""

    retained: list[dict[str, Any]] = []
    ready: list[dict[str, Any]] = []
    for raw in facts:
        fact = deepcopy(dict(raw))
        if fact.get("kind") == "geometry_field":
            resolution, operation = _resolve_geometry(fact, state)
        else:
            resolution, operation = _resolve_condition(fact, state)
        if resolution in {"already_applied", "superseded"}:
            continue
        fact["resolution"] = resolution
        fact["last_checked_version"] = request_version
        retained.append(fact)
        if resolution == "ready" and operation is not None:
            ready.append({"fact": deepcopy(fact), "operation": operation})
    return retained, ready
