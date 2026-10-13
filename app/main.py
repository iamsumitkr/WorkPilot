from contextlib import asynccontextmanager
from html import escape
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse
from app import database
from app.agent import run_task

@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield

app = FastAPI(title="WorkPilot — Autonomous AI Task Worker", version="0.1.0", lifespan=lifespan)

STYLE = """
<style>
:root{font-family:Inter,system-ui,-apple-system,sans-serif;color:#172033;background:#f5f7fb}*{box-sizing:border-box}body{margin:0}.wrap{max-width:1050px;margin:36px auto;padding:0 18px}.hero{background:#101828;color:white;padding:28px;border-radius:18px}.eyebrow{color:#a8c7fa;text-transform:uppercase;letter-spacing:.12em;font-size:12px;font-weight:700}.hero h1{margin:8px 0;font-size:32px}.hero p{color:#d0d5dd;max-width:720px}.panel{background:white;border:1px solid #e5e9f0;border-radius:16px;padding:22px;margin-top:18px;box-shadow:0 4px 18px #10182808}textarea{width:100%;min-height:100px;padding:14px;border:1px solid #cfd6e4;border-radius:10px;font:inherit}button{background:#175cd3;color:white;border:0;border-radius:9px;padding:12px 18px;font-weight:700;cursor:pointer;margin-top:12px}button:hover{background:#1849a9}.examples{display:flex;gap:8px;flex-wrap:wrap}.examples button{background:#eff4ff;color:#1849a9;border:1px solid #d1e0ff;margin:0}.muted{color:#667085}.row{display:flex;justify-content:space-between;gap:14px;align-items:center}.pill{padding:5px 9px;border-radius:99px;background:#ecfdf3;color:#027a48;font-size:12px;font-weight:700}.pill.warning{background:#fffaeb;color:#b54708}.trace{border-left:3px solid #d0d5dd;padding:2px 0 2px 14px;margin:14px 0}.trace strong{display:block}.trace small{color:#667085}.error{color:#b42318}.records{width:100%;border-collapse:collapse}.records th,.records td{text-align:left;padding:10px;border-bottom:1px solid #eaecf0;font-size:14px}.links a{color:#175cd3;margin-right:14px;text-decoration:none}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:700px){.grid{grid-template-columns:1fr}.hero h1{font-size:25px}}
</style>"""

def page(body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>WorkPilot</title>{STYLE}</head><body><main class='wrap'>{body}</main></body></html>"

def shell(content: str) -> str:
    return "<section class='hero'><div class='eyebrow'>CentrAlign AI · Engineering prototype</div><h1>WorkPilot</h1><p>An autonomous task worker that plans with an LLM, uses tools to perform work, and verifies the outcome before reporting completion.</p><div class='links'><a href='/'>Run a task</a><a href='/invoices'>Invoice inbox</a><a href='/records'>Finance records</a><a href='/docs'>API docs</a></div></section>" + content

@app.get("/", response_class=HTMLResponse)
def home():
    body = """
    <section class='panel'><h2>Give WorkPilot a task</h2><p class='muted'>Try a natural-language task. The agent will decide which tools to call and show an execution trace.</p>
    <form action='/run' method='post'><textarea name='task' id='task' required>Find the latest unpaid invoice from ABC Supplies, record it in the finance system, and verify the saved record.</textarea><button type='submit'>Run autonomous task →</button></form>
    <h3>Try another task</h3><div class='examples'><button onclick="document.getElementById('task').value='Find the latest unpaid invoice from Northwind Components and record it in the finance system.'">Northwind invoice</button><button onclick="document.getElementById('task').value='Find the latest unpaid invoice from a company called Not A Real Company and report what you find.'">No-match scenario</button><button onclick="document.getElementById('task').value='Find the latest unpaid invoice from ABC Supplies and report the amount and due date without creating a finance record.'">Read-only report</button></div>
    </section><section class='panel grid'><div><h3>Agent loop</h3><p class='muted'>Task → Gemini tool selection → tool execution → observation → verification → report.</p></div><div><h3>Safety by design</h3><p class='muted'>Seeded demo data, bounded tool set, duplicate prevention, and database-backed verification. No real payments or company systems.</p></div></section>
    """
    return page(shell(body))

@app.post("/run", response_class=HTMLResponse)
def run(task: str = Form(...)):
    try:
        result = run_task(task.strip())
    except Exception as exc:
        result = {"task": task, "status": "failed", "summary": str(exc), "trace": [{"event": "SETUP ERROR", "detail": str(exc), "status": "error"}]}
    status_class = "" if result.get("status") == "completed" else "warning"
    trace_html = "".join(
        f"<div class='trace'><strong>{escape(item.get('event','Event'))} <span class='muted'>· {escape(item.get('status','info'))}</span></strong><div>{escape(str(item.get('detail','')))}</div></div>"
        for item in result.get("trace", [])
    )
    body = f"<section class='panel'><div class='row'><h2>Task result</h2><span class='pill {status_class}'>{escape(result.get('status','unknown').upper())}</span></div><p><b>Task:</b> {escape(task)}</p><h3>Agent summary</h3><p>{escape(result.get('summary',''))}</p><h3>Execution trace</h3>{trace_html}<p><a href='/'>← Run another task</a> · <a href='/records'>View finance records</a></p></section>"
    return page(shell(body))

@app.get("/invoices", response_class=HTMLResponse)
def invoices():
    rows = database.list_invoices()
    table = "<table class='records'><thead><tr><th>Invoice</th><th>Company</th><th>Amount</th><th>Due date</th><th>Status</th><th>Invoice date</th></tr></thead><tbody>"
    table += "".join(f"<tr><td>{escape(r['invoice_id'])}</td><td>{escape(r['company'])}</td><td>₹{r['amount']:,.2f}</td><td>{escape(r['due_date'])}</td><td>{escape(r['status'])}</td><td>{escape(r['invoice_date'])}</td></tr>" for r in rows)
    table += "</tbody></table>"
    return page(shell(f"<section class='panel'><h2>Simulated invoice inbox</h2><p class='muted'>Sample data for the demo; dates are fixed for repeatable testing.</p>{table}</section>"))

@app.get("/records", response_class=HTMLResponse)
def records():
    rows = database.list_records()
    table = "<table class='records'><thead><tr><th>Record ID</th><th>Invoice</th><th>Company</th><th>Amount</th><th>Due date</th><th>Created</th></tr></thead><tbody>"
    table += "".join(f"<tr><td>{r['record_id']}</td><td>{escape(r['invoice_id'])}</td><td>{escape(r['company'])}</td><td>₹{r['amount']:,.2f}</td><td>{escape(r['due_date'])}</td><td>{escape(r['created_at'])}</td></tr>" for r in rows)
    table += "</tbody></table>" if rows else "<p class='muted'>No finance records yet. Run a task to create one.</p>"
    return page(shell(f"<section class='panel'><h2>Finance records</h2>{table}</section>"))

@app.get("/health")
def health():
    return {"status": "ok", "service": "workpilot"}

@app.get("/api/invoices")
def api_invoices():
    return JSONResponse(database.list_invoices())
