# backend/models/database.py
"""
SQLite database setup using SQLAlchemy.
Stores job records, chat sessions, and messages for persistence
across app restarts and for the polling/chat APIs to query.
"""

from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, ForeignKey, text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

DATABASE_URL = "sqlite:///./jobs.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(String, primary_key=True, index=True)
    status = Column(String, default="queued")
    current_node = Column(String, nullable=True)
    progress = Column(Integer, default=0)
    session_id = Column(String, ForeignKey("chat_sessions.session_id"), index=True, nullable=True)
    user_request = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    session_id = Column(String, primary_key=True, index=True)
    title = Column(String, default="New Chat")
    pinned = Column(Integer, default=0)
    active_project_state_json = Column(Text, nullable=True)
    workflow_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("chat_sessions.session_id"), index=True)
    role = Column(String)          # "user" or "assistant"
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class WorkflowEvent(Base):
    __tablename__ = "workflow_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey("jobs.job_id"), index=True)
    session_id = Column(String, ForeignKey("chat_sessions.session_id"), index=True, nullable=True)
    agent = Column(String, index=True)
    content = Column(Text)
    metadata_json = Column(Text, nullable=True)
    content_hash = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Creates tables if they don't exist. Call once at app startup."""
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        # Migration: add session_id to jobs if missing
        job_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(jobs)")).fetchall()
        }
        if "session_id" not in job_columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN session_id VARCHAR"))

        # Migration: add content_hash to workflow_events if missing
        event_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(workflow_events)")).fetchall()
        }
        if "content_hash" not in event_columns:
            connection.execute(text("ALTER TABLE workflow_events ADD COLUMN content_hash VARCHAR"))

        # Migration: add pinned to chat_sessions if missing
        session_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(chat_sessions)")).fetchall()
        }
        if "pinned" not in session_columns:
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN pinned INTEGER DEFAULT 0"))
            
        if "active_project_state_json" not in session_columns:
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN active_project_state_json TEXT"))

        # Migration: add workflow_id to chat_sessions if missing
        if "workflow_id" not in session_columns:
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN workflow_id VARCHAR"))


def get_db_session():
    """Returns a new DB session. Caller is responsible for closing it."""
    return SessionLocal()
