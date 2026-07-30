# backend/graph/workflow.py
"""
LangGraph StateGraph definition.

Flow:
Planner -> Architecture -> Coder -> Executor -> Reviewer -> QA -> Orchestrator -> (loop to Coder if FAIL) -> END
"""

from langgraph.graph import StateGraph, END

from backend.graph.state import AgentState
from backend.graph.nodes import orchestrator_router
from backend.agents.planner_agent import planner_agent
from backend.agents.architecture_agent import architecture_agent
from backend.agents.coder_agent import coder_agent
from backend.agents.executor_agent import executor_agent
from backend.agents.parallel_agents import parallel_reviewer_qa_agent
from backend.agents.orchestrator_agent import orchestrator_agent
from backend.agents.orchestrator_pre_search_agent import orchestrator_pre_search_agent


def build_workflow():
    graph = StateGraph(AgentState)

    # register nodes
    graph.add_node("planner", planner_agent)
    graph.add_node("architecture", architecture_agent)
    graph.add_node("orchestrator_pre_search", orchestrator_pre_search_agent)
    graph.add_node("coder", coder_agent)
    graph.add_node("executor", executor_agent)
    graph.add_node("parallel_reviewer_qa", parallel_reviewer_qa_agent)
    graph.add_node("orchestrator", orchestrator_agent)

    # entry point
    graph.set_entry_point("planner")

    # conditional routing after planner
    graph.add_conditional_edges(
        "planner",
        lambda state: "orchestrator_pre_search" if state.get("is_update") else "architecture"
    )

    # linear edges
    graph.add_edge("architecture", "orchestrator_pre_search")
    graph.add_edge("orchestrator_pre_search", "coder")
    graph.add_edge("coder", "executor")
    graph.add_edge("executor", "parallel_reviewer_qa")
    graph.add_edge("parallel_reviewer_qa", "orchestrator")

    # conditional edge from orchestrator -> loop back to coder OR finish
    graph.add_conditional_edges(
        "orchestrator",
        orchestrator_router,
        {
            "retry": "coder",
            "end": END,
        },
    )

    return graph.compile()