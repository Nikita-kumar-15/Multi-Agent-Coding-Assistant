"""
Generated project artifact endpoints.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend.models.schemas import ArtifactListResponse, DownloadProjectRequest
from backend.services.artifacts import (
    delete_all_artifacts,
    delete_artifact,
    delete_artifacts_for_session,
    get_artifact,
    list_artifacts,
)

router = APIRouter(tags=["artifacts"])


@router.get("/artifacts", response_model=ArtifactListResponse)
def get_artifacts(session_id: str | None = Query(default=None)):
    return ArtifactListResponse(artifacts=list_artifacts(session_id))


def _artifact_zip_response(artifact: dict):
    zip_path = Path(artifact["zip_path"])
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Artifact zip not found")

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{artifact['artifact_id']}.zip",
    )


@router.post("/download-project")
def download_project(request: DownloadProjectRequest):
    artifact = None
    if request.artifact_id:
        artifact = get_artifact(request.artifact_id)
    elif request.job_id:
        artifact = next(
            (item for item in list_artifacts() if item.get("job_id") == request.job_id),
            None,
        )

    if not artifact:
        raise HTTPException(status_code=404, detail="Project artifact not found")
    return _artifact_zip_response(artifact)


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str):
    artifact = get_artifact(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return _artifact_zip_response(artifact)


@router.delete("/artifacts/{artifact_id}")
def remove_artifact(artifact_id: str):
    if not delete_artifact(artifact_id):
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"deleted": True, "artifact_id": artifact_id}


@router.delete("/artifacts")
def remove_artifacts(session_id: str | None = Query(default=None)):
    deleted = (
        delete_artifacts_for_session(session_id)
        if session_id
        else delete_all_artifacts()
    )
    return {"deleted": deleted, "session_id": session_id}
