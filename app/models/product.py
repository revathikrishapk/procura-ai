from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Product(Base):

    __tablename__ = "products"

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
        index=True
    )

    category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    description: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True
    )