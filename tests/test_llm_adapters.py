import os
import unittest
from unittest.mock import Mock, patch

from app.services.adapters import (
    DemoLLMGateway,
    OpenRouterLLMGateway,
    create_llm_gateway,
)


class OpenRouterGatewayTests(unittest.TestCase):
    def setUp(self):
        self.gateway = OpenRouterLLMGateway("test-key", "test/model")

    @patch("app.services.adapters.requests.post")
    def test_request_analysis_uses_configured_openrouter_model(self, post):
        response = Mock()
        response.json.return_value = {
            "choices": [{
                "message": {
                    "content": (
                        '{"product_summary":"Laptop",'
                        '"requirements_summary":"16 GB RAM"}'
                    )
                }
            }]
        }
        post.return_value = response

        result = self.gateway.analyze_request({
            "product_name": "Laptop",
            "description": "16 GB RAM",
            "quantity": 2,
            "budget": 2500,
            "currency": "USD",
        })

        self.assertEqual(result["model_provider"], "openrouter")
        self.assertEqual(result["model"], "test/model")
        self.assertEqual(result["requirements_summary"], "16 GB RAM")
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer test-key",
        )
        self.assertEqual(post.call_args.kwargs["json"]["model"], "test/model")

    @patch("app.services.adapters.requests.post")
    def test_negotiation_output_remains_an_unsent_draft(self, post):
        response = Mock()
        response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"subject":"RFQ","body":"Please confirm availability."}'
                }
            }]
        }
        post.return_value = response

        draft = self.gateway.draft_negotiation(
            {
                "supplier_name": "Supplier",
                "unit_price": 100,
                "currency": "USD",
            },
            {"product_name": "Part", "quantity": 2},
        )

        self.assertEqual(draft["status"], "DRAFT_NOT_SENT")
        self.assertEqual(draft["provider"], "openrouter")
        self.assertEqual(draft["suggested_target_unit_price"], 95)

    @patch("app.services.adapters.requests.post")
    def test_invalid_model_response_fails_explicitly(self, post):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": "not json"}}]
        }
        post.return_value = response

        with self.assertRaisesRegex(RuntimeError, "not valid JSON"):
            self.gateway.analyze_request({
                "product_name": "Laptop",
                "quantity": 1,
                "budget": 100,
            })

    @patch("app.services.adapters.load_dotenv")
    @patch.dict(os.environ, {}, clear=True)
    def test_gateway_factory_uses_demo_without_api_key(self, _load_dotenv):
        self.assertIsInstance(create_llm_gateway(), DemoLLMGateway)

    @patch("app.services.adapters.load_dotenv")
    @patch.dict(
        os.environ,
        {"OPENROUTER_API_KEY": "test-key"},
        clear=True,
    )
    def test_gateway_requires_model_when_openrouter_is_configured(
        self,
        _load_dotenv,
    ):
        with self.assertRaisesRegex(RuntimeError, "OPENROUTER_MODEL"):
            create_llm_gateway()

    @patch("app.services.adapters.load_dotenv")
    @patch.dict(
        os.environ,
        {
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_MODEL": "test/model",
        },
        clear=True,
    )
    def test_gateway_factory_selects_openrouter_when_configured(
        self,
        _load_dotenv,
    ):
        gateway = create_llm_gateway()
        self.assertIsInstance(gateway, OpenRouterLLMGateway)
        self.assertEqual(gateway.model, "test/model")


if __name__ == "__main__":
    unittest.main()
