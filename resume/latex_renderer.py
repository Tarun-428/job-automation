import os
import subprocess
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config.settings import get_settings
from config.logging import get_logger

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


class LaTeXRenderer:
    def __init__(self):
        self.settings = get_settings()
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render_latex(self, template_name: str, context: dict) -> str:
        """Render a Jinja2 LaTeX template with the given context."""
        template = self.env.get_template(template_name)
        return template.render(**context)

    def compile_to_pdf(self, latex_source: str, output_path: str) -> bool:
        """
        Compile LaTeX source to PDF.
        Tries tectonic first, falls back to pdflatex.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_file = os.path.join(tmpdir, "resume.tex")
            with open(tex_file, "w", encoding="utf-8") as f:
                f.write(latex_source)

            success = False
            if self.settings.latex_engine == "tectonic":
                success = self._compile_tectonic(tex_file, output_path)
            if not success:
                success = self._compile_pdflatex(tex_file, tmpdir, output_path)

            return success

    def _compile_tectonic(self, tex_file: str, output_path: str) -> bool:
        try:
            result = subprocess.run(
                ["tectonic", "--outfmt", "pdf", "--outdir", os.path.dirname(output_path), tex_file],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                # Tectonic outputs to same dir as tex file; rename if needed
                expected = os.path.join(
                    os.path.dirname(output_path),
                    os.path.splitext(os.path.basename(tex_file))[0] + ".pdf",
                )
                if os.path.exists(expected) and expected != output_path:
                    os.rename(expected, output_path)
                return os.path.exists(output_path)
            logger.warning("tectonic_failed", stderr=result.stderr[:500])
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("tectonic_not_available", error=str(e))
            return False

    def _compile_pdflatex(self, tex_file: str, tmpdir: str, output_path: str) -> bool:
        try:
            for _ in range(2):  # Run twice for references
                result = subprocess.run(
                    [
                        "pdflatex",
                        "-interaction=nonstopmode",
                        "-output-directory", tmpdir,
                        tex_file,
                    ],
                    capture_output=True, text=True, timeout=60,
                )

            pdf_file = os.path.join(tmpdir, "resume.pdf")
            if os.path.exists(pdf_file):
                import shutil
                shutil.copy2(pdf_file, output_path)
                return True
            logger.warning("pdflatex_no_output", stderr=result.stderr[:500])
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("pdflatex_not_available", error=str(e))
            return False
