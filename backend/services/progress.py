# backend/services/progress.py
"""
Maps the current graph node to a human-readable stage name
and an approximate progress percentage for the frontend.
"""

NODE_PROGRESS_MAP = {
    "planner": ("Planning", 15),
    "architecture": ("System Design", 25),
    "orchestrator_pre_search": ("Researching Best Practices", 35),
    "orchestrator_pre_search_agent": ("Researching Best Practices", 35),
    "coder": ("Generating Code", 45),
    "executor": ("Executing Sandbox", 55),
    "reviewer": ("Code Review", 65),
    "qa": ("Running Tests & QA", 80),
    "orchestrator": ("Finalizing Verdict", 85),
    "Generating Report": ("Generating Report", 92),
    "Generating Test Cases": ("Generating Test Cases", 96),
    "Completed": ("Completed", 100),
    "Failed": ("Failed", 100),
}


def get_stage_info(node_name: str) -> tuple[str, int]:
    """Returns (stage_label, progress_percent) for a given node name."""
    return NODE_PROGRESS_MAP.get(node_name, ("Processing", 0))