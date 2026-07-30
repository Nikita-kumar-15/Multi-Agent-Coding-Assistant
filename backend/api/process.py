# backend/api/process.py
"""
Main process endpoint — routes messages and runs LangGraph pipeline.
"""

import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException

from backend.models.schemas import ProcessRequest, ProcessResponse, StatusResponse
from backend.services.job_store import create_job, get_job, update_job, get_jobs_for_session
from backend.services.job_runner import run_job
from backend.services.session_store import (
    get_messages,
    add_message,
    session_exists,
    create_session,
    get_session_language_preference,
    set_session_language_preference,
)
from backend.agents.conversation_agent import route_message

router = APIRouter()


@router.post("/process", response_model=ProcessResponse)
def start_process(request: ProcessRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())

    # Ensure session exists
    if request.session_id and not session_exists(request.session_id):
        create_session(request.session_id)

    # Get conversation history
    history = get_messages(request.session_id) if request.session_id else []

    # Get previous code and context
    previous_code = None
    active_project_state = None
    
    if request.session_id:
        from backend.services.session_store import get_active_project_state, get_session_workflow_id
        active_project_state = get_active_project_state(request.session_id)
        if not active_project_state:
            active_project_state = {}

        workflow_id = get_session_workflow_id(request.session_id)
        if workflow_id:
            import os
            workspace_dir = os.path.join("workflow", workflow_id, "project")
            if os.path.exists(workspace_dir):
                disk_files = {}
                for root, _, filenames in os.walk(workspace_dir):
                    for filename in filenames:
                        # Skip hidden files and common binary extensions
                        if filename.startswith('.') or filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.ico', '.zip', '.pdf')):
                            continue
                        filepath = os.path.join(root, filename)
                        rel_path = os.path.relpath(filepath, workspace_dir)
                        try:
                            with open(filepath, 'r', encoding='utf-8') as f:
                                disk_files[rel_path] = f.read()
                        except Exception:
                            continue
                
                if disk_files:
                    active_project_state["files"] = disk_files
                    previous_code = "\n\n".join([f"```{fp.split('.')[-1]} path={fp}\n{content}\n```" for fp, content in disk_files.items()])
                    print(f"[SESSION {request.session_id}] Loaded {len(disk_files)} files from physical disk workspace.")
                else:
                    print(f"[SESSION {request.session_id}] Workspace dir exists but is empty.")
            else:
                print(f"[SESSION {request.session_id}] Workspace dir not found on disk.")
        else:
            print(f"[SESSION {request.session_id}] WARNING: Session state missing for UPDATE request — falling back to treating as new project.")

    # Get language preference
    language_preference = None
    if request.session_id:
        language_preference = get_session_language_preference(request.session_id)

    # Route the message
    routing = route_message(
        message=request.message,
        history=history,
        previous_code=previous_code,
        language_preference=language_preference,
    )
    
    if routing.get("success") is False:
        raise HTTPException(status_code=502, detail=routing.get("message", "AI service is temporarily unavailable."))

    # Save detected language if found
    if routing.get("detected_language") and request.session_id:
        set_session_language_preference(
            request.session_id, routing["detected_language"]
        )
        language_preference = routing["detected_language"]

    # CHAT / REWRITE — instant response
    if routing["route"] in ("chat", "rewrite"):
        create_job(job_id, request.message, request.session_id)
        
        result_data = {}
        if routing.get("project_files"):
            from backend.services.artifacts import save_project
            manifest = save_project(routing["project_files"], request.session_id, request.message[:50])
            result_data["project_files"] = routing["project_files"]
            result_data["artifact_id"] = manifest["artifact_id"]
            response_text = routing.get("response", "Generated updated project.")
        else:
            result_data["direct_response"] = routing.get("response", "Done.")
            response_text = routing.get("response", "Done.")

        update_job(
            job_id,
            status="completed",
            current_node="Completed",
            progress=100,
            result=result_data,
        )
        if request.session_id:
            add_message(request.session_id, "user", request.message)
            add_message(request.session_id, "assistant", response_text)
            
        return ProcessResponse(job_id=job_id, status="completed", result=result_data)

    # UPDATE / CODE — full LangGraph pipeline
    create_job(job_id, request.message, request.session_id)
    background_tasks.add_task(
        run_job,
        job_id,
        request.message,
        request.session_id,
        language_preference,
        routing["route"] == "update",
        active_project_state,
        history
    )
    return ProcessResponse(job_id=job_id, status="queued")


@router.get("/status/{job_id}", response_model=StatusResponse)
def get_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return StatusResponse(**job)