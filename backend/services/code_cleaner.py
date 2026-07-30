# backend/services/code_cleaner.py
"""
Strips markdown code fences (```python ... ```) from LLM output
so that the raw code can be safely written to a file and executed.
"""

import re


def extract_code(raw_text: str) -> str:
    """
    Extracts pure code from LLM output that may be wrapped in
    markdown code fences. If no fences are found, returns the
    original text stripped of leading/trailing whitespace.
    """
    # Match ```python ... ``` or ``` ... ```
    match = re.search(r"```(?:python)?\s*\n(.*?)```", raw_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw_text.strip()