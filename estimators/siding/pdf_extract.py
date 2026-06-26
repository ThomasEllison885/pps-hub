"""Extract plain text from PDF bytes (Poppler preferred, pypdf fallback)."""
import os
import subprocess
import tempfile


def extract_pdf_text(pdf_bytes):
    """Return extracted text from a PDF."""
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        f.write(pdf_bytes)
        tmp_path = f.name
    try:
        try:
            result = subprocess.run(
                ['pdftotext', '-layout', tmp_path, '-'],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        try:
            from pypdf import PdfReader
            reader = PdfReader(tmp_path)
            parts = []
            for page in reader.pages:
                parts.append(page.extract_text() or '')
            text = '\n'.join(parts)
            if text.strip():
                return text
        except Exception:
            pass

        raise RuntimeError(
            'Could not read PDF. Upload field measurements instead, or ensure the report is a text-based PDF.'
        )
    finally:
        os.unlink(tmp_path)