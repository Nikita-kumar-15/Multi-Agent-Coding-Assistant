# backend/services/session_store.py
"""
CRUD for ChatSession and ChatMessage.
Includes language preference storage per session.
"""

from backend.models.database import ChatSession, ChatMessage, get_db_session
import json


def create_session(session_id: str, title: str = "New Chat") -> None:
    db = get_db_session()
    try:
        session = ChatSession(session_id=session_id, title=title)
        db.add(session)
        db.commit()
    finally:
        db.close()


def get_all_sessions() -> list[dict]:
    db = get_db_session()
    try:
        sessions = (
            db.query(ChatSession)
            .order_by(ChatSession.created_at.desc())
            .all()
        )
        return [
            {
                "session_id": s.session_id,
                "title": s.title,
                "created_at": str(s.created_at),
            }
            for s in sessions
        ]
    finally:
        db.close()


def session_exists(session_id: str) -> bool:
    db = get_db_session()
    try:
        return (
            db.query(ChatSession)
            .filter(ChatSession.session_id == session_id)
            .first() is not None
        )
    finally:
        db.close()


def add_message(session_id: str, role: str, content: str) -> None:
    db = get_db_session()
    try:
        msg = ChatMessage(
            session_id=session_id, role=role, content=str(content)
        )
        db.add(msg)
        db.commit()
    finally:
        db.close()


def get_messages(session_id: str) -> list[dict]:
    db = get_db_session()
    try:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        return [{"role": m.role, "content": m.content} for m in messages]
    finally:
        db.close()


def rename_session(session_id: str, title: str) -> bool:
    cleaned_title = (title or "").strip()
    if not cleaned_title:
        return False

    db = get_db_session()
    try:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.session_id == session_id)
            .first()
        )
        if not session:
            return False

        session.title = cleaned_title[:120]
        db.commit()
        return True
    finally:
        db.close()


def pin_session(session_id: str, pinned: bool) -> bool:
    db = get_db_session()
    try:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.session_id == session_id)
            .first()
        )
        if not session:
            return False

        session.pinned = 1 if pinned else 0
        db.commit()
        return True
    finally:
        db.close()


def update_session_title(session_id: str, title: str) -> None:
    rename_session(session_id, title)


def delete_session(session_id: str) -> None:
    db = get_db_session()
    try:
        db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).delete()
        db.query(ChatSession).filter(
            ChatSession.session_id == session_id
        ).delete()
        db.commit()
    finally:
        db.close()


# In-memory language preference store (session scoped)
_language_prefs: dict[str, str] = {}


def get_session_language_preference(session_id: str) -> str | None:
    return _language_prefs.get(session_id)


def set_session_language_preference(session_id: str, language: str) -> None:
    _language_prefs[session_id] = language


def get_active_project_state(session_id: str) -> dict | None:
    db = get_db_session()
    try:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.session_id == session_id)
            .first()
        )
        if not session or not session.active_project_state_json:
            print(f"[SESSION_STORE] Loaded active project state for session {session_id}: EMPTY/None")
            return None
        state = json.loads(session.active_project_state_json)
        print(f"[SESSION_STORE] Loaded active project state for session {session_id}: {len(state.get('files', {}))} files found.")
        return state
    finally:
        db.close()


def update_active_project_state(session_id: str, state: dict) -> bool:
    db = get_db_session()
    try:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.session_id == session_id)
            .first()
        )
        if not session:
            return False

        session.active_project_state_json = json.dumps(state)
        db.commit()
        return True
    finally:
        db.close()


def get_session_workflow_id(session_id: str) -> str | None:
    db = get_db_session()
    try:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.session_id == session_id)
            .first()
        )
        if not session or not session.workflow_id:
            return None
        return session.workflow_id
    finally:
        db.close()


def set_session_workflow_id(session_id: str, workflow_id: str) -> bool:
    db = get_db_session()
    try:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.session_id == session_id)
            .first()
        )
        if not session:
            return False

        session.workflow_id = workflow_id
        db.commit()
        return True
    finally:
        db.close()