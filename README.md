# WorkPilot — Autonomous AI Task Worker

WorkPilot is a small agentic-system prototype for the CentrAlign AI engineering internship problem statement. A user describes an invoice task in natural language; Gemini selects tools, the Python application executes those tools against a simulated invoice inbox and finance system, and the agent verifies writes before reporting the result.

## MVP capabilities

- Natural-language task input in a small FastAPI web UI.
- Gemini function/tool calling with a bounded set of Python tools.
- Search simulated invoices by company and status.
- Create finance records in SQLite.
- Idempotent record creation (a repeated tool call will not duplicate a record).
- Verify invoice ID, company, amount, and due date against the source.
- Visible execution trace with tool calls, observations, action results, and verification.
- Sample data and deterministic database tests.

## Architecture

`User task -> FastAPI UI -> Gemini planner/tool selection -> Python tool -> SQLite simulated company app -> observation -> verification -> summary`

The LLM chooses from a limited toolset. The Python functions, not the model, perform database reads and writes. The database enforces a unique invoice ID on finance records, and verification independently compares persisted values with the source invoice.

## Setup (Ubuntu/Linux)

Python 3.10+ recommended.

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
mkdir -p ~/projects
cd ~/projects
# Extract the downloaded workpilot.zip here, then:
cd workpilot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
nano .env
```

Put your Gemini API key in `.env`:

```dotenv
GEMINI_API_KEY=your_real_key_here
GEMINI_MODEL=gemini-2.5-flash
DATABASE_PATH=workpilot.db
```

Do not commit `.env` or share your API key. The `.gitignore` excludes both `.env` and local databases.

## Run

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. API docs are at http://127.0.0.1:8000/docs. Other useful pages: `/invoices`, `/records`, and `/health`.

Try this task:

> Find the latest unpaid invoice from ABC Supplies, record it in the finance system, and verify the saved record.

Expected result with the seeded data: `INV-1042`, amount `24500.00`, due date `2026-10-20`. The app should show a tool trace and the finance record should appear at `/records`.

## Test the database/reliability layer

```bash
pytest -q
```

Tests cover newest-first invoice selection, record verification, idempotent duplicate prevention, and rejection of unknown invoice IDs. These tests do not require a Gemini API key.

## Demo script (60–90 seconds)

1. Open the invoice inbox and show the seeded records.
2. Run the task above from the home page.
3. Walk through the tool-call and verification trace.
4. Open Finance records and show the persisted record.
5. Run the same task again and show that no duplicate record is created.
6. Try the no-match example and explain that the agent should report no invoice rather than inventing one.

## Design decisions

- **Narrow scope:** one business workflow, implemented end-to-end instead of many simulated integrations.
- **Tool boundary:** Gemini chooses tools, while typed Python functions perform the actual work.
- **Verification:** a successful tool response is not treated as proof; the persisted record is read back and compared with source data.
- **Idempotency:** `invoice_id` is unique in the finance table, and repeated writes return the existing record.
- **Safety:** only seeded demo data is used. There is no real payment, external email, or third-party account access.

## Limitations and next steps

- The first version uses a simulated SQLite company application rather than browser automation or real enterprise integrations.
- The LLM can make incorrect tool-selection decisions; the trace and verification make outcomes inspectable but do not eliminate model errors.
- Add structured task states, bounded retries with injected transient failures, explicit approval pauses for consequential actions, and an automated evaluation set.
- Add Playwright against the local simulated web app after the API/tool workflow is stable.
- Add task-level persistence and authentication before any multi-user deployment.

## Assumptions

- Invoice data is preloaded and considered the source of truth.
- “Latest” means the highest invoice date among matching invoices.
- Only unpaid invoices are selected unless the user specifies otherwise.
- Recording means creating a finance record; it does not mean approving or paying an invoice.
