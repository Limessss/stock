"""复盘笔记 CRUD。"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from ..core.time_utils import utc_now
from ..models.review_note import ReviewNote

_STOCK_CODE_RE = re.compile(r'data-code="([A-Z0-9]+)"', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def parse_linked_codes(content_html: str) -> list[str]:
    codes = _STOCK_CODE_RE.findall(content_html or "")
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        key = c.upper()
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def parse_mentions(content_html: str) -> list[dict[str, str]]:
    """从正文 HTML 解析股票标签 code + name。"""
    html = content_html or ""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'<span[^>]*class="[^"]*stock-mention[^"]*"[^>]*>',
        html,
        re.IGNORECASE,
    ):
        tag = m.group(0)
        code_m = re.search(r'data-code="([^"]+)"', tag, re.IGNORECASE)
        name_m = re.search(r'data-name="([^"]+)"', tag, re.IGNORECASE)
        if not code_m:
            continue
        code = code_m.group(1).upper()
        if code in seen:
            continue
        seen.add(code)
        name = name_m.group(1) if name_m else code
        out.append({"code": code, "name": name})
    return out


def html_excerpt(content_html: str, max_len: int = 120) -> str:
    text = _TAG_RE.sub("", content_html or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def _to_summary(note: ReviewNote) -> dict:
    return {
        "id": note.id,
        "title": note.title,
        "trade_date": note.trade_date,
        "tags": note.tags or [],
        "linked_codes": note.linked_codes or [],
        "mentions": parse_mentions(note.content_html),
        "excerpt": html_excerpt(note.content_html),
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


def list_notes(
    session: Session,
    *,
    q: str = "",
    tag: str = "",
    code: str = "",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    stmt: Select = select(ReviewNote)
    count_stmt = select(func.count()).select_from(ReviewNote)

    if q.strip():
        like = f"%{q.strip()}%"
        cond = or_(ReviewNote.title.ilike(like), ReviewNote.content_html.ilike(like))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    if tag.strip():
        stmt = stmt.where(ReviewNote.tags.contains([tag.strip()]))
        count_stmt = count_stmt.where(ReviewNote.tags.contains([tag.strip()]))

    if code.strip():
        norm = code.strip().upper()
        stmt = stmt.where(ReviewNote.linked_codes.contains([norm]))
        count_stmt = count_stmt.where(ReviewNote.linked_codes.contains([norm]))

    total = session.scalar(count_stmt) or 0
    rows = session.scalars(
        stmt.order_by(ReviewNote.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_to_summary(n) for n in rows], int(total)


def get_note(session: Session, note_id: str) -> ReviewNote | None:
    return session.get(ReviewNote, note_id)


def create_note(
    session: Session,
    *,
    title: str,
    content_html: str,
    trade_date: str | None,
    tags: list[str],
) -> ReviewNote:
    now = utc_now()
    note = ReviewNote(
        id=str(uuid.uuid4()),
        title=title.strip() or "无标题",
        content_html=content_html or "",
        trade_date=trade_date,
        tags=tags or [],
        linked_codes=parse_linked_codes(content_html),
        created_at=now,
        updated_at=now,
    )
    session.add(note)
    session.flush()
    return note


def update_note(
    session: Session,
    note: ReviewNote,
    *,
    title: str | None = None,
    content_html: str | None = None,
    trade_date: str | None = None,
    tags: list[str] | None = None,
) -> ReviewNote:
    if title is not None:
        note.title = title.strip() or "无标题"
    if content_html is not None:
        note.content_html = content_html
        note.linked_codes = parse_linked_codes(content_html)
    if trade_date is not None:
        note.trade_date = trade_date or None
    if tags is not None:
        note.tags = tags
    note.updated_at = utc_now()
    session.flush()
    return note


def delete_note(session: Session, note: ReviewNote) -> None:
    session.delete(note)


def list_all_tags(session: Session) -> list[str]:
    rows = session.scalars(select(ReviewNote.tags)).all()
    seen: set[str] = set()
    out: list[str] = []
    for tags in rows:
        for t in tags or []:
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return sorted(out)
