import os
from config.logging import get_logger

logger = get_logger(__name__)


def validate_pdf(pdf_path: str) -> tuple[bool, str]:
    """
    Validate that a PDF file exists, is non-empty, and is a valid PDF.
    Returns (is_valid, reason).
    """
    if not os.path.exists(pdf_path):
        return False, "file_not_found"

    if os.path.getsize(pdf_path) < 1000:  # < 1KB is almost certainly invalid
        return False, "file_too_small"

    try:
        with open(pdf_path, "rb") as f:
            header = f.read(5)
            if not header.startswith(b"%PDF-"):
                return False, "not_a_pdf"

        # Try parsing with pypdf
        try:
            from pypdf import PdfReader
            reader = PdfReader(pdf_path)
            if len(reader.pages) == 0:
                return False, "no_pages"
            # Check text is extractable (ATS-readable)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            if len(text.strip()) < 100:
                return False, "not_ats_readable"
        except Exception as e:
            logger.warning("pdf_parse_error", error=str(e))
            return False, f"parse_error: {e}"

        return True, "ok"
    except Exception as e:
        return False, f"validation_error: {e}"
