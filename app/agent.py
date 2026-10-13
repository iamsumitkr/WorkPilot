import json
import os
import re
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app import database

load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

SYSTEM_INSTRUCTION = """You are WorkPilot, a cautious enterprise task worker.
You must use tools to inspect data and perform requested work; never claim an
action happened unless a tool confirms it. For invoice-processing tasks: search
invoices first, select the newest matching unpaid invoice unless the user
specifies another, create a finance record only when requested, and verify it
after creation. If no invoice matches, say so. Never invent invoice details.
Use only the available tools. Keep the final report concise and distinguish
completed work from failures."""


def run_task(task: str) -> dict:
    """Run a user task with Gemini tool calling and a bounded retry policy."""

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "replace_with_your_gemini_api_key":
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file.")

    trace = []
    client = genai.Client(api_key=api_key)

    def log(event: str, detail: str, status: str = "info") -> None:
        trace.append({"event": event, "detail": detail, "status": status})

    def search_invoices(company: str, status: str = "unpaid") -> dict:
        """Search invoices by company and status; newest matches are returned first."""
        log("TOOL CALL", f"search_invoices(company={company!r}, status={status!r})")
        results = database.find_invoices(company, status)
        log(
            "OBSERVATION",
            f"Found {len(results)} matching invoice(s).",
            "success" if results else "warning",
        )
        return {"count": len(results), "invoices": results}

    def create_finance_record(invoice_id: str) -> dict:
        """Create a finance record from an existing invoice; duplicate-safe."""
        log("TOOL CALL", f"create_finance_record(invoice_id={invoice_id!r})")
        result = database.create_record(invoice_id)
        log(
            "ACTION RESULT",
            json.dumps(result, default=str),
            "success" if result.get("ok") else "error",
        )

        # Verify immediately after a successful/idempotent write. This local
        # database check does not need another Gemini request.
        if result.get("ok"):
            verification = database.verify_record(invoice_id)
            log(
                "VERIFICATION",
                json.dumps(verification, default=str),
                "success" if verification.get("verified") else "error",
            )
            result["verification"] = verification

        return result

    def verify_finance_record(invoice_id: str) -> dict:
        """Verify that a finance record matches its source invoice."""
        log("TOOL CALL", f"verify_finance_record(invoice_id={invoice_id!r})")
        result = database.verify_record(invoice_id)
        log(
            "VERIFICATION",
            json.dumps(result, default=str),
            "success" if result.get("verified") else "error",
        )
        return result

    chat = client.chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[
                search_invoices,
                create_finance_record,
                verify_finance_record,
            ],
            temperature=0.1,
        ),
    )

    def send_with_retry(message: str, max_attempts: int = 3):
        """Retry temporary Gemini errors without retrying permanent failures."""
        for attempt in range(max_attempts):
            try:
                return chat.send_message(message)
            except Exception as exc:
                error_text = str(exc).lower()
                retryable = any(
                    marker in error_text
                    for marker in (
                        "503",
                        "unavailable",
                        "429",
                        "resource_exhausted",
                        "500",
                        "502",
                        "504",
                        "internal server error",
                        "temporarily unavailable",
                    )
                )

                if not retryable or attempt == max_attempts - 1:
                    raise

                match = re.search(
                    r"retry in ([0-9.]+)s",
                    str(exc),
                    re.IGNORECASE,
                )
                if match:
                    delay = min(float(match.group(1)) + 1.0, 30.0)
                else:
                    delay = min(2 ** (attempt + 1), 8)

                log(
                    "RETRY",
                    (
                        f"Gemini temporarily unavailable; retrying in "
                        f"{delay:.1f}s (attempt {attempt + 1}/{max_attempts})."
                    ),
                    "warning",
                )
                time.sleep(delay)

        # Defensive fallback; the loop normally returns or raises.
        raise RuntimeError("Gemini request failed after retry attempts.")

    log("TASK RECEIVED", task)

    try:
        response = send_with_retry(task)
        final_text = (
            getattr(response, "text", None)
            or "The agent returned no text summary. Check the execution trace."
        )
        log("FINAL REPORT", final_text, "success")

        verified = any(
            item["event"] == "VERIFICATION" and item["status"] == "success"
            for item in trace
        )

        return {
            "task": task,
            "status": "completed" if verified else "finished",
            "summary": final_text,
            "trace": trace,
            "model": MODEL,
        }

    except Exception as exc:
        log("AGENT ERROR", f"{type(exc).__name__}: {exc}", "error")

        # If a write was already verified, a later LLM outage must not turn
        # the successful business operation into a failed task.
        verified = any(
            item["event"] == "VERIFICATION" and item["status"] == "success"
            for item in trace
        )
        if verified:
            return {
                "task": task,
                "status": "completed",
                "summary": (
                    "The finance record was saved and verified successfully. "
                    "Gemini failed while finishing its response; see the trace."
                ),
                "trace": trace,
                "model": MODEL,
            }

        return {
            "task": task,
            "status": "failed",
            "summary": (
                "The task could not be fully verified. Review the execution trace."
            ),
            "trace": trace,
            "error": str(exc),
            "model": MODEL,
        }
