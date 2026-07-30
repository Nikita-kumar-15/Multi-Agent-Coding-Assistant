# backend/api/upload.py
"""
File upload API: accepts multiple files (and recursively scanned
folders via webkitdirectory on the frontend), extracts text,
chunks it, and stores embeddings in the vector store.
"""

import os
import uuid
import shutil
from typing import List, Optional, Annotated
from fastapi import APIRouter, UploadFile, File, Form

from backend.models.schemas import UploadResponse
from backend.services.file_parser import extract_text
from backend.services.vectorstore import add_file_to_vectorstore

router = APIRouter()

UPLOAD_DIR = "./uploads"


@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    files: Annotated[List[UploadFile], File(...)],
    session_id: Annotated[Optional[str], Form()] = None,
):
    if not session_id:
        session_id = str(uuid.uuid4())

    session_upload_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_upload_dir, exist_ok=True)

    total_chunks = 0
    files_processed = 0
    skipped_files = []

    for upload_file in files:
        relative_path = upload_file.filename
        dest_path = os.path.join(session_upload_dir, relative_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        with open(dest_path, "wb") as f:
            shutil.copyfileobj(upload_file.file, f)

        text_content = extract_text(dest_path)

        if not text_content.strip():
            skipped_files.append(relative_path)
            continue

        chunks_added = add_file_to_vectorstore(dest_path, text_content, session_id)
        total_chunks += chunks_added
        files_processed += 1

    return UploadResponse(
        session_id=session_id,
        files_processed=files_processed,
        total_chunks=total_chunks,
        skipped_files=skipped_files,
    )