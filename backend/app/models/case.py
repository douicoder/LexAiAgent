import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
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
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=datetime.datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime,
        onupdate=datetime.datetime.utcnow,
    )
