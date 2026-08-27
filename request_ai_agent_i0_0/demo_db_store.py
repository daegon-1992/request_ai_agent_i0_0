"""MySQL helpers for the h2_v2 demo DB POC."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import re
from typing import Any, Mapping


DEFAULT_DB_PORT = 3306
DEFAULT_DB_CHARSET = "utf8mb4"
USER_TABLE = "cae_demo_users"
ANALYSIS_TYPE_TABLE = "cae_demo_analysis_types"
PRODUCT_FAMILY_TABLE = "cae_demo_product_families"
REQUEST_TABLE = "cae_demo_requests"
CASE_TABLE = "cae_demo_request_cases"

REQUEST_COLUMNS = (
    "request_no",
    "requester_user_id",
    "analysis_type_id",
    "product_family_id",
    "app_version",
    "contract_version",
    "submit_ready",
    "analysis_type",
    "product_family_name",
    "product_name",
    "project_name",
    "requester_name",
    "request_date",
    "due_date",
    "purpose",
    "goal",
    "material_type",
    "fan_rpm",
    "room_temp",
    "room_rh",
    "heat_exchanger_temp",
    "heat_exchanger_rh",
    "common_conditions_json",
    "final_cases_json",
    "state_json",
    "final_payload_json",
    "db_upload_note",
)


def _clean(value: object) -> str:
    return str(value or "").strip()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _field_value(value: Any) -> str:
    if isinstance(value, Mapping):
        if "value" in value or "status" in value:
            raw = value.get("value")
            if raw is None or raw == "":
                raw = value.get("display_value")
            return _clean(raw)
    return _clean(value)


def _first_condition_value(fields: Any, key: str) -> str:
    for field in _as_list(fields):
        field_map = _as_mapping(field)
        if _clean(field_map.get("key")) != key:
            continue
        for row in _as_list(field_map.get("values")):
            text = _field_value(row)
            if text:
                return text
        return ""
    return ""


def _first_list_value(value: Any) -> str:
    for item in _as_list(value):
        text = _field_value(item)
        if text:
            return text
    return ""


def _first_case_geometry(final_cases: list[Any]) -> str:
    for item in final_cases:
        case_map = _as_mapping(item)
        visible_cells = _as_mapping(case_map.get("visible_cells"))
        text = _clean(visible_cells.get("geometry"))
        if text:
            return text
    return ""


def _code_from_text(prefix: str, value: str, *, max_length: int = 64) -> str:
    text = _clean(value)
    token = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    if not token:
        token = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12] if text else "unknown"
    return f"{prefix}_{token}"[:max_length]


def _request_no_from_state(state: Mapping[str, Any]) -> str:
    metadata = _as_mapping(state.get("metadata"))
    basic = _as_mapping(state.get("basic_info"))
    return _clean(metadata.get("request_no")) or _field_value(basic.get("request_no"))


def _date_or_none(value: Any) -> str | None:
    text = _field_value(value)
    return text[:10] if text else None


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = _clean(os.getenv(name)).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on", "enabled"}


def _env_int(name: str, *, default: int) -> int:
    raw = _clean(os.getenv(name))
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class DemoDbConfig:
    enabled: bool
    host: str
    port: int
    database: str
    user: str
    password: str
    charset: str
    connect_timeout: int

    @property
    def configured(self) -> bool:
        return bool(self.host and self.database and self.user)

    def public_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "charset": self.charset,
            "connect_timeout": self.connect_timeout,
            "password_set": bool(self.password),
        }


def get_demo_db_config() -> DemoDbConfig:
    return DemoDbConfig(
        enabled=_env_bool("REQUEST_AGENT_DEMO_DB_ENABLED", default=False),
        host=_clean(os.getenv("REQUEST_AGENT_DEMO_DB_HOST")) or "127.0.0.1",
        port=_env_int("REQUEST_AGENT_DEMO_DB_PORT", default=DEFAULT_DB_PORT),
        database=_clean(os.getenv("REQUEST_AGENT_DEMO_DB_NAME")) or "cae_demo",
        user=_clean(os.getenv("REQUEST_AGENT_DEMO_DB_USER")),
        password=str(os.getenv("REQUEST_AGENT_DEMO_DB_PASSWORD") or ""),
        charset=_clean(os.getenv("REQUEST_AGENT_DEMO_DB_CHARSET")) or DEFAULT_DB_CHARSET,
        connect_timeout=_env_int("REQUEST_AGENT_DEMO_DB_CONNECT_TIMEOUT", default=5),
    )


def _mysql_connector():
    try:
        import mysql.connector  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "mysql-connector-python is not installed. "
            "Install it with: py -m pip install -r requirements-h2_v2_demo_db.txt"
        ) from exc
    return mysql.connector


def open_demo_db_connection(config: DemoDbConfig | None = None):
    cfg = config or get_demo_db_config()
    if not cfg.enabled:
        raise RuntimeError("REQUEST_AGENT_DEMO_DB_ENABLED is not enabled.")
    if not cfg.configured:
        raise RuntimeError("Demo DB env is incomplete. Set host, database, and user.")
    connector = _mysql_connector()
    return connector.connect(
        host=cfg.host,
        port=cfg.port,
        database=cfg.database,
        user=cfg.user,
        password=cfg.password,
        charset=cfg.charset,
        connection_timeout=cfg.connect_timeout,
    )


def smoke_check_connection(config: DemoDbConfig | None = None) -> dict[str, Any]:
    cfg = config or get_demo_db_config()
    result: dict[str, Any] = {
        "ok": False,
        "config": cfg.public_dict(),
        "server_version": "",
        "current_database": "",
        "table_count": None,
        "message": "",
    }
    try:
        connection = open_demo_db_connection(cfg)
    except Exception as exc:  # pragma: no cover - environment dependent
        result["message"] = str(exc)
        return result

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT VERSION(), DATABASE()")
        row = cursor.fetchone()
        if row:
            result["server_version"] = str(row[0] or "")
            result["current_database"] = str(row[1] or "")
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name IN (
                'cae_demo_users',
                'cae_demo_analysis_types',
                'cae_demo_analysis_condition_fields',
                'cae_demo_analysis_condition_options',
                'cae_demo_product_families',
                'cae_demo_requests',
                'cae_demo_request_cases'
              )
            """
        )
        count_row = cursor.fetchone()
        result["table_count"] = int(count_row[0] or 0) if count_row else 0
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name IN (
                'cae_demo_users',
                'cae_demo_analysis_types',
                'cae_demo_analysis_condition_fields',
                'cae_demo_analysis_condition_options',
                'cae_demo_product_families',
                'cae_demo_requests',
                'cae_demo_request_cases'
              )
            """
        )
        present_tables = {str(row[0]) for row in cursor.fetchall()}
        required_tables = {
            "cae_demo_users",
            "cae_demo_analysis_types",
            "cae_demo_analysis_condition_fields",
            "cae_demo_analysis_condition_options",
            "cae_demo_product_families",
            "cae_demo_requests",
            "cae_demo_request_cases",
        }
        missing_tables = sorted(required_tables - present_tables)
        result["missing_tables"] = missing_tables
        result["ok"] = not missing_tables
        result["message"] = "Connection succeeded." if not missing_tables else f"Missing tables: {', '.join(missing_tables)}"
    except Exception as exc:  # pragma: no cover - environment dependent
        result["message"] = str(exc)
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        connection.close()
    return result


def build_submission_db_payload(
    *,
    state: Mapping[str, Any],
    final_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Build DB-ready scalar and JSON payloads from the submit contract."""

    payload_state = _as_mapping(final_payload.get("state")) or state
    basic = _as_mapping(payload_state.get("basic_info"))
    overview = _as_mapping(payload_state.get("analysis_overview"))
    geometry = _as_mapping(payload_state.get("geometry"))
    conditions = _as_mapping(payload_state.get("conditions"))
    case_matrix = _as_mapping(final_payload.get("case_matrix")) or _as_mapping(payload_state.get("case_matrix"))
    condition_fields = _as_list(conditions.get("fields"))
    final_cases = _as_list(case_matrix.get("final_cases"))
    common_conditions = _as_mapping(case_matrix.get("common_conditions"))
    request_no = _request_no_from_state(payload_state)
    product_name = _first_list_value(geometry.get("products")) or _first_case_geometry(final_cases)
    product_family_name = (
        _field_value(geometry.get("product_family"))
        or _field_value(geometry.get("product_group"))
        or _first_list_value(geometry.get("product_families"))
        or _field_value(overview.get("product_family"))
        or product_name
    )
    material_type = _first_condition_value(condition_fields, "material_type") or _first_condition_value(condition_fields, "working_fluid")

    request_row = {
        "request_no": request_no,
        "requester_user_id": None,
        "analysis_type_id": None,
        "product_family_id": None,
        "app_version": _clean(final_payload.get("app_version")),
        "contract_version": _clean(final_payload.get("contract_version")),
        "submit_ready": 1 if bool(final_payload.get("submit_ready")) else 0,
        "analysis_type": _field_value(overview.get("analysis_type")),
        "product_family_name": product_family_name,
        "product_name": product_name,
        "project_name": _field_value(overview.get("project_name")),
        "requester_name": _field_value(basic.get("requester_name")),
        "request_date": _date_or_none(overview.get("request_date")),
        "due_date": _date_or_none(overview.get("due_date")),
        "purpose": _field_value(overview.get("purpose")),
        "goal": _field_value(overview.get("goal")),
        "material_type": material_type,
        "fan_rpm": _first_condition_value(condition_fields, "fan_rpm"),
        "room_temp": _first_condition_value(condition_fields, "room_temp"),
        "room_rh": _first_condition_value(condition_fields, "room_rh"),
        "heat_exchanger_temp": _first_condition_value(condition_fields, "heat_exchanger_temp"),
        "heat_exchanger_rh": _first_condition_value(condition_fields, "heat_exchanger_rh"),
        "common_conditions_json": _json_dumps(common_conditions),
        "final_cases_json": _json_dumps(final_cases),
        "state_json": _json_dumps(payload_state),
        "final_payload_json": _json_dumps(final_payload),
        "db_upload_note": "Uploaded from h2_v2 /api/submit demo POC",
    }
    case_rows: list[dict[str, Any]] = []
    for index, case in enumerate(final_cases, start=1):
        case_map = _as_mapping(case)
        visible_cells = _as_mapping(case_map.get("visible_cells"))
        case_rows.append(
            {
                "request_no": request_no,
                "case_id": _clean(case_map.get("case_id")) or f"case_{index:03d}",
                "display_case_no": int(case_map.get("display_case_no") or case_map.get("case_no") or index),
                "geometry_label": _clean(visible_cells.get("geometry")),
                "variable_values_json": _json_dumps(_as_mapping(case_map.get("variable_values"))),
            }
        )
    return {
        "request_no": request_no,
        "request_row": request_row,
        "case_rows": case_rows,
    }


def _upsert_request(cursor: Any, row: Mapping[str, Any]) -> None:
    column_sql = ", ".join(REQUEST_COLUMNS)
    value_sql = ", ".join(["%s"] * len(REQUEST_COLUMNS))
    update_columns = [column for column in REQUEST_COLUMNS if column != "request_no"]
    update_sql = ", ".join(f"{column} = %s" for column in update_columns)
    cursor.execute(
        f"""
        INSERT INTO {REQUEST_TABLE} ({column_sql})
        VALUES ({value_sql})
        ON DUPLICATE KEY UPDATE {update_sql}
        """,
        [row.get(column) for column in REQUEST_COLUMNS] + [row.get(column) for column in update_columns],
    )


def _resolve_user_id(cursor: Any, row: Mapping[str, Any]) -> int | None:
    requester_name = _clean(row.get("requester_name"))
    if not requester_name:
        return None
    state = _as_mapping(_parse_json_text(row.get("state_json")))
    basic = _as_mapping(state.get("basic_info"))
    department = _field_value(basic.get("division")) or _field_value(basic.get("department"))
    email = _field_value(basic.get("requester_email")) or _field_value(basic.get("email"))
    user_uid = _code_from_text("user", email or requester_name, max_length=128)
    if email:
        cursor.execute(
            f"SELECT id FROM {USER_TABLE} WHERE email = %s OR user_uid = %s LIMIT 1",
            [email, user_uid],
        )
    else:
        cursor.execute(f"SELECT id FROM {USER_TABLE} WHERE user_uid = %s LIMIT 1", [user_uid])
    found = cursor.fetchone()
    if found:
        user_id = int(found[0])
        cursor.execute(
            f"""
            UPDATE {USER_TABLE}
            SET user_name = %s,
                department = %s,
                email = %s,
                role_name = COALESCE(role_name, 'Requester'),
                is_active = 1
            WHERE id = %s
            """,
            [requester_name, department or None, email or None, user_id],
        )
        return user_id
    cursor.execute(
        f"""
        INSERT INTO {USER_TABLE} (
          user_uid,
          user_name,
          department,
          email,
          role_name
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        [user_uid, requester_name, department or None, email or None, "Requester"],
    )
    return int(cursor.lastrowid or 0) or None


def _resolve_analysis_type_id(cursor: Any, analysis_type: str) -> int | None:
    name = _clean(analysis_type)
    if not name:
        return None
    code = name.upper() if re.fullmatch(r"[A-Za-z0-9_ -]+", name) else _code_from_text("an", name).upper()
    cursor.execute(
        f"""
        SELECT id
        FROM {ANALYSIS_TYPE_TABLE}
        WHERE analysis_code = %s OR analysis_name = %s
        LIMIT 1
        """,
        [code, name],
    )
    found = cursor.fetchone()
    if found:
        return int(found[0])
    solver_family = "Fluent" if code == "CFD" or "유동" in name else ""
    cursor.execute(
        f"""
        INSERT INTO {ANALYSIS_TYPE_TABLE} (
          analysis_code,
          analysis_name,
          solver_family,
          default_dimension,
          default_precision,
          description
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        [code, name, solver_family or None, "3d" if solver_family == "Fluent" else None, "dp" if solver_family == "Fluent" else None, "Auto-created from h2_v2 submit POC"],
    )
    return int(cursor.lastrowid or 0) or None


def _resolve_product_family_id(cursor: Any, product_family_name: str) -> int | None:
    name = _clean(product_family_name)
    if not name:
        return None
    code = _code_from_text("pf", name).upper()
    cursor.execute(
        f"""
        SELECT id
        FROM {PRODUCT_FAMILY_TABLE}
        WHERE product_family_code = %s OR product_family_name = %s
        LIMIT 1
        """,
        [code, name],
    )
    found = cursor.fetchone()
    if found:
        return int(found[0])
    cursor.execute(
        f"""
        INSERT INTO {PRODUCT_FAMILY_TABLE} (
          product_family_code,
          product_family_name,
          description
        )
        VALUES (%s, %s, %s)
        """,
        [code, name, "Auto-created from h2_v2 submit POC"],
    )
    return int(cursor.lastrowid or 0) or None


def _parse_json_text(value: Any) -> Any:
    if isinstance(value, (Mapping, list)):
        return value
    text = _clean(value)
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _attach_business_master_ids(cursor: Any, row: dict[str, Any]) -> None:
    row["requester_user_id"] = _resolve_user_id(cursor, row)
    row["analysis_type_id"] = _resolve_analysis_type_id(cursor, _clean(row.get("analysis_type")))
    row["product_family_id"] = _resolve_product_family_id(cursor, _clean(row.get("product_family_name")))


def _replace_cases(cursor: Any, *, request_id: int, request_no: str, case_rows: list[dict[str, Any]]) -> None:
    cursor.execute(f"DELETE FROM {CASE_TABLE} WHERE request_id = %s", [request_id])
    if not case_rows:
        return
    cursor.executemany(
        f"""
        INSERT INTO {CASE_TABLE} (
          request_id,
          request_no,
          case_id,
          display_case_no,
          geometry_label,
          variable_values_json
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        [
            [
                request_id,
                request_no,
                row.get("case_id"),
                row.get("display_case_no"),
                row.get("geometry_label"),
                row.get("variable_values_json"),
            ]
            for row in case_rows
        ],
    )


def upload_submission_to_demo_db(
    *,
    state: Mapping[str, Any],
    final_payload: Mapping[str, Any] | None,
    config: DemoDbConfig | None = None,
) -> dict[str, Any]:
    """Upload a submittable final payload to MySQL.

    The function is intentionally defensive: it returns status details instead
    of raising so the demo submit flow can continue even when MySQL is down.
    """

    cfg = config or get_demo_db_config()
    result: dict[str, Any] = {
        "enabled": cfg.enabled,
        "configured": cfg.configured,
        "attempted": False,
        "status": "disabled" if not cfg.enabled else "skipped",
        "request_no": "",
        "db_id": None,
        "case_count": 0,
        "message": "Demo DB upload is disabled.",
    }
    if not cfg.enabled:
        return result
    if not cfg.configured:
        result.update(
            {
                "status": "unconfigured",
                "message": "Demo DB env is incomplete. Set host, database, and user.",
            }
        )
        return result
    if not isinstance(final_payload, Mapping) or not final_payload.get("submit_ready"):
        result.update(
            {
                "status": "skipped",
                "message": "Submission is not ready, so DB upload was skipped.",
            }
        )
        return result

    db_payload = build_submission_db_payload(state=state, final_payload=final_payload)
    request_no = _clean(db_payload.get("request_no"))
    result["request_no"] = request_no
    if not request_no:
        result.update(
            {
                "status": "failed",
                "message": "Request number is missing, so DB upload was skipped.",
            }
        )
        return result

    connection = None
    cursor = None
    result["attempted"] = True
    try:
        connection = open_demo_db_connection(cfg)
        cursor = connection.cursor()
        request_row = dict(_as_mapping(db_payload.get("request_row")))
        _attach_business_master_ids(cursor, request_row)
        _upsert_request(cursor, request_row)
        cursor.execute(f"SELECT id FROM {REQUEST_TABLE} WHERE request_no = %s", [request_no])
        row = cursor.fetchone()
        request_id = int(row[0]) if row else 0
        if not request_id:
            raise RuntimeError("DB upload did not return a request id.")
        case_rows = [dict(item) for item in _as_list(db_payload.get("case_rows")) if isinstance(item, Mapping)]
        _replace_cases(cursor, request_id=request_id, request_no=request_no, case_rows=case_rows)
        connection.commit()
        result.update(
            {
                "status": "saved",
                "db_id": request_id,
                "case_count": len(case_rows),
                "message": f"DB upload completed. id={request_id}, cases={len(case_rows)}",
            }
        )
    except Exception as exc:  # pragma: no cover - depends on DB/network state
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        result.update(
            {
                "status": "failed",
                "message": _clean(exc)[:400],
            }
        )
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None:
            connection.close()
    return result
