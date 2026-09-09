from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.model.base import Base
from app.util.time import now


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    customer_id: Mapped[str | None] = mapped_column(String(64))
    key_id: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(48))
    # Key değeri, cookie ve dosya içeriği audit tablosuna ASLA yazılmaz.
    object_path: Mapped[str | None] = mapped_column(String(1024))
    request_id: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(32))
    __table_args__ = (Index("ix_audit_customer_created", "customer_id", "created_at"),)
