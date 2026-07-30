import time
from datetime import datetime
# backend/agents/architecture_agent.py
"""
Architecture Agent: Reviews the planner's output and finalizes the architecture,
ensuring best practices, appropriate tech stack, and structural soundness.
"""

from datetime import datetime

from backend.graph.state import AgentState
from backend.services.agent_logger import agent_log
from backend.services.model_router import get_model, LLMProviderError
from backend.terminal.logger import tlog

ARCHITECTURE_PROMPT = """You are a Principal Software Architect.
Review the following implementation plan and finalize the architecture.
Ensure the chosen technologies are appropriate, the file structure is sound,
and any missing architectural best practices are added.

Implementation Plan:
{plan}

Provide a finalized architectural blueprint that the Coder can directly follow.
"""

def architecture_agent(state: AgentState) -> AgentState:
    overall_start = time.time()
    print(f"[{datetime.utcnow().isoformat()}] START: Architecture Agent")
    tlog.info("Architecture", "Finalizing architecture...")
    llm = get_model("planner")  # Uses the same model tier as planner
    prompt = ARCHITECTURE_PROMPT.format(plan=state["plan"])
    
    try:
        with agent_log(
            agent_name="Architecture Agent",
            model_name=llm.model_name,
            input_text=prompt,
            next_agent="Coder Agent",
        ) as log:
            response = llm.invoke(prompt)
            log["response"] = response
            log["output"] = response.content
    except LLMProviderError as e:
        state["success"] = False
        state["error"] = str(e)
        elapsed = time.time() - overall_start
        print(f"[{datetime.utcnow().isoformat()}] END: Architecture Agent (took {elapsed:.2f}s)")
        return state

    state["architecture_plan"] = response.content
    state["current_node"] = "architecture_agent"
    state["history"].append("Architecture Agent finalized blueprint.")
    
    if "execution_trace" not in state:
        state["execution_trace"] = []
    state["execution_trace"].append({
        "agent": "Architecture",
        "attempt": state.get("revision_count", 0) + 1,
        "timestamp": datetime.utcnow().isoformat(),
        "verdict": "Completed",
        "details": response.content
    })
    
    tlog.success("Architecture", "Architecture blueprint finalized")
    elapsed = time.time() - overall_start
    print(f"[{datetime.utcnow().isoformat()}] END: Architecture Agent (took {elapsed:.2f}s)")
    return state
