# backend/agents/debugger_agent.py
"""
Debugger Agent: analyzes uploaded code for syntax errors, runtime
errors, logical errors, performance issues, and security issues.
Generates a corrected version with an explanation of every change.
"""

from backend.services.agent_logger import agent_log
from backend.services.code_cleaner import extract_code
from backend.services.language_detector import detect_language
from backend.services.model_router import get_model, LLMProviderError

DEBUG_PROMPT = """You are an expert {language} developer and code reviewer.
Analyze the following code for:
1. Syntax errors
2. Runtime errors
3. Logical errors
4. Performance issues
5. Security issues

Original code:
{code}

Respond in this EXACT format:

ISSUES_FOUND:
<numbered list of every issue found, with line context. Write "None found" if clean.>

CORRECTED_CODE:
<the full corrected and optimized version of the code, wrapped in a code block>

EXPLANATION:
<numbered list explaining each modification you made and why>
"""


def _parse_debug_response(raw_response: str) -> dict:
    """Splits the LLM response into its three labeled sections."""
    sections = {"issues_found": "", "corrected_code": "", "explanation": ""}

    parts = raw_response.split("CORRECTED_CODE:")
    if len(parts) >= 2:
        sections["issues_found"] = parts[0].replace("ISSUES_FOUND:", "").strip()
        remainder = parts[1]

        explanation_parts = remainder.split("EXPLANATION:")
        sections["corrected_code"] = extract_code(explanation_parts[0].strip())
        if len(explanation_parts) >= 2:
            sections["explanation"] = explanation_parts[1].strip()
    else:
        # fallback: couldn't parse cleanly, return raw response in explanation
        sections["explanation"] = raw_response

    return sections


def debugger_agent(code: str, filename: str) -> dict:
    """
    Analyzes and fixes the given code.

    Returns:
        dict with keys: language, issues_found, corrected_code, explanation
    """
    language = detect_language(filename)

    llm = get_model("debugger")
    prompt = DEBUG_PROMPT.format(language=language, code=code)
    try:
        with agent_log(
            agent_name="Debugger Agent",
            model_name=llm.model_name,
            input_text=prompt,
            next_agent="Completed",
        ) as log:
            raw_response = llm.invoke(prompt)
            log["response"] = raw_response
            response = raw_response.content
            log["output"] = response
    except LLMProviderError as e:
        return {
            "success": False,
            "error_type": "llm_provider_error",
            "message": str(e),
        }

    parsed = _parse_debug_response(response)

    return {
        "language": language,
        "issues_found": parsed["issues_found"],
        "corrected_code": parsed["corrected_code"],
        "explanation": parsed["explanation"],
    }
