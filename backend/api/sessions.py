# backend/api/sessions.py
"""
Session management API: create sessions, list sessions,
retrieve a session's message history, and delete sessions
with full cascading cleanup.
"""

import uuid
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException

from backend.models.schemas import (
    SessionListResponse,
    SessionMessagesResponse,
    CreateSessionResponse,
    RenameSessionRequest,
    SessionDetailResponse,
)
from backend.services.session_store import (
    create_session,
    delete_session,
    get_all_sessions,
    get_messages,
    rename_session,
    session_exists,
)
from backend.services.artifacts import delete_artifacts_for_session, list_artifacts
from backend.services.job_store import get_jobs_for_session
from backend.services.upload_store import list_uploaded_files
from backend.services.vectorstore import delete_session_memory
from backend.services.workflow_events import (
    delete_workflow_events_for_session,
    get_workflow_events,
)
from backend.terminal.logger import tlog

router = APIRouter()
UPLOAD_DIR = Path("./uploads")


@router.post("/sessions", response_model=CreateSessionResponse)
def new_session():
    session_id = str(uuid.uuid4())
    create_session(session_id)
    return CreateSessionResponse(
        session_id=session_id,
        session_token=session_id,
        title="New Chat",
    )


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions():
    return SessionListResponse(sessions=get_all_sessions())


@router.get("/sessions/{session_id}/messages", response_model=SessionMessagesResponse)
def session_messages(session_id: str):
    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionMessagesResponse(
        session_id=session_id,
        session_token=session_id,
        messages=get_messages(session_id),
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def session_detail(session_id: str):
    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDetailResponse(
        session_id=session_id,
        session_token=session_id,
        messages=get_messages(session_id),
        uploaded_files=list_uploaded_files(session_id),
        artifacts=list_artifacts(session_id),
        workflows=get_jobs_for_session(session_id),
        agent_events=get_workflow_events(session_id=session_id),
    )


@router.patch("/sessions/{session_id}/pin")
def pin_chat(session_id: str, request: dict):
    from backend.services.session_store import pin_session
    if not pin_session(session_id, request.get("pinned", False)):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"pinned": request.get("pinned", False), "session_id": session_id}


@router.patch("/sessions/{session_id}")
def rename_chat(session_id: str, request: RenameSessionRequest):
    if not rename_session(session_id, request.title):
        raise HTTPException(status_code=404, detail="Session not found or empty title")
    return {"renamed": True, "session_id": session_id, "title": request.title.strip()[:120]}


@router.delete("/conversation/{session_id}")
def delete_conversation(session_id: str):
    """
    Full cascading delete: session + messages + jobs + workflow events
    + artifacts + vector memory + uploaded files.
    """
    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    tlog.info("System", f"Deleting session {session_id[:8]}...")

    # 1. Delete workflow events
    events_deleted = delete_workflow_events_for_session(session_id)

    # 2. Delete artifacts (files + zips)
    artifacts_deleted = delete_artifacts_for_session(session_id)

    # 3. Delete vector memory
    delete_session_memory(session_id)

    # 4. Delete uploaded files from disk
    upload_dir = UPLOAD_DIR / session_id
    if upload_dir.exists():
        shutil.rmtree(upload_dir)

    # 5. Delete session + messages + jobs (cascading in session_store)
    session_deleted = delete_session(session_id)

    tlog.success("System", f"Session deleted (events={events_deleted}, artifacts={artifacts_deleted})")

    return {
        "deleted": session_deleted,
        "session_id": session_id,
        "events_deleted": events_deleted,
        "artifacts_deleted": artifacts_deleted,
    }


@router.delete("/sessions/{session_id}")
def delete_session_endpoint(session_id: str):
    return delete_conversation(session_id)
