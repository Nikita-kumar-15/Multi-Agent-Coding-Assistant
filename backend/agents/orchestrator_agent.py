import time
from datetime import datetime
# backend/agents/orchestrator_agent.py
"""
Orchestrator Agent: The final verdict engine.
It aggregates the execution results, the reviewer findings, and the QA test results
to produce a final unified verdict (PASS, PASS WITH WARNINGS, FAIL) and a clear summary.
"""

from datetime import datetime
from backend.graph.state import AgentState
from backend.services.agent_logger import agent_log
from backend.services.model_router import get_model, LLMProviderError
from backend.terminal.logger import tlog
from backend.services.web_search import web_search, fetch_page_content

ORCHESTRATOR_PROMPT = """You are the Lead Release Manager and Orchestrator.
Review the outputs from the Execution, Code Review, and QA phases.
Provide a final verdict on this generated project.

Execution Success: {execution_success}
Execution Output/Error:
{execution_output}

Review Passed: {review_passed}
Review Feedback & Categories:
{review_feedback}

QA Passed: {qa_passed}
QA Feedback:
{qa_feedback}

Your job is to reconcile these results. Even if QA says PASS, if the Executor says FAIL, the overall result must be FAIL.
Provide your response in exactly this format:

Overall: [PASS, PASS WITH WARNINGS, or FAIL]
Reason:
[A short 2-3 sentence summary explaining the verdict based on the gathered evidence]
"""

ORCHESTRATOR_SEARCH_PROMPT = """Based on the following Orchestrator verdict and failure reasons, extract a single search query to find the correct usage, bug fix, or updated syntax for the failure.
If it's a generic logic error, just return "NONE".

Failure Details:
{feedback}

Respond ONLY with the search query text, or "NONE".
"""

def orchestrator_agent(state: AgentState) -> AgentState:
    overall_start = time.time()
    print(f"[{datetime.utcnow().isoformat()}] START: Orchestrator Agent")
    tlog.info("Orchestrator", "Reconciling results for final verdict...")
    
    qa_fb = state.get("qa_feedback") or ""
    if not qa_fb or "QA_VERDICT:" not in qa_fb:
        if state.get("review_passed"):
            tlog.warning("Orchestrator", "QA feedback missing/malformed, but Reviewer passed. Forcing PASS WITH WARNINGS.")
            state["orchestrator_verdict"] = "PASS WITH WARNINGS"
            state["orchestrator_passed"] = True
            state["orchestrator_feedback"] = "Overall: PASS WITH WARNINGS\nReason: QA Agent produced malformed or empty feedback (INCONCLUSIVE), but Code Review passed. Manual verification recommended."
        else:
            tlog.error("Orchestrator", "QA feedback missing and Reviewer failed. Forcing FAIL.")
            state["orchestrator_verdict"] = "FAIL"
            state["orchestrator_passed"] = False
            state["orchestrator_feedback"] = "Overall: FAIL\nReason: QA Agent produced malformed or empty feedback (INCONCLUSIVE), and Code Review did not pass."
            
        state["current_node"] = "orchestrator_agent"
        state["history"].append(f"Orchestrator provided final verdict: {state['orchestrator_verdict']}")
        
        if "execution_trace" not in state:
            state["execution_trace"] = []
        state["execution_trace"].append({
            "agent": "Orchestrator",
            "attempt": state.get("revision_count", 0) + 1,
            "timestamp": datetime.utcnow().isoformat(),
            "verdict": "FAIL",
            "details": state["orchestrator_feedback"]
        })
        elapsed = time.time() - overall_start
        print(f"[{datetime.utcnow().isoformat()}] END: Orchestrator Agent (took {elapsed:.2f}s)")
        return state

    llm = get_model("qa")  # Uses the reviewer/qa tier
    
    prompt = ORCHESTRATOR_PROMPT.format(
        execution_success=state.get("execution_success"),
        execution_output=state.get("execution_error") or state.get("execution_output") or "None",
        review_passed=state.get("review_passed"),
        review_feedback=state.get("review_feedback") or "None",
        qa_passed=state.get("pytest_passed"),
        qa_feedback=state.get("qa_feedback") or "None",
    )
    
    try:
        with agent_log(
            agent_name="Orchestrator Agent",
            model_name=llm.model_name,
            input_text=prompt,
            next_agent="Router",
        ) as log:
            response = llm.invoke(prompt)
            log["response"] = response
            log["output"] = response.content
    except LLMProviderError as e:
        state["success"] = False
        state["error"] = str(e)
        elapsed = time.time() - overall_start
        print(f"[{datetime.utcnow().isoformat()}] END: Orchestrator Agent (took {elapsed:.2f}s)")
        return state

    output = response.content
    state["orchestrator_feedback"] = output
    
    tlog.info("Orchestrator", f"Raw text being parsed: '{output}'")
    
    if "OVERALL: FAIL" in output.upper():
        state["orchestrator_verdict"] = "FAIL"
        state["orchestrator_passed"] = False
        tlog.warning("Orchestrator", "Extracted verdict: FAIL. Initiating fix search...")
        tlog.info("Orchestrator", "Checking should_trigger_web_search() -> True")
        
        search_prompt = ORCHESTRATOR_SEARCH_PROMPT.format(feedback=output)
        try:
            search_res = llm.invoke(search_prompt)
            query = search_res.content.strip().strip('"').strip("'")
        except LLMProviderError as e:
            state["success"] = False
            state["error"] = str(e)
            elapsed = time.time() - overall_start
            print(f"[{datetime.utcnow().isoformat()}] END: Orchestrator Agent (took {elapsed:.2f}s)")
            return state
        
        if query and query.upper() != "NONE":
            tlog.info("Orchestrator", f"Targeted search query: {query}")
            results = web_search(query, max_results=2)
            if results:
                output += "\n\n--- TARGETED SEARCH RESULTS FOR FIX ---\n"
                for res in results:
                    output += f"Title: {res.get('title')}\nURL: {res.get('href')}\nSnippet: {res.get('body')}\n\n"
                
                for res in results:
                    first_url = res.get('href')
                    if first_url:
                        content = fetch_page_content(first_url)
                        if content:
                            output += f"\nDeep Context ({first_url}):\n{content[:2000]}\n"
                            break
        state["orchestrator_feedback"] = output
    elif "OVERALL: PASS WITH WARNINGS" in output.upper():
        state["orchestrator_verdict"] = "PASS WITH WARNINGS"
        state["orchestrator_passed"] = True
        tlog.warning("Orchestrator", "Extracted verdict: PASS WITH WARNINGS")
        tlog.info("Orchestrator", "Checking should_trigger_web_search() -> False")
    else:
        state["orchestrator_verdict"] = "PASS"
        state["orchestrator_passed"] = True
        tlog.success("Orchestrator", "Extracted verdict: PASS")
        tlog.info("Orchestrator", "Checking should_trigger_web_search() -> False")

    state["current_node"] = "orchestrator_agent"
    state["history"].append(f"Orchestrator provided final verdict: {state['orchestrator_verdict']}")
    
    if "execution_trace" not in state:
        state["execution_trace"] = []
    state["execution_trace"].append({
        "agent": "Orchestrator",
        "attempt": state.get("revision_count", 0) + 1,
        "timestamp": datetime.utcnow().isoformat(),
        "verdict": state["orchestrator_verdict"],
        "details": output
    })
    
    elapsed = time.time() - overall_start
    print(f"[{datetime.utcnow().isoformat()}] END: Orchestrator Agent (took {elapsed:.2f}s)")
    return state
