RESUME_GEN_SYSTEM = """You are an expert ATS resume optimizer and technical writer.
You create tailored, keyword-optimized resumes that pass ATS systems and impress human reviewers.
Always respond with valid JSON matching the provided schema."""


def build_ats_optimization_prompt(profile: dict, job_description: str) -> str:
    return f"""User profile:
{profile}

Job Description:
{job_description}

Analyze the job description and optimize the user's resume for ATS.
Tasks:
1. Extract all important keywords and skills from JD
2. Rewrite experience bullets to match JD language
3. Reorder skills to match JD priority
4. Optimize the summary for this specific role
5. Calculate ATS compatibility score

Return JSON:
{{
  "ats_score": <0-100>,
  "extracted_keywords": ["keyword1", "keyword2"],
  "optimized_summary": "...",
  "optimized_experience": [
    {{
      "company": "",
      "title": "",
      "dates": "",
      "bullets": ["optimized bullet 1", "..."]
    }}
  ],
  "skill_order": ["skill1", "skill2"],
  "confidence": <0.0-1.0>
}}"""


JOB_PARSE_SYSTEM = """You are an expert job description parser.
Extract structured information from job postings accurately.
Always respond with valid JSON."""


def build_job_parse_prompt(raw_text: str) -> str:
    return f"""Parse this job description and extract structured information:

{raw_text}

Return JSON:
{{
  "job_title": "",
  "company": "",
  "location": "",
  "job_type": "<full-time|part-time|contract|internship>",
  "remote": <true|false>,
  "salary_min": <null or int>,
  "salary_max": <null or int>,
  "required_skills": [],
  "preferred_skills": [],
  "required_experience_years": <null or int>,
  "education_required": "",
  "responsibilities": [],
  "benefits": [],
  "platform": "",
  "confidence": <0.0-1.0>
}}"""
