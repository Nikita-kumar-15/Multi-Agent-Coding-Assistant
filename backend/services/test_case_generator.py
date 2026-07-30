"""
Generates dedicated test cases from the final project files and user request.
"""

from backend.services.model_router import get_model
from backend.terminal.logger import tlog

TEST_CASE_PROMPT = """You are a Lead QA Engineer.
Create a dedicated test cases document for the following project.

Original Request:
{request}

Generated Code:
{code}

CRITICAL RULES:
- Examples must use REAL function names, variable names, and data structures from the actual generated code for this project. Never reuse examples from a different type of project.
- Do not include anything except test cases and the unit test table — no plan summary, no agent trace, no architecture notes.

You MUST use EXACTLY this format structure, but adapted to the real code provided:

Test Cases: [Project Name]

1. [Feature/Behavior Name]
Test Case 1
Input: [specific input/initial state relevant to THIS project]
Expected Output: [concrete expected result matching the actual project type]
Result: [one-line summary of what this proves]

2. [Next Feature/Behavior]
Test Case 2
Input: ...
Expected Output: ...

(continue numbering sequentially, covering whichever of these apply to this specific project: happy path/initialization, valid input handling, invalid input handling, boundary values, state transitions, success/completion conditions, error handling, edge cases like empty/full/max limits, reset/restart behavior, concurrent/rapid action handling — skip categories that don't apply)

Suggested Unit Tests

| Test ID | Function Tested | Expected Result |
|---|---|---|
| UT01 | [actual function/component name] | [expected behavior] |
| UT02 | ... | ... |
"""

STRICT_REMINDER = """
REMINDER: Your previous output was malformed. You MUST include both the "Test Cases:" section and a markdown table starting with "| Test ID | Function Tested | Expected Result |". Do not include extra commentary.
"""

def generate_test_cases(state: dict) -> str:
    files = state.get("project_files") or {}
    code_str = "\n\n".join(f"### {path}\n{content}" for path, content in sorted(files.items()))
    if not code_str:
        code_str = state.get("generated_code") or ""
        
    prompt = TEST_CASE_PROMPT.format(
        request=state.get("user_request", "Unknown Request"),
        code=code_str[:25000] # truncate if extremely long
    )
    
    llm = get_model("qa")
    max_retries = 2
    
    for attempt in range(1, max_retries + 1):
        try:
            tlog.info("TestCaseGen", f"Generating test cases (Attempt {attempt})...")
            response = llm.invoke(prompt)
            content = response.content
            
            # Simple validation
            if "Test Cases:" in content and "|" in content:
                tlog.success("TestCaseGen", "Generated valid test cases.")
                return content
            else:
                tlog.warning("TestCaseGen", "Malformed output. Retrying with fallback model...")
                llm = get_model("fallback")
                prompt += STRICT_REMINDER
        except Exception as e:
            tlog.error("TestCaseGen", f"Error generating test cases: {e}")
            if attempt == max_retries:
                return f"# Test Cases\n\nFailed to generate test cases due to error: {e}"
                
    return f"# Test Cases\n\nFailed to generate correctly formatted test cases after {max_retries} attempts."
