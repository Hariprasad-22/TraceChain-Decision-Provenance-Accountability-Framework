# TraceChain Loan Assistant

A dashboard-style chat interface for your TraceChain orchestrator.
It greets the user, lets them either apply for a loan or ask a general
loan/credit question, runs the real pipeline once an application is
complete, and shows the decision with full transparency.

## Layout

```
Deloitte-capstone/
├── Frontend/
│   ├── server.py          ← FastAPI chat backend (this app)
│   ├── web/index.html     ← frontend
│   └── requirements.txt
└── orchestrator/
    ├── orchestrator.py    ← run_pipeline()
    ├── .env               ← DB + Gemini keys
    └── …
```

`server.py` adds `../orchestrator` to `sys.path` and imports
`run_pipeline` the same way `run_pipeline.py` does. No files need to be
copied into the orchestrator folder.

## 1. Install

```bash
# Frontend + shared deps
pip install -r Frontend/requirements.txt

# Also install agent deps used by the orchestrator (aadhaar / payslip / etc.)
# if you haven't already — see imp_docs/*/requirements.txt
```

## 2. Run it

```bash
cd Frontend
uvicorn server:app --reload --port 8000
```

Open **http://localhost:8000** in a browser.

Check the wiring:

```bash
curl http://localhost:8000/api/health
```

You want `"orchestrator_available": true`.

## How the assistant behaves

**1. Welcome.** On load it greets the user and offers two paths: *apply for
a loan*, or *ask a general question*. Quick-reply chips make both one tap
away.

**2. Applying.** Saying anything like "apply for a loan" opens a short,
focused interface: applicant name → Aadhaar image upload → payslip upload
→ loan amount. The CIBIL score is NOT asked — it's "fetched" automatically
in the background during verification (see `simulate_cibil_lookup` in
`server.py`). Optional fields `orchestrator.validate_state()` accepts
(DOB, declared income, credit utilization, DPD history) are defaulted.

**3. Verification.** As soon as the loan amount is given, the UI shows
"sent for verification" with an animated per-agent progress list while
the backend calls `run_pipeline(state)`.

**4. Decision.** The result renders as a rich card: Approved / Rejected /
Manual Review, a risk-score gauge, hash-chain verification, and the
per-agent breakdown — all from what `run_pipeline` returns.

**5. "Why this decision?"** Pulls reasoning from the `final_decisions`
table via `fetch_reasoning_from_db`, falling back to the in-memory
pipeline result if the DB read fails.

**6. General questions.** Loan/credit/banking topics are answered by
Gemini (`GEMINI_API_KEY` / `GEMINI_MODEL` from `orchestrator/.env`).
Out-of-scope questions are declined.

## Notes

- File uploads land in `orchestrator/chat_uploads/<session_id>/` (kept
  outside `Frontend/` so `uvicorn --reload` is not restarted on every upload)
  and are passed as `applicant_data.aadhar_image_path` /
  `payslip_file_path`.
- Sessions are in-memory (fine for local/demo).
- `loan_amount` is capped at ₹50,00,000 and `cibil_score` to 300–900,
  matching `orchestrator.validate_state()`.
