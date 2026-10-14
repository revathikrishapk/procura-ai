# Procura AI

A lightweight local procurement demo API with deterministic fallback behavior for college demos. The application runs locally with SQLite, FastAPI, and LangGraph, and it does not require an external API key to exercise the main workflow.

## Local setup

1. Create and activate a virtual environment.
2. Install dependencies:
   `python -m pip install -r requirements.txt`
3. Copy `.env.example` to `.env`.
4. Start the API:
   `uvicorn app.main:app --reload`
5. Open http://127.0.0.1:8000/

## Demo flow

1. Reset demo data with `POST /demo/reset`.
2. Create a company, product, supplier, and internal supplier offer.
3. Create a procurement case with a product, quantity, budget, and requester.
4. Call `POST /cases/{id}/source` to source internal offers.
5. Run `POST /cases/{id}/evaluate` to rank the offers.
6. Generate a draft with `POST /cases/{id}/rfq-draft`.
7. Approve or reject the request using `POST /cases/{id}/approve` or `POST /cases/{id}/reject`.
8. Check the workflow summary at `GET /cases/{id}/workflow`.
9. Update delivery status with `POST /purchase-orders/{po_id}/delivery`.

## Deterministic local mode

The fallback parser in `app/agents/nodes.py` does not require an external OpenRouter credential. It will extract item names, quantity, and budget from the request text, and the demo UI continues to work without remote LLM calls.

## Environment variables

- `OPENROUTER_API_KEY`: optional for the local demo; set a real value for LLM-backed parsing.
- `OPENROUTER_MODEL`: optional override for the model name.
- `DATABASE_URL`: optional; defaults to a local SQLite file.
- `APP_ENV`: optional; defaults to `development`.

## How to reset the demo safely

Use the built-in route `POST /demo/reset` to clear the demo data in the local SQLite database and recreate a known-good company, product, supplier, and offer. This is safe for the local demo database and does not delete unrelated data in a production environment.

## Troubleshooting

- If a route returns a validation error, confirm the request body includes the required fields and positive values.
- If the page looks blank, confirm the backend is running with `uvicorn app.main:app --reload`.
- If you have a real OpenRouter key, set it in `.env` to replace the demo fallback parser with model-based extraction.
