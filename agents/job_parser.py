import json
import re
from dataclasses import dataclass, field
from typing import Optional, List

from ai.router import AIRouter
from ai.prompts.resume_gen import JOB_PARSE_SYSTEM, build_job_parse_prompt
from config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ParsedJob:
    job_title: str = ""
    company: str = ""
    location: str = ""
    job_type: str = "full-time"
    remote: bool = False
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    required_skills: List[str] = field(default_factory=list)
    preferred_skills: List[str] = field(default_factory=list)
    required_experience_years: Optional[int] = None
    education_required: str = ""
    responsibilities: List[str] = field(default_factory=list)
    benefits: List[str] = field(default_factory=list)
    platform: str = ""
    raw_description: str = ""
    confidence: float = 0.0


class JobParserAgent:
    def __init__(self, ai_router: AIRouter):
        self.ai = ai_router

    async def parse_job_description(self, raw_text: str, url: str = "") -> ParsedJob:
        prompt = build_job_parse_prompt(raw_text)
        result = await self.ai.generate(prompt, system=JOB_PARSE_SYSTEM)

        if not result.success:
            logger.warning("job_parse_failed", url=url)
            return ParsedJob(raw_description=raw_text)

        return self._parse_result(result.text, raw_text)

    def _parse_result(self, text: str, raw_description: str) -> ParsedJob:
        try:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return ParsedJob(
                    job_title=data.get("job_title", ""),
                    company=data.get("company", ""),
                    location=data.get("location", ""),
                    job_type=data.get("job_type", "full-time"),
                    remote=bool(data.get("remote", False)),
                    salary_min=data.get("salary_min"),
                    salary_max=data.get("salary_max"),
                    required_skills=data.get("required_skills", []),
                    preferred_skills=data.get("preferred_skills", []),
                    required_experience_years=data.get("required_experience_years"),
                    education_required=data.get("education_required", ""),
                    responsibilities=data.get("responsibilities", []),
                    benefits=data.get("benefits", []),
                    platform=data.get("platform", ""),
                    raw_description=raw_description,
                    confidence=float(data.get("confidence", 0.5)),
                )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("job_parse_json_error", error=str(e))
        return ParsedJob(raw_description=raw_description, confidence=0.3)

    def detect_platform(self, url: str) -> str:
        url_lower = url.lower()
        platforms = {
            "linkedin.com": "linkedin",
            "indeed.com": "indeed",
            "glassdoor.com": "glassdoor",
            "naukri.com": "naukri",
            "wellfound.com": "wellfound",
            "angel.co": "wellfound",
            "instahyre.com": "instahyre",
            "greenhouse.io": "greenhouse",
            "lever.co": "lever",
            "ashby.io": "ashby",
            "workday.com": "workday",
            "taleo.net": "taleo",
            "successfactors.com": "sap",
        }
        for domain, platform in platforms.items():
            if domain in url_lower:
                return platform
        return "custom"
