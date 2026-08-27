"""全市场日度行情总览（涨跌家数、成交额）预计算。

从 Parquet 缓存一次性扫描构建 `market_overview.parquet`，
后续按日期 O(1) 查询。
"""
from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .tdx_parser import parse_day_file
from .time_util import utc_now_iso

INDEX_CODE = "SH000001"
INDEX_RAW_NAME = "sh000001.day"

# 行情卡片展示的指数（通达信 .day 文件名）
MARKET_INDICES: list[dict[str, str]] = [
    {"code": "SH000001", "name": "上证指数", "market": "sh", "file": "sh000001.day"},
    {"code": "SZ399001", "name": "深证成指", "market": "sz", "file": "sz399001.day"},
    {"code": "SZ399006", "name": "创业板指", "market": "sz", "file": "sz399006.day"},
    {"code": "SH000688", "name": "科创50", "market": "sh", "file": "sh000688.day"},
]
OVERVIEW_NAME = "market_overview.parquet"
OVERVIEW_META_NAME = "market_overview.meta.json"
BUILD_WORKERS = 16


@dataclass
class BuildStatus:
    running: bool = False
    started_at: float = 0.0
    finished_at: float = 0.0
    error: str | None = None
    date_count: int = 0


_build_status = BuildStatus()
_build_lock = threading.Lock()


def _overview_path(cache_dir: Path) -> Path:
    return cache_dir / OVERVIEW_NAME


def _meta_path(cache_dir: Path) -> Path:
    return cache_dir / OVERVIEW_META_NAME


def _manifest_path(cache_dir: Path) -> Path:
    return cache_dir / "manifest.json"


def _load_index_df(raw_dir: Path) -> pd.DataFrame:
    """加载上证指数（交易日历 + 兼容旧逻辑）。"""
    indices = _load_indices(raw_dir)
    return indices.get(INDEX_CODE, pd.DataFrame(columns=["date", "close", "amount"]))


def _load_indices(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """加载全部指数日线。"""
    out: dict[str, pd.DataFrame] = {}
    for spec in MARKET_INDICES:
        path = raw_dir / spec["market"] / "lday" / spec["file"]
        df = parse_day_file(path, min_records=1)
        if df is None or df.empty:
            out[spec["code"]] = pd.DataFrame(columns=["date", "close", "amount"])
            continue
        df = df.sort_values("date").reset_index(drop=True)
        df["change_pct"] = df["close"].pct_change() * 100
        df["change_amt"] = df["close"].diff()
        out[spec["code"]] = df
    return out


def index_bar_at(indices: dict[str, pd.DataFrame], trade_date: str, code: str) -> dict | None:
    """取指定指数在某交易日的行情。"""
    df = indices.get(code)
    if df is None or df.empty:
        return None
    mask = df["date"] == pd.Timestamp(trade_date)
    if not mask.any():
        return None
    row = df.loc[mask].iloc[0]
    return {
        "code": code,
        "close": round(float(row["close"]), 2),
        "change_pct": round(float(row["change_pct"]), 2)
        if pd.notna(row["change_pct"])
        else None,
        "change_amt": round(float(row["change_amt"]), 2)
        if pd.notna(row["change_amt"])
        else None,
    }


def index_bars_for_date(
    indices: dict[str, pd.DataFrame], trade_date: str
) -> list[dict]:
    """返回当日全部指数行情（按 MARKET_INDICES 顺序）。"""
    name_map = {s["code"]: s["name"] for s in MARKET_INDICES}
    rows: list[dict] = []
    for spec in MARKET_INDICES:
        bar = index_bar_at(indices, trade_date, spec["code"])
        if bar is None:
            rows.append(
                {
                    "code": spec["code"],
                    "name": name_map[spec["code"]],
                    "close": None,
                    "change_pct": None,
                    "change_amt": None,
                }
            )
        else:
            rows.append({**bar, "name": name_map[spec["code"]]})
    return rows


def _index_by_date(index_df: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in index_df.itertuples(index=False):
        d = pd.Timestamp(row.date).strftime("%Y-%m-%d")
        out[d] = {
            "index_close": round(float(row.close), 2),
            "index_change_pct": round(float(row.change_pct), 2)
            if pd.notna(row.change_pct)
            else 0.0,
            "index_change_amt": round(float(row.change_amt), 2)
            if pd.notna(row.change_amt)
            else 0.0,
        }
    return out


def _process_stock(path: Path) -> list[tuple[str, int, float]]:
    try:
        df = pd.read_parquet(path, columns=["date", "close", "amount"], engine="pyarrow")
    except Exception:
        return []
    if len(df) < 2:
        return []
    df["date"] = pd.to_datetime(df["date"])
    closes = df["close"].to_numpy()
    amounts = df["amount"].to_numpy()
    dates = df["date"].to_numpy()
    rows: list[tuple[str, int, float]] = []
    for i in range(1, len(df)):
        prev = closes[i - 1]
        cur = closes[i]
        if cur > prev:
            direction = 1
        elif cur < prev:
            direction = -1
        else:
            direction = 0
        d = pd.Timestamp(dates[i]).strftime("%Y-%m-%d")
        rows.append((d, direction, float(amounts[i])))
    return rows


def _build_overview_df(cache_dir: Path) -> pd.DataFrame:
    stats: dict[str, list] = defaultdict(lambda: [0, 0, 0, 0.0])
    paths = list((cache_dir / "sh").glob("*.parquet")) + list(
        (cache_dir / "sz").glob("*.parquet")
    )
    with ThreadPoolExecutor(max_workers=BUILD_WORKERS) as ex:
        futs = [ex.submit(_process_stock, p) for p in paths]
        for fut in as_completed(futs):
            for d, direction, amount in fut.result():
                row = stats[d]
                row[3] += amount
                if direction > 0:
                    row[0] += 1
                elif direction < 0:
                    row[1] += 1
                else:
                    row[2] += 1

    rows = []
    for d in sorted(stats.keys()):
        up, down, flat, amount = stats[d]
        rows.append(
            {
                "trade_date": d,
                "up_count": up,
                "down_count": down,
                "flat_count": flat,
                "total_amount": amount,
            }
        )
    return pd.DataFrame(rows)


def get_build_status() -> BuildStatus:
    return _build_status


def needs_rebuild(cache_dir: Path) -> bool:
    pq = _overview_path(cache_dir)
    meta = _meta_path(cache_dir)
    manifest = _manifest_path(cache_dir)
    if not pq.exists() or not meta.exists():
        return True
    if not manifest.exists():
        return False
    try:
        meta_obj = json.loads(meta.read_text(encoding="utf-8"))
        manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
        return meta_obj.get("cache_last_updated") != manifest_obj.get("last_updated")
    except Exception:
        return True


def _write_meta(cache_dir: Path, *, date_count: int) -> None:
    manifest_last = ""
    manifest = _manifest_path(cache_dir)
    if manifest.exists():
        try:
            manifest_last = json.loads(manifest.read_text(encoding="utf-8")).get(
                "last_updated", ""
            )
        except Exception:
            pass
    _meta_path(cache_dir).write_text(
        json.dumps(
            {
                "built_at": utc_now_iso(),
                "date_count": date_count,
                "cache_last_updated": manifest_last,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def build_overview_sync(raw_dir: Path, cache_dir: Path) -> pd.DataFrame:
    """同步构建并落盘。"""
    overview = _build_overview_df(cache_dir)
    index_df = _load_index_df(raw_dir)
    index_map = _index_by_date(index_df)
    overview["index_close"] = overview["trade_date"].map(
        lambda d: index_map.get(d, {}).get("index_close")
    )
    overview["index_change_pct"] = overview["trade_date"].map(
        lambda d: index_map.get(d, {}).get("index_change_pct")
    )
    overview["index_change_amt"] = overview["trade_date"].map(
        lambda d: index_map.get(d, {}).get("index_change_amt")
    )
    path = _overview_path(cache_dir)
    overview.to_parquet(path, engine="pyarrow", index=False, compression="zstd")
    _write_meta(cache_dir, date_count=len(overview))
    return overview


def start_build_background(raw_dir: Path, cache_dir: Path) -> bool:
    """后台线程构建；若已有任务在跑则返回 False。"""
    if not _build_lock.acquire(blocking=False):
        return False
    try:
        if _build_status.running:
            return False
        _build_status.running = True
        _build_status.started_at = time.time()
        _build_status.finished_at = 0.0
        _build_status.error = None
        _build_status.date_count = 0

        def _run() -> None:
            try:
                df = build_overview_sync(raw_dir, cache_dir)
                _build_status.date_count = len(df)
            except Exception as e:  # noqa: BLE001
                _build_status.error = f"{type(e).__name__}: {e}"
            finally:
                _build_status.running = False
                _build_status.finished_at = time.time()
                _build_lock.release()

        threading.Thread(target=_run, daemon=True, name="market-overview-build").start()
        return True
    except Exception:
        _build_lock.release()
        raise


def ensure_overview(raw_dir: Path, cache_dir: Path) -> None:
    """若缺失或过期则触发后台构建。"""
    if needs_rebuild(cache_dir) and not _build_status.running:
        start_build_background(raw_dir, cache_dir)


def load_overview_df(cache_dir: Path) -> pd.DataFrame | None:
    path = _overview_path(cache_dir)
    if not path.exists():
        return None
    return pd.read_parquet(path, engine="pyarrow")


def trading_dates(index_df: pd.DataFrame) -> list[str]:
    if index_df.empty:
        return []
    return [pd.Timestamp(d).strftime("%Y-%m-%d") for d in index_df["date"]]


def resolve_trade_date(requested: str, index_df: pd.DataFrame) -> tuple[str, bool]:
    """将任意日期对齐到最近一个交易日（含当日）。"""
    req = pd.Timestamp(requested).strftime("%Y-%m-%d")
    dates = trading_dates(index_df)
    if not dates:
        return req, False
    if req in dates:
        return req, False
    prior = [d for d in dates if d <= req]
    if prior:
        resolved = prior[-1]
        return resolved, resolved != req
    return dates[0], True


def _stock_day_stats(path: Path, trade_date: str) -> tuple[int, float] | None:
    """单只股票在指定交易日的涨跌方向与成交额。"""
    try:
        df = pd.read_parquet(path, columns=["date", "close", "amount"], engine="pyarrow")
    except Exception:
        return None
    if len(df) < 2:
        return None
    df["date"] = pd.to_datetime(df["date"])
    ts = pd.Timestamp(trade_date)
    hits = df.index[df["date"] == ts]
    if len(hits) == 0:
        return None
    pos = df.index.get_loc(hits[0])
    if isinstance(pos, slice):
        pos = pos.start
    if not isinstance(pos, int) or pos <= 0:
        return None
    cur = float(df.iloc[pos]["close"])
    prev = float(df.iloc[pos - 1]["close"])
    amount = float(df.iloc[pos]["amount"])
    if cur > prev:
        direction = 1
    elif cur < prev:
        direction = -1
    else:
        direction = 0
    return direction, amount


def stats_for_date_from_cache(cache_dir: Path, trade_date: str) -> dict | None:
    """从本地个股 Parquet 缓存统计指定交易日涨跌家数与成交额。"""
    sh_dir = cache_dir / "sh"
    sz_dir = cache_dir / "sz"
    if not sh_dir.is_dir() and not sz_dir.is_dir():
        return None
    paths = list(sh_dir.glob("*.parquet")) + list(sz_dir.glob("*.parquet"))
    if not paths:
        return None

    up = down = flat = 0
    total_amount = 0.0
    found = False
    with ThreadPoolExecutor(max_workers=BUILD_WORKERS) as ex:
        futs = [ex.submit(_stock_day_stats, p, trade_date) for p in paths]
        for fut in as_completed(futs):
            row = fut.result()
            if row is None:
                continue
            found = True
            direction, amount = row
            total_amount += amount
            if direction > 0:
                up += 1
            elif direction < 0:
                down += 1
            else:
                flat += 1

    if not found:
        return None
    return {
        "up_count": up,
        "down_count": down,
        "flat_count": flat,
        "total_amount": total_amount,
    }


def lookup_cached_market_stats(cache_dir: Path, trade_date: str) -> dict | None:
    """优先读 market_overview.parquet，缺失时从个股缓存现算。"""
    return _lookup_cached_market_stats(str(cache_dir.resolve()), trade_date)


@lru_cache(maxsize=64)
def _lookup_cached_market_stats(cache_dir_str: str, trade_date: str) -> dict | None:
    cache_dir = Path(cache_dir_str)
    overview_path = cache_dir / OVERVIEW_NAME
    if overview_path.exists():
        try:
            df = pd.read_parquet(overview_path, engine="pyarrow")
            hit = lookup_overview(df, trade_date)
            if hit:
                return hit
        except Exception:
            pass
    return stats_for_date_from_cache(cache_dir, trade_date)


def lookup_overview(
    overview_df: pd.DataFrame | None,
    trade_date: str,
) -> dict | None:
    if overview_df is None or overview_df.empty:
        return None
    mask = overview_df["trade_date"] == trade_date
    if not mask.any():
        return None
    row = overview_df.loc[mask].iloc[0]
    return {
        "trade_date": trade_date,
        "index_close": _float_or_none(row.get("index_close")),
        "index_change_pct": _float_or_none(row.get("index_change_pct")),
        "index_change_amt": _float_or_none(row.get("index_change_amt")),
        "up_count": int(row.get("up_count") or 0),
        "down_count": int(row.get("down_count") or 0),
        "flat_count": int(row.get("flat_count") or 0),
        "total_amount": float(row.get("total_amount") or 0),
    }


def _float_or_none(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return float(v)
