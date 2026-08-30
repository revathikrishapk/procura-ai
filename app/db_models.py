from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class ProcurementRequestDB(Base):
    __tablename__ = "procurement_requests"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    raw_request: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    item_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    quantity: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    max_budget: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="received",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )