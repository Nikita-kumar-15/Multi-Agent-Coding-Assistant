"""
Helpers for uploaded files persisted on disk by session.
"""

from __future__ import annotations

from pathlib import Path

UPLOAD_DIR = Path("./uploads")


def list_uploaded_files(session_id: str) -> list[dict]:
    session_dir = UPLOAD_DIR / session_id
    if not session_dir.exists():
        return []
    files = []
    for path in session_dir.rglob("*"):
        if path.is_file():
            files.append(
                {
                    "filename": path.relative_to(session_dir).as_posix(),
                    "path": str(path),
                    "size": path.stat().st_size,
                }
            )
    return sorted(files, key=lambda item: item["filename"])
