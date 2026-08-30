from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    request_no: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )

    requester_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    current_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    current_revision_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    
class RequestRevision(Base):
    __tablename__ = "request_revisions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    request_id: Mapped[int] = mapped_column(
        ForeignKey("requests.id"),
        nullable=False,
    )

    revision_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    submitted_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    state_schema_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    snapshot_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    __table_args__ = (
    UniqueConstraint(
        "request_id",
        "revision_no",
        name="uq_request_revisions_request_revision",
        ),
    )
    
class WorkflowEvent(Base):
    __tablename__ = "workflow_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    request_id: Mapped[int] = mapped_column(
        ForeignKey("requests.id"),
        nullable=False,
    )

    revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("request_revisions.id"),
        nullable=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    from_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    to_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
class ReviewAction(Base):
    __tablename__ = "review_actions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    request_id: Mapped[int] = mapped_column(
        ForeignKey("requests.id"),
        nullable=False,
    )

    revision_id: Mapped[int] = mapped_column(
        ForeignKey("request_revisions.id"),
        nullable=False,
    )

    reviewer_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    action_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    request_id: Mapped[int] = mapped_column(
        ForeignKey("requests.id"),
        nullable=False,
    )

    analyst_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    assigned_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    request_id: Mapped[int] = mapped_column(
        ForeignKey("requests.id"),
        nullable=False,
    )

    revision_id: Mapped[int] = mapped_column(
        ForeignKey("request_revisions.id"),
        nullable=False,
    )

    analyst_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    result_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
class AnalysisType(Base):
    __tablename__ = "analysis_types"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    
class ConditionGroup(Base):
    __tablename__ = "condition_groups"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    
class ConditionField(Base):
    __tablename__ = "condition_fields"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    condition_group_id: Mapped[int] = mapped_column(
        ForeignKey("condition_groups.id"),
        nullable=False,
    )

    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    value_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    unit: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "condition_group_id",
            "code",
            name="uq_condition_fields_group_code",
        ),
    )
    
class AnalysisTypeCondition(Base):
    __tablename__ = "analysis_type_conditions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    analysis_type_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_types.id"),
        nullable=False,
    )

    condition_field_id: Mapped[int] = mapped_column(
        ForeignKey("condition_fields.id"),
        nullable=False,
    )

    required_level: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    allows_not_applicable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "analysis_type_id",
            "condition_field_id",
            name="uq_analysis_type_conditions_type_field",
        ),
    )
    
class ConditionInstance(Base):
    __tablename__ = "condition_instances"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    request_revision_id: Mapped[int] = mapped_column(
        ForeignKey("request_revisions.id"),
        nullable=False,
    )

    condition_group_id: Mapped[int] = mapped_column(
        ForeignKey("condition_groups.id"),
        nullable=False,
    )

    instance_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    instance_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "request_revision_id",
            "instance_key",
            name="uq_condition_instances_revision_key",
        ),
    )
    
class ConditionValue(Base):
    __tablename__ = "condition_values"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    condition_instance_id: Mapped[int] = mapped_column(
        ForeignKey("condition_instances.id"),
        nullable=False,
    )

    condition_field_id: Mapped[int] = mapped_column(
        ForeignKey("condition_fields.id"),
        nullable=False,
    )

    value_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    display_value: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    value_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    value_source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "condition_instance_id",
            "condition_field_id",
            name="uq_condition_values_instance_field",
        ),
    )