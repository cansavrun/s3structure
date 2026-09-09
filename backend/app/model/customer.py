from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.model.base import Base


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    bucket: Mapped[str] = mapped_column(String(63))
    prefix: Mapped[str] = mapped_column(String(512))
    role_arn: Mapped[str | None] = mapped_column(String(256))
    external_id: Mapped[str | None] = mapped_column(String(128))
    kms_key_arn: Mapped[str | None] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
