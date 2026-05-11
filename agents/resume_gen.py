import uuid
from pathlib import Path
from typing import Optional
from uuid import UUID

from ai.router import AIRouter
from agents.job_parser import ParsedJob
from agents.memory import MemoryAgent
from resume.ats_optimizer import ATSOptimizer
from resume.latex_renderer import LaTeXRenderer
from resume.validator import validate_pdf
from db.database import get_db_session
from db.models import TailoredResume
from config.settings import get_settings
from config.logging import get_logger

logger = get_logger(__name__)


class ResumeGenerationAgent:
    def __init__(self, ai_router: AIRouter, memory_agent: MemoryAgent):
        self.ai = ai_router
        self.memory = memory_agent
        self.optimizer = ATSOptimizer(ai_router)
        self.renderer = LaTeXRenderer()
        self.settings = get_settings()

    async def generate_tailored_resume(
        self,
        user_id: UUID,
        parsed_job: ParsedJob,
        application_id: Optional[UUID] = None,
    ) -> Optional[str]:
        """
        Generate a new ATS-optimized resume tailored to the job description.
        Returns path to the compiled PDF or None on failure.
        """
        profile = await self.memory.get_profile(user_id)
        if not profile:
            logger.error("no_profile_for_resume", user_id=str(user_id))
            return None

        # Optimize profile for this specific JD
        optimized = await self.optimizer.optimize(profile, parsed_job.raw_description)

        # Build render context
        context = {
            "full_name": profile.get("full_name", ""),
            "email": profile.get("email", ""),
            "phone": profile.get("phone", ""),
            "location": profile.get("location", ""),
            "linkedin_url": profile.get("linkedin_url", ""),
            "github_url": profile.get("github_url", ""),
            "portfolio_url": profile.get("portfolio_url", ""),
            "optimized_summary": optimized.get("optimized_summary", ""),
            "skill_order": optimized.get("skill_order", []),
            "optimized_experience": optimized.get("optimized_experience", []),
            "education": profile.get("education", []),
            "certifications": profile.get("certifications", []),
        }

        # Render LaTeX
        try:
            latex_source = self.renderer.render_latex("base.tex.j2", context)
        except Exception as e:
            logger.error("latex_render_failed", error=str(e))
            return None

        # Compile PDF
        output_dir = Path(self.settings.storage_local_path) / "resumes" / str(user_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = str(output_dir / f"tailored_{uuid.uuid4().hex[:8]}.pdf")

        success = self.renderer.compile_to_pdf(latex_source, pdf_path)

        if not success:
            logger.error("pdf_compile_failed", user_id=str(user_id))
            # Try fallback: plain text resume as PDF via reportlab
            pdf_path = await self._generate_fallback_pdf(context, output_dir)
            if not pdf_path:
                return None

        # Validate PDF
        is_valid, reason = validate_pdf(pdf_path)
        if not is_valid:
            logger.error("pdf_validation_failed", reason=reason)
            return None

        # Save to DB
        await self._save_tailored_resume(
            user_id=user_id,
            application_id=application_id,
            parsed_job=parsed_job,
            optimized=optimized,
            context=context,
            latex_source=latex_source,
            pdf_path=pdf_path,
        )

        logger.info("tailored_resume_generated", pdf_path=pdf_path, ats_score=optimized.get("ats_score"))
        return pdf_path

    async def _generate_fallback_pdf(self, context: dict, output_dir: Path) -> Optional[str]:
        """Generate a simple PDF using reportlab if LaTeX fails."""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.units import inch

            pdf_path = str(output_dir / f"fallback_{uuid.uuid4().hex[:8]}.pdf")
            doc = SimpleDocTemplate(pdf_path, pagesize=letter)
            styles = getSampleStyleSheet()
            story = []

            story.append(Paragraph(context.get("full_name", ""), styles["Title"]))
            contact = " | ".join(filter(None, [
                context.get("email", ""),
                context.get("phone", ""),
                context.get("location", ""),
            ]))
            story.append(Paragraph(contact, styles["Normal"]))
            story.append(Spacer(1, 0.2 * inch))

            if context.get("optimized_summary"):
                story.append(Paragraph("Summary", styles["Heading2"]))
                story.append(Paragraph(context["optimized_summary"], styles["Normal"]))
                story.append(Spacer(1, 0.1 * inch))

            if context.get("skill_order"):
                story.append(Paragraph("Skills", styles["Heading2"]))
                story.append(Paragraph(", ".join(context["skill_order"]), styles["Normal"]))
                story.append(Spacer(1, 0.1 * inch))

            if context.get("optimized_experience"):
                story.append(Paragraph("Experience", styles["Heading2"]))
                for exp in context["optimized_experience"]:
                    story.append(Paragraph(
                        f"<b>{exp.get('title', '')}</b> at {exp.get('company', '')} — {exp.get('dates', '')}",
                        styles["Normal"]
                    ))
                    for bullet in exp.get("bullets", []):
                        story.append(Paragraph(f"• {bullet}", styles["Normal"]))
                    story.append(Spacer(1, 0.05 * inch))

            doc.build(story)
            logger.info("fallback_pdf_generated", path=pdf_path)
            return pdf_path
        except Exception as e:
            logger.error("fallback_pdf_failed", error=str(e))
            return None

    async def _save_tailored_resume(
        self, user_id, application_id, parsed_job, optimized, context, latex_source, pdf_path
    ) -> None:
        from sqlalchemy import select
        async with get_db_session() as session:
            record = TailoredResume(
                user_id=user_id,
                application_id=application_id,
                job_description=parsed_job.raw_description,
                extracted_keywords=optimized.get("extracted_keywords", []),
                ats_score=optimized.get("ats_score", 0),
                content_json=context,
                latex_source=latex_source,
                pdf_path=pdf_path,
            )
            session.add(record)
