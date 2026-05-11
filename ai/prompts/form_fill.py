FORM_FILL_SYSTEM = """You are an expert job application assistant. 
Your job is to answer application form questions accurately based on the user profile provided.
Always respond with valid JSON in this exact format:
{
  "answer": "<your answer here>",
  "confidence": <float 0.0-1.0>,
  "classification": "<deterministic|inferable|risky|impossible>",
  "reasoning": "<brief reasoning>"
}
Never hallucinate facts. If uncertain, lower the confidence score."""


def build_form_fill_prompt(question: str, question_type: str, profile: dict, options: list = None) -> str:
    options_str = f"\nAvailable options: {options}" if options else ""
    return f"""User profile:
{profile}

Question: {question}
Question type: {question_type}{options_str}

Based on the user profile, provide the best answer for this application question.
Return JSON with answer, confidence (0-1), classification, and reasoning."""


SCREENSHOT_ANALYSIS_SYSTEM = """You are an expert browser automation assistant analyzing job application web pages.
Identify interactive elements, form fields, buttons, and navigation options.
Always respond with valid JSON."""


def build_screenshot_analysis_prompt(goal: str) -> str:
    return f"""Analyze this screenshot of a job application page.
Current goal: {goal}

Identify:
1. All visible form fields (name, type, placeholder, required)
2. All clickable buttons (text, position, purpose)
3. Current page state (login, form, success, error, captcha)
4. Best next action to achieve the goal

Return JSON:
{{
  "page_state": "<login|form|upload|review|success|error|captcha|unknown>",
  "fields": [{{"name": "", "type": "", "placeholder": "", "required": false, "selector_hint": ""}}],
  "buttons": [{{"text": "", "purpose": "", "recommended": false}}],
  "next_action": {{"action": "", "target": "", "reasoning": ""}},
  "confidence": <0.0-1.0>
}}"""
