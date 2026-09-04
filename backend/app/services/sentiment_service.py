"""情绪周期聚合、缓存与人工编辑服务。"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from model.data.sentiment import (
    calculate_local_limit_downs,
    calculate_local_sentiment,
    calculate_local_sentiment_batch,
    get_continuous_board_count,
    get_three_board_origin,
)

from ..core.config import settings
from ..core.time_utils import utc_now
from ..models.market import MarketDailySummary
from ..models.sentiment import (
    ExternalApiSnapshot,
    SentimentDaily,
    SentimentFeedback,
    SentimentLadderItem,
    SentimentTheme,
)
from . import kaipanla_client, market_store

PARSER_VERSION = 4
NEGATIVE_FEEDBACK_LOOKBACK = 10
RECENT_SYNC_DAYS = 30
EXTERNAL_ENDPOINTS_CURRENT = (
    "limit_ladder",
    "limit_reasons",
    "new_high_groups",
    "sector_strength",
    "sector_weakness",
)
EXTERNAL_ENDPOINTS_HISTORY = (
    "limit_reasons",
    "sector_strength",
    "sector_weakness",
)
_sync_locks_guard = threading.Lock()
_sync_locks: dict[str, threading.Lock] = {}


def normalize_date(value: str) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _recent_trade_dates(limit: int = RECENT_SYNC_DAYS) -> list[str]:
    """从本地行情缓存确定最新交易日窗口，不依赖用户选择的日期。"""
    cache_dir = Path(settings.cache_dir)  # type: ignore[arg-type]
    date_parts: list[pd.Series] = []

    overview_path = cache_dir / "market_overview.parquet"
    if overview_path.exists():
        try:
            overview = pd.read_parquet(overview_path, columns=["trade_date"], engine="pyarrow")
            date_parts.append(
                pd.to_datetime(overview["trade_date"], errors="coerce").dropna().tail(limit + 20)
            )
        except Exception:
            pass

    # 市场总览可能比个股缓存稍晚更新；取沪深样本的日期并集补齐最新交易日。
    candidates = sorted((cache_dir / "sh").glob("*.parquet"))[:12]
    candidates += sorted((cache_dir / "sz").glob("*.parquet"))[:12]
    for path in candidates:
        try:
            frame = pd.read_parquet(path, columns=["date"], engine="pyarrow")
        except Exception:
            continue
        if not frame.empty:
            date_parts.append(
                pd.to_datetime(frame["date"], errors="coerce").dropna().tail(limit + 20)
            )

    if not date_parts:
        return []
    dates = pd.concat(date_parts, ignore_index=True).drop_duplicates().sort_values()
    return [value.strftime("%Y-%m-%d") for value in dates.tail(limit)]


def _sync_lock(trade_date: str) -> threading.Lock:
    with _sync_locks_guard:
        return _sync_locks.setdefault(trade_date, threading.Lock())


def _normalize_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if text.startswith(("SH", "SZ", "BJ")):
        return text
    digits = re.sub(r"\D", "", text)
    if len(digits) != 6:
        return text
    if digits.startswith("6"):
        return f"SH{digits}"
    if digits.startswith(("4", "8")):
        return f"BJ{digits}"
    return f"SZ{digits}"


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", value.lower())


def _first(record: dict[str, Any], aliases: Iterable[str], default: Any = None) -> Any:
    indexed = {_key(str(key)): value for key, value in record.items()}
    for alias in aliases:
        if _key(alias) in indexed:
            value = indexed[_key(alias)]
            if value not in (None, ""):
                return value
    return default


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        match = re.search(r"-?\d+", str(value))
        return int(match.group()) if match else default
    except (TypeError, ValueError):
        return default


def _split_themes(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = [str(item) for item in value]
    else:
        raw = re.split(r"[+,，、/|;；]", str(value or ""))
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        name = item.strip().strip("[]()（）")
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def _board_count_from(value: Any) -> int:
    match = re.search(r"(\d+)\s*板", str(value or ""))
    return int(match.group(1)) if match else _as_int(value, 0)


def _walk_records(value: Any, inherited_board: int = 0) -> Iterable[tuple[dict[str, Any], int]]:
    if isinstance(value, list):
        for item in value:
            yield from _walk_records(item, inherited_board)
        return
    if not isinstance(value, dict):
        return

    own_board = _board_count_from(
        _first(
            value,
            ("board_count", "BoardCount", "LianBan", "ContinueBoard", "Height", "名称"),
            inherited_board,
        )
    ) or inherited_board
    code = _first(value, ("code", "Code", "StockID", "stock_code", "股票代码"), "")
    name = _first(value, ("name", "Name", "StockName", "stock_name", "股票名称"), "")
    if code or name:
        yield value, own_board
    for key, child in value.items():
        child_board = own_board or _board_count_from(key)
        if isinstance(child, (dict, list)):
            yield from _walk_records(child, child_board)


def _all_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _all_dicts(item)
    elif isinstance(value, dict):
        yield value
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from _all_dicts(child)


def _parse_ladder(payload: Any) -> list[dict]:
    # 当日 FuPanLa 天梯响应：StockList 为按板数分组的二维数组。
    live_grouped: dict[str, dict] = {}
    if isinstance(payload, dict) and isinstance(payload.get("StockList"), list):
        for group in payload["StockList"]:
            stocks = group if isinstance(group, list) and group and isinstance(group[0], list) else [group]
            for stock in stocks:
                if not isinstance(stock, list) or len(stock) < 2:
                    continue
                code = _normalize_code(stock[0])
                if not code:
                    continue
                board_label = str(stock[11] if len(stock) > 11 else "").strip()
                board_count = _as_int(stock[2] if len(stock) > 2 else None, 0)
                if board_count <= 0:
                    board_count = _board_count_from(board_label) or 1
                live_grouped[code] = {
                    "code": code,
                    "name": str(stock[1] or "").strip(),
                    "board_count": board_count,
                    "board_type": board_label,
                    "limit_time": _as_int(stock[3] if len(stock) > 3 else None, 0) or None,
                    "reason": "",
                    "themes": _split_themes(stock[5] if len(stock) > 5 else ""),
                    "source": "kaipanla",
                }
    if live_grouped:
        return sorted(
            live_grouped.values(), key=lambda item: (-item["board_count"], item["code"])
        )

    # 开盘啦 HisLimitResumption 的真实响应为：题材字典 + StockList 数组。
    # 数组核心位置：0代码、1名称、9连板描述、10板数、11概念、16主因、17详情。
    grouped: dict[str, dict] = {}
    if isinstance(payload, dict) and isinstance(payload.get("list"), list):
        for group in payload["list"]:
            if not isinstance(group, dict):
                continue
            group_name = str(group.get("ZSName") or "").strip()
            for stock in group.get("StockList") or []:
                if not isinstance(stock, list) or len(stock) < 2:
                    continue
                code = _normalize_code(stock[0])
                if not code:
                    continue
                board_label = str(stock[9] if len(stock) > 9 else "").strip()
                board_count = _as_int(stock[10] if len(stock) > 10 else None, 0)
                if board_count <= 0:
                    board_count = _board_count_from(board_label) or 1
                themes: list[str] = []
                for raw in (
                    stock[11] if len(stock) > 11 else "",
                    stock[16] if len(stock) > 16 else "",
                    group_name,
                ):
                    for theme in _split_themes(raw):
                        if theme not in themes:
                            themes.append(theme)
                reason = str(stock[17] if len(stock) > 17 else "").strip()
                limit_time = _as_int(stock[6] if len(stock) > 6 else None, 0) or None
                previous = grouped.get(code)
                if previous is None:
                    grouped[code] = {
                        "code": code,
                        "name": str(stock[1] or "").strip(),
                        "board_count": board_count,
                        "board_type": board_label,
                        "limit_time": limit_time,
                        "reason": reason,
                        "themes": themes,
                        "source": "kaipanla",
                    }
                    continue
                previous["board_count"] = max(int(previous["board_count"]), board_count)
                previous["board_type"] = previous["board_type"] or board_label
                previous["limit_time"] = previous.get("limit_time") or limit_time
                previous["reason"] = previous["reason"] or reason
                previous["themes"] = list(dict.fromkeys([*previous["themes"], *themes]))
    if grouped:
        return sorted(grouped.values(), key=lambda item: (-item["board_count"], item["code"]))

    result: dict[str, dict] = {}
    for record, inherited_board in _walk_records(payload):
        code = _normalize_code(
            _first(record, ("code", "Code", "StockID", "stock_code", "股票代码"), "")
        )
        if not code:
            continue
        name = str(
            _first(record, ("name", "Name", "StockName", "stock_name", "股票名称"), "")
        ).strip()
        board_count = _board_count_from(
            _first(
                record,
                ("board_count", "BoardCount", "LianBan", "ContinueBoard", "days", "连板数"),
                inherited_board,
            )
        ) or inherited_board or 1
        reason = str(
            _first(
                record,
                ("reason", "Reason", "ZhangTingReason", "limit_reason", "Explain", "涨停原因"),
                "",
            )
        ).strip()
        theme_value = _first(
            record,
            ("themes", "theme", "Theme", "Plate", "PlateName", "Concept", "题材", "板块"),
            "",
        )
        board_type = str(
            _first(record, ("board_type", "BoardType", "TypeName", "板型"), "")
        ).strip()
        limit_time = _as_int(
            _first(
                record,
                ("limit_time", "LimitTime", "ZhangTingTime", "ZTTime", "涨停时间"),
                None,
            ),
            0,
        ) or None
        result[code] = {
            "code": code,
            "name": name,
            "board_count": board_count,
            "board_type": board_type,
            "limit_time": limit_time,
            "reason": reason,
            "themes": _split_themes(theme_value),
            "source": "kaipanla",
        }
    return sorted(result.values(), key=lambda item: (-item["board_count"], item["code"]))


def _parse_theme_counts(payload: Any) -> list[dict]:
    candidates: list[dict] = []

    def append_candidate(name: Any, count: Any) -> None:
        normalized_name = str(name or "").strip()
        normalized_count = _as_int(count, -1)
        if normalized_name and normalized_count >= 0 and len(normalized_name) <= 100:
            candidates.append({"name": normalized_name, "count": normalized_count})

    if isinstance(payload, dict):
        # FuPanLa.ZhuShuList: [题材代码, 题材名, 股票数, ...]
        for row in payload.get("ZhuShuList") or []:
            if isinstance(row, list) and len(row) >= 3:
                append_candidate(row[1], row[2])
        # StockNewHigh.List: [题材名, "创新高数,其他数", 题材代码]
        for row in payload.get("List") or []:
            if isinstance(row, list) and len(row) >= 2:
                append_candidate(row[0], row[1])

    for record in _all_dicts(payload):
        name = str(
            _first(
                record,
                ("ZSName", "GroupName", "PlateName", "ThemeName", "ConceptName", "name", "Name", "板块名称"),
                "",
            )
        ).strip()
        count = _as_int(
            _first(record, ("num", "Count", "StockCount", "Num", "number", "value", "数量"), None),
            -1,
        )
        append_candidate(name, count)
    best: dict[str, int] = {}
    for item in candidates:
        best[item["name"]] = max(best.get(item["name"], -1), item["count"])
    return [
        {"name": name, "count": count, "rank": index + 1}
        for index, (name, count) in enumerate(
            sorted(best.items(), key=lambda pair: (-pair[1], pair[0]))[:20]
        )
    ]


def _parse_sector_rankings(payload: Any) -> list[dict]:
    """解析 ZhiShuRanking.RealRankingInfo 的板块强度数组。"""
    rows = payload.get("list") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    result: list[dict] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 4:
            continue
        name = str(row[1] or "").strip()
        if not name:
            continue
        try:
            change_pct = float(row[3])
        except (TypeError, ValueError):
            change_pct = 0.0
        result.append(
            {
                "name": name,
                "count": _as_int(row[2]),
                "rank": len(result) + 1,
                "stage": str(change_pct),
            }
        )
    return result


def _parse_highlights(payload: Any) -> list[dict]:
    result: list[dict] = []
    for record in _all_dicts(payload):
        content = str(
            _first(record, ("content", "Content", "Title", "title", "Desc", "Text", "内容"), "")
        ).strip()
        if not content or len(content) < 4:
            continue
        code = _normalize_code(_first(record, ("StockID", "code", "Code"), ""))
        result.append({"content": content, "linked_codes": [code] if code else []})
    return result[:30]


def _params_hash(params: dict[str, Any]) -> str:
    encoded = json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _snapshot_for(
    session: Session, endpoint: str, trade_date: str, params_hash: str
) -> ExternalApiSnapshot | None:
    return session.scalar(
        select(ExternalApiSnapshot).where(
            ExternalApiSnapshot.source == "kaipanla",
            ExternalApiSnapshot.endpoint == endpoint,
            ExternalApiSnapshot.trade_date == trade_date,
            ExternalApiSnapshot.params_hash == params_hash,
        )
    )


def _fetch_snapshot(
    session: Session, endpoint: str, trade_date: str, *, force: bool
) -> tuple[ExternalApiSnapshot, bool]:
    request = kaipanla_client.build_request(endpoint, trade_date)
    digest = _params_hash(request.public_params)
    existing = _snapshot_for(session, endpoint, trade_date, digest)
    if existing is not None and existing.status in {"success", "empty"} and not force:
        return existing, False

    snapshot = existing or ExternalApiSnapshot(
        id=str(uuid.uuid4()),
        source="kaipanla",
        endpoint=endpoint,
        trade_date=trade_date,
        params_hash=digest,
        request_params=request.public_params,
    )
    if existing is None:
        session.add(snapshot)
    try:
        _, payload = kaipanla_client.fetch(endpoint, trade_date)
        snapshot.payload = payload
        business_error = kaipanla_client.payload_error(payload)
        snapshot.status = (
            "error"
            if business_error
            else "success"
            if kaipanla_client.payload_has_data(payload)
            else "empty"
        )
        snapshot.error = business_error
    except Exception as exc:
        snapshot.status = "error"
        snapshot.error = f"{type(exc).__name__}: {exc}"[:1000]
        snapshot.payload = None
    snapshot.parser_version = PARSER_VERSION
    snapshot.fetched_at = utc_now()
    session.flush()
    return snapshot, True


def _replace_ladder(session: Session, trade_date: str, items: list[dict]) -> None:
    major_codes = set(
        session.scalars(
            select(SentimentLadderItem.code).where(
                SentimentLadderItem.trade_date == trade_date,
                SentimentLadderItem.is_major_first_board.is_(True),
            )
        ).all()
    )
    session.execute(
        delete(SentimentLadderItem).where(SentimentLadderItem.trade_date == trade_date)
    )
    for item in items:
        session.add(
            SentimentLadderItem(
                id=str(uuid.uuid4()),
                trade_date=trade_date,
                code=_normalize_code(item.get("code")),
                name=str(item.get("name") or ""),
                board_count=max(1, _as_int(item.get("board_count"), 1)),
                board_type=str(item.get("board_type") or ""),
                limit_time=_as_int(item.get("limit_time"), 0) or None,
                reason=str(item.get("reason") or ""),
                themes=list(item.get("themes") or []),
                is_major_first_board=_normalize_code(item.get("code")) in major_codes,
                source=str(item.get("source") or "local"),
            )
        )
    session.flush()


def _merge_ladders(local_items: list[dict], external_items: list[dict]) -> list[dict]:
    merged = {_normalize_code(item.get("code")): dict(item) for item in local_items}
    for item in external_items:
        code = _normalize_code(item.get("code"))
        if not code:
            continue
        base = merged.get(code, {})
        merged[code] = {
            "code": code,
            "name": item.get("name") or base.get("name") or "",
            "board_count": item.get("board_count") or base.get("board_count") or 1,
            "board_type": item.get("board_type") or base.get("board_type") or "",
            "limit_time": item.get("limit_time") or base.get("limit_time"),
            "reason": item.get("reason") or base.get("reason") or "",
            "themes": item.get("themes") or base.get("themes") or [],
            "source": "kaipanla",
        }
    return sorted(
        merged.values(),
        key=lambda item: (
            -int(item["board_count"]),
            _as_int(item.get("limit_time"), 0) or 9_999_999_999,
            item["code"],
        ),
    )


def backfill_limit_times_from_snapshots(session: Session) -> int:
    """用已缓存的历史涨停复盘响应补齐当天涨停时间，不触发外部请求。"""
    snapshots = session.scalars(
        select(ExternalApiSnapshot).where(
            ExternalApiSnapshot.source == "kaipanla",
            ExternalApiSnapshot.endpoint == "limit_reasons",
            ExternalApiSnapshot.status == "success",
        )
    ).all()
    updated = 0
    for snapshot in snapshots:
        parsed = {
            item["code"]: item.get("limit_time")
            for item in _parse_ladder(snapshot.payload)
            if item.get("limit_time")
        }
        if not parsed:
            continue
        ladder_items = session.scalars(
            select(SentimentLadderItem).where(
                SentimentLadderItem.trade_date == snapshot.trade_date,
                SentimentLadderItem.code.in_(parsed),
            )
        ).all()
        for item in ladder_items:
            limit_time = _as_int(parsed.get(item.code), 0) or None
            if item.limit_time == limit_time:
                continue
            item.limit_time = limit_time
            item.updated_at = utc_now()
            updated += 1
    session.flush()
    return updated


def backfill_limit_down_stocks(session: Session, trade_dates: list[str] | None = None) -> int:
    """从本地行情缓存批量补齐每日跌停名单，不触发网络请求。"""
    if trade_dates is None:
        trade_dates = list(
            session.scalars(
                select(SentimentDaily.trade_date)
                .where(SentimentDaily.local_complete.is_(True))
                .order_by(SentimentDaily.trade_date)
            ).all()
        )
    dates = [normalize_date(date) for date in trade_dates]
    by_date = calculate_local_limit_downs(settings.cache_dir, dates)  # type: ignore[arg-type]
    updated = 0
    for date in dates:
        daily = session.get(SentimentDaily, date)
        if daily is None:
            continue
        stocks = by_date.get(date, [])
        if (daily.limit_down_stocks or []) == stocks and daily.limit_down_count == len(stocks):
            continue
        daily.limit_down_stocks = stocks
        daily.limit_down_count = len(stocks)
        daily.updated_at = utc_now()
        updated += 1
    session.flush()
    return updated


def _replace_external_themes(
    session: Session, trade_date: str, category: str, themes: list[dict], *, source: str = "kaipanla"
) -> None:
    session.execute(
        delete(SentimentTheme).where(
            SentimentTheme.trade_date == trade_date,
            SentimentTheme.category == category,
            SentimentTheme.manual_override.is_(False),
        )
    )
    for index, item in enumerate(themes[:20]):
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        session.add(
            SentimentTheme(
                id=str(uuid.uuid4()),
                trade_date=trade_date,
                category=category,
                name=name,
                count=_as_int(item.get("count"), 0),
                rank=_as_int(item.get("rank"), index + 1),
                stage=str(item.get("stage") or ""),
                source=source,
                manual_override=False,
            )
        )
    session.flush()


def _aggregate_limit_themes(ladder: list[dict]) -> list[dict]:
    counts: Counter[str] = Counter()
    for item in ladder:
        counts.update(set(str(theme) for theme in item.get("themes") or [] if str(theme).strip()))
    return [
        {"name": name, "count": count, "rank": index + 1}
        for index, (name, count) in enumerate(counts.most_common(20))
    ]


def _derive_new_high_themes(daily: SentimentDaily, ladder: list[dict]) -> list[dict]:
    """用本地百日新高名单与当日开盘啦涨停题材交集生成可审计兜底。"""
    by_code = {_normalize_code(item.get("code")): item for item in ladder}
    counts: Counter[str] = Counter()
    enriched: list[dict] = []
    for stock in daily.new_high_stocks or []:
        item = dict(stock)
        code = _normalize_code(item.get("code"))
        external = by_code.get(code)
        themes = list(item.get("themes") or [])
        if external:
            themes = list(dict.fromkeys([*themes, *(external.get("themes") or [])]))
            item["source"] = "derived"
        item["themes"] = themes
        enriched.append(item)
        counts.update(set(theme for theme in themes if str(theme).strip()))
    daily.new_high_stocks = enriched
    return [
        {"name": name, "count": count, "rank": index + 1}
        for index, (name, count) in enumerate(counts.most_common(20))
    ]


def _market_volume(session: Session, trade_date: str) -> tuple[float | None, float | None]:
    current = session.get(MarketDailySummary, trade_date)
    amount = float(current.total_amount) if current and current.total_amount is not None else None
    previous = session.scalar(
        select(MarketDailySummary)
        .where(
            MarketDailySummary.trade_date < trade_date,
            MarketDailySummary.total_amount.isnot(None),
        )
        .order_by(MarketDailySummary.trade_date.desc())
        .limit(1)
    )
    if amount is None or previous is None or not previous.total_amount:
        return amount, None
    change_pct = (amount / float(previous.total_amount) - 1) * 100
    return amount, round(change_pct, 2)


def _ensure_daily(session: Session, trade_date: str) -> SentimentDaily:
    daily = session.get(SentimentDaily, trade_date)
    if daily is None:
        daily = SentimentDaily(trade_date=trade_date)
        session.add(daily)
        session.flush()
    return daily


def _three_board_origins(session: Session, trade_date: str) -> list[SentimentLadderItem]:
    """按本地行情定位真实三连板的本轮首板，不使用区间累计板数。"""
    three_board_items = session.scalars(
        select(SentimentLadderItem).where(
            SentimentLadderItem.trade_date == trade_date,
        )
    ).all()
    origins = []
    for item in three_board_items:
        if _continuous_board_count(item) != 3:
            continue
        origin_date = get_three_board_origin(
            settings.cache_dir, item.code, item.trade_date, item.name
        )
        if origin_date is None:
            continue
        origin = session.scalar(
            select(SentimentLadderItem)
            .where(
                SentimentLadderItem.code == item.code,
                SentimentLadderItem.trade_date == origin_date,
            )
        )
        if origin is not None:
            origins.append(origin)
    return origins


def _auto_mark_three_board_origins(session: Session, trade_date: str) -> int:
    """将当日真实三连板的本轮首板标为“主要首板”。"""
    marked = 0
    for origin in _three_board_origins(session, trade_date):
        if origin.is_major_first_board:
            continue
        origin.is_major_first_board = True
        origin.updated_at = utc_now()
        marked += 1
    session.flush()
    return marked


def plan_major_first_board_repair(session: Session) -> list[dict]:
    """生成历史自动标记的修复清单；不修改数据库，不访问外部服务。"""
    items = session.scalars(select(SentimentLadderItem)).all()
    expected_ids = {
        origin.id
        for date in sorted({item.trade_date for item in items})
        for origin in _three_board_origins(session, date)
    }
    return [
        {
            "id": item.id,
            "trade_date": item.trade_date,
            "code": item.code,
            "name": item.name,
            "before": item.is_major_first_board,
            "after": item.id in expected_ids,
        }
        for item in items
        if item.is_major_first_board != (item.id in expected_ids)
    ]


def _sync_market_fields(session: Session, daily: SentimentDaily) -> None:
    data = market_store.load_market_day(session, daily.trade_date)
    if data is None:
        try:
            market_store.ensure_market_day(session, daily.trade_date)
        except Exception:
            data = None
        else:
            data = market_store.load_market_day(session, daily.trade_date)
    indices = (data or {}).get("indices") or []
    sh_index = next((item for item in indices if item.get("code") == "SH000001"), None)
    daily.sh_change_pct = sh_index.get("change_pct") if sh_index else None
    daily.up_count = (data or {}).get("up_count")
    daily.down_count = (data or {}).get("down_count")
    daily.flat_count = (data or {}).get("flat_count")


def _apply_local_result(
    session: Session,
    daily: SentimentDaily,
    result: dict,
) -> None:
    for field in ("up_count", "down_count", "flat_count"):
        if field in result:
            setattr(daily, field, result[field])
    daily.limit_up_count = result["limit_up_count"]
    daily.limit_down_count = result["limit_down_count"]
    daily.limit_down_stocks = result["limit_down_stocks"]
    daily.broken_board_count = result["broken_board_count"]
    daily.new_high_100_count = result["new_high_100_count"]
    daily.scanned_stock_count = result["scanned_stock_count"]
    daily.new_high_stocks = result["new_high_stocks"]
    daily.local_complete = bool(result["complete"])
    _replace_ladder(session, daily.trade_date, result["ladder"])


def _sync_local(session: Session, daily: SentimentDaily, *, force: bool) -> dict:
    if daily.local_complete and not force:
        items = session.scalars(
            select(SentimentLadderItem).where(SentimentLadderItem.trade_date == daily.trade_date)
        ).all()
        return {
            "ladder": [
                {
                    "code": item.code,
                    "name": item.name,
                    "board_count": item.board_count,
                    "board_type": item.board_type,
                    "limit_time": item.limit_time,
                    "reason": item.reason,
                    "themes": item.themes or [],
                    "source": item.source,
                }
                for item in items
            ],
            "cached": True,
        }

    result = calculate_local_sentiment(settings.cache_dir, daily.trade_date)  # type: ignore[arg-type]
    _apply_local_result(session, daily, result)
    return {**result, "cached": False}


def _sync_external(
    session: Session, daily: SentimentDaily, local_ladder: list[dict], *, force: bool
) -> dict:
    if not kaipanla_client.is_configured():
        daily.external_complete = False
        daily.external_status = "not_configured"
        return {"configured": False, "network_requests": 0, "statuses": {}}

    today = pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d")
    endpoints = EXTERNAL_ENDPOINTS_CURRENT if daily.trade_date == today else EXTERNAL_ENDPOINTS_HISTORY
    snapshots: dict[str, ExternalApiSnapshot] = {}
    network_requests = 0
    for endpoint in endpoints:
        snapshot, requested = _fetch_snapshot(session, endpoint, daily.trade_date, force=force)
        snapshots[endpoint] = snapshot
        network_requests += int(requested)

    external_ladder = _parse_ladder((snapshots.get("limit_ladder") or snapshots.get("limit_reasons")).payload) if (snapshots.get("limit_ladder") or snapshots.get("limit_reasons")) else []
    reason_ladder = _parse_ladder(snapshots["limit_reasons"].payload) if "limit_reasons" in snapshots else []
    external_ladder = _merge_ladders(external_ladder, reason_ladder)
    merged_ladder = _merge_ladders(local_ladder, external_ladder)
    if merged_ladder:
        _replace_ladder(session, daily.trade_date, merged_ladder)

    limit_themes = _parse_theme_counts(snapshots["limit_reasons"].payload) if "limit_reasons" in snapshots else []
    if not limit_themes:
        limit_themes = _aggregate_limit_themes(merged_ladder)
    if limit_themes:
        _replace_external_themes(session, daily.trade_date, "limit_up", limit_themes)

    new_high_themes = _parse_theme_counts(snapshots["new_high_groups"].payload) if "new_high_groups" in snapshots else []
    theme_source = "kaipanla"
    if not new_high_themes:
        new_high_themes = _derive_new_high_themes(daily, merged_ladder)
        theme_source = "derived"
    if new_high_themes:
        _replace_external_themes(
            session, daily.trade_date, "new_high", new_high_themes, source=theme_source
        )

    strong_sectors = (
        _parse_sector_rankings(snapshots["sector_strength"].payload)
        if "sector_strength" in snapshots
        else []
    )
    weak_sectors = (
        _parse_sector_rankings(snapshots["sector_weakness"].payload)
        if "sector_weakness" in snapshots
        else []
    )
    if "sector_strength" in snapshots:
        _replace_external_themes(
            session, daily.trade_date, "strong_sector", strong_sectors[:5]
        )
    if "sector_weakness" in snapshots:
        _replace_external_themes(
            session, daily.trade_date, "weak_sector", weak_sectors[:5]
        )

    statuses = {name: snapshot.status for name, snapshot in snapshots.items()}
    successful = [status for status in statuses.values() if status == "success"]
    errors = [snapshot.error for snapshot in snapshots.values() if snapshot.status == "error"]
    daily.external_complete = bool(successful) and len(successful) == len(snapshots)
    daily.external_status = (
        "complete"
        if daily.external_complete
        else "partial"
        if successful
        else "empty"
        if statuses and all(status == "empty" for status in statuses.values())
        else "error"
    )
    if errors:
        daily.sync_error = "; ".join(errors)[:2000]
    return {
        "configured": True,
        "network_requests": network_requests,
        "statuses": statuses,
    }


def sync_day(session: Session, trade_date: str, *, force: bool = False) -> dict:
    date = normalize_date(trade_date)
    with _sync_lock(date):
        daily = _ensure_daily(session, date)
        daily.sync_error = ""
        _sync_market_fields(session, daily)
        local = _sync_local(session, daily, force=force)
        external = _sync_external(
            session, daily, list(local.get("ladder") or []), force=force
        )
        _auto_mark_three_board_origins(session, date)
        daily.updated_at = utc_now()
        session.commit()
        return {
            "trade_date": date,
            "local_complete": daily.local_complete,
            "external_status": daily.external_status,
            "local_cached": bool(local.get("cached")),
            **external,
        }


def sync_latest(
    session: Session,
    *,
    force: bool = False,
    days: int = RECENT_SYNC_DAYS,
) -> dict:
    """补齐本地行情最新窗口内缺少的情绪数据。"""
    trade_dates = _recent_trade_dates(days)
    if not trade_dates:
        raise ValueError("本地行情缓存中没有可同步的交易日")

    daily_by_date = {
        daily.trade_date: daily
        for daily in session.scalars(
            select(SentimentDaily).where(SentimentDaily.trade_date.in_(trade_dates))
        ).all()
    }
    local_dates = [
        date
        for date in trade_dates
        if force
        or date not in daily_by_date
        or not daily_by_date[date].local_complete
    ]
    external_retry_dates = {
        date
        for date, daily in daily_by_date.items()
        if kaipanla_client.is_configured() and daily.external_status != "complete"
    }
    dates_to_sync = (
        trade_dates
        if force
        else [
            date
            for date in trade_dates
            if date in local_dates or date in external_retry_dates
        ]
    )
    if not dates_to_sync:
        return {
            "latest_trade_date": trade_dates[-1],
            "window_start": trade_dates[0],
            "window_end": trade_dates[-1],
            "window_days": len(trade_dates),
            "synced_days": 0,
            "skipped_days": len(trade_dates),
            "synced_dates": [],
            "network_requests": 0,
            "external_statuses": {},
        }

    local_by_date = calculate_local_sentiment_batch(
        settings.cache_dir, local_dates  # type: ignore[arg-type]
    )
    unavailable_dates = [
        date
        for date in local_dates
        if not local_by_date.get(date) or not local_by_date[date].get("complete")
    ]
    if unavailable_dates:
        raise ValueError(f"以下交易日本地行情不完整：{', '.join(unavailable_dates)}")

    synced_dates: list[str] = []
    network_requests = 0
    external_statuses: dict[str, str] = {}
    for date in dates_to_sync:
        with _sync_lock(date):
            daily = _ensure_daily(session, date)
            daily.sync_error = ""
            if date in local_dates:
                result = local_by_date[date]
                _sync_market_fields(session, daily)
                _apply_local_result(session, daily, result)
                local_ladder = list(result.get("ladder") or [])
            else:
                local = _sync_local(session, daily, force=False)
                local_ladder = list(local.get("ladder") or [])
            external = _sync_external(
                session,
                daily,
                local_ladder,
                force=force or date in external_retry_dates,
            )
            _auto_mark_three_board_origins(session, date)
            daily.updated_at = utc_now()
            network_requests += int(external.get("network_requests", 0))
            external_statuses[date] = daily.external_status
            synced_dates.append(date)

    session.commit()
    return {
        "latest_trade_date": trade_dates[-1],
        "window_start": trade_dates[0],
        "window_end": trade_dates[-1],
        "window_days": len(trade_dates),
        "synced_days": len(synced_dates),
        "skipped_days": len(trade_dates) - len(synced_dates),
        "synced_dates": synced_dates,
        "network_requests": network_requests,
        "external_statuses": external_statuses,
    }


def _theme_dict(theme: SentimentTheme) -> dict:
    return {
        "id": theme.id,
        "name": theme.name,
        "count": theme.count,
        "rank": theme.rank,
        "stage": theme.stage,
        "source": theme.source,
        "manual_override": theme.manual_override,
    }


def _continuous_board_count(item: SentimentLadderItem) -> int | None:
    # “几天几板”与反包标签记录区间涨停次数，不能直接当作连续板数。
    if re.search(r"\d+\s*天\s*\d+\s*板|断板|反包", item.board_type or ""):
        return get_continuous_board_count(
            settings.cache_dir, item.code, item.trade_date, item.name
        )
    return item.board_count


def _ladder_dict(item: SentimentLadderItem) -> dict:
    return {
        "id": item.id,
        "code": item.code,
        "name": item.name,
        "board_count": item.board_count,
        "continuous_board_count": _continuous_board_count(item),
        "board_type": item.board_type,
        "limit_time": item.limit_time,
        "reason": item.reason,
        "themes": item.themes or [],
        "is_major_first_board": item.is_major_first_board,
        "source": item.source,
    }


def _feedback_dict(item: SentimentFeedback) -> dict:
    return {
        "id": item.id,
        "feedback_type": item.feedback_type,
        "content": item.content,
        "linked_codes": item.linked_codes or [],
        "linked_themes": item.linked_themes or [],
        "source": item.source,
        "confirmed": item.confirmed,
        "sort_order": item.sort_order,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _negative_feedback_for_day(session: Session, daily: SentimentDaily) -> list[dict]:
    limit_down_stocks = daily.limit_down_stocks or []
    down_by_code = {
        _normalize_code(stock.get("code")): stock
        for stock in limit_down_stocks
        if _normalize_code(stock.get("code"))
    }
    if not down_by_code:
        return []
    calendar_cutoff = (
        pd.Timestamp(daily.trade_date) - pd.Timedelta(days=21)
    ).strftime("%Y-%m-%d")
    recent_dates = list(
        session.scalars(
            select(SentimentDaily.trade_date)
            .where(
                SentimentDaily.local_complete.is_(True),
                SentimentDaily.trade_date < daily.trade_date,
                SentimentDaily.trade_date >= calendar_cutoff,
            )
            .order_by(SentimentDaily.trade_date.desc())
            .limit(NEGATIVE_FEEDBACK_LOOKBACK)
        ).all()
    )
    if not recent_dates:
        return []
    ladder_items = session.scalars(
        select(SentimentLadderItem).where(
            SentimentLadderItem.trade_date.in_(recent_dates),
            SentimentLadderItem.code.in_(down_by_code),
            SentimentLadderItem.board_count >= 3,
        )
    ).all()
    best_by_code: dict[str, SentimentLadderItem] = {}
    for item in ladder_items:
        previous = best_by_code.get(item.code)
        if previous is None or (item.board_count, item.trade_date) > (
            previous.board_count,
            previous.trade_date,
        ):
            best_by_code[item.code] = item
    result = []
    for code, item in best_by_code.items():
        stock = down_by_code[code]
        result.append(
            {
                "code": code,
                "name": str(item.name or stock.get("name") or ""),
                "recent_max_board": item.board_count,
                "recent_board_date": item.trade_date,
                "board_type": item.board_type,
                "themes": item.themes or [],
                "source": "derived",
            }
        )
    return sorted(
        result,
        key=lambda item: (
            -item["recent_max_board"],
            -int(item["recent_board_date"].replace("-", "")),
            item["code"],
        ),
    )


def get_day(session: Session, trade_date: str) -> dict | None:
    date = normalize_date(trade_date)
    daily = session.get(SentimentDaily, date)
    if daily is None:
        return None
    themes = session.scalars(
        select(SentimentTheme)
        .where(SentimentTheme.trade_date == date)
        .order_by(SentimentTheme.category, SentimentTheme.rank, SentimentTheme.name)
    ).all()
    ladder = session.scalars(
        select(SentimentLadderItem)
        .where(SentimentLadderItem.trade_date == date)
        .order_by(SentimentLadderItem.board_count.desc(), SentimentLadderItem.code)
    ).all()
    ladder = sorted(
        ladder,
        key=lambda item: (
            -item.board_count,
            item.limit_time or 9_999_999_999,
            item.code,
        ),
    )
    by_category: dict[str, list[dict]] = {
        "limit_up": [],
        "new_high": [],
        "strong_sector": [],
        "weak_sector": [],
    }
    for item in themes:
        by_category.setdefault(item.category, []).append(_theme_dict(item))
    ladder_items = [_ladder_dict(item) for item in ladder]
    ladder_items.sort(key=lambda item: (
        -(item["continuous_board_count"] or 0),
        item["limit_time"] or 9_999_999_999,
        item["code"],
    ))
    max_board = max((item["continuous_board_count"] or 0 for item in ladder_items), default=0)
    three_board_count = sum(1 for item in ladder_items if item["continuous_board_count"] == 3)
    total_amount, amount_change_pct = _market_volume(session, date)
    return {
        "trade_date": date,
        "market": {
            "sh_change_pct": daily.sh_change_pct,
            "up_count": daily.up_count,
            "down_count": daily.down_count,
            "flat_count": daily.flat_count,
            "limit_up_count": daily.limit_up_count,
            "limit_down_count": daily.limit_down_count,
            "broken_board_count": daily.broken_board_count,
            "new_high_100_count": daily.new_high_100_count,
            "scanned_stock_count": daily.scanned_stock_count,
            "total_amount": total_amount,
            "amount_change_pct": amount_change_pct,
        },
        "limit_up_themes": by_category.get("limit_up", [])[:3],
        "new_high_themes": by_category.get("new_high", [])[:3],
        "strong_sectors": by_category.get("strong_sector", [])[:5],
        "weak_sectors": by_category.get("weak_sector", [])[:5],
        "new_high_stocks": daily.new_high_stocks or [],
        "ladder": {
            "max_board": max_board,
            "three_board_count": three_board_count,
            "items": ladder_items,
        },
        "negative_feedback": _negative_feedback_for_day(session, daily),
        "sync_status": {
            "local_complete": daily.local_complete,
            "external_complete": daily.external_complete,
            "external_status": daily.external_status,
            "external_configured": kaipanla_client.is_configured(),
            "sync_error": daily.sync_error,
            "updated_at": daily.updated_at,
        },
    }


def get_matrix(
    session: Session, *, start_date: str | None = None, end_date: str | None = None, limit: int = 20
) -> list[dict]:
    stmt = select(SentimentDaily.trade_date).where(SentimentDaily.local_complete.is_(True))
    if start_date:
        stmt = stmt.where(SentimentDaily.trade_date >= normalize_date(start_date))
    if end_date:
        stmt = stmt.where(SentimentDaily.trade_date <= normalize_date(end_date))
    dates = session.scalars(stmt.order_by(SentimentDaily.trade_date.desc()).limit(limit)).all()
    result: list[dict] = []
    for date in reversed(dates):
        day = get_day(session, date)
        if day is None:
            continue
        # 矩阵保留全部梯队股票，仅剔除不展示的百日新高个股明细，
        # 降低历史分页的 JSON 体积；单日接口仍返回完整数据。
        day["new_high_stocks"] = []
        result.append(day)
    return result


def set_major_first_boards(session: Session, trade_date: str, codes: list[str]) -> dict:
    date = normalize_date(trade_date)
    selected = {_normalize_code(code) for code in codes}
    items = session.scalars(
        select(SentimentLadderItem).where(SentimentLadderItem.trade_date == date)
    ).all()
    for item in items:
        item.is_major_first_board = _continuous_board_count(item) == 1 and item.code in selected
        item.updated_at = utc_now()
    session.commit()
    return get_day(session, date) or {}


def create_feedback(
    session: Session,
    trade_date: str,
    *,
    content: str,
    linked_codes: list[str],
    linked_themes: list[str],
) -> SentimentFeedback:
    date = normalize_date(trade_date)
    _ensure_daily(session, date)
    max_order = max(
        session.scalars(
            select(SentimentFeedback.sort_order).where(
                SentimentFeedback.trade_date == date,
                SentimentFeedback.feedback_type == "positive",
            )
        ).all()
        or [0]
    )
    item = SentimentFeedback(
        id=str(uuid.uuid4()),
        trade_date=date,
        feedback_type="positive",
        content=content.strip(),
        linked_codes=[_normalize_code(code) for code in linked_codes if code.strip()],
        linked_themes=[theme.strip() for theme in linked_themes if theme.strip()],
        source="manual",
        confirmed=True,
        sort_order=max_order + 1,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def update_feedback(
    session: Session,
    feedback_id: str,
    *,
    content: str | None = None,
    linked_codes: list[str] | None = None,
    linked_themes: list[str] | None = None,
) -> SentimentFeedback | None:
    item = session.get(SentimentFeedback, feedback_id)
    if item is None:
        return None
    if content is not None:
        item.content = content.strip()
    if linked_codes is not None:
        item.linked_codes = [_normalize_code(code) for code in linked_codes if code.strip()]
    if linked_themes is not None:
        item.linked_themes = [theme.strip() for theme in linked_themes if theme.strip()]
    item.updated_at = utc_now()
    session.commit()
    session.refresh(item)
    return item


def delete_feedback(session: Session, feedback_id: str) -> bool:
    item = session.get(SentimentFeedback, feedback_id)
    if item is None:
        return False
    session.delete(item)
    session.commit()
    return True


def feedback_to_dict(item: SentimentFeedback) -> dict:
    return _feedback_dict(item)
