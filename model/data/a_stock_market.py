"""行情总览 HTTP 数据源（a-stock-data 架构：腾讯财经 + 东财 push2/push2his）。

- 指数：东财 push2his 日 K（历史）+ 腾讯财经（最新交易日补充）
- 涨跌家数：东财 push2 clist fs=b:MK0010（沪深指数行的 f104/f105/f106 汇总）
- 成交额：东财 push2 clist 全 A 股 f6 分页求和（最新交易日）
"""
from __future__ import annotations

import json
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests

from .time_util import is_after_market_close, is_trading_session

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
EM_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://quote.eastmoney.com/",
    "Origin": "https://quote.eastmoney.com",
}
EM_DC_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://data.eastmoney.com/",
}

# 指数：code=内部代码, name=展示名, secid=东财, tencent=6位代码, tencent_symbol=腾讯完整符号
INDEX_SPECS: list[dict[str, str]] = [
    {
        "code": "SH000001",
        "name": "上证指数",
        "secid": "1.000001",
        "tencent": "000001",
        "tencent_symbol": "sh000001",
    },
    {
        "code": "SZ399001",
        "name": "深证成指",
        "secid": "0.399001",
        "tencent": "399001",
        "tencent_symbol": "sz399001",
    },
    {
        "code": "SZ399006",
        "name": "创业板指",
        "secid": "0.399006",
        "tencent": "399006",
        "tencent_symbol": "sz399006",
    },
    {
        "code": "SH000688",
        "name": "科创50",
        "secid": "1.000688",
        "tencent": "000688",
        "tencent_symbol": "sh000688",
    },
]

# 涨跌家数统计用的指数行（东财大盘板块）
BREADTH_FS = "b:MK0010"
BREADTH_CODES = {"000001", "399001"}
# 全 A 成交额
ASHARE_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"

_session = requests.Session()
_session.trust_env = False
_cache_lock = threading.Lock()
_calendar_cache: list[str] | None = None


def _get_json(url: str, *, params: dict | None = None, headers: dict | None = None, timeout: int = 12) -> dict:
    hdrs = headers or EM_HEADERS
    last_err: Exception | None = None
    for _ in range(3):
        try:
            r = _session.get(url, params=params, headers=hdrs, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last_err = e

    if params:
        from urllib.parse import urlencode

        query = urlencode(params)
        full_url = f"{url}?{query}" if "?" not in url else f"{url}&{query}"
    else:
        full_url = url

    for _ in range(2):
        try:
            req = urllib.request.Request(full_url)
            for k, v in hdrs.items():
                req.add_header(k, v)
            raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8")
            return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            last_err = e

    raise last_err or RuntimeError("request failed")


@dataclass
class IndexDailyBar:
    code: str
    name: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    prev_close: float | None = None
    change_pct: float | None = None
    change_amt: float | None = None
    volume: float | None = None
    amount: float | None = None


@dataclass
class IndexBar:
    code: str
    name: str
    close: float | None
    change_pct: float | None
    change_amt: float | None


@dataclass
class MarketStats:
    up_count: int | None
    down_count: int | None
    flat_count: int | None
    total_amount: float | None


def _to_float(v: Any) -> float | None:
    if v is None or v == "" or v == "-":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _norm_date(d: str) -> str:
    return str(d)[:10]


def _date_key(d: str) -> str:
    return _norm_date(d).replace("-", "")


def tencent_quote_symbols(symbols: list[str]) -> dict[str, dict]:
    """腾讯财经批量行情，symbols 为完整前缀符号如 sh000001。"""
    if not symbols:
        return {}

    url = "https://qt.gtimg.cn/q=" + ",".join(symbols)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    resp = urllib.request.urlopen(req, timeout=12)
    data = resp.read().decode("gbk")

    result: dict[str, dict] = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 33:
            continue
        code = key[2:] if len(key) > 2 else key
        result[code] = {
            "name": vals[1],
            "price": _to_float(vals[3]) or 0.0,
            "last_close": _to_float(vals[4]) or 0.0,
            "change_amt": _to_float(vals[31]) or 0.0,
            "change_pct": _to_float(vals[32]) or 0.0,
            "amount_yuan": (_to_float(vals[37]) or 0.0) * 10000.0,
        }
    return result


def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """腾讯财经批量行情（a-stock-data 1.2）。个股按 6 位代码推断市场前缀。"""
    prefixed: list[str] = []
    for c in codes:
        if c.startswith(("6", "9")):
            prefixed.append(f"sh{c}")
        elif c.startswith("8"):
            prefixed.append(f"bj{c}")
        else:
            prefixed.append(f"sz{c}")
    return tencent_quote_symbols(prefixed)


def recalc_index_change(
    close: float | None, prev_close: float | None
) -> tuple[float | None, float | None, float | None]:
    """按上一交易日收盘价重算涨跌额、涨跌幅。"""
    if close is None or prev_close is None or prev_close == 0:
        return None, None, prev_close
    change_amt = round(close - prev_close, 2)
    change_pct = round(change_amt / prev_close * 100, 2)
    return change_amt, change_pct, prev_close


def tencent_index_kline(tencent_symbol: str, trade_date: str) -> dict | None:
    """腾讯财经历史日 K（a-stock-data 备用），按昨收计算涨跌幅。"""
    dkey = _date_key(trade_date)
    start = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=30)).strftime(
        "%Y-%m-%d"
    )
    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={tencent_symbol},day,{start},{trade_date},60,qfq"
    )
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", "https://gu.qq.com/")
    try:
        raw = urllib.request.urlopen(req, timeout=12).read().decode("utf-8")
        data = json.loads(raw)
        rows = data.get("data", {}).get(tencent_symbol, {}).get("day") or []
        if not rows:
            rows = data.get("data", {}).get(tencent_symbol, {}).get("qfqday") or []
        target_idx = -1
        for i, row in enumerate(rows):
            if row and (row[0] == trade_date or row[0].replace("-", "") == dkey):
                target_idx = i
                break
        if target_idx < 0:
            return None
        row = rows[target_idx]
        open_ = _to_float(row[1])
        close = _to_float(row[2])
        high = _to_float(row[3])
        low = _to_float(row[4])
        volume = _to_float(row[5]) if len(row) > 5 else None
        if close is None:
            return None
        prev_close = _to_float(rows[target_idx - 1][2]) if target_idx > 0 else None
        change_amt, change_pct, prev_close = recalc_index_change(close, prev_close)
        if change_amt is None or change_pct is None:
            return None
        return {
            "date": trade_date,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "prev_close": prev_close,
            "volume": volume,
            "amount": None,
            "change_pct": change_pct,
            "change_amt": change_amt,
        }
    except Exception:
        return None


def eastmoney_index_kline(secid: str, trade_date: str) -> dict | None:
    """东财 push2his 指数日 K，返回指定交易日一根 K 线。"""
    dkey = _date_key(trade_date)
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
    }
    for base in (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        "http://push2his.eastmoney.com/api/qt/stock/kline/get",
    ):
        try:
            d = _get_json(base, params={**params, "beg": dkey, "end": dkey})
            klines = (d.get("data") or {}).get("klines") or []
            if klines:
                parts = klines[0].split(",")
                if len(parts) >= 10:
                    return {
                        "date": parts[0],
                        "open": _to_float(parts[1]),
                        "close": _to_float(parts[2]),
                        "high": _to_float(parts[3]),
                        "low": _to_float(parts[4]),
                        "volume": _to_float(parts[5]),
                        "amount": _to_float(parts[6]),
                        "change_pct": _to_float(parts[8]),
                        "change_amt": _to_float(parts[9]),
                    }
            d2 = _get_json(base, params={**params, "lmt": "10"})
            klines = (d2.get("data") or {}).get("klines") or []
            for line in reversed(klines):
                parts = line.split(",")
                if parts and parts[0] == trade_date and len(parts) >= 10:
                    return {
                        "date": parts[0],
                        "open": _to_float(parts[1]),
                        "close": _to_float(parts[2]),
                        "high": _to_float(parts[3]),
                        "low": _to_float(parts[4]),
                        "volume": _to_float(parts[5]),
                        "amount": _to_float(parts[6]),
                        "change_pct": _to_float(parts[8]),
                        "change_amt": _to_float(parts[9]),
                    }
        except Exception:
            continue
    return None


def eastmoney_index_snapshot(secid: str) -> dict | None:
    """东财 push2 指数快照（push2his 不可用时的实时备用）。"""
    try:
        d = _get_json(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={
                "secid": secid,
                "fields": "f43,f169,f170,f48",
            },
        )
    except Exception:
        return None
    data = d.get("data") or {}
    close = _to_float(data.get("f43"))
    if close is not None:
        close /= 100
    change_amt = _to_float(data.get("f169"))
    if change_amt is not None:
        change_amt /= 100
    change_pct = _to_float(data.get("f170"))
    if change_pct is not None:
        change_pct /= 100
    amount = _to_float(data.get("f48"))
    if close is None:
        return None
    return {
        "close": close,
        "change_pct": change_pct,
        "change_amt": change_amt,
        "amount": amount,
    }


def tencent_latest_trade_date() -> str | None:
    """腾讯 K 线上证指数最近一根日 K 的日期。"""
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,1,qfq"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", "https://gu.qq.com/")
    try:
        raw = urllib.request.urlopen(req, timeout=12).read().decode("utf-8")
        data = json.loads(raw)
        rows = data.get("data", {}).get("sh000001", {}).get("day") or []
        if not rows:
            rows = data.get("data", {}).get("sh000001", {}).get("qfqday") or []
        if rows:
            return rows[-1][0]
    except Exception:
        return None
    return None


def eastmoney_latest_trade_date() -> str | None:
    """以上证指数最近一根日 K 作为最新交易日。"""
    try:
        d = _get_json(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": "1.000001",
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": "101",
                "fqt": "1",
                "lmt": "1",
            },
        )
        klines = (d.get("data") or {}).get("klines") or []
        if klines:
            return klines[-1].split(",")[0]
    except Exception:
        pass
    return tencent_latest_trade_date()


def eastmoney_trading_dates(limit: int = 400) -> list[str]:
    """拉取上证指数最近若干交易日（用于非交易日对齐）。"""
    global _calendar_cache
    if _calendar_cache:
        return _calendar_cache
    try:
        d = _get_json(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": "1.000001",
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": "101",
                "fqt": "1",
                "lmt": str(limit),
            },
        )
        klines = (d.get("data") or {}).get("klines") or []
        if klines:
            _calendar_cache = [line.split(",")[0] for line in klines if line]
            return _calendar_cache
    except Exception:
        pass

    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,{limit},qfq"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", "https://gu.qq.com/")
    try:
        raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
        data = json.loads(raw)
        rows = data.get("data", {}).get("sh000001", {}).get("day") or []
        if not rows:
            rows = data.get("data", {}).get("sh000001", {}).get("qfqday") or []
        _calendar_cache = [row[0] for row in rows if row]
    except Exception:
        return []
    return _calendar_cache


def resolve_trade_date(requested: str, trading_dates: list[str]) -> tuple[str, bool]:
    req = _norm_date(requested)
    if not trading_dates:
        return req, False
    if req in trading_dates:
        return req, False
    prior = [d for d in trading_dates if d <= req]
    if prior:
        resolved = prior[-1]
        return resolved, resolved != req
    return trading_dates[0], True


def _bar_from_dict(spec: dict[str, str], bar: dict) -> IndexDailyBar:
    prev_close = bar.get("prev_close")
    if prev_close is None and bar.get("close") is not None and bar.get("change_amt") is not None:
        prev_close = bar["close"] - bar["change_amt"]
    return IndexDailyBar(
        code=spec["code"],
        name=spec["name"],
        open=_round(bar.get("open")),
        high=_round(bar.get("high")),
        low=_round(bar.get("low")),
        close=_round(bar.get("close")),
        prev_close=_round(prev_close),
        change_pct=_round(bar.get("change_pct")),
        change_amt=_round(bar.get("change_amt")),
        volume=bar.get("volume"),
        amount=bar.get("amount"),
    )


def _round(v: float | None, ndigits: int = 2) -> float | None:
    if v is None:
        return None
    return round(v, ndigits)


def _bar_from_tencent_quote(spec: dict[str, str], tq: dict) -> IndexDailyBar:
    return IndexDailyBar(
        code=spec["code"],
        name=spec["name"],
        open=_round(tq.get("open")),
        high=_round(tq.get("high")),
        low=_round(tq.get("low")),
        close=_round(tq.get("price")),
        prev_close=_round(tq.get("last_close")),
        change_pct=_round(tq.get("change_pct")),
        change_amt=_round(tq.get("change_amt")),
        volume=None,
        amount=tq.get("amount_yuan"),
    )


def fetch_index_daily_bars(trade_date: str) -> list[IndexDailyBar]:
    """获取指定交易日全部指数日 K（含 OHLCV）。"""
    latest = eastmoney_latest_trade_date()
    calendar = get_trading_calendar()
    # 仅盘中用实时行情覆盖；收盘后优先日 K（避免盘中快照被持久化为收盘价）
    use_live = (
        latest == trade_date
        and is_trading_session(calendar)
        and not is_after_market_close(trade_date)
    )
    tencent: dict[str, dict] = {}
    if use_live:
        try:
            raw = tencent_quote_symbols([s["tencent_symbol"] for s in INDEX_SPECS])
            for spec in INDEX_SPECS:
                tq = raw.get(spec["tencent"])
                if tq:
                    tencent[spec["tencent"]] = {
                        **tq,
                        "open": tq.get("open") or None,
                        "high": tq.get("high") or None,
                        "low": tq.get("low") or None,
                    }
            # 腾讯指数 quote 需单独解析 open/high/low
            url = "https://qt.gtimg.cn/q=" + ",".join(s["tencent_symbol"] for s in INDEX_SPECS)
            req = urllib.request.Request(url)
            req.add_header("User-Agent", UA)
            resp = urllib.request.urlopen(req, timeout=12)
            data = resp.read().decode("gbk")
            for line in data.strip().split(";"):
                if not line.strip() or "=" not in line or '"' not in line:
                    continue
                key = line.split("=")[0].split("_")[-1]
                vals = line.split('"')[1].split("~")
                if len(vals) < 35:
                    continue
                code = key[2:] if len(key) > 2 else key
                if code in tencent:
                    tencent[code]["open"] = _to_float(vals[5])
                    tencent[code]["high"] = _to_float(vals[33])
                    tencent[code]["low"] = _to_float(vals[34])
        except Exception:
            tencent = {}

    bars: list[IndexDailyBar] = []
    for spec in INDEX_SPECS:
        bar: dict | None = None
        try:
            bar = eastmoney_index_kline(spec["secid"], trade_date)
        except Exception:
            bar = None

        tq = tencent.get(spec["tencent"])
        snap: dict | None = None
        if use_live and bar is None:
            try:
                snap = eastmoney_index_snapshot(spec["secid"])
            except Exception:
                snap = None

        if bar is None and tq:
            bars.append(_bar_from_tencent_quote(spec, tq))
            continue

        if bar is None and snap:
            bars.append(
                IndexDailyBar(
                    code=spec["code"],
                    name=spec["name"],
                    close=_round(snap.get("close")),
                    change_pct=_round(snap.get("change_pct")),
                    change_amt=_round(snap.get("change_amt")),
                    amount=snap.get("amount"),
                )
            )
            continue

        if bar is None:
            tbar = tencent_index_kline(spec["tencent_symbol"], trade_date)
            if tbar:
                bars.append(_bar_from_dict(spec, tbar))
                continue
            bars.append(IndexDailyBar(spec["code"], spec["name"]))
            continue

        if use_live and tq:
            merged = {
                **bar,
                "close": tq["price"],
                "change_pct": tq["change_pct"],
                "change_amt": tq["change_amt"],
                "open": tq.get("open") or bar.get("open"),
                "high": tq.get("high") or bar.get("high"),
                "low": tq.get("low") or bar.get("low"),
                "prev_close": tq.get("last_close"),
                "amount": tq.get("amount_yuan") or bar.get("amount"),
            }
            bars.append(_bar_from_dict(spec, merged))
            continue

        if use_live and snap:
            merged = {
                **bar,
                "close": snap.get("close"),
                "change_pct": snap.get("change_pct"),
                "change_amt": snap.get("change_amt"),
                "amount": snap.get("amount") or bar.get("amount"),
            }
            bars.append(_bar_from_dict(spec, merged))
            continue

        bars.append(_bar_from_dict(spec, bar))

    return bars


def fetch_index_bars(trade_date: str) -> list[IndexBar]:
    """兼容旧接口：仅返回 close / 涨跌幅。"""
    return [
        IndexBar(b.code, b.name, b.close, b.change_pct, b.change_amt)
        for b in fetch_index_daily_bars(trade_date)
    ]


def align_index_changes_from_calendar(trade_date: str, indices: list[dict]) -> None:
    """按交易日历上一日官方收盘价重算涨跌幅（不依赖库内快照）。"""
    calendar = get_trading_calendar()
    prior = [d for d in calendar if d < trade_date]
    if not prior:
        return
    prev_date = prior[-1]
    for idx in indices:
        close = idx.get("close")
        if close is None:
            continue
        spec = next((s for s in INDEX_SPECS if s["code"] == idx.get("code")), None)
        if spec is None:
            continue
        prev_bar = eastmoney_index_kline(spec["secid"], prev_date)
        if prev_bar is None:
            prev_bar = tencent_index_kline(spec["tencent_symbol"], prev_date)
        if not prev_bar or prev_bar.get("close") is None:
            continue
        change_amt, change_pct, prev_close = recalc_index_change(
            close, float(prev_bar["close"])
        )
        idx["prev_close"] = prev_close
        idx["change_amt"] = change_amt
        idx["change_pct"] = change_pct


def _amount_from_indices(indices: list[dict]) -> float | None:
    """上证+深证成指指数日 K 成交额之和（元）。"""
    codes = {"SH000001", "SZ399001"}
    total = 0.0
    ok = False
    for idx in indices:
        if idx.get("code") not in codes:
            continue
        amt = idx.get("amount")
        if amt is None:
            continue
        total += float(amt)
        ok = True
    return total if ok else None


def fetch_market_day(trade_date: str, *, cache_dir: Path | None = None) -> dict:
    """从 HTTP 拉取完整交易日数据（供数据库持久化）。"""
    indices = [
        {
            "code": b.code,
            "name": b.name,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "prev_close": b.prev_close,
            "change_pct": b.change_pct,
            "change_amt": b.change_amt,
            "volume": b.volume,
            "amount": b.amount,
        }
        for b in fetch_index_daily_bars(trade_date)
    ]
    align_index_changes_from_calendar(trade_date, indices)
    stats = fetch_market_stats(trade_date, cache_dir=cache_dir)
    total_amount = stats.total_amount
    if total_amount is None:
        total_amount = _amount_from_indices(indices)
    return {
        "trade_date": trade_date,
        "indices": indices,
        "up_count": stats.up_count,
        "down_count": stats.down_count,
        "flat_count": stats.flat_count,
        "total_amount": total_amount,
        "data_source": "a-stock-data-http",
    }


def sina_index_amount_sum() -> float | None:
    """新浪指数概况：上证+深证成交额之和（元）。"""
    url = "https://hq.sinajs.cn/list=s_sh000001,s_sz399001"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", "https://finance.sina.com.cn")
    try:
        raw = urllib.request.urlopen(req, timeout=12).read().decode("gbk")
    except Exception:
        return None
    total = 0.0
    ok = False
    for line in raw.strip().split(";"):
        if '"' not in line:
            continue
        parts = line.split('"')[1].split(",")
        if len(parts) >= 6:
            amt = _to_float(parts[5])
            if amt is not None:
                total += amt * 10000.0
                ok = True
    return total if ok else None


def _sina_market_page(page: int, page_size: int = 100) -> list[dict]:
    url = (
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"Market_Center.getHQNodeData?page={page}&num={page_size}&sort=symbol&asc=1&node=hs_a"
    )
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", "https://finance.sina.com.cn")
    try:
        raw = urllib.request.urlopen(req, timeout=12).read().decode()
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def sina_market_breadth() -> MarketStats:
    """新浪 A 股并发分页统计涨跌家数（东财 push2 不可用时的备用）。"""
    up = down = flat = 0
    got_any = False
    max_pages = 60
    workers = 4

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_sina_market_page, p): p for p in range(1, max_pages + 1)}
        for fut in as_completed(futures):
            items = fut.result()
            if not items:
                continue
            got_any = True
            for it in items:
                chg = _to_float(it.get("changepercent"))
                if chg is None:
                    continue
                if chg > 0:
                    up += 1
                elif chg < 0:
                    down += 1
                else:
                    flat += 1

    if not got_any:
        return MarketStats(None, None, None, None)
    return MarketStats(up, down, flat, None)


def eastmoney_market_breadth() -> MarketStats:
    """东财 push2 大盘板块：汇总上证+深证指数的涨跌家数。"""
    d = _get_json(
        "https://push2.eastmoney.com/api/qt/clist/get",
        params={
            "pn": "1",
            "pz": "50",
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fs": BREADTH_FS,
            "fields": "f12,f14,f104,f105,f106",
        },
    )
    items = (d.get("data") or {}).get("diff") or []
    up = down = flat = 0
    found = False
    for it in items:
        code = str(it.get("f12", ""))
        if code not in BREADTH_CODES:
            continue
        found = True
        up += int(_to_float(it.get("f104")) or 0)
        down += int(_to_float(it.get("f105")) or 0)
        flat += int(_to_float(it.get("f106")) or 0)
    if not found:
        return MarketStats(None, None, None, None)
    return MarketStats(up, down, flat, None)


def eastmoney_total_amount() -> float | None:
    """东财 push2 全 A 股分页汇总成交额（元）。"""
    total = 0.0
    page = 1
    page_size = 500
    while True:
        d = _get_json(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": str(page),
                "pz": str(page_size),
                "po": "1",
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fs": ASHARE_FS,
                "fields": "f6",
            },
            timeout=15,
        )
        data = d.get("data") or {}
        items = data.get("diff") or []
        if not items:
            break
        for it in items:
            amt = _to_float(it.get("f6"))
            if amt is not None:
                total += amt
        total_count = int(data.get("total") or 0)
        if page * page_size >= total_count:
            break
        page += 1
    return total if total > 0 else None


def eastmoney_index_amount_sum() -> float | None:
    """最新交易日成交额：上证+深证成指 push2 快照 f48 之和（元）。"""
    total = 0.0
    ok = False
    for secid in ("1.000001", "0.399001"):
        snap = eastmoney_index_snapshot(secid)
        if snap and snap.get("amount"):
            total += float(snap["amount"])
            ok = True
    return total if ok else None


def eastmoney_historical_amount(trade_date: str) -> float | None:
    """历史成交额：上证+深证成指指数 K 线 amount 之和（东财 push2his）。"""
    total = 0.0
    ok = False
    for secid in ("1.000001", "0.399001"):
        try:
            bar = eastmoney_index_kline(secid, trade_date)
        except Exception:
            bar = None
        if bar and bar.get("amount"):
            total += float(bar["amount"])
            ok = True
    return total if ok else None


def fetch_market_stats(trade_date: str, *, cache_dir: Path | None = None) -> MarketStats:
    """获取涨跌家数与成交额。"""
    latest = eastmoney_latest_trade_date()
    calendar = get_trading_calendar()
    use_live = (
        latest
        and trade_date == latest
        and is_trading_session(calendar)
        and not is_after_market_close(trade_date)
    )
    if use_live:
        breadth = MarketStats(None, None, None, None)
        amount: float | None = None

        try:
            breadth = eastmoney_market_breadth()
        except Exception:
            pass
        if breadth.up_count is None:
            try:
                breadth = sina_market_breadth()
            except Exception:
                pass

        try:
            amount = eastmoney_index_amount_sum()
        except Exception:
            pass
        if amount is None:
            amount = sina_index_amount_sum()

        if any(v is not None for v in (breadth.up_count, amount)):
            return MarketStats(
                breadth.up_count,
                breadth.down_count,
                breadth.flat_count,
                amount,
            )

    # 最新交易日收盘后：涨跌家数仍走 push2 汇总，成交额优先日 K
    if latest and trade_date == latest and is_after_market_close(trade_date):
        breadth = MarketStats(None, None, None, None)
        amount: float | None = None

        try:
            breadth = eastmoney_market_breadth()
        except Exception:
            pass
        if breadth.up_count is None:
            try:
                breadth = sina_market_breadth()
            except Exception:
                pass

        amount = eastmoney_historical_amount(trade_date)
        if amount is None:
            try:
                amount = eastmoney_index_amount_sum()
            except Exception:
                pass
        if amount is None:
            amount = sina_index_amount_sum()

        if any(v is not None for v in (breadth.up_count, amount)):
            return MarketStats(
                breadth.up_count,
                breadth.down_count,
                breadth.flat_count,
                amount,
            )

    amount = eastmoney_historical_amount(trade_date)
    if cache_dir is not None:
        from .market_overview import lookup_cached_market_stats

        cached = lookup_cached_market_stats(cache_dir, trade_date)
        if cached:
            return MarketStats(
                cached.get("up_count"),
                cached.get("down_count"),
                cached.get("flat_count"),
                amount if amount is not None else cached.get("total_amount"),
            )
    return MarketStats(None, None, None, amount)


def _disk_cache_path(cache_dir: Path, trade_date: str) -> Path:
    d = cache_dir / "market_http"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_date_key(trade_date)}.json"


def _load_disk_cache(cache_dir: Path, trade_date: str) -> dict | None:
    path = _disk_cache_path(cache_dir, trade_date)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_disk_cache(cache_dir: Path, trade_date: str, payload: dict) -> None:
    path = _disk_cache_path(cache_dir, trade_date)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@lru_cache(maxsize=128)
def _fetch_overview_cached(trade_date: str, cache_dir_str: str) -> dict:
    cache_dir = Path(cache_dir_str)
    latest = eastmoney_latest_trade_date()
    calendar = get_trading_calendar()
    use_disk = not (
        latest == trade_date
        and is_trading_session(calendar)
        and not is_after_market_close(trade_date)
    )
    if use_disk:
        disk = _load_disk_cache(cache_dir, trade_date)
        if disk and any(i.get("close") is not None for i in disk.get("indices", [])):
            return disk

    payload = fetch_market_day(trade_date)
    has_data = any(i.get("close") is not None for i in payload.get("indices", [])) or payload.get(
        "total_amount"
    )
    if has_data and use_disk:
        _save_disk_cache(cache_dir, trade_date, payload)
    return payload


def get_market_day_overview(trade_date: str, cache_dir: Path) -> dict:
    with _cache_lock:
        return _fetch_overview_cached(trade_date, str(cache_dir))


def get_trading_calendar(limit: int = 400) -> list[str]:
    return eastmoney_trading_dates(limit)
