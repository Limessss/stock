"""基于本地 Parquet 的区间涨幅排行，结果按行情版本落盘缓存。"""
from __future__ import annotations

import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCAN_WORKERS = 12
MATRIX_DAYS = 520
MATRIX_DIR = Path("derived") / "interval_gains"
MATRIX_NAME = "close_matrix.parquet"
MATRIX_META_NAME = "close_matrix.meta.json"
_cache_lock = threading.Lock()
_matrix_lock = threading.Lock()


def _load_names(cache_dir: Path) -> dict[str, str]:
    path = cache_dir / "stock_names.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(code).upper(): str(name).strip() for code, name in raw.items()}


def _source_version(cache_dir: Path) -> str:
    parts: list[str] = []
    for path in (cache_dir / "manifest.json", cache_dir / "market_overview.parquet"):
        try:
            stat = path.stat()
            parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
        except OSError:
            parts.append(f"{path.name}:missing")
    return "|".join(parts)


def _matrix_source_version(cache_dir: Path) -> str:
    path = cache_dir / "manifest.json"
    try:
        stat = path.stat()
        return f"{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        return "manifest:missing"


def _matrix_paths(cache_dir: Path) -> tuple[Path, Path]:
    directory = cache_dir / MATRIX_DIR
    return directory / MATRIX_NAME, directory / MATRIX_META_NAME


def _read_matrix_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _matrix_dates(cache_dir: Path) -> list[str]:
    # 用多只本地股票的日期并集生成近期交易日，避免依赖可能稍后才更新的市场总览。
    candidates = sorted((cache_dir / "sh").glob("*.parquet"))[:12]
    candidates += sorted((cache_dir / "sz").glob("*.parquet"))[:12]
    date_parts: list[pd.Series] = []
    for path in candidates:
        try:
            frame = pd.read_parquet(path, columns=["date"], engine="pyarrow")
        except Exception:
            continue
        if not frame.empty:
            date_parts.append(pd.to_datetime(frame["date"], errors="coerce").dropna().tail(MATRIX_DAYS + 20))
    if not date_parts:
        return []
    dates = pd.concat(date_parts, ignore_index=True).drop_duplicates().sort_values()
    return [value.strftime("%Y-%m-%d") for value in dates.tail(MATRIX_DAYS)]


def _read_matrix_row(
    row_index: int,
    path: Path,
    start_date: str,
    date_positions: dict[str, int],
) -> tuple[int, str, list[int], list[float]]:
    close_column = "qfq_close"
    try:
        frame = pd.read_parquet(
            path,
            columns=["date", close_column],
            filters=[("date", ">=", pd.Timestamp(start_date))],
            engine="pyarrow",
        ).rename(columns={close_column: "close"})
    except Exception:
        try:
            frame = pd.read_parquet(
                path,
                columns=["date", "close"],
                filters=[("date", ">=", pd.Timestamp(start_date))],
                engine="pyarrow",
            )
        except Exception:
            return row_index, path.stem.upper(), [], []
    if frame.empty:
        return row_index, path.stem.upper(), [], []
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame = frame.dropna(subset=["date", "close"]).drop_duplicates("date", keep="last")
    positions: list[int] = []
    values: list[float] = []
    for date, close in frame[["date", "close"]].itertuples(index=False, name=None):
        position = date_positions.get(str(date))
        if position is not None:
            positions.append(position)
            values.append(float(close))
    return row_index, path.stem.upper(), positions, values


def build_close_matrix(cache_dir: Path, *, force: bool = False) -> dict[str, Any]:
    """预计算近期收盘价宽表；行情版本不变时直接复用。"""
    cache_dir = Path(cache_dir)
    matrix_path, meta_path = _matrix_paths(cache_dir)
    source_version = _matrix_source_version(cache_dir)
    meta = _read_matrix_meta(meta_path)
    if not force and matrix_path.exists() and meta.get("source_version") == source_version:
        return meta

    with _matrix_lock:
        meta = _read_matrix_meta(meta_path)
        if not force and matrix_path.exists() and meta.get("source_version") == source_version:
            return meta
        dates = _matrix_dates(cache_dir)
        if len(dates) < 2:
            raise ValueError("近期收盘价矩阵缺少交易日")
        paths = list((cache_dir / "sh").glob("*.parquet")) + list((cache_dir / "sz").glob("*.parquet"))
        paths.sort(key=lambda value: value.stem)
        date_positions = {date: index for index, date in enumerate(dates)}
        values = np.full((len(paths), len(dates)), np.nan, dtype=np.float32)
        codes = [path.stem.upper() for path in paths]
        with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as executor:
            futures = [
                executor.submit(_read_matrix_row, index, path, dates[0], date_positions)
                for index, path in enumerate(paths)
            ]
            for future in as_completed(futures):
                row_index, code, positions, closes = future.result()
                codes[row_index] = code
                if positions:
                    values[row_index, positions] = closes

        matrix_path.parent.mkdir(parents=True, exist_ok=True)
        temp_matrix = matrix_path.with_suffix(".parquet.tmp")
        payload = {"code": codes}
        payload.update({date: values[:, index] for index, date in enumerate(dates)})
        pd.DataFrame(payload).to_parquet(
            temp_matrix,
            engine="pyarrow",
            index=False,
            compression="zstd",
        )
        temp_matrix.replace(matrix_path)
        meta = {
            "source_version": source_version,
            "built_at": datetime.now(UTC).isoformat(),
            "start_date": dates[0],
            "end_date": dates[-1],
            "date_count": len(dates),
            "stock_count": len(paths),
        }
        temp_meta = meta_path.with_suffix(".json.tmp")
        temp_meta.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        temp_meta.replace(meta_path)
        return meta


def _read_matrix_gains(
    cache_dir: Path,
    start_date: str,
    end_date: str,
    names: dict[str, str],
) -> list[dict[str, Any]] | None:
    try:
        build_close_matrix(cache_dir)
    except Exception:
        return None
    matrix_path, _ = _matrix_paths(cache_dir)
    try:
        frame = pd.read_parquet(
            matrix_path,
            columns=["code", start_date, end_date],
            engine="pyarrow",
        )
    except Exception:
        return None
    start_values = pd.to_numeric(frame[start_date], errors="coerce")
    end_values = pd.to_numeric(frame[end_date], errors="coerce")
    codes = frame["code"].astype(str).str.upper()
    valid = (
        start_values.notna()
        & end_values.notna()
        & np.isfinite(start_values)
        & np.isfinite(end_values)
        & (start_values > 0)
        & (end_values > 0)
        & codes.str.fullmatch(r"(?:SH|SZ|BJ)\d{6}")
    )
    if not valid.any():
        return []
    selected = frame.loc[valid, ["code"]].copy()
    selected["start_close"] = start_values.loc[valid].astype(float)
    selected["end_close"] = end_values.loc[valid].astype(float)
    selected["gain_pct"] = (selected["end_close"] / selected["start_close"] - 1) * 100
    selected = selected.sort_values(["gain_pct", "code"], ascending=[False, True])
    items: list[dict[str, Any]] = []
    for rank, row in enumerate(selected.itertuples(index=False), 1):
        code = str(row.code).upper()
        items.append({
            "rank": rank,
            "code": code,
            "name": names.get(code, ""),
            "start_close": round(float(row.start_close), 3),
            "end_close": round(float(row.end_close), 3),
            "gain_pct": round(float(row.gain_pct), 4),
        })
    return items


def _resolve_period(
    cache_dir: Path,
    end_date: str | None,
    days: int,
    start_date: str | None = None,
) -> tuple[str, str, int]:
    # 直接从个股行情缓存取交易日，避免 market_overview 更新滞后导致默认区间不是最新。
    available_dates = _matrix_dates(cache_dir)
    if not available_dates:
        raise ValueError("缺少个股交易日缓存，请先在数据管理中更新本地行情")
    dates = pd.Series(pd.to_datetime(available_dates)).drop_duplicates().sort_values()
    if end_date:
        target = pd.Timestamp(end_date)
        dates = dates[dates <= target]
    if dates.empty:
        raise ValueError("所选结束日期之前没有交易日")
    resolved_end = dates.iloc[-1]
    if start_date:
        target_start = pd.Timestamp(start_date)
        candidates = dates[dates >= target_start]
        if candidates.empty:
            raise ValueError("所选区间内没有交易日")
        resolved_start = candidates.iloc[0]
        span_days = int(((dates >= resolved_start) & (dates <= resolved_end)).sum()) - 1
        if span_days < 1:
            raise ValueError("区间至少需要包含两个交易日")
        return (
            resolved_start.strftime("%Y-%m-%d"),
            resolved_end.strftime("%Y-%m-%d"),
            span_days,
        )
    if len(dates) <= days:
        raise ValueError(f"所选日期之前不足 {days} 个交易日")
    return (
        dates.iloc[-(days + 1)].strftime("%Y-%m-%d"),
        resolved_end.strftime("%Y-%m-%d"),
        days,
    )


def _read_gain(path: Path, start_date: str, end_date: str, names: dict[str, str]) -> dict[str, Any] | None:
    try:
        frame = pd.read_parquet(
            path,
            columns=["date", "qfq_close"],
            filters=[("date", ">=", pd.Timestamp(start_date)), ("date", "<=", pd.Timestamp(end_date))],
            engine="pyarrow",
        ).rename(columns={"qfq_close": "close"})
    except Exception:
        try:
            frame = pd.read_parquet(
                path,
                columns=["date", "close"],
                filters=[("date", ">=", pd.Timestamp(start_date)), ("date", "<=", pd.Timestamp(end_date))],
                engine="pyarrow",
            )
        except Exception:
            return None
    if frame.empty:
        return None
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    closes = frame.dropna(subset=["date", "close"]).drop_duplicates("date", keep="last").set_index("date")["close"]
    start_key = pd.Timestamp(start_date)
    end_key = pd.Timestamp(end_date)
    if start_key not in closes.index or end_key not in closes.index:
        return None
    start_close = float(closes.loc[start_key])
    end_close = float(closes.loc[end_key])
    if (
        start_close <= 0
        or end_close <= 0
        or not math.isfinite(start_close)
        or not math.isfinite(end_close)
    ):
        return None
    code = path.stem.upper()
    return {
        "code": code,
        "name": names.get(code, ""),
        "start_close": round(start_close, 3),
        "end_close": round(end_close, 3),
        "gain_pct": round((end_close / start_close - 1) * 100, 4),
    }


def _cache_path(cache_dir: Path, start_date: str, end_date: str) -> Path:
    return cache_dir / "derived" / "interval_gains" / f"{start_date}_{end_date}.json"


def _read_cached(path: Path, source_version: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if payload.get("source_version") == source_version else None


def _write_cached(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(path)


def get_interval_gains(
    cache_dir: Path,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    days: int = 10,
    limit: int = 50,
) -> dict[str, Any]:
    """统计全市场区间涨幅；同一行情版本与区间只扫描一次。"""
    cache_dir = Path(cache_dir)
    resolved_start_date, resolved_end_date, resolved_days = _resolve_period(
        cache_dir, end_date, days, start_date
    )
    source_version = _source_version(cache_dir)
    cache_path = _cache_path(cache_dir, resolved_start_date, resolved_end_date)

    payload = _read_cached(cache_path, source_version)
    cache_hit = payload is not None
    if payload is None:
        with _cache_lock:
            payload = _read_cached(cache_path, source_version)
            cache_hit = payload is not None
            if payload is None:
                paths = list((cache_dir / "sh").glob("*.parquet")) + list((cache_dir / "sz").glob("*.parquet"))
                names = _load_names(cache_dir)
                items = _read_matrix_gains(
                    cache_dir, resolved_start_date, resolved_end_date, names
                )
                source = "local_qfq_close_matrix"
                if items is None:
                    source = "local_qfq_parquet"
                    items = []
                    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as executor:
                        futures = [executor.submit(_read_gain, path, resolved_start_date, resolved_end_date, names) for path in paths]
                        for future in as_completed(futures):
                            item = future.result()
                            if item is not None:
                                items.append(item)
                    items.sort(key=lambda item: (-float(item["gain_pct"]), str(item["code"])))
                    for rank, item in enumerate(items, 1):
                        item["rank"] = rank
                payload = {
                    "start_date": resolved_start_date,
                    "end_date": resolved_end_date,
                    "days": resolved_days,
                    "total_candidates": len(paths),
                    "scanned_stocks": len(items),
                    "source": source,
                    "source_version": source_version,
                    "generated_at": datetime.now(UTC).isoformat(),
                    "items": items,
                }
                _write_cached(cache_path, payload)

    result = dict(payload)
    result["cache_hit"] = cache_hit
    result["items"] = list(payload.get("items", []))[:limit]
    return result
