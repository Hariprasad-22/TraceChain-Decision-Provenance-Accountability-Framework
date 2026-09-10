"""Tests for pii_masking.py - masking and text-scrubbing."""
from pii_masking import mask_aadhaar_number, mask_dob, mask_address, mask_extracted_fields, scrub_text


# --- individual maskers ---

def test_mask_aadhaar_number_keeps_last_four():
    assert mask_aadhaar_number("281948219932") == "xxxx-xxxx-9932"


def test_mask_aadhaar_number_handles_short_input():
    assert mask_aadhaar_number("12") == "xxxx-xxxx-xxxx"


def test_mask_dob_keeps_only_year():
    assert mask_dob("1980-03-25") == "1980-XX-XX"


def test_mask_address_keeps_last_segment_only():
    assert mask_address("62/52, Sama Chowk, Solapur 559797") == "[REDACTED], Solapur 559797"


def test_mask_address_single_segment_fully_redacted():
    assert mask_address("Solapur") == "[REDACTED]"


def test_mask_address_empty_input():
    assert mask_address("") == "[REDACTED]"


# --- mask_extracted_fields ---

def test_mask_extracted_fields_keeps_name_masks_rest():
    extracted = {"name": "Hemal Sen", "dob": "1980-03-25", "gender": "Female",
                 "address": "62/52, Sama Chowk, Solapur 559797", "aadhaar_number": "281948219932"}
    masked = mask_extracted_fields(extracted)

    assert masked["name"] == "Hemal Sen"  # name is NOT masked
    assert masked["aadhaar_number"] == "xxxx-xxxx-9932"
    assert masked["dob"] == "1980-XX-XX"
    assert masked["address"] == "[REDACTED], Solapur 559797"


def test_mask_extracted_fields_does_not_mutate_original():
    extracted = {"name": "Hemal Sen", "aadhaar_number": "281948219932"}
    mask_extracted_fields(extracted)
    assert extracted["aadhaar_number"] == "281948219932"  # original untouched


# --- scrub_text ---

def test_scrub_removes_raw_aadhaar_number():
    extracted = {"aadhaar_number": "281948219932"}
    text = "The Aadhaar number 281948219932 was verified."
    assert "281948219932" not in scrub_text(text, extracted)


def test_scrub_removes_spaced_aadhaar_number():
    extracted = {"aadhaar_number": "281948219932"}
    text = "Number: 2819 4821 9932 confirmed."
    scrubbed = scrub_text(text, extracted)
    assert "2819 4821 9932" not in scrubbed


def test_scrub_removes_raw_dob():
    extracted = {"dob": "1980-03-25"}
    text = "DOB 1980-03-25 matches records."
    assert "1980-03-25" not in scrub_text(text, extracted)


def test_scrub_removes_raw_address():
    extracted = {"address": "62/52, Sama Chowk, Solapur 559797"}
    text = "Address 62/52, Sama Chowk, Solapur 559797 confirmed."
    assert "Sama Chowk" not in scrub_text(text, extracted)


def test_scrub_handles_empty_text():
    assert scrub_text("", {"aadhaar_number": "281948219932"}) == ""


def test_scrub_leaves_unrelated_text_untouched():
    extracted = {"aadhaar_number": "281948219932"}
    text = "Name matches, no concerns flagged."
    assert scrub_text(text, extracted) == text
