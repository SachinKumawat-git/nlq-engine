from __future__ import annotations
from fastapi import APIRouter, HTTPException

from app.db import load_profile
from app.jobs import submit_job
from app.llm_client import get_llm_client
from app.models import JobAccepted, QueryRequest
from app.nl_query import answer_question

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=JobAccepted, status_code=202)
async def query_dataset(req: QueryRequest):
    try:
        profile = load_profile(req.dataset_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown dataset_id '{req.dataset_id}'. Ingest a CSV first via POST /ingest.",
        )

    llm = get_llm_client()

    def _work():
        result = answer_question(llm, profile, req.dataset_id, req.question)
        return result.model_dump()

    job = submit_job("query", _work)
    return JobAccepted(
        job_id=job.job_id,
        poll_url=f"/jobs/{job.job_id}",
        stream_url=f"/jobs/{job.job_id}/stream",
    )
