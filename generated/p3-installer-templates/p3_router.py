from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .cosmos_interaction_store import CosmosInteractionStore


router = APIRouter(prefix="/p3", tags=["p3"])


@lru_cache(maxsize=1)
def _store() -> CosmosInteractionStore:
    return CosmosInteractionStore()


class SessionCreate(BaseModel):
    title: str | None = None


class InteractionCreate(BaseModel):
    session_id: str
    request_id: str
    question: str
    answer: str
    grounded: bool
    citations: list[Any] = Field(default_factory=list)
    technology_ids: list[str] = Field(default_factory=list)


class FeedbackCreate(BaseModel):
    session_id: str
    request_id: str
    rating: int = Field(ge=-1, le=1)
    comment: str | None = None


@router.post("/sessions")
def create_session(payload: SessionCreate):
    doc = _store().create_session(title=payload.title)
    return {
        "status": "PASS",
        "session_id": doc["sessionId"],
        "credential_mode": _store().credential_mode,
    }


@router.post("/interactions")
def create_interaction(payload: InteractionCreate):
    try:
        doc = _store().add_interaction(
            session_id=payload.session_id,
            request_id=payload.request_id,
            question=payload.question,
            answer=payload.answer,
            grounded=payload.grounded,
            citations=payload.citations,
            technology_ids=payload.technology_ids,
        )
        return {
            "status": "PASS",
            "id": doc["id"],
            "session_id": doc["sessionId"],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/feedback")
def create_feedback(payload: FeedbackCreate):
    try:
        doc = _store().add_feedback(
            session_id=payload.session_id,
            request_id=payload.request_id,
            rating=payload.rating,
            comment=payload.comment,
        )
        return {
            "status": "PASS",
            "id": doc["id"],
            "session_id": doc["sessionId"],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/sessions/{session_id}")
def read_session(session_id: str):
    docs = _store().get_session_documents(session_id)
    return {
        "status": "PASS",
        "session_id": session_id,
        "count": len(docs),
        "documents": docs,
    }
