from pydantic import BaseModel
from typing import Optional


class EntityCandidateRunStart(BaseModel):
    query: str
    thread_id: str
    checkpoint_ns: str


class EntityCandidateRunComplete(BaseModel):
    intel_run_id: str
    pipeline_version: str
    has_candidates: bool


class EntityCandidateRunError(BaseModel):
    error: str
    error_type: str
