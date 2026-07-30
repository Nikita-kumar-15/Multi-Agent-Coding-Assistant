from backend.models.database import ChatSession, get_db_session, init_db
from backend.services.session_store import (
    create_session,
    delete_session,
    pin_session,
    rename_session,
    session_exists,
)


def test_rename_and_pin_session():
    init_db()
    session_id = "test-session-rename-pin"

    create_session(session_id, "Original")
    assert session_exists(session_id)

    assert rename_session(session_id, "Updated") is True
    assert pin_session(session_id, True) is True

    db = get_db_session()
    try:
        session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        assert session is not None
        assert session.title == "Updated"
        assert session.pinned == 1
    finally:
        db.close()

    delete_session(session_id)
    assert session_exists(session_id) is False
