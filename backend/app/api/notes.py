"""复盘笔记 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.database import get_session
from ..schemas.note import (
    NoteCreateRequest,
    NoteDetail,
    NoteListResponse,
    NoteSummary,
    NoteUpdateRequest,
)
from ..services import note_service

router = APIRouter()


@router.get("/notes/tags", response_model=list[str])
def list_tags(session: Session = Depends(get_session)) -> list[str]:
    return note_service.list_all_tags(session)


@router.get("/notes", response_model=NoteListResponse)
def list_notes(
    q: str = Query(default="", max_length=100),
    tag: str = Query(default="", max_length=50),
    code: str = Query(default="", max_length=16),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> NoteListResponse:
    items, total = note_service.list_notes(
        session, q=q, tag=tag, code=code, page=page, page_size=page_size
    )
    return NoteListResponse(
        items=[NoteSummary.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/notes", response_model=NoteDetail)
def create_note(
    req: NoteCreateRequest,
    session: Session = Depends(get_session),
) -> NoteDetail:
    note = note_service.create_note(
        session,
        title=req.title,
        content_html=req.content_html,
        trade_date=req.trade_date,
        tags=req.tags,
    )
    session.commit()
    return NoteDetail.model_validate(note)


@router.get("/notes/{note_id}", response_model=NoteDetail)
def get_note(
    note_id: str,
    session: Session = Depends(get_session),
) -> NoteDetail:
    note = note_service.get_note(session, note_id)
    if note is None:
        raise HTTPException(404, "note not found")
    return NoteDetail.model_validate(note)


@router.put("/notes/{note_id}", response_model=NoteDetail)
def update_note(
    note_id: str,
    req: NoteUpdateRequest,
    session: Session = Depends(get_session),
) -> NoteDetail:
    note = note_service.get_note(session, note_id)
    if note is None:
        raise HTTPException(404, "note not found")
    note_service.update_note(
        session,
        note,
        title=req.title,
        content_html=req.content_html,
        trade_date=req.trade_date,
        tags=req.tags,
    )
    session.commit()
    return NoteDetail.model_validate(note)


@router.delete("/notes/{note_id}")
def delete_note(
    note_id: str,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    note = note_service.get_note(session, note_id)
    if note is None:
        raise HTTPException(404, "note not found")
    note_service.delete_note(session, note)
    session.commit()
    return {"status": "ok"}
