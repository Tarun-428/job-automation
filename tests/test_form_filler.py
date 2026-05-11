import pytest
from agents.form_fill import FormFillerAgent


def test_normalize_typo_immediate():
    result = FormFillerAgent._normalize_user_input("immedite")
    assert result == "Immediate"


def test_normalize_clean_input():
    result = FormFillerAgent._normalize_user_input("  Python Developer  ")
    assert result == "Python Developer"


def test_normalize_skip_unknown():
    result = FormFillerAgent._normalize_user_input("Some random answer")
    assert result == "Some random answer"
