from __future__ import annotations
import asyncio
import json

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.jobs import get_job, subscribe
from app.models import JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id '{job_id}'.")
    return JobStatus(**job.to_public())


@router.get("/{job_id}/stream")
async def stream_job_status(job_id: str):
    q = subscribe(job_id)
    if q is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id '{job_id}'.")

    async def event_gen():
        loop = asyncio.get_event_loop()
        while True:
            payload = await loop.run_in_executor(None, q.get)
            yield {"event": "status", "data": json.dumps(payload, default=str)}
            if payload["status"] in ("done", "failed"):
                break

    return EventSourceResponse(event_gen())
