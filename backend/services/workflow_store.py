"""
Workflow persistence facade used by the frontend polling contract.

The project already stores workflow/job state in the jobs table. This module
keeps that storage behind workflow-oriented names so the API can expose
workflow_id/status/final_result without duplicating persistence.
"""

from __future__ import annotations

from backend.services.job_store import create_job, get_job, update_job


def create_workflow(workflow_id: str, user_request: str, session_id: str | None = None) -> None:
    create_job(workflow_id, user_request, session_id=session_id)


def update_workflow(
    workflow_id: str,
    *,
    status: str | None = None,
    current_node: str | None = None,
    progress: int | None = None,
    final_result: dict | None = None,
    error: str | None = None,
) -> None:
    update_job(
        workflow_id,
        status=status,
        current_node=current_node,
        progress=progress,
        result=final_result,
        error=error,
    )


def get_workflow(workflow_id: str) -> dict | None:
    return get_job(workflow_id)


def get_poll_response(workflow_id: str) -> dict | None:
    workflow = get_workflow(workflow_id)
    if not workflow:
        return None
    return {
        "workflow_id": workflow["job_id"],
        "status": workflow["status"],
        "final_result": workflow.get("result") if workflow["status"] == "completed" else None,
        "error": workflow.get("error"),
    }
