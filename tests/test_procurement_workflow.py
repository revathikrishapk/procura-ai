import unittest

from fastapi.testclient import TestClient

from app.main import app


class ProcurementWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        response = self.client.post("/demo/reset")
        self.assertEqual(response.status_code, 200, response.text)
        self.case_id = response.json()["case_id"]

    def test_valid_and_invalid_intake(self):
        valid = self.client.post(
            "/cases",
            json={
                "company_id": 1,
                "product_id": 1,
                "quantity": 5,
                "budget": 6000,
                "currency": "USD",
                "requester_name": "Casey",
                "notes": "Laptop order",
            },
        )
        self.assertEqual(valid.status_code, 201, valid.text)

        invalid = self.client.post(
            "/cases",
            json={
                "company_id": 1,
                "product_id": 1,
                "quantity": 0,
                "budget": 500,
                "currency": "USD",
                "requester_name": "Casey",
            },
        )
        self.assertIn(invalid.status_code, (400, 422), invalid.text)

    def test_internal_supplier_sourcing(self):
        source = self.client.post(f"/cases/{self.case_id}/source")
        self.assertEqual(source.status_code, 200, source.text)
        payload = source.json()
        self.assertIn("offers", payload)
        self.assertTrue(len(payload["offers"]) >= 1)

    def test_budget_and_currency_eligibility(self):
        self.client.post("/suppliers", json={"name": "Price Outlier", "contact_email": "outlier@example.com", "country": "US", "reliability_score": 0.9, "verification_score": 0.9})
        self.client.post(
            "/offers",
            json={
                "supplier_id": 2,
                "product_id": 1,
                "price": 25000,
                "currency": "USD",
                "lead_time_days": 10,
                "is_internal": True,
            },
        )
        response = self.client.post(f"/cases/{self.case_id}/evaluate")
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertTrue("selected_offer" in result or result["status"] == "no_valid_supplier")

    def test_approval_interrupt_and_po_creation(self):
        source = self.client.post(f"/cases/{self.case_id}/source")
        self.assertEqual(source.status_code, 200, source.text)

        evaluate = self.client.post(f"/cases/{self.case_id}/evaluate")
        self.assertEqual(evaluate.status_code, 200, evaluate.text)

        draft = self.client.post(f"/cases/{self.case_id}/rfq-draft")
        self.assertEqual(draft.status_code, 200, draft.text)

        approve = self.client.post(
            f"/cases/{self.case_id}/approve",
            json={"approver_name": "Marcus", "decision": "approved", "reason": "Checked by reviewer."},
        )
        self.assertEqual(approve.status_code, 200, approve.text)
        self.assertEqual(approve.json()["status"], "po_created")

        repeated = self.client.post(
            f"/cases/{self.case_id}/approve",
            json={"approver_name": "Marcus", "decision": "approved", "reason": "Repeat action."},
        )
        self.assertEqual(repeated.status_code, 200, repeated.text)

        workflow = self.client.get(f"/cases/{self.case_id}/workflow")
        self.assertEqual(workflow.status_code, 200, workflow.text)
        self.assertIn("purchase_order", workflow.json())


if __name__ == "__main__":
    unittest.main()
