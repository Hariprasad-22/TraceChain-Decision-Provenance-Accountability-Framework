"""
server.py
---------
TraceChain Loan Assistant — backend for the chat dashboard.

Lives in `Frontend/` and imports the real pipeline from the sibling
`orchestrator/` package (same `run_pipeline` used by `run_pipeline.py`).
Env vars (DB, Gemini) are loaded from `orchestrator/.env`.

Run:
    pip install -r requirements.txt
    cd Frontend
    uvicorn server:app --reload --port 8000

Uploads are stored under ``orchestrator/chat_uploads/`` (outside the
Frontend watch folder) so file uploads do not restart the server.

Conversation design
--------------------
1. Welcome — greets the user, offers to (a) start a loan application or
   (b) answer a general loan/credit/EMI question.
2. Apply flow — a short, focused sequence collects only what
   `orchestrator.validate_state()` actually requires plus CIBIL score:
   name -> CIBIL score -> Aadhaar upload -> payslip upload -> loan amount.
   Everything else (DOB, declared income, utilization, DPD history) is
   optional in the orchestrator, so it's defaulted rather than asked, to
   keep the interface small as requested.
3. Verification — once the amount is given, the UI shows "sent for
   verification" and an animated per-agent progress sequence while the
   backend actually calls `run_pipeline(state)` in the background.
4. Decision — the result (Approved / Rejected / Manual Review) is shown
   with the overall risk score, hash-chain verification, and per-agent
   breakdown. If the decision isn't a clean approval, a "Why this
   decision?" action is offered.
5. Reasoning — pulls the stored reasoning for that orchestration straight
   from the `final_decisions` table (falls back to the in-memory pipeline
   result if the DB read isn't available), and displays it.
6. After that, the assistant returns to general mode: loan/credit
   questions not tied to a specific application are answered via the
   Gemini API (using GEMINI_API_KEY from your .env); anything unrelated
   to loans/credit/banking is politely declined as out of scope.

None of this modifies orchestrator.py, the agents, or the DB layer. If the
DB / imp_docs agent modules aren't wired up yet, the chat still runs and
collects a full application — it just shows a clear in-chat error at the
verification step instead of crashing.
"""

from __future__ import annotations

import os
import re
import sys
import json
import uuid
import shutil
import hashlib
import logging
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

logger = logging.getLogger("chat_ui")
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
# Repo layout: Deloitte-capstone/{Frontend, orchestrator}/
ORCH_DIR = BASE_DIR.parent / "orchestrator"


def _prepare_orchestrator_import() -> None:
    """
    Put orchestrator first on sys.path and drop any cached impostor modules.

    Aadhaar's tree ships a top-level ``chain.py`` that shadows the
    orchestrator's ``chain/`` package if that agent dir is ahead on
    ``sys.path`` (common after agent imports or a uvicorn --reload).
    """
    orch = str(ORCH_DIR.resolve())
    while orch in sys.path:
        sys.path.remove(orch)
    sys.path.insert(0, orch)

    for key in list(sys.modules):
        if key == "chain" or key.startswith("chain."):
            mod = sys.modules[key]
            origin = getattr(mod, "__file__", None) or ""
            try:
                under_orch = Path(origin).resolve().is_relative_to(ORCH_DIR.resolve())
            except (OSError, ValueError):
                under_orch = False
            paths = getattr(mod, "__path__", None)
            if under_orch:
                continue
            if paths and any(
                str(Path(p).resolve()).startswith(str(ORCH_DIR.resolve())) for p in paths
            ):
                continue
            del sys.modules[key]


# Prefer orchestrator/.env (DB + Gemini); fall back to Frontend/.env if present.
load_dotenv(ORCH_DIR / ".env")
load_dotenv(BASE_DIR / ".env")

# ─── try to import the real orchestrator ──────────────────────────────────────
# ─── try to import the real orchestrator ──────────────────────────────────────
_prepare_orchestrator_import()
try:
    # orchestrator/__init__.py re-exports run_pipeline from orchestrator.py
    from orchestrator import run_pipeline
    ORCHESTRATOR_AVAILABLE = True
    ORCHESTRATOR_IMPORT_ERROR = None
    logger.info("Orchestrator imported successfully from %s", ORCH_DIR)
except ImportError:
    # Fallback: import directly from orchestrator.py module
    try:
        import importlib.util, sys as _sys
        _spec = importlib.util.spec_from_file_location(
            "orchestrator_module",
            ORCH_DIR / "orchestrator.py",
        )
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        run_pipeline = _mod.run_pipeline
        ORCHESTRATOR_AVAILABLE = True
        ORCHESTRATOR_IMPORT_ERROR = None
        logger.info("Orchestrator loaded via direct file import fallback.")
    except Exception as exc2:  # noqa: BLE001
        run_pipeline = None
        ORCHESTRATOR_AVAILABLE = False
        ORCHESTRATOR_IMPORT_ERROR = str(exc2)
        logger.warning("Could not import orchestrator.run_pipeline: %s", exc2)
except Exception as exc:  # noqa: BLE001
    run_pipeline = None
    ORCHESTRATOR_AVAILABLE = False
    ORCHESTRATOR_IMPORT_ERROR = str(exc)
    logger.warning("Could not import orchestrator.run_pipeline: %s", exc)

WEB_DIR = BASE_DIR / "web"
# Keep uploads outside Frontend/ so uvicorn --reload is not tripped by every upload
# (a reload with a polluted sys.path used to break the orchestrator import).
UPLOAD_DIR = ORCH_DIR / "chat_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="TraceChain Loan Assistant")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# ─── Gemini (general loan/credit Q&A, out of the orchestrator's scope) ────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

LOAN_SYSTEM_PROMPT = (
    "You are the general-knowledge assistant embedded inside TraceChain, a bank "
    "loan platform. Answer ONLY questions about loans, credit, EMIs, interest "
    "rates, CIBIL/credit scores, loan eligibility, documentation, and personal "
    "finance/banking in general terms. Keep answers under 100 words, factual and "
    "neutral, and never give specific individualized financial or legal advice. "
    "If the user's message is NOT about loans, credit, or banking/personal "
    "finance, reply with exactly the single token OUT_OF_SCOPE and nothing else."
)

LOAN_KEYWORDS = {
    "loan", "loans", "cibil", "credit", "emi", "interest", "bank", "aadhaar",
    "aadhar", "payslip", "income", "score", "repay", "repayment", "tenure",
    "collateral", "mortgage", "debt", "finance", "financial", "eligibility",
    "apply", "application", "approval", "approved", "rejected", "installment",
    "principal", "overdue", "dpd", "kyc", "interest rate", "borrow", "lender",
    "lending", "npa", "default", "guarantor", "co-applicant", "disbursement",
    "document", "documents", "proof", "id proof", "verification", "verify",
    "salary", "payment", "amount", "processing fee",
}


def _looks_loan_related(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in LOAN_KEYWORDS)


def validate_upload_type(field: str, original_name: str, content_type: Optional[str]) -> None:
    """Reject obviously invalid document types before they reach the pipeline."""
    name = (original_name or "").lower()
    ctype = (content_type or "").lower()

    if field == "aadhaar":
        allowed_exts = {".png", ".jpg", ".jpeg", ".webp"}
        if not (name.endswith(tuple(allowed_exts)) or "image" in ctype):
            raise HTTPException(400, "Aadhaar must be a valid image file (.png, .jpg, .jpeg, .webp)")
        return

    if field == "payslip":
        allowed_exts = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
        if not (name.endswith(tuple(allowed_exts)) or "pdf" in ctype or "image" in ctype):
            raise HTTPException(400, "Payslip must be a PDF or image file")
        return

    if field == "bank":
        allowed_exts = {".csv", ".xls", ".xlsx"}
        if not (name.endswith(tuple(allowed_exts)) or "csv" in ctype or "excel" in ctype or "spreadsheet" in ctype):
            raise HTTPException(400, "Bank statement must be a CSV or Excel file (.csv, .xls, .xlsx)")
        return


GENERIC_FAILURE_REPLY = (
    "😕 We couldn't complete verification for this application due to a technical "
    "issue on our side -- no decision was reached. Please try again in a little "
    "while, or start a new application."
)


def friendly_error_reply(error_msg: str) -> str:
    """Return the user-facing error message for a failed verification run."""
    msg = (error_msg or "").lower()
    if "missing required field" in msg:
        if "loan_amount" in msg:
            return "⚠️ Please enter the loan amount before submitting the application for verification."
        if "applicant_name" in msg:
            return "⚠️ Please enter the applicant's full name before verifying the application."
        if "user_id" in msg or "application_id" in msg:
            return (
                "⚠️ The application identifiers are not in the required format. Use user IDs starting with "
                "100001 and application IDs starting with APP-100001."
            )
        return "⚠️ Some required application details are missing. Please complete the form and try again."
    if "missing uploaded file" in msg or "does not exist" in msg or "not a valid file" in msg:
        return (
            "📎 One or more uploaded documents could not be found on disk. Please re-upload the "
            "Aadhaar image, payslip, and bank statement CSV, then try verification again."
        )
    if "unable to process input image" in msg or "invalid_argument" in msg or "process input image" in msg:
        return (
            "🖼️ The Aadhaar image could not be processed by the verifier. Please upload a clear, valid "
            "Aadhaar image (PNG/JPG/JPEG) and try again."
        )
    if "agent a001 failed" in msg:
        if "unable to process input image" in msg or "invalid_argument" in msg:
            return (
                "🖼️ The Aadhaar image could not be processed by the verifier. Please upload a clear, valid "
                "Aadhaar image (PNG/JPG/JPEG) and try again."
            )
    if "user_id must start" in msg or "application_id must start" in msg:
        return (
            "⚠️ The application identifiers are not in the required format. Use user IDs starting with "
            "100001 and application IDs starting with APP-100001."
        )
    if "loan_amount out of range" in msg:
        return "⚠️ Please enter a valid loan amount between ₹1 and ₹50,00,000 before verifying."
    return GENERIC_FAILURE_REPLY


def ask_gemini(question: str) -> Optional[str]:
    """Call Gemini for a general loan/finance question. Returns None on any failure."""
    if not GEMINI_API_KEY:
        return None
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": LOAN_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": question}]}],
        "generationConfig": {"maxOutputTokens": 220, "temperature": 0.4},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini call failed: %s", exc)
        return None


def general_loan_answer(question: str, assume_relevant: bool = False) -> str:
    """
    assume_relevant=True is used when the question was asked *inside* the loan
    application flow (e.g. mid-upload) -- there it's safe to assume any question
    is loan/process related even if it doesn't hit a keyword (e.g. "what
    documents do I need?"), so we skip the out-of-scope refusal in that context.
    """
    reply = ask_gemini(question)
    if reply is not None:
        if reply.strip().upper().startswith("OUT_OF_SCOPE") and not assume_relevant:
            return (
                "I can only help with loan, credit, and banking-related questions here 🙂. "
                "Try asking about loan eligibility, CIBIL scores, EMIs or interest rates — "
                "or say **\"apply for a loan\"** to start an application."
            )
        if reply.strip().upper().startswith("OUT_OF_SCOPE") and assume_relevant:
            reply = None  # fall through to the generic "can't reach it" message below
        else:
            return reply
    # Gemini unavailable — degrade gracefully.
    if assume_relevant or _looks_loan_related(question):
        return (
            "I'd normally look that up for you 🔍, but the general knowledge assistant "
            "isn't reachable right now (check `GEMINI_API_KEY` in your `.env`). "
            "I can still help you **apply for a loan** and explain your decision "
            "once it's processed."
        )
    return (
        "I can only help with loan, credit, and banking-related questions here 🙂. "
        "Try asking about loan eligibility, CIBIL scores, EMIs or interest rates — "
        "or say **\"apply for a loan\"** to start an application."
    )


# ─── DB-grounded reasoning lookup ──────────────────────────────────────────────

def fetch_reasoning_from_db(orchestration_id: str) -> Optional[str]:
    """Read the stored reasoning straight from final_decisions. None if unavailable."""
    if not ORCHESTRATOR_AVAILABLE:
        return None
    try:
        from db.connection import get_conn, release_conn
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT reasoning FROM final_decisions "
                    "WHERE orchestration_id = %s ORDER BY timestamp DESC LIMIT 1",
                    (orchestration_id,),
                )
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            release_conn(conn)
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB reasoning fetch failed (falling back to in-memory result): %s", exc)
        return None


def simulate_cibil_lookup(state: dict) -> int:
    """
    Stand-in for a real credit-bureau lookup: the applicant never types a CIBIL
    score, it's "fetched" automatically during verification. Deterministic per
    applicant (same name/application -> same score) so repeated runs are stable
    for demoing, but otherwise behaves like an opaque external lookup.
    Replace this with a real CIBIL/bureau API call when one is available.
    """
    basis = f"{state.get('applicant_name', '')}|{state.get('user_id', '')}|{state.get('application_id', '')}"
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return 300 + (int(digest, 16) % 601)  # 300-900 inclusive


# ─── session model ─────────────────────────────────────────────────────────────

COLLECT_STAGES = ["name", "aadhaar_upload", "payslip_upload", "bank_upload", "loan_amount"]

STEP_LABELS = ["Welcome", "Details", "Documents", "Loan Amount", "Verifying", "Decision"]


def step_index(session: dict) -> int:
    fs = session["flow_stage"]
    if fs is None:
        return 5 if session["result"] is not None else 0
    if fs == "name":
        return 1
    if fs in ("aadhaar_upload", "payslip_upload", "bank_upload"):
        return 2
    if fs == "loan_amount":
        return 3
    if fs == "verifying":
        return 4
    return 0


PROMPTS = {
    "name": "Let's get your application started! 🚀 What's the applicant's **full name**?",
    "aadhaar_upload": "Thanks! 🪪 Please **upload the Aadhaar image** below.",
    "payslip_upload": "Got it ✅ Now let's grab the **payslip** 📄 (PDF or image).",
    "bank_upload": "Excellent ✅ Please upload the **bank statement file** (.csv, .xls, .xlsx) 🏦 for the financial review.",
    "loan_amount": "Last step! 💰 How much would you like to borrow? (up to ₹50,00,000)",
}

UPLOAD_HINTS = {
    "aadhaar_upload": {"field": "aadhaar", "label": "Aadhaar image", "accept": "image/*"},
    "payslip_upload": {"field": "payslip", "label": "Payslip (PDF)", "accept": "application/pdf,image/*"},
    "bank_upload": {"field": "bank", "label": "Bank statement (CSV / Excel)", "accept": ".csv,.xls,.xlsx,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
}

CHIPS = {
    "welcome": ["📝 Apply for a loan", "❓ What is a CIBIL score?", "📄 What documents do I need?"],
    "loan_amount": ["₹50,000", "₹1,00,000", "₹2,00,000", "₹5,00,000"],
    "post_decision_review": ["🤔 Why this decision?", "📝 New application", "💬 Ask a loan question"],
    "post_decision_approved": ["🎉 New application", "💬 Ask a loan question"],
    "post_reason": ["📝 New application", "💬 Ask a loan question"],
}

SESSIONS: dict[str, dict] = {}


def new_session() -> dict:
    # Persistent numeric user ids: maintain a small counter in Frontend/user_counter.json
    counter_file = BASE_DIR / "user_counter.json"
    try:
        if counter_file.exists():
            with counter_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                next_id = int(data.get("next", 100001))
        else:
            next_id = 100001
    except Exception:
        next_id = 100001

    # increment counter atomically-ish (best effort)
    try:
        with counter_file.open("w", encoding="utf-8") as f:
            json.dump({"next": next_id + 1}, f)
    except Exception:
        pass

    user_id = str(next_id)
    application_id = f"APP-{next_id}"

    return {
        "id": str(uuid.uuid4()),
        "flow_stage": None,  # None = idle/general mode
        "state": {
            "user_id": user_id,
            "application_id": application_id,
            "applicant_data": {},
        },
        "result": None,
        "reason_given": False,
        "retry_count": 0,
        "display_name": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def get_session(session_id: Optional[str]) -> dict:
    if session_id and session_id in SESSIONS:
        return SESSIONS[session_id]
    s = new_session()
    SESSIONS[s["id"]] = s
    return s


def session_summary(session: dict) -> dict:
    s = session["state"]
    ad = s.get("applicant_data", {})
    return {
        "name": s.get("applicant_name"),
        "cibil": s.get("cibil_score"),
        "loan_amount": s.get("loan_amount"),
        "aadhaar_uploaded": bool(ad.get("aadhar_image_path")),
        "payslip_uploaded": bool(ad.get("payslip_file_path")),
        "bank_uploaded": bool(ad.get("bank_statement_file_path")),
    }


def build_response(
    session: dict, reply: str, *, chips: Optional[list[str]] = None,
    upload: Optional[dict] = None, trigger_verify: bool = False,
    done: bool = False, result: Optional[dict] = None,
) -> dict:
    return {
        "session_id": session["id"],
        "reply": reply,
        "flow_stage": session["flow_stage"],
        "upload": upload,
        "chips": chips or [],
        "trigger_verify": trigger_verify,
        "step_index": step_index(session),
        "steps": STEP_LABELS,
        "summary": session_summary(session),
        "done": done,
        "result": result,
    }


def reset_state(session: dict) -> None:
    session["flow_stage"] = "name"
    session["result"] = None
    session["reason_given"] = False
    session["retry_count"] = 0
    session["state"] = {
        "user_id": str(100001),
        "application_id": "APP-100001",
        "applicant_data": {},
        # optional fields the orchestrator accepts but this short flow doesn't ask for
        "applicant_dob": None,
        "declared_monthly_income": None,
        "credit_utilization_pct": 0.0,
        "dpd_history": [],
    }


# ─── intent detection ──────────────────────────────────────────────────────────

# Starts a fresh application (only meaningful when there ISN'T one already in progress).
_START_RE = re.compile(
    r"\b(apply(ing|)|applied|new loan|want(ed|ing|s|)? (a |to )?(get a |take a )?loan|"
    r"take a loan|get a loan|loan application|start(ing|ed|)? (my |a |the )?application|"
    r"need (a |)loan|looking for (a |)loan|interested in (a |)loan)\b",
    re.I,
)
# Explicitly throws away an in-progress application and begins again.
_RESTART_RE = re.compile(r"\b(start over|new application|restart)\b", re.I)
# Walks away from the form entirely.
_CANCEL_RE = re.compile(r"\b(cancel|stop|quit|exit|never ?mind|forget it)\b", re.I)
# Plain small talk -- shouldn't hit the "loan questions only" refusal.
_GREETING_RE = re.compile(
    r"^\s*(hi+|hello+|hey+|hiya|yo|sup|good\s*(morning|afternoon|evening)|namaste)\W*$", re.I,
)


def is_greeting(text: str) -> bool:
    return _GREETING_RE.match(text.strip()) is not None


def greeting_prefix(session: dict) -> str:
    name = session["state"].get("applicant_name") or session.get("display_name")
    return f"Hi {name.split()[0]}! 👋 " if name else "Hi there! 👋 "


# "my name is X" / "I'm X" / "call me X" -- small talk, not a loan question,
# and not necessarily the applicant's name for THIS application either.
_INTRO_RE = re.compile(r"\b(my name is|i am|i'm|this is|call me)\s+([a-zA-Z][a-zA-Z\s]{1,30})", re.I)
# Guards against "I am applying for a loan" being misread as a name introduction.
_NON_NAME_WORDS = {
    "applying", "looking", "trying", "interested", "here", "back", "done",
    "ready", "good", "fine", "great", "new", "just", "still", "also", "not",
    "sure", "okay", "ok", "loan", "loans", "apply", "applicant", "for", "a",
    "an", "the", "to", "in", "going", "about",
}


def extract_intro_name(text: str) -> Optional[str]:
    m = _INTRO_RE.search(text)
    if not m:
        return None
    name = re.split(r"[.,!?;]| and | but ", m.group(2).strip())[0].strip()
    words = name.split()
    if not (1 <= len(words) <= 4):
        return None
    if any(w.lower() in _NON_NAME_WORDS for w in words):
        return None
    return " ".join(w.capitalize() for w in words)
_REASON_RE = re.compile(
    r"\b(why|reason|explain|rejected|not approved|denied|declined)\b", re.I,
)
# Distinguishes "why was I rejected" (about MY result) from "why aadhar for loan"
# (a general question that happens to contain "why").
_OUTCOME_WORDS_RE = re.compile(
    r"\b(rejected|rejection|denied|denial|declined|decline|not approved|approved|"
    r"approval|decision|decided|status)\b", re.I,
)
# Only route to "explain MY application's outcome" when the question actually
# references the applicant's own result -- plain domain words like "aadhaar" or
# "cibil" on their own are general questions and should go to general_loan_answer.
_MY_APPLICATION_RE = re.compile(
    r"\b(my|this|our|the) (application|loan|decision|score|status|result|"
    r"cibil|risk|account(ability)?)\b",
    re.I,
)
# Heuristic for "this looks like a question, not a form answer" -- used so that
# a genuine question typed mid-form (e.g. while we're asking for a name) gets
# answered instead of being swallowed as if it were the field's value.
_QUESTION_RE = re.compile(
    r"\?\s*$|^\s*(what|why|how|when|where|which|who|is|are|does|do|can|could|"
    r"should|will|would)\b",
    re.I,
)


def maybe_answer_side_question(text: str) -> Optional[str]:
    """If `text` reads like a question rather than form input, answer it. Else None."""
    if _QUESTION_RE.search(text.strip()):
        # Asked mid-form -> safe to assume it's about the loan/application process
        # even if it doesn't hit a keyword (e.g. "what documents do I need?").
        return general_loan_answer(text, assume_relevant=True)
    return None


def fetch_agent_breakdown_from_db(orchestration_id: str) -> list[dict]:
    """Query DB for agent decisions for a given orchestration and return
    a list formatted like the orchestrator `agent_breakdown` entries.
    """
    if not ORCHESTRATOR_AVAILABLE or not orchestration_id:
        return []
    try:
        from db.connection import get_conn, release_conn
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ae.agent_id, ad.decision_output, ad.confidence_score,
                           ad.reasoning, ac.composite_risk_score
                    FROM agent_executions ae
                    LEFT JOIN agent_decisions ad ON ae.execution_id = ad.execution_id
                    LEFT JOIN accountability_scores ac ON ae.execution_id = ac.execution_id
                    WHERE ae.orchestration_id = %s
                    ORDER BY ae.sequence_number
                    """,
                    (orchestration_id,),
                )
                rows = cur.fetchall()
        finally:
            release_conn(conn)
        breakdown = []
        for r in rows:
            agent_id, decision_output, confidence_score, reasoning, composite = r
            breakdown.append({
                "agent_id": agent_id,
                "agent_name": {
                    "A001": "Aadhaar Verification",
                    "A002": "Payslip Income Verification",
                    "A003": "Bank Statement Analysis",
                    "A004": "CIBIL Score",
                }.get(agent_id, agent_id),
                "decision_output": decision_output,
                "confidence_score": float(confidence_score) if confidence_score is not None else 0.0,
                "composite_risk_score": float(composite) if composite is not None else 0.0,
                "reasoning": reasoning or "",
            })
        return breakdown
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB agent breakdown fetch failed: %s", exc)
        return []


# ─── parsing helpers ────────────────────────────────────────────────────────────

def _is_skip(text: str) -> bool:
    return text.strip().lower() in {"skip", "none", "no", "n/a", "-"}


def _parse_float(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", "").replace("₹", "").strip())
    except ValueError:
        return None


def _parse_int(text: str) -> Optional[int]:
    try:
        return int(re.sub(r"[^\d-]", "", text.strip()))
    except ValueError:
        return None


def handle_stage_input(session: dict, stage: str, text: str) -> tuple[str, bool]:
    """Returns (reply_or_error, advanced)."""
    state = session["state"]

    if stage == "name":
        candidate = extract_intro_name(text) or text.strip()
        if len(candidate) < 2:
            return "That doesn't quite look like a full name -- mind typing it again? 🙂", False
        state["applicant_name"] = candidate
        return "", True

    if stage == "loan_amount":
        val = _parse_float(text)
        if val is None or not (0 < val <= 5_000_000):
            return "Please enter a loan amount between ₹1 and ₹50,00,000 (numbers only) 💰", False
        state["loan_amount"] = val
        return "", True

    return "", False


# ─── decision rendering + application-specific Q&A ─────────────────────────────

def render_result_markdown(result: dict) -> str:
    decision = result.get("loan_decision", "Unknown")
    emoji = {"Approved": "✅", "Rejected": "❌", "Manual Review": "⚠️"}.get(decision, "ℹ️")
    oa = result.get("overall_accountability", {})
    responsible = result.get("responsible_agent") or result.get("responsible_agent_id")
    responsible_label = {
        "A001": "Aadhaar Verification",
        "A002": "Payslip Income Verification",
        "A003": "Bank Statement Analysis",
        "A004": "CIBIL Score",
    }.get(str(responsible), str(responsible or "—"))

    lines = [
        f"## {emoji} Decision: {decision}",
        "",
        result.get("reasoning", ""),
        "",
        f"**Driving agent:** {responsible_label}",
        f"**Overall risk score:** {oa.get('composite_score', 0):.2f}/10 ({oa.get('risk_level', '—')})",
        f"**Chain verified:** {'✅ Yes' if result.get('chain_verified') else '❌ No'}",
        f"**Orchestration ID:** `{result.get('orchestration_id')}`",
        "",
        "### Agent breakdown",
    ]
    for a in result.get("agent_breakdown", []):
        d = (a.get("decision_output") or "").lower()
        sym = "✅" if d in ("verified", "approve", "approved") else \
              "❌" if d in ("rejected", "high_risk", "high_risk_auto") else "⚠️"
        lines.append(
            f"- {sym} **{a['agent_name']}** — `{a.get('decision_output')}` "
            f"({a.get('confidence_score', 0):.0%} confidence, risk {a.get('composite_risk_score', 0):.1f}/10)"
        )
    return "\n".join(lines)


def answer_from_result(session: dict, question: str) -> str:
    result = session["result"]
    q = question.lower()

    if "error" in result:
        return (
            "That application couldn't be completed due to a technical hiccup on our side 😕 -- "
            "no decision was reached. Please try applying again."
        )

    breakdown = {a["agent_id"]: a for a in result.get("agent_breakdown", [])}
    by_name = {
        "aadhaar": "A001", "aadhar": "A001", "identity": "A001",
        "payslip": "A002", "income": "A002",
        "bank": "A003", "statement": "A003",
        "cibil": "A004", "credit": "A004",
    }
    for keyword, agent_id in by_name.items():
        if keyword in q and agent_id in breakdown:
            a = breakdown[agent_id]
            sym = "✅" if a["decision_output"] == "verified" else \
                  "❌" if a["decision_output"] in ("rejected", "high_risk") else "⚠️"
            return (
                f"{sym} **{a['agent_name']}** decided `{a['decision_output']}` "
                f"with {a['confidence_score']:.0%} confidence "
                f"(risk score {a['composite_risk_score']:.1f}/10).\n\n{a['reasoning']}"
            )

    if _REASON_RE.search(q):
        return reason_reply(session)

    if any(k in q for k in ["risk", "accountability"]) or (("score" in q) and "cibil" not in q):
        oa = result.get("overall_accountability", {})
        return (
            f"📊 Overall accountability composite score: **{oa.get('composite_score', 0):.2f}/10** "
            f"({oa.get('risk_level', '—')} risk), averaged across {oa.get('agent_count', 0)} agents."
        )

    if any(k in q for k in ["tamper", "chain", "hash", "verif", "provenance", "audit"]):
        ok = result.get("chain_verified")
        return (
            f"🔗 The provenance hash chain for this orchestration was "
            f"{'✅ verified — no tampering detected.' if ok else '❌ NOT verified — please check the audit log.'}"
        )

    if any(k in q for k in ["decision", "approved", "rejected", "status", "result"]):
        # Return the full reasoning/summary for the final decision so the user
        # always sees the verdict and the synthesized explanation.
        return reason_reply(session)

    if any(k in q for k in ["agent", "breakdown", "steps", "pipeline"]):
        lines = []
        for a in breakdown.values():
            sym = "✅" if a["decision_output"] == "verified" else \
                  "❌" if a["decision_output"] in ("rejected", "high_risk") else "⚠️"
            lines.append(f"{sym} **{a['agent_name']}** ({a['agent_id']}): {a['decision_output']} "
                         f"({a['confidence_score']:.0%} confidence)")
        return "Here's how each agent ruled:\n\n" + "\n".join(lines)

    emoji = {"Approved": "✅", "Rejected": "❌", "Manual Review": "⚠️"}.get(result.get("loan_decision"), "ℹ️")
    return (
        f"{emoji} Final decision was **{result.get('loan_decision')}**. "
        "You can ask *\"why was this decided?\"*, about a specific agent (Aadhaar, payslip, CIBIL), "
        "the risk score, or whether the record is tamper-proof."
    )


def reason_reply(session: dict) -> str:
    result = session["result"]
    if not result or "error" in (result or {}):
        return "There's no completed decision to explain yet -- want to apply for a loan? 📝"

    orchestration_id = result.get("orchestration_id")
    db_reasoning = fetch_reasoning_from_db(orchestration_id) if orchestration_id else None

    # Prefer in-memory result reasoning if it includes the Bank agent (A003),
    # otherwise fall back to the DB-stored reasoning. This ensures the UI shows
    # A003's decision immediately after a fresh run even if the DB record was
    # written earlier without A003.
    result_breakdown = {a["agent_id"] for a in (result.get("agent_breakdown") or [])}
    db_breakdown = set()
    if orchestration_id:
        try:
            db_rows = fetch_agent_breakdown_from_db(orchestration_id)
            db_breakdown = {a["agent_id"] for a in db_rows}
        except Exception:
            db_breakdown = set()

    if "A003" in result_breakdown:
        reasoning = result.get("reasoning", db_reasoning or "No reasoning was recorded for this decision.")
    else:
        reasoning = db_reasoning or result.get("reasoning", "No reasoning was recorded for this decision.")
    session["reason_given"] = True

    emoji = {"Approved": "✅", "Rejected": "❌", "Manual Review": "⚠️"}.get(result.get("loan_decision"), "ℹ️")
    source_note = "_(retrieved from the `final_decisions` record)_" if db_reasoning else ""
    return (
        f"{emoji} Here's the reasoning behind the **{result.get('loan_decision')}** decision "
        f"for orchestration `{orchestration_id}`: {source_note}\n\n"
        f"{reasoning}\n\n"
        "That's the full picture for this application 🙌. Ask me a general loan question, "
        "or start a new application whenever you're ready."
    )


# ─── idle / general-mode handling ──────────────────────────────────────────────

def handle_idle_input(session: dict, text: str) -> tuple[str, list[str]]:
    if is_greeting(text):
        reply = greeting_prefix(session) + (
            "I'm your TraceChain loan assistant 🤖 -- I can help you apply for a loan, "
            "or answer questions about loans, CIBIL scores, and EMIs. What would you like to do?"
        )
        return reply, CHIPS["welcome"]

    if _RESTART_RE.search(text) or _START_RE.search(text):
        reset_state(session)
        return PROMPTS["name"], []

    intro_name = extract_intro_name(text)
    if intro_name and not _MY_APPLICATION_RE.search(text):
        session["display_name"] = intro_name
        reply = (
            f"Nice to meet you, {intro_name}! 😊 I'm your TraceChain loan assistant -- "
            "I can help you apply for a loan, or answer any loan/credit questions. "
            "What would you like to do?"
        )
        return reply, CHIPS["welcome"]

    result = session["result"]
    has_clean_result = result is not None and "error" not in result
    references_my_app = _MY_APPLICATION_RE.search(text) is not None
    # A bare "why"/"reason"/"explain" is only about MY result when it's paired
    # with an outcome word (rejected/approved/decision/...) or references "my
    # application" directly -- otherwise it's a general question that happens
    # to use the word "why" (e.g. "why aadhar for loan") and should go to
    # general_loan_answer instead of being assumed to be about a decision.
    is_about_my_result = references_my_app or (_REASON_RE.search(text) is not None and _OUTCOME_WORDS_RE.search(text) is not None)

    if has_clean_result and is_about_my_result:
        reply = answer_from_result(session, text)
        chips = CHIPS["post_reason"]
        return reply, chips

    if is_about_my_result and not has_clean_result:
        if result is not None and "error" in result:
            return (
                "That application couldn't be completed, so there's no decision to explain 😕 -- "
                "want to try applying again?", ["📝 Apply for a loan"],
            )
        return "You don't have an application decision yet -- want to apply for a loan? 📝", ["📝 Apply for a loan"]

    return general_loan_answer(text), []


# ─── routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "web/index.html not found")
    return FileResponse(index_path)


@app.post("/api/start")
def api_start():
    session = new_session()
    SESSIONS[session["id"]] = session
    reply = (
        "👋 Welcome to **TraceChain** — I'm your loan assistant.\n\n"
        "I can help you **apply for a loan**, or answer general questions about loans, "
        "CIBIL scores, EMIs, and eligibility. How can I help today? 😊"
    )
    return build_response(session, reply, chips=CHIPS["welcome"])


FIELD_LABELS = {
    "name": "the applicant's full name",
    "aadhaar_upload": "the Aadhaar image",
    "payslip_upload": "the payslip",
    "bank_upload": "the bank statement file",
    "loan_amount": "the loan amount",
}

# "wrong aadhaar" / "change my name" / "redo the payslip" -- lets someone fix a
# field they already filled in without cancelling and losing everything else.
FIELD_EDIT_TRIGGERS = {
    "name": re.compile(r"\b(change|edit|fix|wrong|redo)\b.*\bname\b", re.I),
    "aadhaar_upload": re.compile(r"\b(change|edit|fix|wrong|redo|re-?upload)\b.*\baadhaa?r\b", re.I),
    "payslip_upload": re.compile(r"\b(change|edit|fix|wrong|redo|re-?upload)\b.*\bpayslip\b", re.I),
    "bank_upload": re.compile(r"\b(change|edit|fix|wrong|redo|re-?upload)\b.*\b(bank|statement|csv|excel|xls|xlsx)\b", re.I),
    "loan_amount": re.compile(r"\b(change|edit|fix|wrong|redo)\b.*\b(amount|loan amount)\b", re.I),
}


def matched_edit_field(text: str) -> Optional[str]:
    for field_stage, pattern in FIELD_EDIT_TRIGGERS.items():
        if pattern.search(text):
            return field_stage
    return None


def clear_field(state: dict, field_stage: str) -> None:
    if field_stage == "name":
        state.pop("applicant_name", None)
    elif field_stage == "aadhaar_upload":
        state.get("applicant_data", {}).pop("aadhar_image_path", None)
    elif field_stage == "payslip_upload":
        state.get("applicant_data", {}).pop("payslip_file_path", None)
    elif field_stage == "bank_upload":
        state.get("applicant_data", {}).pop("bank_statement_file_path", None)
    elif field_stage == "loan_amount":
        state.pop("loan_amount", None)


def next_incomplete_stage(state: dict) -> Optional[str]:
    """Which COLLECT_STAGES field is still missing -- None once everything is filled."""
    if not state.get("applicant_name"):
        return "name"
    ad = state.get("applicant_data", {})
    if not ad.get("aadhar_image_path"):
        return "aadhaar_upload"
    if not ad.get("payslip_file_path"):
        return "payslip_upload"
    if not ad.get("bank_statement_file_path"):
        return "bank_upload"
    if not state.get("loan_amount"):
        return "loan_amount"
    return None


def advance_after(session: dict, reply_prefix: str = "") -> dict:
    """Move to whatever's still missing, or trigger verification once everything's filled."""
    session["retry_count"] = 0
    nxt = next_incomplete_stage(session["state"])
    if nxt is None:
        session["flow_stage"] = "verifying"
        reply = reply_prefix + (
            "Your application has been sent for verification! 📨 "
            "I'm checking the Aadhaar document, payslip, bank statement and CIBIL "
            "score now -- this only takes a moment... ⏳"
        )
        return build_response(session, reply, trigger_verify=True)
    session["flow_stage"] = nxt
    return build_response(
        session, reply_prefix + PROMPTS[nxt],
        chips=CHIPS.get(nxt, []), upload=UPLOAD_HINTS.get(nxt),
    )


def cancel_flow(session: dict) -> str:
    session["flow_stage"] = None
    session["retry_count"] = 0
    return (
        "No problem 👍 -- I've cancelled that application, nothing was submitted. "
        "I'm still here if you want to try again, or if you have a general loan question."
    )


@app.post("/api/message")
def api_message(session_id: str = Form(...), message: str = Form(...)):
    session = get_session(session_id)
    stage = session["flow_stage"]

    if stage is None:
        reply, chips = handle_idle_input(session, message)
        return build_response(session, reply, chips=chips, upload=UPLOAD_HINTS.get(session["flow_stage"]))

    # ── mid-form intents that should never be swallowed as literal field data ──
    if _CANCEL_RE.search(message):
        return build_response(session, cancel_flow(session), chips=["📝 Apply for a loan", "💬 Ask a loan question"])

    if _RESTART_RE.search(message):
        reset_state(session)
        return build_response(session, "Starting a fresh application! 🆕\n\n" + PROMPTS["name"])

    if is_greeting(message):
        reply = greeting_prefix(session) + PROMPTS.get(stage, "")
        return build_response(session, reply, upload=UPLOAD_HINTS.get(stage), chips=CHIPS.get(stage, []))

    # Introducing themselves mid-form ("my name is X") is small talk, not field
    # data -- except when the stage literally IS "name", where it's handled as
    # the actual answer further down (handle_stage_input extracts it there).
    if stage != "name":
        intro_name = extract_intro_name(message)
        if intro_name and not _MY_APPLICATION_RE.search(message):
            session["display_name"] = intro_name
            reply = f"Nice to meet you, {intro_name}! 😊 " + PROMPTS.get(stage, "")
            return build_response(session, reply, upload=UPLOAD_HINTS.get(stage), chips=CHIPS.get(stage, []))

    edit_field = matched_edit_field(message)
    if edit_field is not None:
        clear_field(session["state"], edit_field)
        session["flow_stage"] = edit_field
        session["retry_count"] = 0
        label = FIELD_LABELS.get(edit_field, "that")
        return build_response(
            session, f"No problem 👍 -- let's redo {label}.\n\n{PROMPTS[edit_field]}",
            chips=CHIPS.get(edit_field, []), upload=UPLOAD_HINTS.get(edit_field),
        )

    if _START_RE.search(message):
        # Already mid-application (any stage, including "name" itself) -- don't
        # treat an apply-intent phrase as literal field data, and don't reset progress.
        reply = (
            f"You're already partway through an application 🙂 -- I still need "
            f"{FIELD_LABELS.get(stage, 'that')} to continue. "
            f"(Or type **cancel** to stop, or **change name/aadhaar/payslip/amount** to fix something.)"
        )
        return build_response(session, reply, upload=UPLOAD_HINTS.get(stage), chips=CHIPS.get(stage, []))

    if stage in ("aadhaar_upload", "payslip_upload", "bank_upload"):
        side = maybe_answer_side_question(message)
        if side is not None:
            reply = f"{side}\n\n---\n{PROMPTS[stage]}"
            return build_response(session, reply, upload=UPLOAD_HINTS[stage])
        docs = {
            "aadhaar_upload": "Aadhaar image 🪪",
            "payslip_upload": "payslip 📄",
            "bank_upload": "bank statement CSV 🏦",
        }
        reply = (f"Please use the upload area below to attach the {docs[stage]}. "
                 f"Or ask me anything else in the meantime!")
        return build_response(session, reply, upload=UPLOAD_HINTS[stage])

    side = maybe_answer_side_question(message)
    if side is not None:
        reply = f"{side}\n\n---\n{PROMPTS[stage]}"
        return build_response(session, reply, chips=CHIPS.get(stage, []), upload=UPLOAD_HINTS.get(stage))

    reply, advanced = handle_stage_input(session, stage, message)

    if not advanced:
        session["retry_count"] = session.get("retry_count", 0) + 1
        if session["retry_count"] >= 3:
            reply += (
                "\n\nStill stuck? 🤔 Type **cancel** to stop the application, or ask me "
                "anything else about loans in the meantime."
            )
        return build_response(session, reply, chips=CHIPS.get(stage, []), upload=UPLOAD_HINTS.get(stage))

    return advance_after(session)


@app.post("/api/upload")
async def api_upload(session_id: str = Form(...), field: str = Form(...), file: UploadFile = File(...)):
    session = get_session(session_id)

    if field not in ("aadhaar", "payslip", "bank"):
        raise HTTPException(400, "Unknown upload field")

    validate_upload_type(field, file.filename or "", file.content_type)

    session_dir = UPLOAD_DIR / session["id"]
    session_dir.mkdir(parents=True, exist_ok=True)
    dest = session_dir / f"{field}_{file.filename}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    ad = session["state"]["applicant_data"]
    if field == "aadhaar":
        ad["aadhar_image_path"] = str(dest)
    elif field == "payslip":
        ad["payslip_file_path"] = str(dest)
    else:
        ad["bank_statement_file_path"] = str(dest)

    # Resume wherever is still missing -- handles both the normal forward flow
    # and re-uploads triggered by "change aadhaar" / "wrong payslip" etc.
    return advance_after(session, reply_prefix=f"Got **{file.filename}** ✅\n\n")


@app.post("/api/verify")
def api_verify(session_id: str = Form(...)):
    session = get_session(session_id)
    state = session["state"]

    # CIBIL score is never asked in chat -- it's "fetched" here, in the background,
    # as part of verification (see simulate_cibil_lookup docstring).
    if not state.get("cibil_score"):
        state["cibil_score"] = simulate_cibil_lookup(state)

    if not ORCHESTRATOR_AVAILABLE:
        logger.error("Pipeline unavailable at /api/verify: %s", ORCHESTRATOR_IMPORT_ERROR)
        session["result"] = {"error": "unavailable"}
        session["flow_stage"] = None
        return build_response(
            session, GENERIC_FAILURE_REPLY, chips=["📝 New application"], done=True, result=session["result"],
        )

    try:
        result = run_pipeline(state)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline execution failed")
        result = {"error": str(exc), "loan_decision": "Manual Review"}

    session["result"] = result
    session["flow_stage"] = None

    # If the orchestrator returned a result but omitted some agents (e.g. A003),
    # try to fetch missing agent decisions from the DB and merge them into the
    # result so the UI always shows the complete agent breakdown.
    try:
        if "agent_breakdown" in result and result.get("orchestration_id"):
            present = {a["agent_id"] for a in result.get("agent_breakdown", [])}
            if "A003" not in present:
                db_rows = fetch_agent_breakdown_from_db(result.get("orchestration_id"))
                for r in db_rows:
                    if r["agent_id"] not in present:
                        result.setdefault("agent_breakdown", []).append(r)
    except Exception:
        logger.exception("Failed merging DB agent breakdown into result")
    if "error" in result:
        logger.error("Pipeline returned an error for %s: %s", state.get("application_id"), result["error"])
        reply = friendly_error_reply(str(result.get("error", "")))
        chips = ["📝 New application"]
    else:
        reply = render_result_markdown(result)
        chips = CHIPS["post_decision_approved"] if result.get("loan_decision") == "Approved" \
            else CHIPS["post_decision_review"]

    return build_response(session, reply, chips=chips, done=True, result=result)


@app.get("/api/health")
def health():
    return JSONResponse({
        "status": "ok",
        "orchestrator_available": ORCHESTRATOR_AVAILABLE,
        "orchestrator_import_error": ORCHESTRATOR_IMPORT_ERROR,
        "gemini_configured": bool(GEMINI_API_KEY),
    })
