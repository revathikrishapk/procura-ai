import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./procura.db")

engine_options = {}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_options)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)


class Base(DeclarativeBase):
    pass


def init_db():

    from app.models.company import Company
    from app.models.product import Product
    from app.models.supplier import Supplier
    from app.models.supplier_product import SupplierProduct

    from app.models.case import ProcurementCase
    from app.models.quote import Quote
    from app.models.approval import Approval
    from app.models.po import PurchaseOrder
    from app.models.delivery import Delivery
    from app.models.workflow_event import WorkflowEvent

    Base.metadata.create_all(
        bind=engine
    )