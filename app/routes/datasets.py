from __future__ import annotations
from fastapi import APIRouter, HTTPException

from app.db import load_profile, sample_rows
from app.models import DatasetSummary

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("/{dataset_id}", response_model=DatasetSummary)
async def get_dataset(dataset_id: str):
    try:
        profile = load_profile(dataset_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Unknown dataset_id '{dataset_id}'.")
    return DatasetSummary(
        dataset_id=profile.dataset_id,
        row_count=profile.row_count,
        columns=[c.__dict__ for c in profile.columns],
        sample_rows=sample_rows(dataset_id, limit=5),
    )
