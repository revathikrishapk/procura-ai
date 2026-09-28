from sqlalchemy import String, Integer, Date
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    po_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False
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

    supplier_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False
    )

    expected_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    expected_delivery_date: Mapped[Date | None] = mapped_column(
        Date,
        nullable=True
    )

    actual_delivery_date: Mapped[Date | None] = mapped_column(
        Date,
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="PENDING",
        index=True
    )

    tracking_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )