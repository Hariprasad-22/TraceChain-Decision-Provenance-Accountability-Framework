"""Tests for guardrails.py - hard validation and scoped permissions."""
from datetime import date, timedelta

import pytest

from guardrails import (
    validate_aadhaar_format, validate_age, name_similarity, dob_matches,
    scope_for_aadhar_agent, ValidationError,
)


# --- validate_aadhaar_format ---

def test_valid_aadhaar_format_passes():
    assert validate_aadhaar_format("260181590833") is True


def test_invalid_checksum_raises():
    with pytest.raises(ValidationError):
        validate_aadhaar_format("260181590834")


def test_missing_aadhaar_number_raises():
    with pytest.raises(ValidationError):
        validate_aadhaar_format(None)


# --- validate_age ---

def test_adult_passes():
    dob = (date.today() - timedelta(days=365 * 25)).isoformat()
    assert validate_age(dob) is True


def test_minor_raises():
    dob = (date.today() - timedelta(days=365 * 10)).isoformat()
    with pytest.raises(ValidationError):
        validate_age(dob)


def test_unparseable_dob_raises():
    with pytest.raises(ValidationError):
        validate_age("not-a-date")


def test_exactly_18_passes():
    # boundary case - turned 18 a week ago
    dob = (date.today().replace(year=date.today().year - 18) - timedelta(days=7)).isoformat()
    assert validate_age(dob) is True


# --- name_similarity ---

def test_identical_names_full_similarity():
    assert name_similarity("Hemal Sen", "Hemal Sen") == 1.0


def test_case_insensitive_match():
    assert name_similarity("HEMAL SEN", "hemal sen") == 1.0


def test_completely_different_names_low_similarity():
    assert name_similarity("Hemal Sen", "sri") < 0.5


def test_minor_spelling_variant_high_similarity():
    # small transliteration-style difference should still score high
    assert name_similarity("Mohammed Khan", "Mohammad Khan") > 0.85


# --- dob_matches ---

def test_matching_dob():
    assert dob_matches("1991-11-19", "1991-11-19") is True


def test_mismatched_dob():
    assert dob_matches("1991-11-19", "1990-01-01") is False


def test_dob_matches_handles_none():
    assert dob_matches(None, "1991-11-19") is False


# --- scope_for_aadhar_agent ---

def test_scope_extracts_only_permitted_fields():
    state = {
        "application_id": "APP-001",
        "loan_amount": 150000,
        "applicant_name": "Hemal Sen",
        "applicant_dob": "1980-03-25",
        "applicant_data": {"aadhar_image_path": "some/path.png", "credit_bureau_record": {"score": 780}},
    }
    scoped = scope_for_aadhar_agent(state)

    assert scoped["applicant_name"] == "Hemal Sen"
    assert scoped["aadhar_image_path"] == "some/path.png"
    # Scoped permissions: must NOT leak fields belonging to other agents
    assert "credit_bureau_record" not in scoped
