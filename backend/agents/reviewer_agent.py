import time
from datetime import datetime
# backend/agents/reviewer_agent.py
"""
Reviewer Agent: reviews generated code for bugs, security issues,
and bad practices. Decides PASS/FAIL.
"""

from datetime import datetime
from backend.graph.state import AgentState
from backend.services.agent_logger import agent_log
from backend.services.model_router import get_model, LLMProviderError
from backend.terminal.logger import tlog
from backend.agents.coder_agent import CONDENSED_GOLDEN_RULES

REVIEWER_PROMPT = """You are a strict senior code reviewer.
Review the following code and its execution results against the GOLDEN RULES.
Do not guess or hallucinate errors. Only comment on verified issues.
Classify your findings strictly into:
- Critical (e.g. Compilation failed, Security vulnerabilities, XSS risks via innerHTML, missed major sections of the plan, use of `<script type="module">` or ES module `import`/`export` statements in frontend JS)
- Major (e.g. Core feature missing or broken, missing accessibility attributes, external images used, state/data integrity errors)
- Minor (e.g. UI glitches)
- Suggestion (e.g. Refactoring, component splitting)

{rules}

Code:
{code}

Execution Success: {execution_success}
Execution Output/Error:
{execution_output}

If there are ANY Critical or Major issues, your VERDICT must be FAIL.
Respond in this EXACT format:

VERDICT: PASS or FAIL
CRITICAL: [number]
MAJOR: [number]
MINOR: [number]
SUGGESTIONS: [number]
FEEDBACK: 
<Your detailed feedback here>
"""

import re

def check_uncalled_functions(code: str) -> list[str]:
    defined_functions = set()
    for m in re.finditer(r'\bfunction\s+([a-zA-Z_$][0-9a-zA-Z_$]*)\s*\(', code):
        defined_functions.add(m.group(1))
    for m in re.finditer(r'\b(?:const|let|var)\s+([a-zA-Z_$][0-9a-zA-Z_$]*)\s*=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*=>)', code):
        defined_functions.add(m.group(1))
    
    uncalled = []
    for func in defined_functions:
        occurrences = len(re.findall(r'\b' + re.escape(func) + r'\b', code))
        if occurrences <= 1:
            uncalled.append(func)
            
    return uncalled

def check_duplicate_element_queries(files: dict) -> list[str]:
    id_locations = {}
    errors = []
    for filepath, content in files.items():
        if not filepath.endswith('.js'):
            continue
        ids = set()
        for m in re.finditer(r'getElementById\(\s*[\'"]([a-zA-Z0-9_-]+)[\'"]\s*\)', content):
            ids.add(m.group(1))
        for m in re.finditer(r'querySelector\(\s*[\'"]#([a-zA-Z0-9_-]+)[\'"]\s*\)', content):
            ids.add(m.group(1))
            
        for element_id in ids:
            if element_id not in id_locations:
                id_locations[element_id] = []
            id_locations[element_id].append(filepath)
            
    for element_id, locations in id_locations.items():
        if len(locations) > 1:
            errors.append(f"Element ID '{element_id}' is queried in multiple files: {', '.join(locations)}. This often indicates duplicate event listeners and fragmented logic. You MUST integrate the logic for this element into a SINGLE existing file instead of creating duplicate files.")
            
    return errors

def _code_for_review(state: AgentState) -> str:
    files = state.get("project_files") or {}
    if not files:
        elapsed = time.time() - overall_start
        print(f"[{datetime.utcnow().isoformat()}] END: Reviewer Agent (took {elapsed:.2f}s)")
        return state.get("generated_code") or ""
    # Exclude markdown reports (which contain old plans/errors) to prevent confusing the AI
    filtered_files = {path: content for path, content in files.items() if not path.endswith('.md')}
    return "\n\n".join(
        f"### {path}\n{content}" for path, content in sorted(filtered_files.items())
    )

def reviewer_agent(state: AgentState) -> AgentState:
    overall_start = time.time()
    print(f"[{datetime.utcnow().isoformat()}] START: Reviewer Agent")
    tlog.info("Reviewer", "Reviewing code...")
    llm = get_model("reviewer")
    code_to_review = _code_for_review(state)
    
    uncalled = check_uncalled_functions(code_to_review)
    if uncalled:
        tlog.warning("Reviewer", f"Static check failed: Uncalled functions detected ({', '.join(uncalled)}). Bypassing LLM.")
        passed = False
        categories = {"critical": 1, "major": 0, "minor": 0, "suggestions": 0}
        response = "VERDICT: FAIL\nCRITICAL: 1\nMAJOR: 0\nMINOR: 0\nSUGGESTIONS: 0\nFEEDBACK:\nCRITICAL: The following functions were defined but never called or wired to events: " + ", ".join(uncalled) + ". A project with uncalled render/handler functions is incomplete. You MUST add an initialization block (e.g. DOMContentLoaded) that invokes them and wires all event listeners."
        
        state["review_passed"] = passed
        state["reviewer_categories"] = categories
        state["review_feedback"] = response
        state["current_node"] = "reviewer_agent"
        state["revision_count"] = state.get("revision_count", 0) + 1
        state["history"].append("Reviewer verdict: FAIL (Static check: Uncalled functions)")
        
        if "execution_trace" not in state:
            state["execution_trace"] = []
        state["execution_trace"].append({
            "agent": "Reviewer",
            "attempt": state["revision_count"],
            "timestamp": datetime.utcnow().isoformat(),
            "verdict": "FAIL",
            "details": response
        })
        elapsed = time.time() - overall_start
        print(f"[{datetime.utcnow().isoformat()}] END: Reviewer Agent (took {elapsed:.2f}s)")
        return state

    project_files = state.get("project_files") or {}
    duplicate_errors = check_duplicate_element_queries(project_files)
    if duplicate_errors:
        tlog.warning("Reviewer", f"Static check failed: Duplicate element queries detected. Bypassing LLM.")
        passed = False
        categories = {"critical": len(duplicate_errors), "major": 0, "minor": 0, "suggestions": 0}
        error_msg = " ".join(duplicate_errors)
        response = f"VERDICT: FAIL\nCRITICAL: {len(duplicate_errors)}\nMAJOR: 0\nMINOR: 0\nSUGGESTIONS: 0\nFEEDBACK:\nCRITICAL: {error_msg}"
        
        state["review_passed"] = passed
        state["reviewer_categories"] = categories
        state["review_feedback"] = response
        state["current_node"] = "reviewer_agent"
        state["revision_count"] = state.get("revision_count", 0) + 1
        state["history"].append("Reviewer verdict: FAIL (Static check: Duplicate Element Queries)")
        
        if "execution_trace" not in state:
            state["execution_trace"] = []
        state["execution_trace"].append({
            "agent": "Reviewer",
            "attempt": state["revision_count"],
            "timestamp": datetime.utcnow().isoformat(),
            "verdict": "FAIL",
            "details": response
        })
        elapsed = time.time() - overall_start
        print(f"[{datetime.utcnow().isoformat()}] END: Reviewer Agent (took {elapsed:.2f}s)")
        return state

    if len(code_to_review) > 15000:
        code_to_review = code_to_review[:15000] + "\n\n...[TRUNCATED for length]..."

    prompt = REVIEWER_PROMPT.format(
        rules=CONDENSED_GOLDEN_RULES,
        code=code_to_review,
        execution_success=state.get("execution_success"),
        execution_output=state.get("execution_error") or state.get("execution_output") or "None"
    )
    
    start_time = time.time()
    try:
        with agent_log(
            agent_name="Reviewer Agent",
            model_name=llm.model_name,
            input_text=prompt,
            next_agent="QA Agent",
        ) as log:
            raw_response = llm.invoke(prompt)
            log["response"] = raw_response
            response = raw_response.content
            log["output"] = response
    except LLMProviderError as e:
        state["success"] = False
        state["error"] = str(e)
        elapsed = time.time() - overall_start
        print(f"[{datetime.utcnow().isoformat()}] END: Reviewer Agent (took {elapsed:.2f}s)")
        return state
    elapsed = time.time() - start_time
    tlog.info("Reviewer", f"LLM generation took {elapsed:.1f} seconds")

    passed = "VERDICT: PASS" in response.upper()

    # Parse counts
    categories = {"critical": 0, "major": 0, "minor": 0, "suggestions": 0}
    try:
        if m := re.search(r"CRITICAL:\s*(\d+)", response, re.IGNORECASE):
            categories["critical"] = int(m.group(1))
        if m := re.search(r"MAJOR:\s*(\d+)", response, re.IGNORECASE):
            categories["major"] = int(m.group(1))
        if m := re.search(r"MINOR:\s*(\d+)", response, re.IGNORECASE):
            categories["minor"] = int(m.group(1))
        if m := re.search(r"SUGGESTIONS:\s*(\d+)", response, re.IGNORECASE):
            categories["suggestions"] = int(m.group(1))
    except Exception:
        pass

    state["review_passed"] = passed
    state["reviewer_categories"] = categories
    state["review_feedback"] = response
    state["current_node"] = "reviewer_agent"
    state["revision_count"] = state.get("revision_count", 0) + 1
    state["history"].append(f"Reviewer verdict: {'PASS' if passed else 'FAIL'}")

    if passed:
        tlog.success("Reviewer", "Code review passed")
    else:
        tlog.warning("Reviewer", f"Code review FAILED (revision {state['revision_count']})")

    if "execution_trace" not in state:
        state["execution_trace"] = []
    state["execution_trace"].append({
        "agent": "Reviewer",
        "attempt": state.get("revision_count", 0) + 1,
        "timestamp": datetime.utcnow().isoformat(),
        "verdict": "PASS" if passed else "FAIL",
        "details": response
    })
    
    elapsed = time.time() - overall_start
    print(f"[{datetime.utcnow().isoformat()}] END: Reviewer Agent (took {elapsed:.2f}s)")
    return state
