"""通达信 .day 二进制文件解析。

每个 .day 文件由一连串 32 字节记录组成：
  date(uint32) open high low close (price *100)  amount(float32)  volume(uint32)  pad(uint32)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


_DAY_RECORD_DTYPE = np.dtype([
    ("date", "<u4"),
    ("open", "<u4"),
    ("high", "<u4"),
    ("low", "<u4"),
    ("close", "<u4"),
    ("amount", "<f4"),
    ("volume", "<u4"),
    ("_pad", "<u4"),
])

_EXCLUDE_PREFIX = (
    # 上证债券 / ETF / 基金等
    "11", "12", "13", "50", "51", "56", "58",
    # 深证 ETF / 指数等
    "15", "16", "18", "39",
)


def parse_day_file(path: Path, *, min_records: int = 120) -> pd.DataFrame | None:
    """解析单个 .day 文件为 DataFrame；少于 min_records 条记录返回 None。"""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    n = len(raw) // 32
    if n < min_records:
        return None

    arr = np.frombuffer(raw[: n * 32], dtype=_DAY_RECORD_DTYPE)
    df = pd.DataFrame({
        "date": arr["date"].astype(str),
        "open": arr["open"] / 100.0,
        "high": arr["high"] / 100.0,
        "low": arr["low"] / 100.0,
        "close": arr["close"] / 100.0,
        "volume": arr["volume"].astype(np.float64),
        "amount": arr["amount"].astype(np.float64),
    })
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if df.empty:
        return None
    return df


def is_a_share_code(stem: str) -> bool:
    """是否为受支持的 A 股股票文件名（含 sh/sz 前缀的小写 stem）。

    排除指数、ETF、债券、北交所等。
    """
    code = stem.lower()
    if len(code) < 8:
        return False
    market, num = code[:2], code[2:]
    if not num.isdigit():
        return False
    if num.startswith(_EXCLUDE_PREFIX) or num.startswith("880"):
        return False
    if market == "sh":
        return num.startswith(("600", "601", "603", "605", "688", "689"))
    if market == "sz":
        return num.startswith(("000", "001", "002", "003", "300", "301"))
    return False


def market_of(code: str) -> str:
    """返回所属板块：科创板 / 创业板 / 沪主板 / 深主板。"""
    c = code.upper()
    num = c[2:]
    if num.startswith(("688", "689")):
        return "科创板"
    if num.startswith(("300", "301")):
        return "创业板"
    if c.startswith("SH"):
        return "沪主板"
    return "深主板"


def raw_last_date(path: Path, *, min_records: int = 120) -> str | None:
    """只读 .day 文件最后一条记录的交易日（YYYYMMDD 字符串），用于增量判断。"""
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size < 32 * min_records:
        return None
    try:
        with path.open("rb") as f:
            f.seek(size - 32)
            rec = np.frombuffer(f.read(32), dtype=_DAY_RECORD_DTYPE)
        d = int(rec["date"][0])
        if d <= 0:
            return None
        return str(d)
    except OSError:
        return None


def iter_day_files(raw_dir: Path) -> list[Path]:
    """枚举原始数据目录下的所有 .day 文件（sh/lday + sz/lday）。"""
    files: list[Path] = []
    for sub in ("sh/lday", "sz/lday"):
        d = raw_dir / sub
        if d.is_dir():
            files.extend(d.glob("*.day"))
    return sorted(files)
