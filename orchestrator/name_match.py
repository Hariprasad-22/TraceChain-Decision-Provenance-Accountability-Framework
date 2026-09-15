"""
Name matching helpers used by document agents (Aadhaar / Payslip / Bank).

Agents keep their own decision_output. When the document name does not match
the applicant-entered name, we only annotate the result; the orchestrator
uses that flag to force a final loan Rejected with that agent as driver.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional

NAME_MATCH_THRESHOLD = 0.90


def normalize_name(name: Optional[str]) -> str:
    text = (name or "").strip().lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def name_similarity(name_a: Optional[str], name_b: Optional[str]) -> float:
    a = normalize_name(name_a)
    b = normalize_name(name_b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def names_match(name_a: Optional[str], name_b: Optional[str], threshold: float = NAME_MATCH_THRESHOLD) -> bool:
    return name_similarity(name_a, name_b) >= threshold


def name_mismatch_reason(
    agent_label: str,
    applicant_name: str,
    document_name: Optional[str],
) -> str:
    return f"The name on the {agent_label} does not match the name given in the application."


def annotate_name_mismatch(
    result: dict,
    *,
    agent_label: str,
    applicant_name: str,
    document_name: Optional[str],
) -> bool:
    """
    If both names are present and do not match, append a short note to reasoning
    and set a flag — without changing the agent's own decision_output / confidence.

    If either name is missing/unreadable, skip comparison (do not force reject).
    Returns True when a mismatch was annotated.
    """
    output_data = (result.get("execution") or {}).setdefault("output_data", {})
    app_name = (applicant_name or "").strip()
    doc_name = (document_name or "").strip()

    # Cannot compare — leave the agent decision alone (avoids false final Rejected
    # when bank CSV / payslip OCR has no name field).
    if not app_name or not doc_name:
        output_data["name_match"] = None
        output_data["name_mismatch"] = False
        return False

    if names_match(app_name, doc_name):
        output_data["name_match"] = True
        output_data["name_mismatch"] = False
        return False

    reason = name_mismatch_reason(agent_label, app_name, doc_name)
    decision = result.setdefault("decision", {})
    prior = (decision.get("reasoning") or "").strip()
    if reason.lower() not in prior.lower():
        decision["reasoning"] = f"{prior}\n\n{reason}".strip() if prior else reason

    output_data["name_match"] = False
    output_data["name_mismatch"] = True
    output_data["name_mismatch_reason"] = reason
    return True
