"""江恩角度线：自动识别关键拐点并生成角度线坐标。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

# 同花顺标准 9 条江恩角度线：1×8 … 1×1 … 8×1
STANDARD_FAN_RATIOS: list[tuple[str, float]] = [
    ("1×8", 1 / 8),
    ("1×4", 1 / 4),
    ("1×3", 1 / 3),
    ("1×2", 1 / 2),
    ("1×1", 1.0),
    ("2×1", 2.0),
    ("3×1", 3.0),
    ("4×1", 4.0),
    ("8×1", 8.0),
]

# 上升江恩线（从低点向右上方辐射）
UP_FAN_COLORS = [
    "#bdbdbd", "#90a4ae", "#81c784", "#66bb6a", "#ffeb3b",
    "#ff9800", "#f44336", "#e53935", "#d500f9",
]

# 下降江恩线（从高点向右下方辐射）
DOWN_FAN_COLORS = [
    "#bdbdbd", "#78909c", "#64b5f6", "#42a5f5", "#5c6bc0",
    "#7e57c2", "#673ab7", "#512da8", "#311b92",
]

# 窗口最高点距最近 N 个交易日内则不画下降江恩线
RECENT_HIGH_SKIP_DAYS = 7


@dataclass
class Pivot:
    idx: int
    date: str
    price: float
    kind: Literal["low", "high"]
    reason: str
    score: float = 0.0


def _fmt_date(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%d")


def _swing_low_indices(lows: pd.Series, half: int) -> list[int]:
    out: list[int] = []
    n = len(lows)
    for i in range(half, n - half):
        window = lows.iloc[i - half : i + half + 1]
        if lows.iloc[i] <= window.min():
            out.append(i)
    return out


def _swing_high_indices(highs: pd.Series, half: int) -> list[int]:
    out: list[int] = []
    n = len(highs)
    for i in range(half, n - half):
        window = highs.iloc[i - half : i + half + 1]
        if highs.iloc[i] >= window.max():
            out.append(i)
    return out


def _move_after_low(df: pd.DataFrame, idx: int) -> float:
    low = float(df.iloc[idx]["low"])
    if low <= 0 or idx >= len(df) - 1:
        return 0.0
    peak = float(df.iloc[idx + 1 :]["high"].max())
    return (peak - low) / low


def _move_after_high(df: pd.DataFrame, idx: int) -> float:
    high = float(df.iloc[idx]["high"])
    if high <= 0 or idx >= len(df) - 1:
        return 0.0
    trough = float(df.iloc[idx + 1 :]["low"].min())
    return (high - trough) / high


def _find_launch_low_pivot(df: pd.DataFrame) -> Pivot | None:
    """识别连板/爆发起涨点：连续涨停或短期急涨的第一档低点。"""
    n = len(df)
    if n < 5:
        return None

    closes = df["close"].values
    lows = df["low"].values
    best: Pivot | None = None
    best_score = 0.0

    i = 1
    while i < n:
        prev_close = float(closes[i - 1])
        if prev_close <= 0:
            i += 1
            continue

        pct = (float(closes[i]) - prev_close) / prev_close

        if pct >= 0.095:
            chain_start = i
            chain_end = i
            while chain_end + 1 < n:
                pc = float(closes[chain_end])
                if pc <= 0:
                    break
                nxt = (float(closes[chain_end + 1]) - pc) / pc
                if nxt >= 0.095:
                    chain_end += 1
                else:
                    break

            chain_len = chain_end - chain_start + 1
            lookback_start = max(0, chain_start - 5)
            anchor_slice = lows[lookback_start : chain_start + 1]
            anchor_rel = int(anchor_slice.argmin())
            anchor_idx = lookback_start + anchor_rel

            peak_after = float(df.iloc[anchor_idx + 1 :]["high"].max()) if anchor_idx < n - 1 else 0.0
            anchor_price = float(df.iloc[anchor_idx]["low"])
            if anchor_price <= 0 or peak_after <= 0:
                i = chain_end + 1
                continue

            total_move = (peak_after - anchor_price) / anchor_price
            if total_move < 0.15:
                i = chain_end + 1
                continue

            launch_date = _fmt_date(df.iloc[chain_start]["date"])
            score = total_move * (1.0 + 0.35 * chain_len)
            if score > best_score:
                best_score = score
                if chain_len >= 2:
                    reason = f"连板起点 {launch_date}（{chain_len} 连板，涨幅 {total_move * 100:.1f}%）"
                else:
                    reason = f"起涨首板 {launch_date}（涨幅 {total_move * 100:.1f}%）"
                best = Pivot(
                    idx=anchor_idx,
                    date=_fmt_date(df.iloc[anchor_idx]["date"]),
                    price=round(anchor_price, 2),
                    kind="low",
                    reason=reason,
                    score=round(score, 4),
                )
            i = chain_end + 1
            continue

        i += 1

    return best


def _find_high_after_low(df: pd.DataFrame, low_idx: int) -> int:
    """起涨低点之后的阶段最高点（须留出下降线绘制空间）。"""
    highs = df["high"]
    n = len(df)
    if low_idx >= n - 1:
        return int(highs.values.argmax())

    tail_start = low_idx + 1
    tail = df.iloc[tail_start:]
    rel_peak = int(tail["high"].values.argmax())
    peak_idx = tail_start + rel_peak

    # 若阶段高点在最后一根，向前找最近的摆动高点以便下降线能向右延伸
    if peak_idx >= n - 2:
        swing_highs = _swing_high_indices(df["high"], half=5)
        candidates = [i for i in swing_highs if tail_start <= i < n - 5]
        if candidates:
            return max(candidates, key=lambda i: float(df.iloc[i]["high"]))
    return peak_idx


def _find_main_wave_pair(
    df: pd.DataFrame,
    *,
    swing_half: int,
    min_move_pct: float,
) -> tuple[Pivot, Pivot]:
    """主波段配对：窗口内幅度最大的 低→高 结构。"""
    lows = df["low"]
    highs = df["high"]
    swing_lows = _swing_low_indices(lows, swing_half)

    best_low_idx: int | None = None
    best_high_idx: int | None = None
    best_swing = 0.0

    candidates = swing_lows if swing_lows else [int(lows.values.argmin())]

    for low_idx in candidates:
        move_up = _move_after_low(df, low_idx)
        if move_up < min_move_pct:
            continue
        after_high = float(df.iloc[low_idx + 1 :]["high"].max())
        high_slice = df.iloc[low_idx + 1 :]
        if high_slice.empty:
            continue
        high_idx = low_idx + 1 + int(high_slice["high"].values.argmax())
        swing = (after_high - float(df.iloc[low_idx]["low"])) / float(df.iloc[low_idx]["low"])
        recency = (low_idx + 1) / len(df)
        score = swing * (0.7 + 0.3 * recency)
        if score > best_swing:
            best_swing = score
            best_low_idx = low_idx
            best_high_idx = high_idx

    if best_low_idx is None or best_high_idx is None:
        low_idx = int(lows.values.argmin())
        high_slice = df.iloc[low_idx + 1 :] if low_idx < len(df) - 1 else df.iloc[-1:]
        if len(high_slice) > 0:
            high_idx = low_idx + 1 + int(high_slice["high"].values.argmax())
        else:
            high_idx = int(highs.values.argmax())
        reason = f"{len(df)}日窗口极值配对"
    else:
        low_idx = best_low_idx
        high_idx = best_high_idx
        pct = (float(df.iloc[high_idx]["high"]) - float(df.iloc[low_idx]["low"])) / float(
            df.iloc[low_idx]["low"]
        ) * 100
        reason = f"主波段（涨幅 {pct:.1f}%）"

    low_pivot = Pivot(
        idx=low_idx,
        date=_fmt_date(df.iloc[low_idx]["date"]),
        price=round(float(df.iloc[low_idx]["low"]), 2),
        kind="low",
        reason=reason,
        score=round(best_swing, 4),
    )
    high_pivot = Pivot(
        idx=high_idx,
        date=_fmt_date(df.iloc[high_idx]["date"]),
        price=round(float(df.iloc[high_idx]["high"]), 2),
        kind="high",
        reason=reason,
        score=round(best_swing, 4),
    )
    return low_pivot, high_pivot


def _find_first_wave_peak(
    df: pd.DataFrame,
    low_idx: int,
    *,
    max_bars: int = 45,
    pullback_pct: float = 0.08,
) -> tuple[int, float]:
    """第一波主升浪高点：起涨后首次急涨段的顶点。"""
    n = len(df)
    end = min(n, low_idx + max_bars)
    if low_idx >= end - 1:
        return low_idx, float(df.iloc[low_idx]["high"])

    peak_idx = low_idx
    peak_high = float(df.iloc[low_idx]["high"])

    for i in range(low_idx + 1, end):
        h = float(df.iloc[i]["high"])
        c = float(df.iloc[i]["close"])
        if h >= peak_high:
            peak_high = h
            peak_idx = i
            continue
        if peak_idx <= low_idx:
            continue
        drop = max(
            (peak_high - h) / peak_high if peak_high > 0 else 0.0,
            (peak_high - c) / peak_high if peak_high > 0 else 0.0,
        )
        if i > peak_idx + 1 and drop >= pullback_pct:
            break

    return peak_idx, peak_high


def _find_first_wave_trough(
    df: pd.DataFrame,
    high_idx: int,
    *,
    max_bars: int = 45,
    bounce_pct: float = 0.08,
) -> tuple[int, float]:
    """第一波回踩低点：高点之后首次明显回调的谷底。"""
    n = len(df)
    end = min(n, high_idx + max_bars)
    if high_idx >= end - 1:
        return high_idx, float(df.iloc[high_idx]["low"])

    trough_idx = high_idx
    trough_low = float(df.iloc[high_idx]["low"])

    for i in range(high_idx + 1, end):
        lo = float(df.iloc[i]["low"])
        c = float(df.iloc[i]["close"])
        if lo <= trough_low:
            trough_low = lo
            trough_idx = i
            continue
        if trough_idx <= high_idx:
            continue
        bounce = max(
            (c - trough_low) / trough_low if trough_low > 0 else 0.0,
            (lo - trough_low) / trough_low if trough_low > 0 else 0.0,
        )
        if i > trough_idx + 1 and bounce >= bounce_pct:
            break

    return trough_idx, trough_low


def _find_window_high_pivot(df: pd.DataFrame) -> Pivot:
    """窗口内最高点，作为下降江恩线起点。"""
    highs = df["high"].values
    max_h = float(highs.max())
    idx = max(i for i, h in enumerate(highs) if float(h) >= max_h - 1e-9)
    return Pivot(
        idx=idx,
        date=_fmt_date(df.iloc[idx]["date"]),
        price=round(max_h, 2),
        kind="high",
        reason="窗口内最高点",
        score=0.0,
    )


def _high_in_recent_bars(high_idx: int, total_bars: int, recent: int = RECENT_HIGH_SKIP_DAYS) -> bool:
    """最高点是否落在最近 recent 个交易日内（含最后一根）。"""
    return high_idx >= total_bars - recent


def _find_trough_after_high(df: pd.DataFrame, high_idx: int) -> tuple[int, float]:
    """高点之后的回调低点，用于下降扇形 8×1 校准。"""
    n = len(df)
    if high_idx >= n - 1:
        return high_idx, float(df.iloc[high_idx]["low"])

    trough_idx, trough_low = _find_first_wave_trough(df, high_idx)
    if trough_idx > high_idx:
        return trough_idx, trough_low

    after = df.iloc[high_idx + 1 :]
    rel = int(after["low"].values.argmin())
    return high_idx + 1 + rel, float(after.iloc[rel]["low"])


def _price_display_bounds(df: pd.DataFrame) -> tuple[float, float]:
    """江恩线可视延伸上下界，避免拉垮 K 线纵轴。"""
    lo = float(df["low"].min())
    hi = float(df["high"].max())
    margin = max((hi - lo) * 0.15, hi * 0.05, 0.05)
    return max(lo - margin, 0.01), hi + margin


def _build_morph_line_points(
    df: pd.DataFrame,
    anchor_idx: int,
    anchor_price: float,
    ref_idx: int,
    ref_price: float,
    *,
    ratio: float,
    direction: Literal["up", "down"],
) -> list[dict[str, Any]]:
    """按形态校准：8×1 线必过参考点 ref（上升过第一波高点 / 下降过第一波低点）。"""
    bars = ref_idx - anchor_idx
    if bars <= 0:
        return []

    price_lo, price_hi = _price_display_bounds(df)

    if direction == "up":
        move = ref_price - anchor_price
        if move <= 0:
            return []
        unit = move / (8.0 * bars)
        slope = ratio * unit
        points: list[dict[str, Any]] = []
        for i in range(anchor_idx, len(df)):
            b = i - anchor_idx
            price = anchor_price + slope * b
            if price > price_hi and i > ref_idx:
                break
            points.append({
                "time": _fmt_date(df.iloc[i]["date"]),
                "value": round(price, 2),
            })
        return points

    move = anchor_price - ref_price
    if move <= 0:
        return []
    unit = move / (8.0 * bars)
    slope = ratio * unit
    points = []
    for i in range(anchor_idx, len(df)):
        b = i - anchor_idx
        price = anchor_price - slope * b
        if price <= 0 or (price < price_lo and i > ref_idx):
            break
        points.append({
            "time": _fmt_date(df.iloc[i]["date"]),
            "value": round(max(price, 0.01), 2),
        })
    return points


def _adaptive_price_scale(df: pd.DataFrame) -> float:
    lo = float(df["low"].min())
    hi = float(df["high"].max())
    span = max(hi - lo, hi * 0.01, 0.01)
    return span / max(len(df), 1)


def _one_by_one_scale_from_morph(
    anchor_price: float,
    ref_price: float,
    bars: int,
    direction: Literal["up", "down"],
) -> float:
    """形态校准后的 1×1 斜率（元/交易日）。"""
    if bars <= 0:
        return 0.0
    move = (ref_price - anchor_price) if direction == "up" else (anchor_price - ref_price)
    if move <= 0:
        return 0.0
    return round(move / (8.0 * bars), 4)


def _build_line_points(
    df: pd.DataFrame,
    anchor_idx: int,
    anchor_price: float,
    *,
    ratio: float,
    direction: Literal["up", "down"],
    price_scale: float,
) -> list[dict[str, Any]]:
    sign = 1.0 if direction == "up" else -1.0
    points: list[dict[str, Any]] = []
    for i in range(anchor_idx, len(df)):
        bars = i - anchor_idx
        price = anchor_price + sign * ratio * bars * price_scale
        if direction == "down" and price <= 0:
            break
        points.append({
            "time": _fmt_date(df.iloc[i]["date"]),
            "value": round(max(price, 0.01), 2),
        })
    return points


def _idx_at_date(df: pd.DataFrame, date_str: str) -> int:
    """在窗口内定位交易日；非交易日则取不晚于该日的最近一根 K 线。"""
    target = pd.Timestamp(date_str).normalize()
    exact: int | None = None
    nearest_on_or_before: int | None = None
    for i in range(len(df)):
        bar_date = pd.Timestamp(df.iloc[i]["date"]).normalize()
        if bar_date == target:
            exact = i
            break
        if bar_date <= target:
            nearest_on_or_before = i
    if exact is not None:
        return exact
    if nearest_on_or_before is not None:
        return nearest_on_or_before
    raise ValueError(f"日期早于当前窗口: {date_str}")


def _manual_up_pivot(df: pd.DataFrame, date_str: str) -> Pivot:
    idx = _idx_at_date(df, date_str)
    return Pivot(
        idx=idx,
        date=_fmt_date(df.iloc[idx]["date"]),
        price=round(float(df.iloc[idx]["low"]), 2),
        kind="low",
        reason="用户指定上升起点",
        score=0.0,
    )


def _manual_down_pivot(df: pd.DataFrame, date_str: str) -> Pivot:
    idx = _idx_at_date(df, date_str)
    return Pivot(
        idx=idx,
        date=_fmt_date(df.iloc[idx]["date"]),
        price=round(float(df.iloc[idx]["high"]), 2),
        kind="high",
        reason="用户指定下降起点",
        score=0.0,
    )


def compute_gann_analysis(
    df: pd.DataFrame,
    *,
    swing_half: int = 10,
    min_move_pct: float = 0.08,
    up_anchor_date: str | None = None,
    down_anchor_date: str | None = None,
) -> dict[str, Any]:
    """基于 OHLC DataFrame 计算江恩角度线（与策略无关）。"""
    if df.empty or len(df) < swing_half * 2 + 5:
        return {
            "anchors": {"up": None, "down": None},
            "calibration": {"up_ref": None, "down_ref": None},
            "lines": [],
            "price_scale": 0.0,
            "window_bars": len(df),
            "note": "K 线数据不足，无法计算江恩角度线",
        }

    work = df.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date", ascending=True).reset_index(drop=True)

    low_pivot, _high_pivot_unused = _find_main_wave_pair(
        work, swing_half=swing_half, min_move_pct=min_move_pct
    )

    if up_anchor_date:
        low_pivot = _manual_up_pivot(work, up_anchor_date)
    else:
        launch_low = _find_launch_low_pivot(work)
        if launch_low is not None:
            low_pivot = launch_low

    # 形态校准：上升 8×1 线粘合第一波主升浪高点
    peak_idx, peak_price = _find_first_wave_peak(work, low_pivot.idx)
    if peak_idx <= low_pivot.idx:
        peak_idx = min(low_pivot.idx + 1, len(work) - 1)
        peak_price = float(work.iloc[peak_idx]["high"])
    peak_pivot = Pivot(
        idx=peak_idx,
        date=_fmt_date(work.iloc[peak_idx]["date"]),
        price=round(peak_price, 2),
        kind="high",
        reason="第一波主升浪高点（8×1 校准点）",
        score=low_pivot.score,
    )

    # 下降起点：用户指定或窗口内最高点
    n_bars = len(work)
    if down_anchor_date:
        window_high_pivot = _manual_down_pivot(work, down_anchor_date)
    else:
        window_high_pivot = _find_window_high_pivot(work)
    high_pivot = window_high_pivot
    skip_down = _high_in_recent_bars(window_high_pivot.idx, n_bars)

    if skip_down:
        reason = (
            f"用户指定下降起点（最近{RECENT_HIGH_SKIP_DAYS}日内，不画下降线）"
            if down_anchor_date
            else f"窗口内最高点（最近{RECENT_HIGH_SKIP_DAYS}日内，不画下降线）"
        )
        high_pivot = Pivot(
            idx=window_high_pivot.idx,
            date=window_high_pivot.date,
            price=window_high_pivot.price,
            kind="high",
            reason=reason,
            score=0.0,
        )
        trough_pivot = Pivot(
            idx=window_high_pivot.idx,
            date=window_high_pivot.date,
            price=round(float(work.iloc[window_high_pivot.idx]["low"]), 2),
            kind="low",
            reason="—",
            score=0.0,
        )
    else:
        trough_idx, trough_price = _find_trough_after_high(work, window_high_pivot.idx)
        trough_pivot = Pivot(
            idx=trough_idx,
            date=_fmt_date(work.iloc[trough_idx]["date"]),
            price=round(trough_price, 2),
            kind="low",
            reason="高点后回调低点（8×1 校准点）",
            score=low_pivot.score,
        )

    peak_bars = peak_idx - low_pivot.idx
    price_scale = _one_by_one_scale_from_morph(
        low_pivot.price, peak_price, peak_bars, "up"
    )

    lines: list[dict[str, Any]] = []

    for (label, ratio), color in zip(STANDARD_FAN_RATIOS, UP_FAN_COLORS, strict=True):
        pts = _build_morph_line_points(
            work,
            low_pivot.idx,
            low_pivot.price,
            peak_idx,
            peak_price,
            ratio=ratio,
            direction="up",
        )
        if len(pts) >= 2:
            lines.append({
                "label": f"{label}↑",
                "color": color,
                "direction": "up",
                "points": pts,
            })

    if not skip_down:
        trough_idx = trough_pivot.idx
        trough_price = trough_pivot.price
        trough_bars = trough_idx - window_high_pivot.idx
        if (
            trough_bars > 0
            and trough_price < window_high_pivot.price
            and window_high_pivot.idx < n_bars - 1
        ):
            for (label, ratio), color in zip(STANDARD_FAN_RATIOS, DOWN_FAN_COLORS, strict=True):
                pts = _build_morph_line_points(
                    work,
                    window_high_pivot.idx,
                    window_high_pivot.price,
                    trough_idx,
                    trough_price,
                    ratio=ratio,
                    direction="down",
                )
                if len(pts) >= 2:
                    lines.append({
                        "label": f"{label}↓",
                        "color": color,
                        "direction": "down",
                        "points": pts,
                    })

    return {
        "anchors": {
            "up": {
                "date": low_pivot.date,
                "price": low_pivot.price,
                "kind": low_pivot.kind,
                "reason": low_pivot.reason,
            },
            "down": {
                "date": high_pivot.date,
                "price": high_pivot.price,
                "kind": high_pivot.kind,
                "reason": high_pivot.reason,
            },
        },
        "calibration": {
            "up_ref": {
                "date": peak_pivot.date,
                "price": peak_pivot.price,
                "kind": peak_pivot.kind,
                "reason": peak_pivot.reason,
            },
            "down_ref": None if skip_down else {
                "date": trough_pivot.date,
                "price": trough_pivot.price,
                "kind": trough_pivot.kind,
                "reason": trough_pivot.reason,
            },
        },
        "lines": lines,
        "price_scale": price_scale,
        "window_bars": len(work),
        "note": "",
    }
