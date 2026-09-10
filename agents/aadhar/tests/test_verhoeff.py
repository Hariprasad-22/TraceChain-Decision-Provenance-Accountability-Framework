"""Tests for verhoeff.py - the Aadhaar checksum algorithm."""
from verhoeff import is_valid_aadhaar_checksum, verhoeff_checksum_digit


def test_valid_checksum_accepted():
    # 260181590833 is a known Verhoeff-valid number from our own generator
    assert is_valid_aadhaar_checksum("260181590833") is True


def test_corrupted_last_digit_rejected():
    # Same number with the last digit changed - must fail
    assert is_valid_aadhaar_checksum("260181590834") is False


def test_corrupted_middle_digit_rejected():
    assert is_valid_aadhaar_checksum("260181590833".replace("1", "9", 1)) is False


def test_wrong_length_rejected():
    assert is_valid_aadhaar_checksum("12345") is False
    assert is_valid_aadhaar_checksum("1234567890123") is False


def test_non_digit_string_rejected():
    assert is_valid_aadhaar_checksum("26018159083x") is False


def test_empty_or_none_rejected():
    assert is_valid_aadhaar_checksum("") is False
    assert is_valid_aadhaar_checksum(None) is False


def test_generated_checksum_digit_is_self_consistent():
    # Generating a checksum digit for a prefix should produce a number
    # that is_valid_aadhaar_checksum() itself accepts as valid.
    prefix = "12345678901"
    digit = verhoeff_checksum_digit(prefix)
    assert is_valid_aadhaar_checksum(prefix + str(digit)) is True
