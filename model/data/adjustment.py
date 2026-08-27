"""通达信 GBBQ 除权事件缓存与前复权计算。"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pytdx.reader.gbbq_reader import GbbqReader

GBBQ_CACHE_DIR = Path("derived") / "gbbq"
EVENTS_NAME = "corporate_actions.parquet"
META_NAME = "corporate_actions.meta.json"
PRICE_COLUMNS = ("open", "high", "low", "close")


def adjustment_paths(cache_dir: Path) -> tuple[Path, Path]:
    directory = Path(cache_dir) / GBBQ_CACHE_DIR
    return directory / EVENTS_NAME, directory / META_NAME


def _stock_code(market: int, code: str) -> str:
    value = str(code).zfill(6)
    # GBBQ: market=1 上海，market=0 深圳。
    return ("SH" if int(market) == 1 else "SZ") + value


def _version_for_group(group: pd.DataFrame) -> str:
    canonical = group[
        ["ex_date", "cash_dividend", "rights_price", "bonus_ratio", "rights_ratio"]
    ].to_csv(index=False, header=False, float_format="%.8g")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def parse_gbbq_to_cache(
    gbbq_path: Path,
    cache_dir: Path,
    *,
    source_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """解码 GBBQ，只保存 category=1 的除权除息事件。"""
    raw = GbbqReader().get_df(str(gbbq_path))
    if raw is None or raw.empty:
        raise ValueError("GBBQ 解码结果为空")
    events = raw.loc[raw["category"] == 1].copy()
    events["code"] = [
        _stock_code(market, code)
        for market, code in events[["market", "code"]].itertuples(index=False, name=None)
    ]
    events["ex_date"] = pd.to_datetime(
        events["datetime"].astype(str), format="%Y%m%d", errors="coerce"
    )
    events = events.rename(columns={
        "hongli_panqianliutong": "cash_dividend",
        "peigujia_qianzongguben": "rights_price",
        "songgu_qianzongguben": "bonus_ratio",
        "peigu_houzongguben": "rights_ratio",
    })
    value_columns = ["cash_dividend", "rights_price", "bonus_ratio", "rights_ratio"]
    for column in value_columns:
        events[column] = pd.to_numeric(events[column], errors="coerce").fillna(0.0)
        events.loc[~np.isfinite(events[column]), column] = 0.0
    events = events[["code", "ex_date", *value_columns]].dropna(subset=["ex_date"])
    events = events.drop_duplicates(["code", "ex_date"], keep="last")
    events = events.sort_values(["code", "ex_date"]).reset_index(drop=True)

    versions = {
        str(code): _version_for_group(group)
        for code, group in events.groupby("code", sort=False)
    }
    events_path, meta_path = adjustment_paths(cache_dir)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    temp_events = events_path.with_suffix(".parquet.tmp")
    events.to_parquet(temp_events, engine="pyarrow", index=False, compression="zstd")
    temp_events.replace(events_path)

    meta = {
        "source": "tdx_gbbq",
        "source_meta": source_meta or {},
        "parsed_at": datetime.now(UTC).isoformat(),
        "event_count": int(len(events)),
        "stock_count": int(len(versions)),
        "code_versions": versions,
    }
    temp_meta = meta_path.with_suffix(".json.tmp")
    temp_meta.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    temp_meta.replace(meta_path)
    return meta


class AdjustmentStore:
    """按需读取本地 GBBQ 事件，并给原始日线追加前复权列。"""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self._meta_mtime_ns = -1
        self._versions: dict[str, str] = {}
        self._events: dict[str, pd.DataFrame] = {}

    def _reload_if_needed(self) -> None:
        events_path, meta_path = adjustment_paths(self.cache_dir)
        try:
            mtime_ns = meta_path.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0
        if mtime_ns == self._meta_mtime_ns:
            return
        self._meta_mtime_ns = mtime_ns
        self._versions = {}
        self._events = {}
        if not meta_path.exists() or not events_path.exists():
            return
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self._versions = {
                str(code).upper(): str(version)
                for code, version in (meta.get("code_versions") or {}).items()
            }
            frame = pd.read_parquet(events_path, engine="pyarrow")
            frame["ex_date"] = pd.to_datetime(frame["ex_date"], errors="coerce")
            for code, group in frame.dropna(subset=["ex_date"]).groupby("code", sort=False):
                self._events[str(code).upper()] = group.sort_values("ex_date").reset_index(drop=True)
        except Exception:
            self._versions = {}
            self._events = {}

    def version_for(self, code: str) -> str:
        self._reload_if_needed()
        return self._versions.get(code.upper(), "none")

    def apply_qfq(self, code: str, frame: pd.DataFrame) -> pd.DataFrame:
        """追加 qfq_* 价格和仿射系数；成交量、成交额保持原值。"""
        self._reload_if_needed()
        result = frame.copy()
        if result.empty:
            return result
        dates = pd.to_datetime(result["date"], errors="coerce")
        events = self._events.get(code.upper())
        if events is not None and not events.empty:
            # 尚未生效的未来事件不能影响当前历史价格。
            events = events.loc[events["ex_date"] <= dates.max()].sort_values(
                "ex_date", ascending=False
            )

        multipliers = np.ones(len(result), dtype=np.float64)
        offsets = np.zeros(len(result), dtype=np.float64)
        if events is not None and not events.empty:
            event_rows = list(events.itertuples(index=False))
            event_index = 0
            multiplier = 1.0
            offset = 0.0
            for row_index in range(len(result) - 1, -1, -1):
                row_date = dates.iloc[row_index]
                while event_index < len(event_rows) and event_rows[event_index].ex_date > row_date:
                    event = event_rows[event_index]
                    m = (10.0 + float(event.bonus_ratio) + float(event.rights_ratio)) / 10.0
                    c = (
                        float(event.cash_dividend)
                        - float(event.rights_ratio) * float(event.rights_price)
                    ) / 10.0
                    if m != 0:
                        multiplier = multiplier / m
                        offset = offset - multiplier * c
                    event_index += 1
                multipliers[row_index] = multiplier
                offsets[row_index] = offset

        result["qfq_mul"] = multipliers
        result["qfq_add"] = offsets
        for column in PRICE_COLUMNS:
            raw_values = pd.to_numeric(result[column], errors="coerce").to_numpy(dtype=np.float64)
            adjusted = raw_values * multipliers + offsets
            # A 股价格均为正数；向量化实现通达信的四舍五入到分。
            result[f"qfq_{column}"] = np.floor(adjusted * 100.0 + 0.5) / 100.0
        return result
