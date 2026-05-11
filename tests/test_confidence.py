import pytest
from ai.confidence import (
    extract_confidence_from_text,
    classify_question,
    needs_escalation,
)


def test_extract_confidence_from_json():
    text = '{"answer": "Python", "confidence": 0.95, "classification": "deterministic"}'
    assert extract_confidence_from_text(text) == 0.95


def test_extract_confidence_from_phrase():
    text = "Based on the profile, confidence: 0.82"
    assert extract_confidence_from_text(text) == 0.82


def test_extract_confidence_default():
    text = "The answer is Python"
    result = extract_confidence_from_text(text)
    assert 0.0 <= result <= 1.0


def test_classify_risky_question():
    cls = classify_question("What is your expected salary?", "80000", 0.7)
    assert cls == "risky"


def test_classify_deterministic():
    cls = classify_question("What is your name?", "John Doe", 0.95)
    assert cls == "deterministic"


def test_needs_escalation_impossible():
    assert needs_escalation("impossible", 0.1) is True


def test_needs_escalation_risky_low_confidence():
    assert needs_escalation("risky", 0.6) is True


def test_no_escalation_deterministic():
    assert needs_escalation("deterministic", 0.95) is False
