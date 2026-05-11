import re
from typing import Optional


def extract_confidence_from_text(text: str) -> float:
    """
    Try to parse a confidence score from AI output.
    AI is prompted to return JSON with a 'confidence' field.
    Fall back to heuristic scoring.
    """
    import json
    try:
        # Try to find JSON block in output
        json_match = re.search(r"\{.*?\}", text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            conf = data.get("confidence", None)
            if conf is not None:
                return float(conf)
    except (json.JSONDecodeError, ValueError):
        pass

    # Heuristic fallback: look for explicit confidence phrase
    match = re.search(r"confidence[:\s]+([0-9.]+)", text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass

    # Default moderate confidence if none found
    return 0.65


def classify_question(question: str, answer: str, confidence: float) -> str:
    """Classify a question-answer pair for escalation logic."""
    question_lower = question.lower()

    risky_keywords = [
        "salary", "compensation", "notice period", "start date",
        "authorize", "authorized", "sponsor", "visa", "relocate",
        "criminal", "felony", "disability", "veteran",
        "equity", "bonus", "expected", "require",
    ]
    for kw in risky_keywords:
        if kw in question_lower:
            if confidence < 0.85:
                return "risky"
            return "inferable"

    if confidence >= 0.90:
        return "deterministic"
    elif confidence >= 0.75:
        return "inferable"
    elif confidence >= 0.50:
        return "risky"
    else:
        return "impossible"


def needs_escalation(classification: str, confidence: float, threshold: float = 0.75) -> bool:
    if classification == "impossible":
        return True
    if classification == "risky" and confidence < threshold:
        return True
    return False
