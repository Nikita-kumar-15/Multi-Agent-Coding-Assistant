import time
from datetime import datetime
from backend.graph.state import AgentState
from backend.agents.reviewer_agent import reviewer_agent
from backend.agents.qa_agent import qa_agent
import concurrent.futures

def parallel_reviewer_qa_agent(state: AgentState) -> AgentState:
    print(f"[{datetime.utcnow().isoformat()}] START: Parallel Reviewer & QA")
    overall_start = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        state_for_reviewer = state.copy()
        state_for_qa = state.copy()
        
        state_for_reviewer["history"] = list(state.get("history", []))
        state_for_qa["history"] = list(state.get("history", []))
        
        state_for_reviewer["execution_trace"] = list(state.get("execution_trace", []))
        state_for_qa["execution_trace"] = list(state.get("execution_trace", []))
        
        future_rev = executor.submit(reviewer_agent, state_for_reviewer)
        future_qa = executor.submit(qa_agent, state_for_qa)
        
        new_state_rev = future_rev.result()
        new_state_qa = future_qa.result()
        
    state["review_feedback"] = new_state_rev.get("review_feedback")
    state["review_passed"] = new_state_rev.get("review_passed")
    
    # CRITICAL: Preserve the retry counter incremented by Reviewer
    if "revision_count" in new_state_rev:
        state["revision_count"] = new_state_rev["revision_count"]
    
    state["generated_tests"] = new_state_qa.get("generated_tests")
    state["pytest_output"] = new_state_qa.get("pytest_output")
    state["pytest_passed"] = new_state_qa.get("pytest_passed")
    state["qa_feedback"] = new_state_qa.get("qa_feedback")
    
    if new_state_rev.get("success") is False:
        state["success"] = False
        state["error"] = new_state_rev.get("error")
    if new_state_qa.get("success") is False:
        state["success"] = False
        state["error"] = new_state_qa.get("error")
        
    original_hist_len = len(state.get("history", []))
    rev_new_hist = new_state_rev.get("history", [])[original_hist_len:]
    qa_new_hist = new_state_qa.get("history", [])[original_hist_len:]
    state["history"].extend(rev_new_hist)
    state["history"].extend(qa_new_hist)
    
    original_trace_len = len(state.get("execution_trace", []))
    rev_new_trace = new_state_rev.get("execution_trace", [])[original_trace_len:]
    qa_new_trace = new_state_qa.get("execution_trace", [])[original_trace_len:]
    state["execution_trace"].extend(rev_new_trace)
    state["execution_trace"].extend(qa_new_trace)
    
    state["current_node"] = "parallel_reviewer_qa"
    
    elapsed = time.time() - overall_start
    print(f"[{datetime.utcnow().isoformat()}] END: Parallel Reviewer & QA (took {elapsed:.2f}s)")
    return state
