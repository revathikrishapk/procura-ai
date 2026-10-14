import asyncio
import unittest

from app.agents.nodes import analyze_quotations_node, evaluate_suppliers_node, parse_request_node, source_suppliers_node


class LLMAdapterTests(unittest.TestCase):
    def test_parse_request_node_uses_demo_fallback(self):
        result = asyncio.run(parse_request_node({"raw_request": "Need 4 laptops under $8000"}))
        self.assertEqual(result["quantity"], 4)
        self.assertEqual(result["max_budget"], 8000.0)
        self.assertIn("laptop", result["item_name"].lower())

    def test_supplier_ranking_and_quote_selection(self):
        source = asyncio.run(source_suppliers_node({}))
        ranked = asyncio.run(evaluate_suppliers_node({"suppliers": source["suppliers"]}))
        self.assertGreater(len(ranked["suppliers"]), 0)

        quotes = asyncio.run(analyze_quotations_node({"quantity": 3, "max_budget": 500, "suppliers": source["suppliers"]}))
        self.assertIn("selected_supplier", quotes)
        self.assertIn("quotations", quotes)


if __name__ == "__main__":
    unittest.main()
