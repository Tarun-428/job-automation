import json
import re
from typing import Optional

from ai.router import AIRouter
from ai.prompts.resume_gen import RESUME_GEN_SYSTEM, build_ats_optimization_prompt
from config.logging import get_logger

logger = get_logger(__name__)


class ATSOptimizer:
    def __init__(self, ai_router: AIRouter):
        self.ai = ai_router

    async def optimize(self, profile: dict, job_description: str) -> dict:
        """
        Rewrite and optimize resume content for a specific JD.
        Returns optimized resume content dict.
        """
        prompt = build_ats_optimization_prompt(profile, job_description)
        result = await self.ai.generate(prompt, system=RESUME_GEN_SYSTEM)

        if not result.success:
            logger.warning("ats_optimization_failed")
            return self._fallback_optimization(profile)

        try:
            match = re.search(r"\{.*\}", result.text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return {
                    "ats_score": data.get("ats_score", 70),
                    "extracted_keywords": data.get("extracted_keywords", []),
                    "optimized_summary": data.get("optimized_summary", profile.get("summary", "")),
                    "optimized_experience": data.get("optimized_experience", profile.get("experience", [])),
                    "skill_order": data.get("skill_order", list(profile.get("skills", {}).keys())),
                    "confidence": float(data.get("confidence", 0.7)),
                }
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("ats_parse_error", error=str(e))

        return self._fallback_optimization(profile)

    def _fallback_optimization(self, profile: dict) -> dict:
        return {
            "ats_score": 60,
            "extracted_keywords": [],
            "optimized_summary": profile.get("summary", ""),
            "optimized_experience": profile.get("experience", []),
            "skill_order": list(profile.get("skills", {}).keys()),
            "confidence": 0.5,
        }
