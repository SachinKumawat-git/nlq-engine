from __future__ import annotations
import os
import uuid

from fastapi import APIRouter, UploadFile, File, HTTPException

from app.config import settings
from app.db import ingest_csv
from app.jobs import submit_job
from app.models import JobAccepted

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("", response_model=JobAccepted, status_code=202)
async def ingest_dataset(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    os.makedirs(settings.upload_dir, exist_ok=True)
    tmp_name = f"{uuid.uuid4().hex}_{file.filename}"
    tmp_path = os.path.join(settings.upload_dir, tmp_name)

    size = 0
    max_bytes = settings.max_upload_mb * 1024 * 1024
    with open(tmp_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                out.close()
                os.remove(tmp_path)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {settings.max_upload_mb}MB limit.",
                )
            out.write(chunk)

    def _work():
        try:
            profile = ingest_csv(tmp_path, file.filename)
            return {
                "dataset_id": profile.dataset_id,
                "row_count": profile.row_count,
                "columns": [c.__dict__ for c in profile.columns],
            }
        finally:
            # The DuckDB database/profile are the durable ingestion artifacts;
            # do not retain duplicate upload files after the job finishes.
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    job = submit_job("ingest", _work)
    return JobAccepted(
        job_id=job.job_id,
        poll_url=f"/jobs/{job.job_id}",
        stream_url=f"/jobs/{job.job_id}/stream",
    )
