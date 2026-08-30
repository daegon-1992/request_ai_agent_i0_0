"""seed submission master data

Revision ID: d2f8a41c9b70
Revises: 51c32db542a4
Create Date: 2026-08-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert


revision: str = "d2f8a41c9b70"
down_revision: Union[str, Sequence[str], None] = "51c32db542a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ANALYSIS_TYPES = (
    ("AIRFLOW", "풍량", "ACTIVE", 10),
    ("AIRFLOW_PATTERN", "기류 패턴", "ACTIVE", 20),
    ("DEW", "이슬맺힘", "ACTIVE", 30),
    ("HEX_VELOCITY_PROFILE", "열교환기 유속 프로파일", "ACTIVE", 40),
)

CONDITION_GROUPS = (
    ("OPERATING", "운전 조건", "팬 구성과 회전수 조건", 10),
    ("HEAT_EXCHANGER", "열교환기 사양", "열교환기 형상 사양", 20),
    ("SUPPLY_AIR", "취출 공기 조건", "취출 공기의 온도와 상대습도", 30),
    ("SPACE_ENVIRONMENT", "공간 환경 조건", "설치 공간의 온도와 상대습도", 40),
)

CONDITION_FIELDS = (
    ("OPERATING", "fan_rpm", "팬 회전수(RPM)", "number", "RPM", 10),
    ("HEAT_EXCHANGER", "name", "사양", "text", None, 10),
    ("HEAT_EXCHANGER", "tube_diameter", "관 직경(Pi)", "text", "mm", 20),
    ("HEAT_EXCHANGER", "fin_type", "Fin type", "text", None, 30),
    ("HEAT_EXCHANGER", "row_count", "열 수", "integer", None, 40),
    ("HEAT_EXCHANGER", "fpi", "FPI", "number", None, 50),
    ("SUPPLY_AIR", "heat_exchanger_temp", "취출 온도", "number", "°C", 10),
    ("SUPPLY_AIR", "heat_exchanger_rh", "취출 상대습도", "number", "%", 20),
    ("SPACE_ENVIRONMENT", "room_temp", "공간 온도", "number", "°C", 10),
    ("SPACE_ENVIRONMENT", "room_rh", "공간 상대습도", "number", "%", 20),
)

ANALYSIS_TYPE_FIELDS = {
    "AIRFLOW": (
        ("OPERATING", "fan_rpm"),
        ("HEAT_EXCHANGER", "name"),
        ("HEAT_EXCHANGER", "tube_diameter"),
        ("HEAT_EXCHANGER", "fin_type"),
        ("HEAT_EXCHANGER", "row_count"),
        ("HEAT_EXCHANGER", "fpi"),
    ),
    "HEX_VELOCITY_PROFILE": (
        ("OPERATING", "fan_rpm"),
        ("HEAT_EXCHANGER", "name"),
        ("HEAT_EXCHANGER", "tube_diameter"),
        ("HEAT_EXCHANGER", "fin_type"),
        ("HEAT_EXCHANGER", "row_count"),
        ("HEAT_EXCHANGER", "fpi"),
    ),
    "AIRFLOW_PATTERN": (
        ("OPERATING", "fan_rpm"),
        ("HEAT_EXCHANGER", "name"),
        ("HEAT_EXCHANGER", "tube_diameter"),
        ("HEAT_EXCHANGER", "fin_type"),
        ("HEAT_EXCHANGER", "row_count"),
        ("HEAT_EXCHANGER", "fpi"),
        ("SUPPLY_AIR", "heat_exchanger_temp"),
        ("SPACE_ENVIRONMENT", "room_temp"),
    ),
    "DEW": tuple(
        (group_code, field_code)
        for group_code, field_code, _name, _value_type, _unit, _sort_order
        in CONDITION_FIELDS
    ),
}


def _tables() -> tuple[sa.Table, sa.Table, sa.Table, sa.Table]:
    metadata = sa.MetaData()
    analysis_types = sa.Table(
        "analysis_types",
        metadata,
        sa.Column("id", sa.Integer),
        sa.Column("code", sa.String),
        sa.Column("name", sa.String),
        sa.Column("status", sa.String),
        sa.Column("sort_order", sa.Integer),
    )
    condition_groups = sa.Table(
        "condition_groups",
        metadata,
        sa.Column("id", sa.Integer),
        sa.Column("code", sa.String),
        sa.Column("name", sa.String),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String),
        sa.Column("sort_order", sa.Integer),
    )
    condition_fields = sa.Table(
        "condition_fields",
        metadata,
        sa.Column("id", sa.Integer),
        sa.Column("condition_group_id", sa.Integer),
        sa.Column("code", sa.String),
        sa.Column("name", sa.String),
        sa.Column("value_type", sa.String),
        sa.Column("unit", sa.String),
        sa.Column("status", sa.String),
        sa.Column("sort_order", sa.Integer),
    )
    analysis_type_conditions = sa.Table(
        "analysis_type_conditions",
        metadata,
        sa.Column("analysis_type_id", sa.Integer),
        sa.Column("condition_field_id", sa.Integer),
        sa.Column("required_level", sa.String),
        sa.Column("allows_not_applicable", sa.Boolean),
        sa.Column("sort_order", sa.Integer),
    )
    return analysis_types, condition_groups, condition_fields, analysis_type_conditions


def upgrade() -> None:
    analysis_types, condition_groups, condition_fields, analysis_type_conditions = _tables()
    bind = op.get_bind()

    for code, name, status, sort_order in ANALYSIS_TYPES:
        statement = insert(analysis_types).values(
            code=code,
            name=name,
            status=status,
            sort_order=sort_order,
        )
        bind.execute(
            statement.on_conflict_do_update(
                index_elements=[analysis_types.c.code],
                set_={
                    "name": statement.excluded.name,
                    "status": statement.excluded.status,
                    "sort_order": statement.excluded.sort_order,
                },
            )
        )

    for code, name, description, sort_order in CONDITION_GROUPS:
        statement = insert(condition_groups).values(
            code=code,
            name=name,
            description=description,
            status="ACTIVE",
            sort_order=sort_order,
        )
        bind.execute(
            statement.on_conflict_do_update(
                index_elements=[condition_groups.c.code],
                set_={
                    "name": statement.excluded.name,
                    "description": statement.excluded.description,
                    "status": statement.excluded.status,
                    "sort_order": statement.excluded.sort_order,
                },
            )
        )

    group_ids = dict(bind.execute(sa.select(condition_groups.c.code, condition_groups.c.id)).all())
    for group_code, code, name, value_type, unit, sort_order in CONDITION_FIELDS:
        statement = insert(condition_fields).values(
            condition_group_id=group_ids[group_code],
            code=code,
            name=name,
            value_type=value_type,
            unit=unit,
            status="ACTIVE",
            sort_order=sort_order,
        )
        bind.execute(
            statement.on_conflict_do_update(
                index_elements=[condition_fields.c.condition_group_id, condition_fields.c.code],
                set_={
                    "name": statement.excluded.name,
                    "value_type": statement.excluded.value_type,
                    "unit": statement.excluded.unit,
                    "status": statement.excluded.status,
                    "sort_order": statement.excluded.sort_order,
                },
            )
        )

    analysis_type_ids = dict(bind.execute(sa.select(analysis_types.c.code, analysis_types.c.id)).all())
    field_ids = {
        (group_code, code): field_id
        for group_code, code, field_id in bind.execute(
            sa.select(condition_groups.c.code, condition_fields.c.code, condition_fields.c.id).join(
                condition_fields,
                condition_fields.c.condition_group_id == condition_groups.c.id,
            )
        ).all()
    }
    mappings = []
    for analysis_type_code, fields in ANALYSIS_TYPE_FIELDS.items():
        for sort_order, field_key in enumerate(fields, start=1):
            mappings.append(
                {
                    "analysis_type_id": analysis_type_ids[analysis_type_code],
                    "condition_field_id": field_ids[field_key],
                    "required_level": "REQUIRED",
                    "allows_not_applicable": False,
                    "sort_order": sort_order * 10,
                }
            )
    for mapping in mappings:
        statement = insert(analysis_type_conditions).values(**mapping)
        bind.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    analysis_type_conditions.c.analysis_type_id,
                    analysis_type_conditions.c.condition_field_id,
                ],
                set_={
                    "required_level": statement.excluded.required_level,
                    "allows_not_applicable": statement.excluded.allows_not_applicable,
                    "sort_order": statement.excluded.sort_order,
                },
            )
        )


def downgrade() -> None:
    # These rows may have existed before this migration.  Preserve shared
    # master data when downgrading instead of deleting user-managed rows.
    pass
