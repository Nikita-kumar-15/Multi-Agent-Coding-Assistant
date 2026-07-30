# backend/services/file_parser.py
"""
Extracts plain text from various uploaded file formats so that
they can be chunked and embedded into the vector store.
"""

import os
from pypdf import PdfReader
from docx import Document as DocxDocument

TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".java", ".c", ".cpp", ".md", ".txt",
    ".csv", ".json", ".html", ".css",
}


def extract_text(file_path: str) -> str:
    """
    Reads a file and returns its text content based on extension.
    Returns an empty string for unsupported/binary formats (e.g. images).
    """
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == ".pdf":
            return _extract_pdf(file_path)
        elif ext == ".docx":
            return _extract_docx(file_path)
        elif ext in TEXT_EXTENSIONS:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        else:
            # images and other binary formats are skipped for text extraction
            return ""
    except Exception as e:
        return f"[ERROR reading {file_path}: {e}]"


def _extract_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(file_path: str) -> str:
    doc = DocxDocument(file_path)
    return "\n".join(para.text for para in doc.paragraphs)