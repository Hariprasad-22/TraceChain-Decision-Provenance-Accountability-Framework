"""
Extracts structured fields (name, DOB, gender, address, Aadhaar number)
from an Aadhaar card image using Gemini's vision capability.
"""
from llm_client import call_vision_llm

EXTRACTION_PROMPT = """You are extracting fields from an Indian Aadhaar card image.
Return ONLY valid JSON, no markdown fences, with this exact shape:
{"name": str, "dob": "YYYY-MM-DD", "gender": str, "address": str, "aadhaar_number": "12 digits, no spaces"}
If a field is unreadable, use null for that field."""


def extract_aadhaar_fields(image_path: str) -> dict:
    return call_vision_llm(EXTRACTION_PROMPT, image_path)
