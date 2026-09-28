"""Pydantic request/response models."""
from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


class JobAccepted(BaseModel):
    job_id: str
    status: str = "queued"
    poll_url: str
    stream_url: Optional[str] = None


class JobStatus(BaseModel):
    job_id: str
    type: str
    status: str  # queued | running | done | failed
    created_at: float
    updated_at: float
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class DatasetSummary(BaseModel):
    dataset_id: str
    row_count: int
    columns: list[dict[str, Any]]
    sample_rows: list[dict[str, Any]]


class QueryRequest(BaseModel):
    dataset_id: str = Field(..., description="ID returned by /ingest")
    question: str = Field(..., min_length=1, max_length=2000)


class QueryResult(BaseModel):
    question: str
    answerable: bool
    answer: Optional[str] = None
    sql: Optional[str] = None
    columns: Optional[list[str]] = None
    rows: Optional[list[list[Any]]] = None
    row_count: Optional[int] = None
    refusal_reason: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: str = "internal_error"
