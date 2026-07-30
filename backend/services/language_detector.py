# backend/services/language_detector.py
"""
Detects programming language from file extension.
Simple and reliable for the supported language set.
"""

EXTENSION_LANGUAGE_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".h": "C/C++ Header",
}


def detect_language(filename: str) -> str:
    """Returns the detected language name, or 'Unknown' if unsupported."""
    import os
    ext = os.path.splitext(filename)[1].lower()
    return EXTENSION_LANGUAGE_MAP.get(ext, "Unknown")