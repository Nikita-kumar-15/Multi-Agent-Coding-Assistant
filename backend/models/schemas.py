# backend/models/schemas.py
"""
Pydantic schemas for API request/response validation.
"""

from pydantic import BaseModel
from typing import Optional, Any, List


class ProcessRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    session_token: Optional[str] = None

    @property
    def effective_session_id(self) -> Optional[str]:
        return self.session_token or self.session_id


class ProcessResponse(BaseModel):
    job_id: str
    status: str
    workflow_id: Optional[str] = None
    session_id: Optional[str] = None
    session_token: Optional[str] = None
    result: Optional[Any] = None


class StatusResponse(BaseModel):
    job_id: str
    status: str
    current_node: Optional[str] = None
    progress: int
    result: Optional[Any] = None
    final_result: Optional[Any] = None
    error: Optional[str] = None


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    session_token: Optional[str] = None
    message: str

    @property
    def effective_session_id(self) -> Optional[str]:
        return self.session_token or self.session_id


class ChatResponse(BaseModel):
    response: str
    session_id: str
    session_token: Optional[str] = None


class PollResponse(BaseModel):
    workflow_id: str
    status: str
    final_result: Optional[Any] = None
    error: Optional[str] = None


class UploadResponse(BaseModel):
    session_id: str
    files_processed: int
    total_chunks: int
    skipped_files: List[str]


class DebugResponse(BaseModel):
    filename: str
    language: str
    issues_found: str
    corrected_code: str
    explanation: str


class SessionInfo(BaseModel):
    session_id: str
    session_token: Optional[str] = None
    title: str
    pinned: bool = False
    created_at: str


class RenameSessionRequest(BaseModel):
    title: str


class SessionListResponse(BaseModel):
    sessions: List[SessionInfo]


class MessageInfo(BaseModel):
    role: str
    content: str


class SessionMessagesResponse(BaseModel):
    session_id: str
    session_token: Optional[str] = None
    messages: List[MessageInfo]


class UploadedFileInfo(BaseModel):
    filename: str
    path: str
    size: int


class WorkflowInfo(BaseModel):
    job_id: str
    status: str
    current_node: Optional[str] = None
    progress: int
    result: Optional[Any] = None
    error: Optional[str] = None


class AgentEventInfo(BaseModel):
    id: int
    job_id: str
    session_id: Optional[str] = None
    agent: str
    content: str
    metadata: Optional[Any] = None
    created_at: str


class SessionDetailResponse(BaseModel):
    session_id: str
    session_token: Optional[str] = None
    messages: List[MessageInfo]
    uploaded_files: List[UploadedFileInfo]
    artifacts: List[Any]
    workflows: List[WorkflowInfo]
    agent_events: List[AgentEventInfo]


class CreateSessionResponse(BaseModel):
    session_id: str
    session_token: Optional[str] = None
    title: str


class ArtifactInfo(BaseModel):
    artifact_id: str
    job_id: str
    session_id: Optional[str] = None
    created_at: str
    request: str
    files: List[str]
    zip_exists: bool = True


class ArtifactListResponse(BaseModel):
    artifacts: List[ArtifactInfo]


class DownloadProjectRequest(BaseModel):
    artifact_id: Optional[str] = None
    job_id: Optional[str] = None
