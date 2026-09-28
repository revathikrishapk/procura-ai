from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SupplierProduct(Base):

    __tablename__ = "supplier_products"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    company_id: Mapped[str] = mapped_column(
        String(64),
        index=True
    )

    supplier_id: Mapped[str] = mapped_column(
        String(64),
        index=True
    )

    product_id: Mapped[str] = mapped_column(
        String(64),
        index=True
    )

    last_price: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    currency: Mapped[str] = mapped_column(
        String(10),
        default="INR"
    )

    lead_time_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    source: Mapped[str] = mapped_column(
        String(50),
        default="INTERNAL"
    )