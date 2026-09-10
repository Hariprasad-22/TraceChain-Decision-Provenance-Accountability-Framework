"""
Gemini client for the loan-approval agents, using the current `google-genai`
SDK (the old `google.generativeai` package is deprecated as of Aug 2025).
Requires GOOGLE_API_KEY to be set.
"""
import os
import json

from google import genai
from google.genai import types

import logging
logging.getLogger("google_genai").setLevel(logging.ERROR)  # silence the harmless AFC notice

API_KEY = os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "GOOGLE_API_KEY is not set. Get a free key at aistudio.google.com "
        "and run: $env:GOOGLE_API_KEY=\"your-key-here\"  (PowerShell)"
    )

_client = genai.Client(api_key=API_KEY)
# Configurable via env var so you can switch models without editing code -
# Google's newest flagship models (like 3.6/3.7-flash) launch with much
# tighter free-tier daily quotas than established models. If you hit a 429
# RESOURCE_EXHAUSTED error, try: $env:GEMINI_MODEL="gemini-3.5-flash"
# (PowerShell) and re-run, without touching this file.
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")


def call_agent_llm(system_prompt: str, user_prompt: str) -> dict:
    """Returns a parsed JSON dict with decision_output, confidence_score,
    reasoning, and risk_factors."""
    full_prompt = (
        f"{system_prompt}\n\n{user_prompt}\n\n"
        "Respond with ONLY valid JSON matching this shape, no markdown fences: "
        '{"decision_output": str, "confidence_score": float (0-1), '
        '"reasoning": str, "risk_factors": {"irreversibility": int (0-10), '
        '"impact": int (0-10), "explainability": int (0-10)}}'
    )
    response = _client.models.generate_content(
        model=MODEL,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    return json.loads(response.text)


def call_vision_llm(prompt: str, image_path: str) -> dict:
    """Multimodal call: reads an image (e.g. an Aadhaar card) and extracts
    structured fields as JSON."""
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    mime_type = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
    full_prompt = f"{prompt}\n\nRespond with ONLY valid JSON, no markdown fences."

    response = _client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            full_prompt,
        ],
        config=types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )
    return json.loads(response.text)


def embed_text(text: str) -> list:
    """Returns a Gemini embedding vector for retrieval."""
    response = _client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
    )
    return response.embeddings[0].values
