from __future__ import annotations
from fastapi import APIRouter
from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "llm_model": (
            settings.ollama_model
            if settings.llm_provider == "ollama"
            else settings.openai_model
        ),
    }
