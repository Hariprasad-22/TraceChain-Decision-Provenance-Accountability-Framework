"""
scoring/overall_score.py
------------------------
Computes the overall (orchestration-level) accountability score
from the individual agent accountability scores.

Design decisions:
  - All 4 agents (Aadhaar, Payslip, Bank, CIBIL) carry equal weight.
  - Skipped agents (bank stub) are excluded from the average.
  - The orchestrator recomputes composite_risk_score using the
    canonical formula from the DB schema comment:
        0.40 * irreversibility + 0.35 * impact + 0.25 * (10 - explainability)
  - The same formula is applied for the overall score to keep
    all numbers consistent across the system.

Risk level thresholds (matching risk_level_for() in execution_record.py):
  - composite >= 7.0  → High
  - composite >= 4.0  → Medium
  - composite <  4.0  → Low
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─── formula (canonical, from DB schema comment) ───────────────────────────────

def compute_composite(
    impact: int,
    irreversibility: int,
    explainability: int,
) -> float:
    """
    Canonical TraceChain composite risk formula.
    Inputs are 0-10 integers.
    """
    return round(
        0.40 * irreversibility
        + 0.35 * impact
        + 0.25 * (10 - explainability),
        2,
    )


def risk_level(composite: float) -> str:
    if composite >= 7.0:
        return "High"
    if composite >= 4.0:
        return "Medium"
    return "Low"


# ─── per-agent score normalisation ────────────────────────────────────────────

def normalise_agent_score(accountability: dict) -> dict:
    """
    Recompute composite_risk_score using the canonical formula regardless
    of which formula the individual agent used internally.
    Returns an updated accountability dict.
    """
    impact          = int(accountability.get("impact_score", 0))
    irreversibility = int(accountability.get("irreversibility_score", 0))
    explainability  = int(accountability.get("explainability_score", 10))

    composite = compute_composite(impact, irreversibility, explainability)
    level     = risk_level(composite)

    updated = dict(accountability)
    updated["composite_risk_score"] = composite
    updated["risk_level"]           = level
    return updated


# ─── overall orchestration score ──────────────────────────────────────────────

def compute_overall(agent_accountabilities: list[dict]) -> dict:
    """
    Compute the overall accountability score for the whole orchestration.

    Parameters
    ----------
    agent_accountabilities : list[dict]
        List of (normalised) accountability dicts from each active agent.
        Skipped agents (bank stub) should be excluded before calling this.

    Returns
    -------
    dict with:
        overall_composite  – float, 0-10
        overall_risk_level – str
        agent_scores       – list of per-agent breakdown dicts
        agent_count        – int (how many agents contributed)
    """
    if not agent_accountabilities:
        logger.warning("No agent accountabilities provided — overall score is 0.")
        return {
            "overall_composite":  0.0,
            "overall_risk_level": "Low",
            "agent_scores":       [],
            "agent_count":        0,
        }

    # Normalise each agent's composite to the canonical formula first
    normalised = [normalise_agent_score(a) for a in agent_accountabilities]

    # Simple equal-weight average of composite scores
    total     = sum(a["composite_risk_score"] for a in normalised)
    count     = len(normalised)
    composite = round(total / count, 2)
    level     = risk_level(composite)

    logger.info(
        "Overall score: composite=%.2f level=%s (from %d agents)",
        composite, level, count,
    )

    return {
        "overall_composite":  composite,
        "overall_risk_level": level,
        "agent_scores":       normalised,
        "agent_count":        count,
    }


# ─── responsible agent determination ─────────────────────────────────────────

def determine_responsible_agent(agent_results: list[dict]) -> Optional[str]:
    """
    Identify which agent drove the final decision most significantly.

    Logic:
      - If any agent rejected → the first rejecting agent is responsible.
      - Otherwise → the agent with the highest composite risk score.

    Parameters
    ----------
    agent_results : list[dict]
        Each dict must have: agent_id, decision_output, composite_risk_score.

    Returns
    -------
    str | None  — agent_id string, e.g. 'A001'
    """
    # First rejecting agent
    for r in agent_results:
        if r.get("decision_output") in ("rejected", "invalid_format",
                                         "underage_applicant", "high_risk_auto",
                                         "high_risk", "invalid_score",
                                         "invalid_input", "missing_data"):
            return r.get("agent_id")

    # Highest risk among non-rejected
    if agent_results:
        return max(agent_results, key=lambda r: r.get("composite_risk_score", 0))["agent_id"]

    return None
