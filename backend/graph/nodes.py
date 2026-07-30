# backend/graph/nodes.py
"""
Conditional routing logic for the graph.
"""

from backend.graph.state import AgentState

def orchestrator_router(state: AgentState) -> str:
    """
    Decides whether to loop back to coder_agent or end the workflow.
    """
    from backend.terminal.logger import tlog
    
    if state.get("orchestrator_passed"):
        return "end"
        
    max_retries = state.get("max_revisions", 3)
    current_retry = state.get("revision_count", 0)
    
    if current_retry >= max_retries:
        tlog.error("Orchestrator", f"Max retries ({max_retries}) reached without PASS verdict. Halting workflow.")
        print(f"[ORCHESTRATOR] MAX_RETRIES ({max_retries}) reached. Halting loop.")
        return "end"
        
    reason = "QA/Reviewer feedback indicates FAIL or WARNINGS."
    if state.get("qa_feedback") and "QA_VERDICT: REJECT" in state["qa_feedback"]:
        reason = state["qa_feedback"].split('\n')[0]
        
    tlog.warning("Orchestrator", f"Retry {current_retry + 1}/{max_retries} triggered. Reason: {reason}")
    print(f"[ORCHESTRATOR] Retry {current_retry + 1}/{max_retries} triggered. Reason: {reason}")
    
    return "retry"