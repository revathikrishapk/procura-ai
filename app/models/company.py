from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Company(Base):

    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )