from sqlalchemy import String, Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    case_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False
    )

    company_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False
    )

    requested_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    approved_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    amount: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    currency: Mapped[str] = mapped_column(
        String(10),
        default="INR"
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="PENDING",
        index=True
    )

    comments: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )