# Procura AI

Procura AI is a working procurement-workflow prototype. A FastAPI backend runs a
LangGraph state graph for request intake, supplier sourcing and evaluation,
quotation comparison, negotiation/RFQ drafting, human approval, purchase-order
creation, and delivery tracking. The React dashboard shows each case's current
stage, evaluated offers and evidence, unsent drafts, audit events, and approval
actions.

The graph uses shared typed state and a SQLite LangGraph checkpointer keyed by
case ID. Workflow events are also persisted in the application database. An
approval request interrupts graph execution; approving or rejecting resumes
the saved execution rather than starting a new workflow. The requester cannot
approve or reject their own request. This separation-of-duties check is a
prototype safeguard, not user authentication or authorization.

## Run locally on Windows

Start the API from the repository root:

```bat
call .venv\Scripts\activate
python -m uvicorn app.main:app --reload
```

The API initializes the SQLite schema and listens at `http://localhost:8000`.
Interactive API documentation is at `http://localhost:8000/docs`.

In another Command Prompt:

```bat
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. External supplier discovery requires
`TAVILY_API_KEY` in a repository-root `.env` file.

## Workflow

1. Intake validates the company, product, positive quantity, budget, and
   currency; incomplete or invalid requests do not proceed to sourcing.
2. Sourcing checks the company's internal supplier catalog first. If no
   matching in-budget offer exists, Tavily searches for external offers.
   Procura only creates an external offer when it extracts an explicit price
   in the requested currency. The source URL and price evidence are retained;
   it never fabricates a price.
3. Supplier evaluation scores eligible offers and records verification
   status. Quotation analysis compares offers, selects a candidate, and creates
   an approval request.
4. The negotiation agent prepares provider-labeled RFQ drafts. Drafts are
   explicitly marked **not sent**; this prototype does not contact suppliers.
5. LangGraph pauses at a human approval interrupt. A separate approver can
   approve or reject the request. Approval creates a PO record and initializes
   delivery tracking; rejection does not create a PO.
6. Update PO and delivery statuses from the dashboard/API. Marking a delivery
   complete closes its procurement case.

Each case's workflow status, checkpointed graph state, and execution-event
history can be inspected in the dashboard or at
`GET /cases/{case_id}/workflow`. Failed or empty sourcing can be retried from
the dashboard or with `POST /cases/{case_id}/source`.

## Integration boundaries

Tavily is the only live external service currently used, when configured.
The LLM gateway, email/RFQ, ERP, and logistics integrations are local demo
adapters: no supplier messages are sent, no ERP system is updated, and no
carrier is contacted. Replace these adapters in `app/services/adapters.py`
when provider credentials and APIs are available. The local persistence layer
uses SQLite; production identity/access management and deployment-grade
database, secrets, and monitoring infrastructure are not configured.

## Tests

Run the workflow integration tests with:

```bat
.venv\Scripts\python.exe -m unittest tests.test_procurement_workflow -v
```
