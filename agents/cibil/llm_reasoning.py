import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
        _client = genai.Client(api_key=api_key)
        return _client
    except Exception as exc:
        logging.warning("Could not initialize CIBIL genai Client: %s", exc)
        return None


# Fixed, deterministic mapping — irreversibility and impact depend ONLY on
# which decision_output was made, never on free LLM judgment. This keeps
# risk severity consistent: a "verified" case can never score riskier than
# a "needs_review" or "high_risk" case.
RISK_FACTOR_MAP = {
    "verified":         {"irreversibility": 2, "impact": 3},
    "needs_review":     {"irreversibility": 4, "impact": 5},
    "high_risk":        {"irreversibility": 6, "impact": 7},
    "high_risk_auto":   {"irreversibility": 8, "impact": 9},
    "invalid_score":    {"irreversibility": 1, "impact": 2},
    "missing_data":     {"irreversibility": 1, "impact": 2},
    "stale_report":     {"irreversibility": 1, "impact": 2},
    "insufficient_history": {"irreversibility": 2, "impact": 3},
    "agent_error":      {"irreversibility": 0, "impact": 0},
}


def generate_reasoning(score, utilization_pct, decision_output, similar_cases):
    fixed_factors = RISK_FACTOR_MAP.get(decision_output, {"irreversibility": 5, "impact": 5})

    client = get_client()
    if client is not None:
        try:
            precedent_text = f"Similar past cases: {similar_cases}" if similar_cases else "No similar past cases found."
            prompt = f"""You are explaining a credit risk decision for a loan application.

Rule engine decision (FIXED — do not change this): {decision_output}
CIBIL score: {score}
Credit utilization: {utilization_pct}%
{precedent_text}

Return ONLY valid JSON, no other text, in this exact shape:
{{
  "reasoning": "2-3 sentence plain-language explanation",
  "explainability": <int 0-10, how clearly this decision can be justified from the score/utilization/precedent alone>
}}"""
            response = client.models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                contents=prompt,
            )
            text = response.text.strip().replace("```json", "").replace("```", "").strip()
            llm_output = json.loads(text)
            explainability = int(llm_output.get("explainability", 9))
            reasoning = llm_output.get("reasoning", "")
            return {
                "reasoning": reasoning,
                "risk_factors": {
                    "irreversibility": fixed_factors["irreversibility"],
                    "impact": fixed_factors["impact"],
                    "explainability": explainability,
                }
            }
        except Exception as exc:
            logging.warning("CIBIL LLM reasoning call failed: %s", exc)

    # Fallback reasoning if API key is not present or API call fails
    reasoning = (
        f"Applicant CIBIL score is {score} with {utilization_pct:.1f}% credit utilization. "
        f"Rule engine evaluated risk tier as {decision_output.upper()}."
    )
    return {
        "reasoning": reasoning,
        "risk_factors": {
            "irreversibility": fixed_factors["irreversibility"],
            "impact": fixed_factors["impact"],
            "explainability": 9,
        }
    }