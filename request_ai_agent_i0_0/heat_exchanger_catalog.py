"""Load the embedded standard heat-exchanger specifications.

The pressure-loss workbook remains supported as an explicit override for
diagnostics and catalog refreshes, but normal application runtime does not
depend on that external file.
"""

from __future__ import annotations

import os
import posixpath
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from .condition_fieldsets import HEAT_EXCHANGER_TYPES, heat_exchanger_type_from_tube_diameter


WORKBOOK_ENV = "HEAT_EXCHANGER_DB_PATH"
WORKBOOK_FILENAME = "열교환기압력손실DB_Final.xlsx"
WORKSHEET_NAME = "압손DB_과제결과"
STANDARD_MARKER = "O"
SPEC_FIELD_KEYS = ("tube_diameter", "fin_type", "row_count", "fpi")

# Canonical rows copied from the workbook's standard ("O") entries.  Keep the
# workbook order because the UI uses it as the cascading-select display order.
EMBEDDED_STANDARD_SPECS: tuple[tuple[str, str, str, str], ...] = (
    ("5", "Slit(Half)", "1", "21"),
    ("5", "Slit(Half)", "2", "20"),
    ("5", "Slit(Half)", "2", "21"),
    ("5", "Slit(Half)", "2", "22"),
    ("5", "Slit(Half)", "3", "21"),
    ("5", "Slit(Half)", "3", "22"),
    ("5", "Slit(High)", "2", "22"),
    ("7", "Louver", "1", "18"),
    ("7", "Louver", "1", "19"),
    ("7", "Louver", "1", "21"),
    ("7", "Louver", "2", "18"),
    ("7", "Louver", "2", "19"),
    ("7", "Louver", "2", "21"),
    ("7", "Louver", "3", "18"),
    ("7", "Louver", "3", "19"),
    ("7", "Louver", "3", "20"),
    ("7", "Louver", "3", "21"),
    ("7", "Louver", "4", "19"),
    ("7", "Louver", "4", "21"),
    ("7", "WL+", "1", "14"),
    ("7", "WL+", "2", "14"),
    ("7", "WL+", "2", "16"),
    ("7", "WL+", "2", "17"),
    ("7", "WL+", "2", "18"),
    ("7", "WL+", "3", "14"),
    ("7", "WL+", "3", "16"),
    ("7", "WL+", "3", "17"),
    ("7", "WL+", "3", "18"),
    ("7", "Slit(Half)", "2", "18"),
    ("7", "Slit(Half)", "2", "19"),
    ("7", "Slit(Half)", "2", "20"),
    ("7", "Slit(Half)", "2", "21"),
    ("7", "Slit(Half)", "2", "22"),
    ("7", "Slit(Half)", "3", "18"),
    ("7", "Slit(Half)", "3", "19"),
    ("7", "Slit(Half)", "3", "20"),
    ("7", "Slit(Half)", "3", "21"),
    ("7", "Slit(4-4)", "2", "18"),
    ("7", "Slit(4-4)", "2", "19"),
    ("7", "Slit(4-4)", "2", "20"),
    ("7", "Slit(4-4)", "2", "21"),
    ("7", "Slit(4-4)", "3", "19"),
    ("7", "Slit(4-4)", "3", "20"),
    ("7", "Corrugate", "2", "17"),
    ("7", "Corrugate", "2", "18"),
    ("7", "Corrugate", "3", "18"),
    ("7", "Corrugate(\uc2e0\uaddc)", "2", "16"),
    ("7", "Corrugate(\uc2e0\uaddc)", "2", "17"),
    ("7", "Corrugate(\uc2e0\uaddc)", "3", "16"),
    ("W10.5", "Flat(MCE)", "2", "67"),
    ("W14.5", "Flat(MCE)", "2", "67"),
    ("W16", "Flat(MCC)", "1", "75"),
    ("W16", "Flat(MCC)", "2", "75"),
)

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS = {"main": _MAIN_NS, "rel": _REL_NS}
_CELL_COLUMN = re.compile(r"[A-Z]+")


class HeatExchangerCatalogError(RuntimeError):
    """Raised when the configured workbook cannot provide the required catalog."""


def embedded_heat_exchanger_catalog() -> list[dict[str, str]]:
    """Return mutable row copies of the built-in canonical catalog."""

    return [dict(zip(SPEC_FIELD_KEYS, values)) for values in EMBEDDED_STANDARD_SPECS]


def resolve_heat_exchanger_workbook(path: str | Path | None = None) -> Path:
    """Resolve the explicitly supplied, configured, or workspace workbook path."""

    if path is not None:
        return Path(path).expanduser().resolve()
    configured = os.getenv(WORKBOOK_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "docs" / WORKBOOK_FILENAME


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t")) for item in root]


def _worksheet_path(archive: ZipFile, sheet_name: str) -> str:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        relationship.attrib["Id"]: relationship.attrib["Target"]
        for relationship in relationships.findall(f"{{{_PACKAGE_REL_NS}}}Relationship")
    }
    for sheet in workbook.findall("main:sheets/main:sheet", _NS):
        if sheet.attrib.get("name") != sheet_name:
            continue
        relationship_id = sheet.attrib.get(f"{{{_REL_NS}}}id", "")
        target = targets.get(relationship_id, "")
        if not target:
            break
        if target.startswith("/"):
            return target.lstrip("/")
        return posixpath.normpath(posixpath.join("xl", target))
    raise HeatExchangerCatalogError(f"워크시트를 찾을 수 없습니다: {sheet_name}")


def _cell_text(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", _NS)).strip()
    value_node = cell.find("main:v", _NS)
    if value_node is None or value_node.text is None:
        return ""
    if cell_type == "s":
        try:
            return shared_strings[int(value_node.text)].strip()
        except (IndexError, ValueError):
            return ""
    return value_node.text.strip()


def _sheet_rows(archive: ZipFile, sheet_path: str, shared_strings: list[str]) -> list[dict[str, str]]:
    root = ElementTree.fromstring(archive.read(sheet_path))
    rows: list[dict[str, str]] = []
    for row in root.findall(".//main:sheetData/main:row", _NS):
        values: dict[str, str] = {}
        for cell in row.findall("main:c", _NS):
            match = _CELL_COLUMN.match(cell.attrib.get("r", ""))
            if match:
                values[match.group(0)] = _cell_text(cell, shared_strings)
        rows.append(values)
    return rows


def load_heat_exchanger_catalog(path: str | Path | None = None) -> list[dict[str, str]]:
    """Return canonical rows, using the embedded catalog by default.

    Passing ``path`` explicitly retains the workbook loader for catalog audits
    and controlled refreshes.  Normal runtime calls intentionally avoid all
    filesystem dependencies.
    """

    if path is None:
        return embedded_heat_exchanger_catalog()

    workbook_path = resolve_heat_exchanger_workbook(path)
    if not workbook_path.is_file():
        raise HeatExchangerCatalogError(f"열교환기 압손 DB 파일을 찾을 수 없습니다: {workbook_path}")
    try:
        with ZipFile(workbook_path) as archive:
            shared_strings = _shared_strings(archive)
            sheet_path = _worksheet_path(archive, WORKSHEET_NAME)
            rows = _sheet_rows(archive, sheet_path, shared_strings)
    except (BadZipFile, KeyError, OSError, ElementTree.ParseError) as exc:
        raise HeatExchangerCatalogError(f"열교환기 압손 DB를 읽지 못했습니다: {workbook_path}") from exc

    header_aliases = {
        "tube_diameter": "관경",
        "fin_type": "핀타입",
        "row_count": "열수",
        "fpi": "FPI",
        "standard": "표준 여부",
    }
    header_columns: dict[str, str] = {}
    data_start = 0
    for index, row in enumerate(rows):
        by_header = {value: column for column, value in row.items()}
        if all(header in by_header for header in header_aliases.values()):
            header_columns = {key: by_header[header] for key, header in header_aliases.items()}
            data_start = index + 1
            break
    if not header_columns:
        raise HeatExchangerCatalogError("압손 DB에서 필수 열을 찾을 수 없습니다.")

    catalog: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    keys = ("tube_diameter", "fin_type", "row_count", "fpi")
    for row in rows[data_start:]:
        if row.get(header_columns["standard"], "").strip().upper() != STANDARD_MARKER:
            continue
        values = tuple(row.get(header_columns[key], "").strip() for key in keys)
        if not all(values) or values in seen:
            continue
        seen.add(values)
        catalog.append(dict(zip(keys, values)))
    return catalog


def build_heat_exchanger_catalog_payload(path: str | Path | None = None) -> dict[str, Any]:
    """Build the API payload from embedded rows or an explicit workbook."""

    try:
        rows = load_heat_exchanger_catalog(path)
    except HeatExchangerCatalogError as exc:
        return {
            "status": "unavailable",
            "rows": [],
            "row_count": 0,
            "sheet": WORKSHEET_NAME,
            "standard_marker": STANDARD_MARKER,
            "message": str(exc),
        }
    return {
        "status": "loaded",
        "rows": rows,
        "row_count": len(rows),
        "source": "embedded" if path is None else "workbook",
        "sheet": WORKSHEET_NAME,
        "standard_marker": STANDARD_MARKER,
    }


def _field_value(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("value", "")
    return str("" if value is None else value).replace("\x00", "").strip()


def _comparable_value(field_key: str, value: Any) -> str:
    """Normalize notation only for comparison; never invent a catalog value."""

    text = re.sub(r"\s+", "", _field_value(value)).casefold()
    suffixes = {
        "tube_diameter": ("mm", "pi"),
        "row_count": ("rows", "row", "열", "r"),
        "fpi": ("fpi",),
    }
    for suffix in suffixes.get(field_key, ()):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        text = text.rstrip("0").rstrip(".") if "." in text else text
    # The canonical State represents Micro-Channel fin variants as Flat while
    # the workbook keeps the detailed Flat(MCE/MCC) label.  The other three
    # attributes still disambiguate the registered workbook row.
    if field_key == "fin_type" and text.startswith("flat("):
        return "flat"
    return text


def _same_spec(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return all(
        _comparable_value(field_key, left.get(field_key))
        == _comparable_value(field_key, right.get(field_key))
        for field_key in SPEC_FIELD_KEYS
    )


def _complete_spec(spec: Mapping[str, Any]) -> bool:
    return all(_field_value(spec.get(field_key)) for field_key in SPEC_FIELD_KEYS)


def catalog_field_allowed_values(
    spec: Mapping[str, Any],
    field_key: str,
    heat_exchanger_type: str,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Return workbook-order values matching the card's other entered fields."""

    if field_key not in SPEC_FIELD_KEYS or heat_exchanger_type not in HEAT_EXCHANGER_TYPES:
        return ()
    fixed_value = _field_value(spec.get(field_key))
    micro_channel_fin = heat_exchanger_type == HEAT_EXCHANGER_TYPES[1] and field_key == "fin_type"
    if micro_channel_fin and not fixed_value:
        return ()

    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if heat_exchanger_type_from_tube_diameter(row.get("tube_diameter")) != heat_exchanger_type:
            continue
        if any(
            other_key != field_key
            and _field_value(spec.get(other_key))
            and _comparable_value(other_key, spec.get(other_key))
            != _comparable_value(other_key, row.get(other_key))
            for other_key in SPEC_FIELD_KEYS
        ):
            continue
        value = fixed_value if micro_channel_fin else _field_value(row.get(field_key))
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return tuple(values)


def _prospective_heat_exchanger_specs(
    proposed_state: Mapping[str, Any],
    operations: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, str]], set[int], bool]:
    conditions = proposed_state.get("conditions")
    cards = conditions.get("condition_sets") if isinstance(conditions, Mapping) else None
    heat_cards = [
        card
        for card in (cards if isinstance(cards, list) else [])
        if isinstance(card, Mapping) and _field_value(card.get("type")) == "heat_exchanger"
    ]
    specs = [
        {
            field_key: _field_value(
                card.get("fields", {}).get(field_key, "")
                if isinstance(card.get("fields"), Mapping)
                else ""
            )
            for field_key in SPEC_FIELD_KEYS
        }
        for card in heat_cards
    ]
    card_indexes = {
        _field_value(card.get("id")): index
        for index, card in enumerate(heat_cards)
        if _field_value(card.get("id"))
    }
    touched: set[int] = set()
    series_lengths: set[int] = set()
    for operation in operations:
        if not isinstance(operation, Mapping):
            continue
        op = _field_value(operation.get("op"))
        field_key = _field_value(operation.get("field_key"))
        if field_key not in SPEC_FIELD_KEYS:
            continue
        if op == "set_condition_card_series" and _field_value(operation.get("card_type")) == "heat_exchanger":
            values = operation.get("values")
            if not isinstance(values, list):
                continue
            series_lengths.add(len(values))
            for index, value in enumerate(values):
                if index < len(specs):
                    specs[index][field_key] = _field_value(value)
                    touched.add(index)
        elif op == "set_condition_field":
            index = card_indexes.get(_field_value(operation.get("card_id")))
            if index is not None:
                specs[index][field_key] = _field_value(operation.get("value"))
                touched.add(index)
    return specs, touched, len(series_lengths) > 1


def validate_heat_exchanger_proposal(
    proposed_state: Mapping[str, Any],
    operations: Iterable[Mapping[str, Any]],
    *,
    catalog_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate touched, complete heat-exchanger specs against canonical rows."""

    operation_list = [operation for operation in operations if isinstance(operation, Mapping)]
    specs, touched, mismatched_series = _prospective_heat_exchanger_specs(proposed_state, operation_list)
    if not touched:
        return {"valid": True, "message": "", "invalid_specs": [], "alternatives": []}
    if mismatched_series:
        return {
            "valid": False,
            "message": "복수 열교환기 사양의 속성별 개수가 일치하지 않아 Proposal을 만들지 않았습니다.",
            "invalid_specs": [],
            "alternatives": [],
        }

    try:
        rows = list(catalog_rows) if catalog_rows is not None else load_heat_exchanger_catalog()
    except HeatExchangerCatalogError:
        return {
            "valid": True,
            "message": "",
            "invalid_specs": [],
            "alternatives": [],
        }

    complete_touched = [specs[index] for index in sorted(touched) if _complete_spec(specs[index])]
    invalid = [spec for spec in complete_touched if not any(_same_spec(spec, row) for row in rows)]
    if not invalid:
        return {"valid": True, "message": "", "invalid_specs": [], "alternatives": []}

    return {
        "valid": True,
        "message": "",
        "invalid_specs": invalid,
        "alternatives": [],
    }
