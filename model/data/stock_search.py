"""股票搜索（代码 / 名称 / 拼音首字母）。"""
from __future__ import annotations

import re
from functools import lru_cache

from .names import _load

try:
    from pypinyin import Style, lazy_pinyin

    def _name_initials(name: str) -> str:
        parts = lazy_pinyin(name, style=Style.FIRST_LETTER, errors="ignore")
        return "".join(p for p in parts if p).upper()
except ImportError:

    def _name_initials(name: str) -> str:
        return ""


def _market_label(code: str) -> str:
    c = code.upper()
    if c.startswith("SH"):
        return "沪A"
    if c.startswith("SZ"):
        if c[2:].startswith(("0", "3")):
            return "深A"
        return "深A"
    return "A股"


def _normalize_query(q: str) -> str:
    return q.strip().upper()


def _code_digits(code: str) -> str:
    return re.sub(r"[^0-9]", "", code.upper())


def _score_item(code: str, name: str, query: str, query_digits: str) -> int:
    code_u = code.upper()
    digits = _code_digits(code_u)
    initials = _name_initials(name)

    if query_digits and digits.startswith(query_digits):
        return 1000 - len(query_digits)
    if code_u.startswith(query):
        return 900 - len(query)
    if query_digits and query_digits in digits:
        return 800
    if query and query in code_u:
        return 700
    if query and name.upper().find(query) >= 0:
        return 600 - name.upper().find(query)
    if query and initials.startswith(query):
        return 500 - len(query)
    if query and query in initials:
        return 400
    return 0


@lru_cache(maxsize=8)
def _search_cached(query: str, limit: int) -> tuple[dict[str, str | int], ...]:
    data = _load()
    if not query:
        return ()

    query_digits = _code_digits(query)
    scored: list[tuple[int, str, str]] = []
    for code, name in data.items():
        if not name:
            continue
        score = _score_item(code, name, query, query_digits)
        if score > 0:
            scored.append((score, code, name))

    scored.sort(key=lambda x: (-x[0], x[1]))
    out: list[dict[str, str | int]] = []
    for score, code, name in scored[:limit]:
        out.append({
            "code": code,
            "name": name,
            "market": _market_label(code),
            "score": score,
        })
    return tuple(out)


def search_stocks(q: str, *, limit: int = 15) -> list[dict[str, str | int]]:
    """搜索 A 股列表，支持代码、名称、拼音首字母（如 ZGSY → 中国石油）。"""
    query = _normalize_query(q)
    if not query:
        return []
    return list(_search_cached(query, min(limit, 50)))


def clear_search_cache() -> None:
    _search_cached.cache_clear()
