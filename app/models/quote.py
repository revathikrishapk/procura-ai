from sqlalchemy import String, Integer, Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Quote(Base):
    __tablename__ = "quotes"

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

    supplier_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False
    )

    product_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    unit_price: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    total_price: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    currency: Mapped[str] = mapped_column(
        String(10),
        default="INR"
    )

    delivery_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    payment_terms: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    validity_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="RECEIVED"
    )