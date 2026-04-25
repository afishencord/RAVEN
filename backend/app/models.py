from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="viewer", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RemediationProfile(TimestampMixin, Base):
    __tablename__ = "remediation_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    allowed_action_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_targets: Mapped[list[str]] = mapped_column(JSON, default=list)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300)
    retry_limit: Mapped[int] = mapped_column(Integer, default=1)
    post_action_validation: Mapped[dict] = mapped_column(JSON, default=dict)


class NodeGroup(TimestampMixin, Base):
    __tablename__ = "node_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)


class Node(TimestampMixin, Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    environment: Mapped[str] = mapped_column(String(32), default="prod", index=True)
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    health_check_type: Mapped[str] = mapped_column(String(32), default="http")
    health_check_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expected_status_code: Mapped[int] = mapped_column(Integer, default=200)
    expected_response_contains: Mapped[str | None] = mapped_column(String(255), nullable=True)
    check_interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=5)
    retry_count: Mapped[int] = mapped_column(Integer, default=3)
    remediation_profile: Mapped[str] = mapped_column(String(64), default="command-executor", index=True)
    execution_mode: Mapped[str] = mapped_column(String(32), default="runner", index=True)
    execution_target: Mapped[str] = mapped_column(String(255))
    group_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    context_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_command_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_id: Mapped[int | None] = mapped_column(ForeignKey("credentials.id"), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    current_status: Mapped[str] = mapped_column(String(32), default="healthy", index=True)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_incident_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    health_checks: Mapped[list["HealthCheckResult"]] = relationship(back_populates="node", cascade="all, delete-orphan")
    incidents: Mapped[list["Incident"]] = relationship(back_populates="node", cascade="all, delete-orphan")
    executions: Mapped[list["ExecutionTask"]] = relationship(back_populates="node", cascade="all, delete-orphan")


class HealthCheckResult(Base):
    __tablename__ = "health_check_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    node: Mapped["Node"] = relationship(back_populates="health_checks")


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    severity: Mapped[str] = mapped_column(String(32), default="high")
    failure_type: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_failure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    node: Mapped["Node"] = relationship(back_populates="incidents")
    recommendations: Mapped[list["AIRecommendation"]] = relationship(back_populates="incident", cascade="all, delete-orphan")
    messages: Mapped[list["AlertMessage"]] = relationship(back_populates="incident", cascade="all, delete-orphan")
    notes: Mapped[list["IncidentNote"]] = relationship(back_populates="incident", cascade="all, delete-orphan")
    approvals: Mapped[list["ApprovalDecision"]] = relationship(back_populates="incident", cascade="all, delete-orphan")


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="generated")
    suspected_issue_classification: Mapped[str] = mapped_column(String(128))
    summary: Mapped[str] = mapped_column(Text)
    troubleshooting_steps: Mapped[list[str]] = mapped_column(JSON, default=list)
    proposed_actions: Mapped[list[dict]] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(Text)
    raw_response: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    incident: Mapped["Incident"] = relationship(back_populates="recommendations")


class AlertMessage(Base):
    __tablename__ = "alert_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    channel_type: Mapped[str] = mapped_column(String(32), default="internal")
    status: Mapped[str] = mapped_column(String(32), default="open")
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    incident: Mapped["Incident"] = relationship(back_populates="messages")


class IncidentNote(Base):
    __tablename__ = "incident_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    incident: Mapped["Incident"] = relationship(back_populates="notes")


class ExecutionTask(Base):
    __tablename__ = "execution_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("remediation_profiles.id"), index=True)
    action_key: Mapped[str] = mapped_column(String(128))
    proposal_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    proposal_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target: Mapped[str] = mapped_column(String(255))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    execution_method: Mapped[str] = mapped_column(String(32), default="local")
    execution_mode: Mapped[str] = mapped_column(String(32), default="runner")
    approved_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    command_preview: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_validation_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    node: Mapped["Node"] = relationship(back_populates="executions")


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("ai_recommendations.id"), nullable=True)
    execution_task_id: Mapped[int | None] = mapped_column(ForeignKey("execution_tasks.id"), nullable=True)
    action_key: Mapped[str] = mapped_column(String(128))
    decision: Mapped[str] = mapped_column(String(32), index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    incident: Mapped["Incident"] = relationship(back_populates="approvals")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Credential(TimestampMixin, Base):
    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    secret_value: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
