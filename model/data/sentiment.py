"""情绪周期的本地行情计算。

只使用已经构建的个股 Parquet 缓存，不发起任何网络请求。外部数据源不可用时，
这里提供涨跌停数量、百日新高和连板梯队的可审计兜底。
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path

import pandas as pd


LOCAL_SCAN_WORKERS = 8


@dataclass(frozen=True)
class StockSentimentRow:
    code: str
    name: str
    is_limit_up: bool
    is_limit_down: bool
    touched_limit_up: bool
    board_count: int
    board_type: str
    is_new_high_100: bool
    first_board_date: str | None = None


def _load_names(cache_dir: Path) -> dict[str, str]:
    path = cache_dir / "stock_names.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(k).upper(): str(v).strip() for k, v in raw.items()}


def _limit_pct(code: str, name: str) -> Decimal:
    upper_name = name.upper()
    if "ST" in upper_name:
        return Decimal("0.05")
    number = code.upper().replace("SH", "").replace("SZ", "")
    if number.startswith(("300", "301", "688", "689")):
        return Decimal("0.20")
    return Decimal("0.10")


def _limit_pct_for_bar(
    code: str,
    name: str,
    previous_close: float,
    high: float,
    low: float,
    close: float,
) -> Decimal:
    """按当日价格区间修正可能过期的当前名称所对应的涨跌幅限制。

    stock_names.json 只保存当前名称，计算历史日期时可能把已经摘帽的股票仍按
    ST 的 5% 限制处理。若当日价格实际越过 5% 边界，则该日不可能是 ST，按
    所属板块的常规限制修正。普通股票恰好收在 +/-5% 并不足以反推历史 ST，
    以免产生误判。
    """
    configured = _limit_pct(code, name)
    board_pct = _limit_pct(code, "")
    if board_pct <= Decimal("0.05") or previous_close <= 0:
        return configured

    st_pct = Decimal("0.05")
    st_up = _limit_price(previous_close, st_pct, up=True)
    st_down = _limit_price(previous_close, st_pct, up=False)
    if high > st_up + 0.011 or low < st_down - 0.011:
        return board_pct
    return configured


def _limit_price(previous_close: float, pct: Decimal, *, up: bool) -> float:
    base = Decimal(str(previous_close))
    factor = Decimal("1") + pct if up else Decimal("1") - pct
    return float((base * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _near(left: float, right: float) -> bool:
    return abs(float(left) - float(right)) <= 0.011


def _read_window(path: Path, trade_date: str) -> pd.DataFrame | None:
    columns = ["date", "open", "high", "low", "close"]
    end = pd.Timestamp(trade_date)
    start = end - pd.Timedelta(days=240)
    try:
        df = pd.read_parquet(
            path,
            columns=columns,
            filters=[("date", ">=", start), ("date", "<=", end)],
            engine="pyarrow",
        )
    except Exception:
        try:
            df = pd.read_parquet(path, columns=columns, engine="pyarrow")
        except Exception:
            return None
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    return df[df["date"] <= end].sort_values("date").reset_index(drop=True)


def _scan_stock(path: Path, trade_date: str, names: dict[str, str]) -> StockSentimentRow | None:
    df = _read_window(path, trade_date)
    if df is None or len(df) < 2:
        return None
    target = pd.Timestamp(trade_date)
    hits = df.index[df["date"] == target]
    if len(hits) == 0:
        return None
    pos = int(hits[-1])
    if pos <= 0:
        return None

    code = path.stem.upper()
    name = names.get(code, "")
    today = df.iloc[pos]
    previous_close = float(df.iloc[pos - 1]["close"])
    close = float(today["close"])
    high = float(today["high"])
    low = float(today["low"])
    pct = _limit_pct_for_bar(code, name, previous_close, high, low, close)
    up_price = _limit_price(previous_close, pct, up=True)
    down_price = _limit_price(previous_close, pct, up=False)

    open_price = float(today["open"])
    is_limit_up = _near(close, up_price)
    is_limit_down = _near(close, down_price)
    touched_limit_up = high >= up_price - 0.011

    board_count = 0
    if is_limit_up:
        cursor = pos
        while cursor > 0:
            current_close = float(df.iloc[cursor]["close"])
            prior_close = float(df.iloc[cursor - 1]["close"])
            cursor_pct = _limit_pct_for_bar(
                code,
                name,
                prior_close,
                float(df.iloc[cursor]["high"]),
                float(df.iloc[cursor]["low"]),
                current_close,
            )
            expected = _limit_price(prior_close, cursor_pct, up=True)
            if not _near(current_close, expected):
                break
            board_count += 1
            cursor -= 1

    board_type = ""
    if is_limit_up:
        if _near(open_price, up_price) and _near(high, up_price) and _near(low, up_price):
            board_type = "一字板"
        elif _near(open_price, up_price) and low < up_price - 0.011:
            board_type = "T字板"
        else:
            board_type = "换手板"

    is_new_high_100 = False
    if pos >= 99:
        window = df.iloc[pos - 99 : pos + 1]
        previous_high = float(window.iloc[:-1]["high"].max())
        is_new_high_100 = high >= previous_high

    return StockSentimentRow(
        code=code,
        name=name,
        is_limit_up=is_limit_up,
        is_limit_down=is_limit_down,
        touched_limit_up=touched_limit_up,
        board_count=board_count,
        board_type=board_type,
        is_new_high_100=is_new_high_100,
        first_board_date=(
            df.iloc[pos - board_count + 1]["date"].strftime("%Y-%m-%d")
            if board_count else None
        ),
    )


@lru_cache(maxsize=8192)
def _cached_stock_sentiment(
    path: Path, trade_date: str, name: str, mtime_ns: int, size: int
) -> StockSentimentRow | None:
    # 文件版本参与缓存键，行情更新后自动重新计算。
    return _scan_stock(path, trade_date, {path.stem.upper(): name})


def _get_stock_sentiment(
    cache_dir: Path, code: str, trade_date: str, name: str = ""
) -> StockSentimentRow | None:
    code = code.upper()
    if len(code) != 8 or code[:2] not in {"SH", "SZ"} or not code[2:].isdigit():
        return None
    path = Path(cache_dir) / code[:2].lower() / f"{code}.parquet"
    try:
        stat = path.stat()
    except OSError:
        return None
    return _cached_stock_sentiment(path, trade_date, name, stat.st_mtime_ns, stat.st_size)


def get_continuous_board_count(
    cache_dir: Path, code: str, trade_date: str, name: str = ""
) -> int | None:
    """由本地行情计算实际连续涨停天数；行情缺失时返回 None。"""
    row = _get_stock_sentiment(cache_dir, code, trade_date, name)
    return row.board_count if row is not None else None


def get_three_board_origin(
    cache_dir: Path, code: str, trade_date: str, name: str = ""
) -> str | None:
    """仅在当日实际连续三板时返回本轮首板日期，不回退到上一轮。"""
    row = _get_stock_sentiment(cache_dir, code, trade_date, name)
    return row.first_board_date if row is not None and row.board_count == 3 else None


def calculate_local_sentiment(cache_dir: Path, trade_date: str) -> dict:
    """扫描某个交易日并返回基础情绪数据；结果应由服务层持久化复用。"""
    cache_dir = Path(cache_dir)
    paths = list((cache_dir / "sh").glob("*.parquet")) + list(
        (cache_dir / "sz").glob("*.parquet")
    )
    names = _load_names(cache_dir)
    rows: list[StockSentimentRow] = []
    with ThreadPoolExecutor(max_workers=LOCAL_SCAN_WORKERS) as executor:
        futures = [executor.submit(_scan_stock, path, trade_date, names) for path in paths]
        for future in as_completed(futures):
            row = future.result()
            if row is not None:
                rows.append(row)

    limit_up = [row for row in rows if row.is_limit_up]
    limit_down = [row for row in rows if row.is_limit_down]
    new_high = [row for row in rows if row.is_new_high_100]
    ladder = [
        {
            "code": row.code,
            "name": row.name,
            "board_count": row.board_count,
            "board_type": row.board_type,
            "reason": "",
            "themes": [],
            "source": "local",
        }
        for row in limit_up
        if row.board_count > 0
    ]
    ladder.sort(key=lambda item: (-int(item["board_count"]), str(item["code"])))
    new_high_stocks = [
        {"code": row.code, "name": row.name, "themes": [], "source": "local"}
        for row in sorted(new_high, key=lambda item: item.code)
    ]
    limit_down_stocks = [
        {"code": row.code, "name": row.name, "themes": [], "source": "local"}
        for row in sorted(limit_down, key=lambda item: item.code)
    ]
    return {
        "trade_date": trade_date,
        "scanned_stock_count": len(rows),
        "limit_up_count": len(limit_up),
        "limit_down_count": len(limit_down),
        "limit_down_stocks": limit_down_stocks,
        "broken_board_count": sum(1 for row in rows if row.touched_limit_up and not row.is_limit_up),
        "new_high_100_count": len(new_high),
        "new_high_stocks": new_high_stocks,
        "ladder": ladder,
        "complete": len(rows) > 0,
    }


def _scan_stock_dates(
    path: Path,
    trade_dates: list[str],
    names: dict[str, str],
) -> list[tuple[str, StockSentimentRow, int]]:
    """一次读取单只股票，计算多个交易日的情绪指标和涨跌方向。"""
    if not trade_dates:
        return []
    columns = ["date", "open", "high", "low", "close"]
    earliest = pd.Timestamp(trade_dates[0]) - pd.Timedelta(days=240)
    latest = pd.Timestamp(trade_dates[-1])
    try:
        df = pd.read_parquet(
            path,
            columns=columns,
            filters=[("date", ">=", earliest), ("date", "<=", latest)],
            engine="pyarrow",
        )
    except Exception:
        try:
            df = pd.read_parquet(path, columns=columns, engine="pyarrow")
        except Exception:
            return []
    if df.empty:
        return []
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] <= latest].sort_values("date").reset_index(drop=True)
    if len(df) < 2:
        return []

    positions = {pd.Timestamp(value): pos for pos, value in enumerate(df["date"])}
    code = path.stem.upper()
    name = names.get(code, "")
    found: list[tuple[str, StockSentimentRow, int]] = []
    for trade_date in trade_dates:
        pos = positions.get(pd.Timestamp(trade_date))
        if pos is None or pos <= 0:
            continue
        today = df.iloc[pos]
        previous_close = float(df.iloc[pos - 1]["close"])
        close = float(today["close"])
        high = float(today["high"])
        low = float(today["low"])
        open_price = float(today["open"])
        pct = _limit_pct_for_bar(code, name, previous_close, high, low, close)
        up_price = _limit_price(previous_close, pct, up=True)
        down_price = _limit_price(previous_close, pct, up=False)
        is_limit_up = _near(close, up_price)
        is_limit_down = _near(close, down_price)

        board_count = 0
        if is_limit_up:
            cursor = pos
            while cursor > 0:
                current_close = float(df.iloc[cursor]["close"])
                prior_close = float(df.iloc[cursor - 1]["close"])
                cursor_pct = _limit_pct_for_bar(
                    code,
                    name,
                    prior_close,
                    float(df.iloc[cursor]["high"]),
                    float(df.iloc[cursor]["low"]),
                    current_close,
                )
                expected = _limit_price(prior_close, cursor_pct, up=True)
                if not _near(current_close, expected):
                    break
                board_count += 1
                cursor -= 1

        board_type = ""
        if is_limit_up:
            if _near(open_price, up_price) and _near(high, up_price) and _near(low, up_price):
                board_type = "一字板"
            elif _near(open_price, up_price) and low < up_price - 0.011:
                board_type = "T字板"
            else:
                board_type = "换手板"

        is_new_high_100 = False
        if pos >= 99:
            window = df.iloc[pos - 99 : pos + 1]
            previous_high = float(window.iloc[:-1]["high"].max())
            is_new_high_100 = high >= previous_high

        direction = 1 if close > previous_close else -1 if close < previous_close else 0
        found.append(
            (
                trade_date,
                StockSentimentRow(
                    code=code,
                    name=name,
                    is_limit_up=is_limit_up,
                    is_limit_down=is_limit_down,
                    touched_limit_up=high >= up_price - 0.011,
                    board_count=board_count,
                    board_type=board_type,
                    is_new_high_100=is_new_high_100,
                    first_board_date=(
                        df.iloc[pos - board_count + 1]["date"].strftime("%Y-%m-%d")
                        if board_count else None
                    ),
                ),
                direction,
            )
        )
    return found


def calculate_local_sentiment_batch(
    cache_dir: Path,
    trade_dates: list[str],
) -> dict[str, dict]:
    """一次遍历 Parquet 缓存，批量生成多个交易日的本地情绪数据。"""
    dates = sorted(set(trade_dates))
    if not dates:
        return {}
    cache_dir = Path(cache_dir)
    paths = list((cache_dir / "sh").glob("*.parquet")) + list(
        (cache_dir / "sz").glob("*.parquet")
    )
    names = _load_names(cache_dir)
    rows_by_date: dict[str, list[StockSentimentRow]] = {date: [] for date in dates}
    breadth: dict[str, list[int]] = {date: [0, 0, 0] for date in dates}
    with ThreadPoolExecutor(max_workers=LOCAL_SCAN_WORKERS) as executor:
        futures = [executor.submit(_scan_stock_dates, path, dates, names) for path in paths]
        for future in as_completed(futures):
            for date, row, direction in future.result():
                rows_by_date[date].append(row)
                breadth[date][0 if direction > 0 else 1 if direction < 0 else 2] += 1

    results: dict[str, dict] = {}
    for date in dates:
        rows = rows_by_date[date]
        limit_up = [row for row in rows if row.is_limit_up]
        limit_down = [row for row in rows if row.is_limit_down]
        new_high = [row for row in rows if row.is_new_high_100]
        ladder = [
            {
                "code": row.code,
                "name": row.name,
                "board_count": row.board_count,
                "board_type": row.board_type,
                "reason": "",
                "themes": [],
                "source": "local",
            }
            for row in limit_up
            if row.board_count > 0
        ]
        ladder.sort(key=lambda item: (-int(item["board_count"]), str(item["code"])))
        up_count, down_count, flat_count = breadth[date]
        results[date] = {
            "trade_date": date,
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
            "scanned_stock_count": len(rows),
            "limit_up_count": len(limit_up),
            "limit_down_count": len(limit_down),
            "limit_down_stocks": [
                {"code": row.code, "name": row.name, "themes": [], "source": "local"}
                for row in sorted(limit_down, key=lambda item: item.code)
            ],
            "broken_board_count": sum(
                1 for row in rows if row.touched_limit_up and not row.is_limit_up
            ),
            "new_high_100_count": len(new_high),
            "new_high_stocks": [
                {"code": row.code, "name": row.name, "themes": [], "source": "local"}
                for row in sorted(new_high, key=lambda item: item.code)
            ],
            "ladder": ladder,
            "complete": len(rows) > 0,
        }
    return results


def calculate_local_limit_downs(cache_dir: Path, trade_dates: list[str]) -> dict[str, list[dict]]:
    """一次遍历本地 Parquet，为多个交易日生成跌停股票名单。"""
    dates = sorted(set(trade_dates))
    result: dict[str, list[dict]] = {date: [] for date in dates}
    if not dates:
        return result
    cache_dir = Path(cache_dir)
    paths = list((cache_dir / "sh").glob("*.parquet")) + list(
        (cache_dir / "sz").glob("*.parquet")
    )
    names = _load_names(cache_dir)
    targets = {date: pd.Timestamp(date) for date in dates}

    def scan(path: Path) -> list[tuple[str, dict]]:
        columns = ["date", "high", "low", "close"]
        earliest = pd.Timestamp(dates[0]) - pd.Timedelta(days=10)
        latest = pd.Timestamp(dates[-1])
        try:
            df = pd.read_parquet(
                path,
                columns=columns,
                filters=[("date", ">=", earliest), ("date", "<=", latest)],
                engine="pyarrow",
            )
        except Exception:
            try:
                df = pd.read_parquet(path, columns=columns, engine="pyarrow")
            except Exception:
                return []
        if df.empty:
            return []
        df["date"] = pd.to_datetime(df["date"])
        df = df[(df["date"] >= earliest) & (df["date"] <= latest)].sort_values("date").reset_index(drop=True)
        if len(df) < 2:
            return []
        code = path.stem.upper()
        name = names.get(code, "")
        found: list[tuple[str, dict]] = []
        for date, target in targets.items():
            hits = df.index[df["date"] == target]
            if len(hits) == 0:
                continue
            pos = int(hits[-1])
            if pos <= 0:
                continue
            close = float(df.iloc[pos]["close"])
            previous_close = float(df.iloc[pos - 1]["close"])
            high = float(df.iloc[pos]["high"])
            low = float(df.iloc[pos]["low"])
            pct = _limit_pct_for_bar(code, name, previous_close, high, low, close)
            if _near(close, _limit_price(previous_close, pct, up=False)):
                found.append(
                    (date, {"code": code, "name": name, "themes": [], "source": "local"})
                )
        return found

    with ThreadPoolExecutor(max_workers=LOCAL_SCAN_WORKERS) as executor:
        futures = [executor.submit(scan, path) for path in paths]
        for future in as_completed(futures):
            for date, stock in future.result():
                result[date].append(stock)
    for stocks in result.values():
        stocks.sort(key=lambda item: item["code"])
    return result
