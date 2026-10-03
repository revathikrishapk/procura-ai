import unittest
from unittest.mock import Mock, patch

import requests
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.main import app
from app.models.approval import Approval
from app.models.case import ProcurementCase
from app.models.company import Company
from app.models.delivery import Delivery
from app.models.po import PurchaseOrder
from app.models.product import Product
from app.models.quote import Quote
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct
from app.routes import approvals, cases, delivery, po, quotes
from app.services.sourcing_agent import SourcingError, search_external_suppliers


class ProcurementWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)

        def get_test_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        for route_module in (cases, approvals, delivery, po, quotes):
            app.dependency_overrides[route_module.get_db] = get_test_db

        with self.Session() as db:
            db.add_all([
                Company(id="COMP-TEST", name="Test Company"),
                Product(
                    id="PROD-TEST",
                    company_id="COMP-TEST",
                    name="NVIDIA H100",
                    category="GPU",
                ),
                Supplier(
                    id="SUP-TEST",
                    company_id="COMP-TEST",
                    name="Internal Supplier",
                    verification_status="VERIFIED",
                ),
                SupplierProduct(
                    id="SP-TEST",
                    company_id="COMP-TEST",
                    supplier_id="SUP-TEST",
                    product_id="PROD-TEST",
                    last_price=2000000,
                    currency="INR",
                    lead_time_days=14,
                ),
            ])
            db.commit()

        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def create_case(self, product="NVIDIA H100", budget=5000000):
        return self.client.post(
            "/cases",
            json={
                "company_id": "COMP-TEST",
                "requested_by": "Requester",
                "product_name": product,
                "quantity": 2,
                "budget": budget,
            },
        )

    def test_internal_offer_requires_approval_then_generates_po_and_delivery(self):
        response = self.create_case()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "PENDING_APPROVAL")

        with self.Session() as db:
            approval = db.scalar(select(Approval))
            selected_quote = db.scalar(
                select(Quote).where(Quote.status == "SELECTED")
            )
            self.assertIsNotNone(approval)
            self.assertEqual(approval.status, "PENDING")
            self.assertEqual(selected_quote.total_price, 4000000)

        decision = self.client.patch(
            f"/approvals/{approval.id}/approve",
            json={"approved_by": "Approver"},
        )
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(decision.json()["status"], "APPROVED")

        with self.Session() as db:
            purchase_order = db.scalar(select(PurchaseOrder))
            delivery_record = db.scalar(select(Delivery))
            case_record = db.get(ProcurementCase, response.json()["id"])
            self.assertEqual(purchase_order.status, "APPROVED")
            self.assertIsNotNone(delivery_record)
            self.assertEqual(case_record.status, "PO_GENERATED")
            purchase_order_id = purchase_order.id
            delivery_id = delivery_record.id

        issued = self.client.patch(
            f"/purchase-orders/{purchase_order_id}/status?new_status=ISSUED"
        )
        self.assertEqual(issued.status_code, 200)
        transit = self.client.patch(
            f"/deliveries/{delivery_id}/status?new_status=IN_TRANSIT"
        )
        self.assertEqual(transit.status_code, 200)
        delivered = self.client.patch(
            f"/deliveries/{delivery_id}/status?new_status=DELIVERED"
        )
        self.assertEqual(delivered.status_code, 200)
        with self.Session() as db:
            self.assertEqual(
                db.get(ProcurementCase, response.json()["id"]).status,
                "CLOSED",
            )

    @patch("app.routes.cases.search_external_suppliers")
    def test_external_offer_is_provenanced_and_requires_approval(self, search):
        search.return_value = [
            {
                "supplier_name": "Web Supplier",
                "product_name": "NVIDIA H100",
                "unit_price": 2200000,
                "total_price": 4400000,
                "currency": "INR",
                "lead_time_days": 10,
                "source": "https://supplier.example/products/h100",
                "source_type": "external",
                "price_evidence": "NVIDIA H100: ₹22 lakh each",
                "extraction_method": "page",
            }
        ]

        response = self.create_case(product="NVIDIA H100 Enterprise")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "PENDING_APPROVAL")
        search.assert_called_once()

        with self.Session() as db:
            quote = db.scalar(select(Quote))
            self.assertIn("https://supplier.example/products/h100", quote.notes)
            self.assertIn("₹22 lakh each", quote.notes)
            self.assertEqual(db.scalar(select(Approval)).status, "PENDING")

    @patch("app.routes.cases.search_external_suppliers", return_value=[])
    def test_no_priced_offer_does_not_create_a_fake_quote(self, _search):
        response = self.create_case(product="Unavailable product", budget=1000)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "NO_MATCHING_OFFERS")

        with self.Session() as db:
            self.assertIsNone(db.scalar(select(Quote)))
            self.assertIsNone(db.scalar(select(Approval)))

    @patch(
        "app.routes.cases.search_external_suppliers",
        side_effect=SourcingError("Tavily unavailable"),
    )
    def test_external_sourcing_failure_is_saved_and_retryable(self, _search):
        response = self.create_case(product="Uncatalogued product")
        self.assertEqual(response.status_code, 502)
        with self.Session() as db:
            failed_case = db.scalar(select(ProcurementCase))
            self.assertEqual(failed_case.status, "SOURCING_FAILED")
            case_id = failed_case.id

        retry = self.client.post(f"/cases/{case_id}/source")
        self.assertEqual(retry.status_code, 502)
        self.assertIn("Tavily unavailable", retry.json()["detail"])

    def test_missing_required_budget_is_rejected_before_sourcing(self):
        response = self.client.post(
            "/cases",
            json={
                "company_id": "COMP-TEST",
                "product_name": "NVIDIA H100",
                "quantity": 2,
            },
        )
        self.assertEqual(response.status_code, 422)
        blank_product = self.client.post(
            "/cases",
            json={
                "company_id": "COMP-TEST",
                "product_name": "   ",
                "quantity": 2,
                "budget": 1000,
            },
        )
        self.assertEqual(blank_product.status_code, 422)

    def test_rejecting_approval_does_not_create_purchase_order(self):
        response = self.create_case()
        with self.Session() as db:
            approval = db.scalar(select(Approval))

        decision = self.client.patch(
            f"/approvals/{approval.id}/reject",
            json={"approved_by": "Approver", "comments": "Over budget"},
        )
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(decision.json()["status"], "REJECTED")

        with self.Session() as db:
            self.assertIsNone(db.scalar(select(PurchaseOrder)))
            self.assertEqual(
                db.get(ProcurementCase, response.json()["id"]).status,
                "REJECTED",
            )


if __name__ == "__main__":
    unittest.main()


class LiveSourcingTests(unittest.TestCase):
    @patch("app.services.sourcing_agent.os.getenv", return_value="test-key")
    @patch("app.services.sourcing_agent.requests.post")
    def test_tavily_search_extracts_price_evidence_from_supplier_page(
        self,
        post,
        _getenv,
    ):
        search_response = Mock()
        search_response.json.return_value = {
            "results": [{
                "title": "NVIDIA H100 accelerator",
                "url": "https://supplier.example/nvidia-h100",
                "content": "NVIDIA H100 accelerator product listing",
                "score": 0.9,
            }, {
                "title": "NVIDIA H100 hourly rental",
                "url": "https://other.example/h100",
                "content": "NVIDIA H100 available for ₹30 per hour",
                "score": 0.8,
            }]
        }
        extract_response = Mock()
        extract_response.json.return_value = {
            "results": [{
                "url": "https://supplier.example/nvidia-h100",
                "raw_content": "NVIDIA H100 accelerator: ₹22 lakh per unit.",
            }, {
                "url": "https://other.example/h100",
                "raw_content": "NVIDIA H100 available for ₹30 per hour.",
            }]
        }
        post.side_effect = [search_response, extract_response]

        offers = search_external_suppliers(
            "NVIDIA H100",
            budget=5_000_000,
            quantity=2,
        )

        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0]["unit_price"], 2_200_000)
        self.assertEqual(offers[0]["total_price"], 4_400_000)
        self.assertEqual(offers[0]["extraction_method"], "page")
        self.assertIn("NVIDIA H100", offers[0]["price_evidence"])
        self.assertIn("₹22 lakh", offers[0]["price_evidence"])
        self.assertEqual(post.call_count, 2)

    @patch("app.services.sourcing_agent.os.getenv", return_value="test-key")
    @patch("app.services.sourcing_agent.requests.post")
    def test_unpriced_result_is_not_invented_as_an_offer(self, post, _getenv):
        search_response = Mock()
        search_response.json.return_value = {
            "results": [{
                "title": "NVIDIA H100 accelerator",
                "url": "https://supplier.example/nvidia-h100",
                "content": "Contact us for current availability.",
            }]
        }
        extract_response = Mock()
        extract_response.json.return_value = {
            "results": [{
                "url": "https://supplier.example/nvidia-h100",
                "raw_content": "NVIDIA H100 accelerator is available. Contact us for a quote.",
            }]
        }
        post.side_effect = [search_response, extract_response]

        offers = search_external_suppliers(
            "NVIDIA H100",
            budget=5_000_000,
            quantity=1,
        )

        self.assertEqual(offers, [])

    @patch("app.services.sourcing_agent.os.getenv", return_value="test-key")
    @patch("app.services.sourcing_agent.requests.post")
    def test_tavily_errors_are_reported_not_replaced_with_mock_prices(
        self,
        post,
        _getenv,
    ):
        post.side_effect = requests.ConnectionError("Tavily unavailable")

        with self.assertRaisesRegex(SourcingError, "Web search failed"):
            search_external_suppliers(
                "NVIDIA H100",
                budget=5_000_000,
                quantity=1,
            )
