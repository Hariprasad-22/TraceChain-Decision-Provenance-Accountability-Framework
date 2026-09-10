"""
PII masking for TraceChain's stored/displayed output.

Agents always reason over REAL, unmasked data internally - guardrails,
name/DOB matching, and LLM reasoning all need the actual values to verify
anything. Masking is applied only to what gets permanently STORED (in
AGENT_EXECUTIONS.input_data and PROVENANCE_RECORDS.input_data) and
DISPLAYED - so even if the audit log itself were ever exposed, it never
contained raw PII in the first place.

Aadhaar masking format matches UIDAI's own convention (see
uidai_ekyc_guidelines.md, Section 1.2): first 8 digits masked, last 4
digits visible.
"""


def mask_aadhaar_number(number: str) -> str:
    if not number or len(number) < 4:
        return "xxxx-xxxx-xxxx"
    last4 = number[-4:]
    return f"xxxx-xxxx-{last4}"


def mask_dob(dob: str) -> str:
    """Keeps only the birth year - e.g. '1980-03-25' -> '1980-XX-XX'.
    Enough for an age-band audit view, without exposing the exact date."""
    if not dob or len(dob) < 4:
        return "XXXX-XX-XX"
    year = dob[:4]
    return f"{year}-XX-XX"


def mask_address(address: str) -> str:
    """Keeps only the last comma-separated segment (city/pincode),
    redacts the rest (house number, street, locality)."""
    if not address:
        return "[REDACTED]"
    parts = [p.strip() for p in address.split(",")]
    if len(parts) <= 1:
        return "[REDACTED]"
    return f"[REDACTED], {parts[-1]}"


def mask_extracted_fields(extracted: dict) -> dict:
    """Returns a masked copy for storage/display. Name is kept - an audit
    record needs to identify WHOSE decision this was - but the direct
    identifiers (Aadhaar number, DOB, address) are masked."""
    masked = dict(extracted)
    if masked.get("aadhaar_number"):
        masked["aadhaar_number"] = mask_aadhaar_number(masked["aadhaar_number"])
    if masked.get("dob"):
        masked["dob"] = mask_dob(masked["dob"])
    if masked.get("address"):
        masked["address"] = mask_address(masked["address"])
    return masked


def scrub_text(text: str, raw_extracted: dict) -> str:
    """Safety net: if free-text reasoning (from the LLM, or a guardrail's
    own error message) happens to restate a raw sensitive value verbatim,
    replace it with its masked form before the text is stored/displayed."""
    if not text:
        return text
    scrubbed = text

    number = raw_extracted.get("aadhaar_number")
    if number:
        scrubbed = scrubbed.replace(number, mask_aadhaar_number(number))
        if len(number) == 12:
            spaced = f"{number[0:4]} {number[4:8]} {number[8:12]}"
            scrubbed = scrubbed.replace(spaced, mask_aadhaar_number(number))

    dob = raw_extracted.get("dob")
    if dob:
        scrubbed = scrubbed.replace(dob, mask_dob(dob))

    address = raw_extracted.get("address")
    if address:
        scrubbed = scrubbed.replace(address, mask_address(address))

    return scrubbed
