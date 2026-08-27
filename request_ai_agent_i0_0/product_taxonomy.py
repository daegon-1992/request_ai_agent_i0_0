"""Canonical four-level product taxonomy used by request context."""

from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


TAXONOMY_FILENAME = "product_taxonomy.json"
DIVISION_DISPLAY_ORDER = ("SAC", "RAC", "Air Care", "Chiller")
DIVISION_ALIASES = {
    "aircare": "Air Care",
    "air care": "Air Care",
    "에어케어": "Air Care",
}


def _clean(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _canonical_division(value: Any) -> str:
    clean = _clean(value)
    return DIVISION_ALIASES.get(clean.casefold(), clean)


@lru_cache(maxsize=1)
def _payload() -> dict[str, Any]:
    path = Path(__file__).with_name(TAXONOMY_FILENAME)
    raw = json.loads(path.read_text(encoding="utf-8"))
    paths = raw.get("paths")
    if not isinstance(paths, list):
        raise ValueError("invalid_product_taxonomy_paths")
    if raw.get("row_count") != len(paths):
        raise ValueError("invalid_product_taxonomy_row_count")
    return raw


def load_product_taxonomy() -> dict[str, Any]:
    return deepcopy(_payload())


def taxonomy_paths() -> list[dict[str, Any]]:
    return deepcopy(_payload()["paths"])


def taxonomy_path_by_id(taxonomy_id: Any) -> dict[str, Any] | None:
    wanted = _clean(taxonomy_id)
    if not wanted:
        return None
    return next((deepcopy(item) for item in _payload()["paths"] if item.get("taxonomy_id") == wanted), None)


def build_taxonomy_tree() -> dict[str, dict[str, dict[str, list[dict[str, Any]]]]]:
    present = {_clean(item.get("division")) for item in _payload()["paths"]}
    tree: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {
        division: {} for division in DIVISION_DISPLAY_ORDER if division in present
    }
    for item in _payload()["paths"]:
        division = _clean(item.get("division"))
        product_lineup = _clean(item.get("product_lineup"))
        platform = _clean(item.get("platform"))
        leaf = {
            "taxonomy_id": _clean(item.get("taxonomy_id")),
            "chassis": item.get("chassis") if item.get("chassis") is None else _clean(item.get("chassis")),
            "display_path": _clean(item.get("display_path")),
        }
        tree.setdefault(division, {}).setdefault(product_lineup, {}).setdefault(platform, []).append(leaf)
    return tree


def find_product_taxonomy_matches(criteria: Mapping[str, Any]) -> list[dict[str, Any]]:
    allowed = ("taxonomy_id", "division", "product_lineup", "platform", "chassis")
    filters: dict[str, str | None] = {}
    for key in allowed:
        if key not in criteria:
            continue
        value = criteria.get(key)
        if key == "chassis" and value is None:
            filters[key] = None
            continue
        clean = _canonical_division(value) if key == "division" else _clean(value)
        if clean:
            filters[key] = clean.casefold()
    if not filters:
        return []
    matches: list[dict[str, Any]] = []
    for item in _payload()["paths"]:
        if all(
            (item.get(key) is None if expected is None else _clean(item.get(key)).casefold() == expected)
            for key, expected in filters.items()
        ):
            matches.append(deepcopy(item))
    return matches


def product_taxonomy_answer(criteria: Mapping[str, Any], matches: list[Mapping[str, Any]]) -> str:
    subject_values = []
    for key in ("division", "product_lineup", "platform", "chassis"):
        if key == "chassis" and key in criteria and criteria.get(key) is None:
            subject_values.append("null")
        elif _clean(criteria.get(key)):
            subject_values.append(_clean(criteria.get(key)))
    subject = " / ".join(subject_values) or _clean(criteria.get("taxonomy_id")) or "요청한 항목"
    if not matches:
        return (
            f"현재 제품 분류 기준에서 {subject}에 일치하는 경로를 찾지 못했습니다. "
            "해석 대상 제품 분류는 등록된 목록에서만 선택할 수 있습니다. 새로운 Product Line-up, Platform 또는 "
            "Chassis가 필요한 경우 해석의뢰관리자에게 분류 추가를 요청해 주세요."
        )
    descriptions = [_clean(item.get("display_path")) for item in matches]
    if len(descriptions) == 1:
        return f"제품 분류 기준에서 {descriptions[0]}에 해당합니다."
    return "제품 분류 기준에서 가능한 경로는 다음과 같습니다. " + "; ".join(descriptions)


def build_product_taxonomy_payload() -> dict[str, Any]:
    payload = _payload()
    division_codes: dict[str, str] = {}
    for item in payload["paths"]:
        label = _clean(item.get("division"))
        division_codes.setdefault(label, _clean(item.get("division_code")))
    ordered_labels = [label for label in DIVISION_DISPLAY_ORDER if label in division_codes]
    ordered_labels.extend(label for label in division_codes if label not in DIVISION_DISPLAY_ORDER)
    divisions = [{"code": division_codes[label], "label": label} for label in ordered_labels]
    return {
        "taxonomy_version": _clean(payload.get("taxonomy_version")),
        "source": _clean(payload.get("source")),
        "row_count": len(payload["paths"]),
        "variant_count": int(payload.get("variant_count", 0)),
        "division_counts": deepcopy(payload.get("division_counts", {})),
        "division_rules": deepcopy(payload.get("division_rules", {})),
        "divisions": divisions,
        "hierarchy": build_taxonomy_tree(),
        "paths": taxonomy_paths(),
    }
