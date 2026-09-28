from sqlalchemy import String, Integer, Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ProcurementCase(Base):
    __tablename__ = "procurement_cases"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
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

    product_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    budget: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
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

    current_stage: Mapped[str] = mapped_column(
        String(50),
        default="INTAKE"
    )