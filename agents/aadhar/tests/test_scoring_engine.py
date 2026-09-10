"""Automated tests for scoring.py - the accountability scoring engine."""
import pytest

from scoring import score_decision, HUMAN_REVIEW_THRESHOLD


def test_low_risk_decision_scores_low():
    b = score_decision(irreversibility=0, impact=1, explainability=10)
    assert b.risk_score < 30
    assert b.needs_human_review is False


def test_high_risk_decision_scores_high_and_flagged():
    b = score_decision(irreversibility=9, impact=9, explainability=2)
    assert b.risk_score >= HUMAN_REVIEW_THRESHOLD
    assert b.needs_human_review is True


def test_review_threshold_boundary():
    # Score right at the threshold should be flagged; one point below should not.
    just_below = score_decision(irreversibility=5, impact=5, explainability=6)
    assert just_below.risk_score < HUMAN_REVIEW_THRESHOLD
    assert just_below.needs_human_review is False


def test_out_of_range_inputs_raise():
    with pytest.raises(ValueError):
        score_decision(irreversibility=11, impact=5, explainability=5)
    with pytest.raises(ValueError):
        score_decision(irreversibility=5, impact=-1, explainability=5)


def test_reason_mentions_irreversibility_when_high():
    b = score_decision(irreversibility=9, impact=2, explainability=9)
    assert "hard to undo" in b.reason


def test_reason_is_routine_when_all_low_risk():
    b = score_decision(irreversibility=1, impact=1, explainability=9)
    assert b.reason == "routine, low-stakes decision"
