import time
from datetime import datetime
# backend/agents/qa_agent.py
"""
QA Agent: generates additional test cases if needed, runs pytest
against the generated code, and validates whether requirements
are functionally satisfied.
"""

import tempfile
from pathlib import Path
import subprocess
from datetime import datetime

from backend.graph.state import AgentState
from backend.services.agent_logger import agent_log
from backend.services.model_router import get_model, LLMProviderError
from backend.services.sandbox import CPU_LIMIT, MEMORY_LIMIT, PODMAN_IMAGE
from backend.terminal.logger import tlog

QA_PROMPT = """You are a Lead QA Engineer. 
Review the implementation plan, the generated code, the execution results, and the Reviewer's findings.

Plan:
{plan}

Code:
{code}

Reviewer Findings:
{review_feedback}

Execution Output:
{execution_output}

Your job is to strictly verify the functional behavior and plan completeness.
1. Cross-check the generated file list and rendered features against EVERY bullet point in the implementation plan's Acceptance Criteria — flag ANY missing section as a Major/Critical failure, not just functional bugs.
2. Check if the required functionality works.
3. Adapt to the project type (e.g., if React: button clicks, UI layout, responsiveness; if Flask: API status, DB behavior).
4. If no automated tests exist or you cannot execute them, explicitly state: "No automated tests found. Manual verification required."

Respond in this exact format:
QA_VERDICT: APPROVE or REJECT
QA_FEEDBACK: <detailed reasoning>

Then, document your test cases in a structured markdown table with the following exact columns:
| Test Type | Description | Example/Result | Status (Pass/Fail) |
|---|---|---|---|

For the "Test Type", you MUST use ONLY relevant categories from this standard taxonomy (do not use all of them, only the relevant ones):
- Happy Path
- Positive Testing
- Negative Testing
- Boundary Value Testing
- Edge Case Testing
- Corner Case Testing
- Validation Testing
- Error Handling Testing
- Exception Testing
- Usability Testing
- Accessibility Testing
- Compatibility Testing
- Performance Testing
- Load Testing
- Stress Testing
- Security Testing
- Regression Testing
- Smoke Testing
- Sanity Testing
- Exploratory Testing
- End-to-End (E2E) Testing
"""


def _run_project_checks(files: dict[str, str], timeout: int = 15) -> dict:
    """Runs compile and unittest discovery inside the Podman sandbox."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        for relative_path, content in files.items():
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        command = "python3 -m compileall . && python3 -m unittest discover -v"
        podman_cmd = [
            "podman", "run",
            "--rm",
            "--network=none",
            f"--memory={MEMORY_LIMIT}",
            f"--cpus={CPU_LIMIT}",
            "--read-only",
            "--tmpfs", "/tmp",
            "--volume", f"{tmp_dir}:/sandbox:ro",
            "--workdir", "/sandbox",
            PODMAN_IMAGE,
            "sh", "-c", command,
        ]

        try:
            result = subprocess.run(
                podman_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "passed": result.returncode == 0,
                "output": result.stdout + "\n" + result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "output": f"Project checks timed out after {timeout} seconds.",
            }
        except FileNotFoundError:
            return {
                "passed": False,
                "output": "Podman is not installed or not found in PATH.",
            }


def _code_for_review(state: AgentState) -> str:
    files = state.get("project_files") or {}
    if not files:
        elapsed = time.time() - overall_start
        print(f"[{datetime.utcnow().isoformat()}] END: QA Agent (took {elapsed:.2f}s)")
        return state.get("generated_code") or ""
    
    # Exclude markdown reports (which contain old plans/errors) to prevent confusing the AI
    filtered_files = {path: content for path, content in files.items() if not path.endswith('.md')}
    
    return "\n\n".join(
        f"### {path}\n{content}" for path, content in sorted(filtered_files.items())
    )


def _run_pytest_on_code(code: str, timeout: int = 15) -> dict:
    """Compatibility wrapper for older callers."""
    try:
        return _run_project_checks({"main.py": code}, timeout=timeout)
    except Exception as exc:
        return {
            "passed": False,
            "output": str(exc),
        }


def qa_agent(state: AgentState) -> AgentState:
    overall_start = time.time()
    print(f"[{datetime.utcnow().isoformat()}] START: QA Agent")
    tlog.info("QA", "Running tests and validating requirements concurrently...")
    import concurrent.futures
    
    # Define tasks to run in parallel
    def run_tests():
        return _run_project_checks(state.get("project_files") or {})
        
    def run_llm_validation():
        llm = get_model("qa")
        code_to_review = _code_for_review(state)
        if len(code_to_review) > 15000:
            code_to_review = code_to_review[:15000] + "\n\n...[TRUNCATED for length]..."
            
        is_update = bool(state.get("is_update"))
        plan_to_use = state.get("plan") or ""
        
        if is_update:
            plan_to_use = f"USER UPDATE REQUEST (Only evaluate if this request was fulfilled. Ignore the original project plan):\n{state.get('user_request')}"
        else:
            if "Acceptance Criteria" in plan_to_use:
                parts = plan_to_use.split("Acceptance Criteria", 1)
                if len(parts) > 1:
                    plan_to_use = "Acceptance Criteria" + parts[1].split("##", 1)[0]
                
        prompt = QA_PROMPT.format(
            plan=plan_to_use, 
            code=code_to_review,
            review_feedback=state.get("review_feedback") or "None",
            execution_output=state.get("execution_error") or state.get("execution_output") or "None"
        )
        
        start_time = time.time()
        with agent_log(
            agent_name="QA Agent",
            model_name=llm.model_name,
            input_text=prompt,
            next_agent="Orchestrator Agent",
        ) as log:
            raw_response = llm.invoke(prompt)
            qa_response = raw_response.content.strip()
            
            if not qa_response or "QA_VERDICT:" not in qa_response:
                tlog.warning("QA", "Empty or malformed QA response. Retrying with fallback model (gpt-oss-120b)...")
                fallback_llm = get_model("fallback")
                retry_prompt = prompt + "\n\nCRITICAL INSTRUCTION: You MUST output 'QA_VERDICT: APPROVE' or 'QA_VERDICT: REJECT' and provide the required table. Do NOT output a blank response. Keep reasoning extremely concise to avoid token limits."
                raw_response = fallback_llm.invoke(retry_prompt)
                qa_response = raw_response.content.strip()
                
            log["response"] = raw_response
            log["output"] = qa_response
            
        elapsed = time.time() - start_time
        tlog.info("QA", f"LLM generation took {elapsed:.1f} seconds")
        return qa_response

    # Execute in parallel
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_tests = executor.submit(run_tests)
            future_llm = executor.submit(run_llm_validation)
            
            pytest_result = future_tests.result()
            qa_response = future_llm.result()
    except LLMProviderError as e:
        state["success"] = False
        state["error"] = str(e)
        elapsed = time.time() - overall_start
        print(f"[{datetime.utcnow().isoformat()}] END: QA Agent (took {elapsed:.2f}s)")
        return state

    state["pytest_passed"] = pytest_result["passed"]
    state["pytest_output"] = pytest_result["output"]

    if pytest_result["passed"]:
        tlog.success("QA", "Tests passed")
    else:
        tlog.warning("QA", "Tests failed")

    qa_approved = "QA_VERDICT: APPROVE" in qa_response.upper()

    state["qa_feedback"] = qa_response
    state["test_revision_count"] = state.get("test_revision_count", 0) + 1
    state["current_node"] = "qa_agent"
    state["history"].append(
        f"QA Agent: pytest={'passed' if pytest_result['passed'] else 'failed'}, "
        f"verdict={'approve' if qa_approved else 'reject'}"
    )

    # Final pass condition: BOTH pytest passes AND QA approves
    state["pytest_passed"] = pytest_result["passed"] and qa_approved

    if state["pytest_passed"]:
        tlog.success("QA", "QA approved — all checks passed")
    else:
        tlog.warning("QA", f"QA verdict: {'approve' if qa_approved else 'reject'}")

    if "execution_trace" not in state:
        state["execution_trace"] = []
    
    details = f"Tests Passed: {pytest_result['passed']}\n"
    if pytest_result["output"]:
        details += f"Test Output:\n{pytest_result['output'][:500]}...\n\n"
    details += f"QA Feedback:\n{qa_response}"

    state["execution_trace"].append({
        "agent": "QA",
        "attempt": state.get("revision_count", 0) + 1,
        "timestamp": datetime.utcnow().isoformat(),
        "verdict": "APPROVE" if qa_approved else "REJECT",
        "details": details
    })

    elapsed = time.time() - overall_start
    print(f"[{datetime.utcnow().isoformat()}] END: QA Agent (took {elapsed:.2f}s)")
    return state
