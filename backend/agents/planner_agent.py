import time
from datetime import datetime
# backend/agents/planner_agent.py
"""
Planner Agent: takes the raw user request and breaks it into
a clear, structured implementation plan.
"""

from datetime import datetime

from backend.graph.state import AgentState
from backend.services.agent_logger import agent_log
from backend.services.model_router import get_model, LLMProviderError
from backend.terminal.logger import tlog

PLANNER_PROMPT = """You are a senior software product manager and architect.
Break the following user request into a clear, structured implementation plan.

{context_section}

Your plan MUST include the following sections:
1. Overview & Acceptance Criteria
2. File Structure & Edits
   - If this is a new project, list the directories and files to create.
   - If this is an update to an EXISTING project, explicitly list EXACTLY which existing files need to be modified, which new files to create, which files to DELETE, and which files to leave untouched.
3. Dependencies & Libraries
4. Test Cases & Edge Cases
5. Coding Standards

User request:
{request}
"""


def planner_agent(state: AgentState) -> AgentState:
    overall_start = time.time()
    print(f"[{datetime.utcnow().isoformat()}] START: Planner Agent")
    tlog.info("Planner", "Planning task...")
    llm = get_model("planner")
    is_update = state.get("is_update", False)
    next_agent = "Orchestrator Pre Search" if is_update else "Architecture Agent"

    context_section = ""
    if is_update:
        context_section = f"CURRENT WORKSPACE CONTEXT:\n{state.get('previous_code', 'No existing code found.')}\n\nTreat the above files as the absolute source of truth. Plan how to modify them to achieve the user's request."
        
    prompt = PLANNER_PROMPT.format(request=state["user_request"], context_section=context_section)
    
    try:
        with agent_log(
            agent_name="Planner Agent",
            model_name=llm.model_name,
            input_text=prompt,
            next_agent=next_agent,
        ) as log:
            response = llm.invoke(prompt)
            log["response"] = response
            log["output"] = response.content
    except LLMProviderError as e:
        state["success"] = False
        state["error"] = str(e)
        elapsed = time.time() - overall_start
        print(f"[{datetime.utcnow().isoformat()}] END: Planner Agent (took {elapsed:.2f}s)")
        return state

    state["plan"] = response.content
    state["current_node"] = "planner_agent"
    state["history"].append("Planner created implementation plan.")
    
    if "execution_trace" not in state:
        state["execution_trace"] = []
    state["execution_trace"].append({
        "agent": "Planner",
        "attempt": state.get("revision_count", 0) + 1,
        "timestamp": datetime.utcnow().isoformat(),
        "verdict": "Completed",
        "details": response.content
    })
    
    tlog.success("Planner", "Implementation plan created")
    elapsed = time.time() - overall_start
    print(f"[{datetime.utcnow().isoformat()}] END: Planner Agent (took {elapsed:.2f}s)")
    return state
