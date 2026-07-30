# backend/api/debug.py
"""
Debug API: accepts an uploaded code file, runs the Debugger Agent
on it, and returns issues found, corrected code, and explanation.
"""

from typing import Annotated
from fastapi import APIRouter, UploadFile, File

from backend.models.schemas import DebugResponse
from backend.agents.debugger_agent import debugger_agent

router = APIRouter()


@router.post("/debug", response_model=DebugResponse)
async def debug_code(
    file: Annotated[UploadFile, File(...)],
):
    content_bytes = await file.read()
    code = content_bytes.decode("utf-8", errors="ignore")

    result = debugger_agent(code, file.filename)

    return DebugResponse(
        filename=file.filename,
        language=result["language"],
        issues_found=result["issues_found"],
        corrected_code=result["corrected_code"],
        explanation=result["explanation"],
    )