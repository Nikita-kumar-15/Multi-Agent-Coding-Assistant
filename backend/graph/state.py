# backend/graph/state.py
"""
Shared LangGraph state — includes language_preference field.
"""

from typing import TypedDict, List, Optional, Dict, Any

class AgentState(TypedDict):
    # Input
    user_request: str
    user_history: List[Dict[str, str]]   # ← NEW: actual user conversation history
    language_preference: Optional[str]
    is_update: Optional[bool]
    previous_code: Optional[str]
    active_project_state: Optional[dict]

    # Planning
    # Planning
    plan: Optional[str]
    architecture_plan: Optional[str]
    initial_search_context: Optional[str]

    # Coding
    generated_code: Optional[str]
    project_files: Optional[dict]
    code_explanation: Optional[str]

    # Review
    review_feedback: Optional[str]
    review_passed: Optional[bool]

    # Orchestrator
    orchestrator_feedback: Optional[str]
    orchestrator_verdict: Optional[str]

    # Execution
    execution_output: Optional[str]
    execution_error: Optional[str]
    execution_success: Optional[bool]
    execution_time: Optional[float]

    # QA
    generated_tests: Optional[str]
    pytest_output: Optional[str]
    pytest_passed: Optional[bool]
    qa_feedback: Optional[str]

    # Artifact
    artifact_id: Optional[str]

    # Loop control
    revision_count: int
    max_revisions: int
    test_revision_count: int
    max_test_revisions: int

    # Progress
    current_node: Optional[str]
    history: List[str]
    execution_trace: List[Dict[str, Any]]
    
    # Error Handling (Critical so LangGraph doesn't drop them)
    success: Optional[bool]
    error: Optional[str]