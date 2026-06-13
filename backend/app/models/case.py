import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String, default="en")
    case_type: Mapped[str | None] = mapped_column(String)
    severity: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="processing")
    relevant_sections: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text)
    next_steps: Mapped[list] = mapped_column(JSON, default=list)
    agent_reasoning: Mapped[str | None] = mapped_column(Text)
    legal_notice_draft: Mapped[str | None] = mapped_column(Text)
    pdf_url: Mapped[str | None] = mapped_column(String)
    pdf_id: Mapped[str | None] = mapped_column(String)
    clarifying_questions: Mapped[list] = mapped_column(JSON, default=list)
    action_buttons: Mapped[list] = mapped_column(JSON, default=list)
    ai_message: Mapped[str | None] = mapped_column(Text)
    legal_domain: Mapped[str | None] = mapped_column(String)
    case_readiness_score: Mapped[int] = mapped_column(Integer, default=0)
    evidence_available: Mapped[list] = mapped_column(JSON, default=list)
    evidence_missing: Mapped[list] = mapped_column(JSON, default=list)
    risk_level: Mapped[str] = mapped_column(String, default="medium")
    recommended_actions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        onupdate=datetime.now(timezone.utc),
    )
