"""K 线数据读取（给前端画图用）。"""
from __future__ import annotations

from typing import Any

import pandas as pd

from model.data.indicators import add_indicators
from model.data.tdx_parser import parse_day_file

from ..core.config import settings
from .cache_service import get_cache

INDEX_NAMES: dict[str, str] = {
    "SH000001": "上证指数",
    "SH000016": "上证50",
    "SH000300": "沪深300",
    "SH000688": "科创50",
    "SH000852": "中证1000",
    "SH000905": "中证500",
    "SZ399001": "深证成指",
    "SZ399005": "中小100",
    "SZ399006": "创业板指",
    "SZ399303": "国证2000",
}


def _is_index_code(code: str) -> bool:
    normalized = code.upper()
    return normalized.startswith("SH000") or normalized.startswith("SZ399")


def _load_frame(code: str) -> pd.DataFrame | None:
    """优先读取个股 Parquet；指数直接读取通达信日线原始文件。"""
    normalized = code.upper()
    cached = get_cache().load(normalized)
    if cached is not None:
        return cached
    if not _is_index_code(normalized):
        return None
    market = "sh" if normalized.startswith("SH") else "sz"
    raw_path = settings.raw_dir / market / "lday" / f"{normalized.lower()}.day"  # type: ignore[operator]
    return parse_day_file(raw_path, min_records=1)


def get_kline_name(code: str) -> str | None:
    return INDEX_NAMES.get(code.upper())


def _idx_at_or_before(df: pd.DataFrame, date_str: str) -> int:
    ts = pd.Timestamp(date_str)
    mask = df["date"] <= ts
    if not mask.any():
        raise ValueError(f"date not in data: {date_str}")
    return int(df.index[mask][-1])


def get_kline(
    code: str,
    last_n: int = 250,
    *,
    adjust: str = "qfq",
    end_date: str | None = None,
    min_date: str | None = None,
    center_date: str | None = None,
    max_date: str | None = None,
) -> dict[str, Any]:
    """返回 K 线 + 指标。

    - 默认：最近 last_n 根
    - center_date：以该交易日为窗口中点，向前后各取约 last_n/2 根
    - end_date：窗口右端对齐到该交易日（与 center_date 互斥，诊断旧逻辑）
    - min_date / max_date：扩展窗口以覆盖买卖日、试盘日等标记
    """
    df = _load_frame(code)
    if df is None:
        return {
            "code": code,
            "candles": [],
            "ma5": [],
            "ma10": [],
            "ma20": [],
            "ma60": [],
            "volume": [],
            "macd": [],
            "dif": [],
            "dea": [],
        }

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date", ascending=True).reset_index(drop=True)
    use_qfq = adjust == "qfq" and all(
        f"qfq_{column}" in df.columns for column in ("open", "high", "low", "close")
    )

    if center_date:
        center_idx = _idx_at_or_before(df, center_date)
        half = max(1, last_n // 2)
        start_idx = center_idx - half
        end_idx = center_idx + half
        for extra in (min_date, max_date):
            if extra:
                idx = _idx_at_or_before(df, extra)
                start_idx = min(start_idx, idx - 12)
                end_idx = max(end_idx, idx + 12)
        start_idx = max(0, start_idx)
        end_idx = min(len(df) - 1, end_idx)
        df = df.iloc[start_idx : end_idx + 1]
    elif end_date:
        end_idx = _idx_at_or_before(df, end_date)
        start_idx = max(0, end_idx - last_n + 1)
        if min_date:
            min_idx = _idx_at_or_before(df, min_date)
            start_idx = min(start_idx, max(0, min_idx - 15))
        df = df.iloc[start_idx : end_idx + 1]
    else:
        df = df.tail(last_n)

    df = df.reset_index(drop=True)
    if "macd" not in df.columns:
        df = add_indicators(df)

    candles = []
    volume = []
    macd_bars: list[dict[str, Any]] = []
    dif_line: list[dict[str, Any]] = []
    dea_line: list[dict[str, Any]] = []
    ma_lines: dict[str, list] = {f"ma{p}": [] for p in (5, 10, 20, 60)}
    prev_close: float | None = None

    for _, r in df.iterrows():
        ds = r["date"].strftime("%Y-%m-%d")
        price_prefix = "qfq_" if use_qfq else ""
        close = float(r[f"{price_prefix}close"])
        change_pct: float | None = None
        if prev_close is not None and prev_close > 0:
            change_pct = round((close - prev_close) / prev_close * 100, 2)
        prev_close = close
        raw_amount = r.get("amount")
        amount = round(float(raw_amount), 2) if pd.notna(raw_amount) else None
        candles.append({
            "time": ds,
            "open": round(float(r[f"{price_prefix}open"]), 2),
            "high": round(float(r[f"{price_prefix}high"]), 2),
            "low": round(float(r[f"{price_prefix}low"]), 2),
            "close": round(close, 2),
            "change_pct": change_pct,
            "amount": amount,
        })
        volume.append({
            "time": ds,
            "value": float(r["volume"]),
            "color": "#ef5350" if r["close"] >= r["open"] else "#26a69a",
        })
        indicator_prefix = "qfq_" if use_qfq and "qfq_macd" in df.columns else ""
        macd_v = r.get(f"{indicator_prefix}macd")
        if pd.notna(macd_v):
            mv = float(macd_v)
            macd_bars.append({
                "time": ds,
                "value": round(mv, 4),
                "color": "#ef5350" if mv >= 0 else "#26a69a",
            })
        dif_v = r.get(f"{indicator_prefix}dif")
        if pd.notna(dif_v):
            dif_line.append({"time": ds, "value": round(float(dif_v), 4)})
        dea_v = r.get(f"{indicator_prefix}dea")
        if pd.notna(dea_v):
            dea_line.append({"time": ds, "value": round(float(dea_v), 4)})
        for p in (5, 10, 20, 60):
            v = r.get(f"{indicator_prefix}ma{p}")
            if pd.notna(v):
                ma_lines[f"ma{p}"].append({"time": ds, "value": round(float(v), 2)})

    return {
        "code": code.upper(),
        "adjustment": "qfq" if use_qfq else "none",
        "candles": candles,
        "volume": volume,
        "macd": macd_bars,
        "dif": dif_line,
        "dea": dea_line,
        **ma_lines,
    }
