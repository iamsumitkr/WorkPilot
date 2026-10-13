import json
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from app import database

load_dotenv()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
SYSTEM_INSTRUCTION = """You are WorkPilot, a cautious enterprise task worker. You must use tools to inspect data and perform requested work; never claim an action happened unless a tool confirms it. For invoice-processing tasks: search invoices first, select the newest matching unpaid invoice unless the user specifies another, create a finance record only when requested, and verify it after creation. If no invoice matches, say so. Never invent invoice details. Use only the available tools. Keep the final report concise and distinguish completed work from failures."""

def run_task(task: str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "replace_with_your_gemini_api_key":
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file.")
    trace = []
    client = genai.Client(api_key=api_key)

    def log(event, detail, status="info"):
        trace.append({"event": event, "detail": detail, "status": status})

    def search_invoices(company: str, status: str = "unpaid") -> dict:
        """Search the simulated invoice inbox by company name and status. Use status 'unpaid' by default. Returns matching invoice records newest first."""
        log("TOOL CALL", f"search_invoices(company={company!r}, status={status!r})")
        results = database.find_invoices(company, status)
        log("OBSERVATION", f"Found {len(results)} matching invoice(s).", "success" if results else "warning")
        return {"count": len(results), "invoices": results}

    def create_finance_record(invoice_id: str) -> dict:
        """Create a finance system record from an existing invoice. Safe to call again: it will not create duplicate records. Do this only when the user asks to record or enter the invoice."""
        log("TOOL CALL", f"create_finance_record(invoice_id={invoice_id!r})")
        result = database.create_record(invoice_id)
        log("ACTION RESULT", json.dumps(result, default=str), "success" if result.get("ok") else "error")
        return result

    def verify_finance_record(invoice_id: str) -> dict:
        """Verify a finance record exists and its invoice ID, company, amount, and due date match the source invoice."""
        log("TOOL CALL", f"verify_finance_record(invoice_id={invoice_id!r})")
        result = database.verify_record(invoice_id)
        log("VERIFICATION", json.dumps(result, default=str), "success" if result.get("verified") else "error")
        return result

    chat = client.chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[search_invoices, create_finance_record, verify_finance_record],
            temperature=0.1,
        ),
    )
    log("TASK RECEIVED", task)
    try:
        response = chat.send_message(task)
        final_text = response.text or "The agent finished without returning a text summary. Check the execution trace."
        log("FINAL REPORT", final_text, "success")
        return {"task": task, "status": "completed" if any(x["event"] == "VERIFICATION" and x["status"] == "success" for x in trace) or "report only" in task.lower() else "finished", "summary": final_text, "trace": trace, "model": MODEL}
    except Exception as exc:
        log("AGENT ERROR", f"{type(exc).__name__}: {exc}", "error")
        return {"task": task, "status": "failed", "summary": "The task could not be completed. Review the error in the trace.", "trace": trace, "error": str(exc), "model": MODEL}
