"""
Accountability scoring engine.

Turns three raw risk factors (irreversibility, impact, explainability) into
a single 0-100 risk score, plus a human-review flag. Weights and threshold
are named constants up top so they're easy to justify to a mentor/reviewer.
"""
from dataclasses import dataclass

# --- Weights ---
# Irreversibility weighted highest: an action that can't be undone deserves the
# most scrutiny regardless of anything else.
# Impact weighted almost as high: how much damage a wrong call causes.
# Explainability weighted lowest and inverted: it doesn't make an action risky
# on its own, but it removes our ability to catch a bad irreversible/high-impact
# call before it causes harm - so it amplifies the other two rather than
# standing alone.
WEIGHT_IRREVERSIBILITY = 0.40
WEIGHT_IMPACT = 0.35
WEIGHT_EXPLAINABILITY = 0.25

# Above this score, the decision must be surfaced to a human - either for
# review before acting (if the pipeline allows a pause) or for audit
# immediately after (if it doesn't).
HUMAN_REVIEW_THRESHOLD = 60


@dataclass
class ScoreBreakdown:
    risk_score: int
    needs_human_review: bool
    irreversibility_contribution: float
    impact_contribution: float
    explainability_contribution: float
    reason: str


def score_decision(irreversibility: int, impact: int, explainability: int) -> ScoreBreakdown:
    """All three inputs are 0-10. Returns a full breakdown, not just a number,
    so the audit dashboard can show WHY a decision scored the way it did -
    that "why" is the whole point of an accountability score."""
    for name, val in [("irreversibility", irreversibility), ("impact", impact), ("explainability", explainability)]:
        if not 0 <= val <= 10:
            raise ValueError(f"{name} must be between 0 and 10, got {val}")

    irr_contrib = irreversibility * WEIGHT_IRREVERSIBILITY
    imp_contrib = impact * WEIGHT_IMPACT
    inverted_exp = 10 - explainability
    exp_contrib = inverted_exp * WEIGHT_EXPLAINABILITY

    raw = irr_contrib + imp_contrib + exp_contrib   # 0-10 scale
    risk_score = round(raw * 10)                    # 0-100 scale
    needs_review = risk_score >= HUMAN_REVIEW_THRESHOLD

    reason_parts = []
    if irreversibility >= 7:
        reason_parts.append("hard to undo")
    if impact >= 7:
        reason_parts.append("high operational impact")
    if explainability <= 4:
        reason_parts.append("poorly explainable")
    reason = ", ".join(reason_parts) if reason_parts else "routine, low-stakes decision"

    return ScoreBreakdown(
        risk_score=risk_score,
        needs_human_review=needs_review,
        irreversibility_contribution=round(irr_contrib, 2),
        impact_contribution=round(imp_contrib, 2),
        explainability_contribution=round(exp_contrib, 2),
        reason=reason,
    )
