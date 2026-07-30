"""
HITL chat API.

Human replies and lightweight conversation turns go through this endpoint.
Long-running code generation remains on /process + /poll/{workflow_id}.
"""

import uuid

from fastapi import APIRouter, HTTPException

from backend.agents.conversation_agent import route_message
from backend.models.schemas import ChatRequest, ChatResponse
from backend.services.session_store import (
    add_message,
    create_session,
    get_messages,
    session_exists,
)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    session_id = request.effective_session_id or str(uuid.uuid4())
    if not session_exists(session_id):
        create_session(session_id)

    history = get_messages(session_id)
    previous_code = None
    previous_language = "Python"
    for msg in reversed(history):
        if msg["role"] == "assistant" and "```" in msg["content"]:
            previous_code = msg["content"]
            for lang in ["python", "java", "javascript", "typescript", "html", "css", "c++", "c"]:
                if f"```{lang}" in msg["content"].lower():
                    previous_language = lang.capitalize()
                    break
            break

    add_message(session_id, "user", request.message)

    try:
        routed = route_message(
            message=request.message,
            history=history,
            previous_code=previous_code,
            previous_language=previous_language,
        )
        response_text = routed.get("response") or "Got it. Send a build request when you want me to start the workflow."
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    add_message(session_id, "assistant", response_text)
    return ChatResponse(
        response=response_text,
        session_id=session_id,
        session_token=session_id,
    )
