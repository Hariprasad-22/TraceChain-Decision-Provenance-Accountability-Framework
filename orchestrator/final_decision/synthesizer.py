"""
final_decision/synthesizer.py
------------------------------
Generates the human-readable final loan decision and reasoning
after all agents have run.

Decision rules (deterministic, then explanatory):
  - 'Rejected'       — any agent output contains a hard reject keyword.
  - 'Manual Review'  — any agent output contains a review/uncertain keyword
                       and no hard rejection occurred.
  - 'Approved'       — all active agents verified successfully.

Rejected keywords (hard stops):
    rejected, high_risk_auto, high_risk, invalid_format,
    underage_applicant, invalid_score, invalid_input, missing_data

Review keywords (soft flags):
    needs_review, manual_review, needs_human_review

Approved keyword:
    verified

The synthesizer also writes a structured summary combining all four
agent reasonings into one coherent paragraph that can be shown to
the loan officer or applicant.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ─── decision classification ───────────────────────────────────────────────────

_REJECT_KEYWORDS = {
    "rejected", "high_risk_auto", "high_risk",
    "invalid_format", "underage_applicant",
    "invalid_score", "invalid_input", "missing_data",
}

_REVIEW_KEYWORDS = {
    "needs_review", "manual_review", "needs_human_review",
}

_APPROVE_KEYWORDS = {
    "verified",
}

# Map to FINAL_DECISIONS.answer CHECK constraint values
_DB_ANSWER_MAP = {
    "Approved":      "Approved",
    "Rejected":      "Rejected",
    "Manual Review": "Manual Review",
}

# Agent display names for human-readable output
_AGENT_NAMES = {
    "A001": "Aadhaar Verification",
    "A002": "Payslip Income Verification",
    "A003": "Bank Statement Analysis",
    "A004": "CIBIL Score",
}


def _classify(decision_output: str) -> str:
    """Return 'Rejected', 'Manual Review', or 'Approved' for a single agent output."""
    d = (decision_output or "").lower().strip()
    if d in _REJECT_KEYWORDS:
        return "Rejected"
    if d in _REVIEW_KEYWORDS:
        return "Manual Review"
    if d in _APPROVE_KEYWORDS:
        return "Approved"
    # Unknown output — treat as Manual Review (safe default)
    logger.warning("Unknown decision_output '%s' — defaulting to Manual Review", decision_output)
    return "Manual Review"


# ─── main synthesizer ─────────────────────────────────────────────────────────

def synthesize(
    agent_results: list[dict],
    overall_composite: float,
    overall_risk_level: str,
    responsible_agent_id: str,
) -> dict:
    """
    Produce the final decision dict ready to be written to FINAL_DECISIONS.

    Parameters
    ----------
    agent_results : list[dict]
        Each dict must have:
          - agent_id
          - decision_output
          - confidence_score
          - reasoning
          - composite_risk_score  (normalised by orchestrator)
        Skipped agents (bank stub) should be excluded.
    overall_composite : float
        Overall accountability score (0-10).
    overall_risk_level : str
        'Low' | 'Medium' | 'High'
    responsible_agent_id : str
        Which agent drove the decision (from scoring.determine_responsible_agent).

    Returns
    -------
    dict with keys matching FINAL_DECISIONS table columns plus a
    'agent_breakdown' list for the orchestrator's response payload.
    """
    # ── step 1: determine final answer ────────────────────────────────────────
    final_answer = "Approved"  # optimistic default
    for res in agent_results:
        classification = _classify(res.get("decision_output", ""))
        if classification == "Rejected":
            final_answer = "Rejected"
            break                          # hard stop — no need to check further
        if classification == "Manual Review":
            final_answer = "Manual Review" # soft flag — continue checking others

    # ── step 2: build per-agent summary lines ─────────────────────────────────
    lines = []
    for res in agent_results:
        name   = _AGENT_NAMES.get(res["agent_id"], res["agent_id"])
        output = res.get("decision_output", "unknown")
        conf   = res.get("confidence_score", 0.0)
        reason = res.get("reasoning", "")
        composite = res.get("composite_risk_score", 0.0)

        lines.append(
            f"[{name}] Decision: {output} (confidence: {conf:.0%}, "
            f"risk: {composite:.1f}/10). Reason: {reason}"
        )

    # ── step 3: compose the full reasoning paragraph ───────────────────────────
    resp_name = _AGENT_NAMES.get(responsible_agent_id, responsible_agent_id)
    intro_map = {
        "Approved":      "All verification checks passed.",
        "Rejected":      f"The application was rejected. Driving agent: {resp_name}.",
        "Manual Review": f"The application requires manual review. Key concern raised by: {resp_name}.",
    }
    intro = intro_map[final_answer]

    reasoning = (
        f"{intro}\n\n"
        + "\n".join(lines)
        + f"\n\nOverall accountability risk score: {overall_composite:.1f}/10 ({overall_risk_level})."
    )

    # ── step 4: agent breakdown for response payload ──────────────────────────
    breakdown = [
        {
            "agent_id":            r["agent_id"],
            "agent_name":          _AGENT_NAMES.get(r["agent_id"], r["agent_id"]),
            "decision_output":     r.get("decision_output"),
            "confidence_score":    r.get("confidence_score"),
            "composite_risk_score": r.get("composite_risk_score"),
            "reasoning":           r.get("reasoning"),
        }
        for r in agent_results
    ]

    return {
        # Fields for FINAL_DECISIONS table
        "answer":               final_answer,
        "responsible_agent_id": responsible_agent_id,
        "reasoning":            reasoning,
        "risk_score":           overall_composite,
        "decision_status":      "Final",
        "timestamp":            datetime.now(timezone.utc),
        # Extra context for orchestrator response (not stored in DB)
        "agent_breakdown":      breakdown,
        "overall_risk_level":   overall_risk_level,
    }
