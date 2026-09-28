from sqlalchemy import String, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Supplier(Base):

    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    company_id: Mapped[str] = mapped_column(
        String(64),
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    website: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    reliability_score: Mapped[float] = mapped_column(
        Float,
        default=0.0
    )

    verification_status: Mapped[str] = mapped_column(
        String(50),
        default="UNVERIFIED"
    )

    discovery_source: Mapped[str] = mapped_column(
        String(50),
        default="INTERNAL"
    )