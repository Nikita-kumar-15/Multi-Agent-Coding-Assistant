# backend/services/job_store.py
"""
CRUD helper functions for Job records.
Keeps database logic out of the API layer and the background worker.
"""

import json
from backend.models.database import Job, get_db_session


def create_job(job_id: str, user_request: str, session_id: str | None = None) -> None:
    db = get_db_session()
    try:
        job = Job(
            job_id=job_id,
            status="queued",
            current_node=None,
            progress=0,
            session_id=session_id,
            user_request=user_request,
        )
        db.add(job)
        db.commit()
    finally:
        db.close()


def update_job(
    job_id: str,
    status: str = None,
    current_node: str = None,
    progress: int = None,
    result: dict = None,
    error: str = None,
) -> None:
    db = get_db_session()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            return
        if status is not None:
            job.status = status
        if current_node is not None:
            job.current_node = current_node
        if progress is not None:
            job.progress = progress
        if result is not None:
            job.result_json = json.dumps(result, default=str)
        if error is not None:
            job.error = error
        db.commit()
    finally:
        db.close()


def get_job(job_id: str) -> dict | None:
    db = get_db_session()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            return None
        return {
            "job_id": job.job_id,
            "status": job.status,
            "current_node": job.current_node,
            "progress": job.progress,
            "session_id": job.session_id,
            "user_request": job.user_request,
            "result": json.loads(job.result_json) if job.result_json else None,
            "error": job.error,
        }
    finally:
        db.close()


def get_jobs_for_session(session_id: str) -> list[dict]:
    db = get_db_session()
    try:
        jobs = (
            db.query(Job)
            .filter(Job.session_id == session_id)
            .order_by(Job.created_at.desc())
            .all()
        )
        return [
            {
                "job_id": job.job_id,
                "status": job.status,
                "current_node": job.current_node,
                "progress": job.progress,
                "session_id": job.session_id,
                "user_request": job.user_request,
                "result": json.loads(job.result_json) if job.result_json else None,
                "error": job.error,
            }
            for job in jobs
        ]
    finally:
        db.close()
