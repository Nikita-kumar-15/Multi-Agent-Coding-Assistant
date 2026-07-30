"""
Persistent agent/workflow conversation events with deduplication.
"""

from __future__ import annotations

import hashlib
import json

from backend.models.database import WorkflowEvent, get_db_session


def _compute_hash(job_id: str, agent: str, content: str) -> str:
    """Compute a dedup hash from job_id + agent + content."""
    raw = f"{job_id}|{agent}|{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def add_workflow_event(
    *,
    job_id: str,
    session_id: str | None,
    agent: str,
    content: str,
    metadata: dict | None = None,
) -> None:
    """Inserts a workflow event, skipping exact duplicates per job."""
    ch = _compute_hash(job_id, agent, content)
    db = get_db_session()
    try:
        # Check for duplicate
        existing = (
            db.query(WorkflowEvent)
            .filter(
                WorkflowEvent.job_id == job_id,
                WorkflowEvent.content_hash == ch,
            )
            .first()
        )
        if existing is not None:
            return  # skip duplicate

        event = WorkflowEvent(
            job_id=job_id,
            session_id=session_id,
            agent=agent,
            content=content,
            metadata_json=json.dumps(metadata or {}, default=str),
            content_hash=ch,
        )
        db.add(event)
        db.commit()
    finally:
        db.close()


def get_workflow_events(session_id: str | None = None, job_id: str | None = None) -> list[dict]:
    db = get_db_session()
    try:
        query = db.query(WorkflowEvent)
        if session_id:
            query = query.filter(WorkflowEvent.session_id == session_id)
        if job_id:
            query = query.filter(WorkflowEvent.job_id == job_id)
        events = query.order_by(WorkflowEvent.created_at.asc()).all()
        return [
            {
                "id": event.id,
                "job_id": event.job_id,
                "session_id": event.session_id,
                "agent": event.agent,
                "content": event.content,
                "metadata": json.loads(event.metadata_json) if event.metadata_json else {},
                "created_at": str(event.created_at),
            }
            for event in events
        ]
    finally:
        db.close()


def delete_workflow_events_for_session(session_id: str) -> int:
    db = get_db_session()
    try:
        count = db.query(WorkflowEvent).filter(WorkflowEvent.session_id == session_id).delete()
        db.commit()
        return count
    finally:
        db.close()


def delete_workflow_events_for_job(job_id: str) -> int:
    """Deletes all workflow events for a specific job."""
    db = get_db_session()
    try:
        count = db.query(WorkflowEvent).filter(WorkflowEvent.job_id == job_id).delete()
        db.commit()
        return count
    finally:
        db.close()
