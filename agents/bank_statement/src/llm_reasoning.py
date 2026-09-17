from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from google import genai
except ImportError:  # pragma: no cover
    genai = None


def _load_api_key_from_env_file() -> str | None:
    """Load a local .env file if present in the project root."""

    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return None

    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in {"GEMINI_API_KEY", "GOOGLE_API_KEY"} and value:
                os.environ[key] = value
                return value
    except OSError:
        return None

    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def build_llm_prompt(result: dict[str, Any]) -> str:
    """Build a dynamic prompt for Gemini based on each financial result."""

    decision = result["decision"]
    health = result["financial_health"]
    flags = result["risk_flags"]
    metrics = result["financial_metrics"]

    if health == "HEALTHY":
        tone = "Explain why this profile is strong, stable, and low risk."
    elif health == "MODERATE_RISK":
        tone = (
            "Explain the tradeoff and why this is a borderline profile with "
            "some risk indicators but still not a severe default case."
        )
    else:
        tone = "Explain the main concerns and why this is a high-risk profile."

    return f"""
    You are a financial analyst explaining a bank statement review.

    Decision: {decision}
    Financial health: {health}
    Risk flags: {flags}

    Financial metrics:
    - Average monthly income: ₹{metrics['average_monthly_income']:.2f}
    - Average monthly expense: ₹{metrics['average_monthly_expense']:.2f}
    - Average monthly EMI: ₹{metrics['average_monthly_emi']:.2f}
    - Average monthly surplus: ₹{metrics['average_monthly_surplus']:.2f}
    - EMI-to-income ratio: {metrics['emi_to_income_ratio']:.2%}
    - Savings ratio: {metrics['savings_ratio']:.2%}

    Instructions:
    1. Use only the provided numbers.
    2. Do not invent facts or metrics.
    3. Keep it concise but professional.
    4. Explain the decision in plain English.
    5. Mention the main reason(s) behind the result.
    {tone}
    """.strip()


def generate_llm_reasoning(result: dict[str, Any]) -> str:
    """Generate a short human-readable explanation using Gemini."""

    api_key = _load_api_key_from_env_file() or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return (
            "LLM reasoning unavailable: no Gemini API key found. Create a .env file in the project root with "
            "GEMINI_API_KEY=your_key_here or set the environment variable before running the script."
        )

    if genai is None:
        return (
            "LLM reasoning unavailable: the required Gemini Python package is not installed. "
            "Run: py -m pip install google-genai"
        )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=build_llm_prompt(result),
        )
        return response.text
    except Exception as exc:  # pragma: no cover - network / key issues
        print("GEMINI ERROR:", repr(exc))
        return (
            "LLM reasoning unavailable: the Gemini request failed. "
            "The rule-based explanation remains the verified output."
        )

