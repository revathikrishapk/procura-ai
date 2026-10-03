# Procura AI

Procura AI is an early procurement workflow MVP built with FastAPI, SQLAlchemy, SQLite, and React.

## Run locally on Windows

Start the API from the repository root:

```bat
call .venv\Scripts\activate
python -m uvicorn app.main:app --reload
```

The API initializes the SQLite schema at startup and listens at `http://localhost:8000`. Interactive API docs are at `http://localhost:8000/docs`.

In another Command Prompt:

```bat
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. External supplier sourcing requires `TAVILY_API_KEY` in the repository-root `.env` file.

## Procurement flow

1. Submit a case with a company, product, positive quantity, positive budget, and currency.
2. Procura checks the company catalog and filters internal supplier offers by currency and total budget.
3. If no internal offer fits, Tavily searches the web and extracts the result pages. Procura only creates quotes when it finds an explicit price in the requested currency, with price evidence and the source URL recorded in the quote notes. It does not fabricate a price when pages contain no usable price.
4. The lowest-priced eligible offer is selected and an approval is created. Other eligible offers are retained as alternatives.
5. An authorized human approves or rejects the offer in the dashboard or API. Approval automatically creates an approved purchase-order record and a delivery-tracking record; rejection does not create a purchase order.
6. After the buyer sends the PO to the supplier outside Procura, mark it issued. Update delivery as it moves in transit and mark it delivered to close the case.

If external sourcing fails or returns no priced offers, the case records `SOURCING_FAILED` or `NO_MATCHING_OFFERS`. Retry sourcing from the dashboard after the issue is resolved.

Web-extracted pricing is a lead for human review, not a binding supplier quote. Procura does not email suppliers or transmit orders to vendor systems; the purchase-order record is generated only after explicit human approval.

## Tests

Run the workflow integration tests with:

```bat
.venv\Scripts\python.exe -m unittest tests.test_procurement_workflow -v
```
