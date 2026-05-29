"""Parquet 数据缓存。

按 `<market>/<code>.parquet` 单股票一文件保存（含完整指标列）。
- 比 pickle 紧凑约 40%，跨语言可读
- 单股票文件支持按需懒加载（不必一次性把 2GB 全部载入内存）
- 简单的 manifest 记录最后更新时间，支持增量更新

文件布局：
  <cache_dir>/
    sh/sh600000.parquet
    sz/sz000001.parquet
    manifest.json
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from .indicators import add_indicators
from .tdx_parser import is_a_share_code, iter_day_files, parse_day_file, raw_last_date


MANIFEST_NAME = "manifest.json"
META_SUFFIX = ".meta.json"
PARQUET_VERSION = 2


def _norm_date(d: str) -> str:
    return str(d)[:10].replace("-", "")


@dataclass
class BuildResult:
    """单次构建统计。"""
    total_files: int
    row_count: int
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    incremental: bool = False


@dataclass
class CacheStats:
    total_files: int
    total_rows: int
    total_size_mb: float
    last_updated: str


class DataCache:
    """按代码懒加载的 Parquet 缓存。"""

    def __init__(self, raw_dir: Path, cache_dir: Path):
        self.raw_dir = Path(raw_dir)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, pd.DataFrame] = {}

    # ------------------- 路径辅助 -------------------

    def _parquet_path(self, code: str) -> Path:
        c = code.upper()
        market_dir = "sh" if c.startswith("SH") else "sz"
        return self.cache_dir / market_dir / f"{c}.parquet"

    @property
    def manifest_path(self) -> Path:
        return self.cache_dir / MANIFEST_NAME

    def _meta_path(self, code: str) -> Path:
        return self._parquet_path(code).with_suffix(META_SUFFIX)

    def _read_meta(self, code: str) -> dict | None:
        path = self._meta_path(code)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _write_meta(self, code: str, *, raw_path: Path, df: pd.DataFrame) -> None:
        last = pd.Timestamp(df["date"].iloc[-1]).strftime("%Y-%m-%d")
        data = {
            "last_date": last,
            "raw_mtime": raw_path.stat().st_mtime,
            "rows": len(df),
        }
        self._meta_path(code).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    def _needs_rebuild(self, code: str, raw_path: Path, *, incremental: bool) -> bool:
        if not incremental:
            return True
        pq = self._parquet_path(code)
        if not pq.exists():
            return True
        meta = self._read_meta(code)
        if meta is None and pq.exists():
            if self._bootstrap_meta(code, raw_path):
                meta = self._read_meta(code)
        if meta is None:
            return True
        tail = raw_last_date(raw_path)
        if tail is None:
            return True
        cached_last = _norm_date(str(meta.get("last_date", "")))
        if tail != cached_last:
            return True
        try:
            if float(meta.get("raw_mtime", 0)) != raw_path.stat().st_mtime:
                # 文件时间变了但末日未变：通常无需重算；若修正历史数据请全量重建
                return False
        except OSError:
            return True
        return False

    def _bootstrap_meta(self, code: str, raw_path: Path) -> bool:
        """旧缓存无 .meta.json 时，若末日与 raw 一致则补写 meta 并跳过重建。"""
        tail = raw_last_date(raw_path)
        if tail is None:
            return False
        pq = self._parquet_path(code)
        try:
            dates = pd.read_parquet(pq, columns=["date"], engine="pyarrow")
        except Exception:
            return False
        if dates.empty:
            return False
        cached = _norm_date(pd.Timestamp(dates["date"].iloc[-1]).strftime("%Y-%m-%d"))
        if cached != tail:
            return False
        self._meta_path(code).write_text(
            json.dumps({
                "last_date": pd.Timestamp(dates["date"].iloc[-1]).strftime("%Y-%m-%d"),
                "raw_mtime": raw_path.stat().st_mtime,
                "rows": len(dates),
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        return True

    # ------------------- 写入 / 构建 -------------------

    def build(
        self,
        codes: Iterable[str] | None = None,
        *,
        incremental: bool = True,
        progress_cb=None,
    ) -> BuildResult:
        """构建 Parquet 缓存。

        incremental=True（默认）：仅处理「无缓存 / 末日有更新」的股票，日常增量很快。
        incremental=False：全量重建所有股票。
        """
        files = iter_day_files(self.raw_dir)
        files = [p for p in files if is_a_share_code(p.stem)]
        if codes is not None:
            wanted = {c.upper() for c in codes}
            files = [p for p in files if p.stem.upper() in wanted]

        total = len(files)
        updated = skipped = failed = 0
        rows_added = 0

        for i, path in enumerate(files, 1):
            code = path.stem.upper()
            if not self._needs_rebuild(code, path, incremental=incremental):
                skipped += 1
                if progress_cb:
                    progress_cb(i, total)
                continue

            df = parse_day_file(path)
            if df is None:
                failed += 1
                if progress_cb:
                    progress_cb(i, total)
                continue

            df = add_indicators(df)
            self.save(code, df)
            self._write_meta(code, raw_path=path, df=df)
            updated += 1
            rows_added += len(df)
            if progress_cb and (i % 50 == 0 or i == total):
                progress_cb(i, total)

        file_count = len(list(self.cache_dir.rglob("*.parquet")))
        row_count = self._count_total_rows()
        self._write_manifest(file_count=file_count, row_count=row_count, incremental=incremental)
        return BuildResult(
            total_files=file_count,
            row_count=row_count,
            updated=updated,
            skipped=skipped,
            failed=failed,
            incremental=incremental,
        )

    def _count_total_rows(self) -> int:
        total = 0
        for market in ("sh", "sz"):
            mdir = self.cache_dir / market
            if not mdir.is_dir():
                continue
            for meta_path in mdir.glob(f"*{META_SUFFIX}"):
                try:
                    m = json.loads(meta_path.read_text(encoding="utf-8"))
                    total += int(m.get("rows", 0))
                except Exception:
                    pass
        if total > 0:
            return total
        if self.manifest_path.exists():
            try:
                return int(json.loads(self.manifest_path.read_text(encoding="utf-8")).get("row_count", 0))
            except Exception:
                pass
        return 0

    def save(self, code: str, df: pd.DataFrame) -> None:
        path = self._parquet_path(code)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, engine="pyarrow", index=False, compression="zstd")
        self._memory[code.upper()] = df

    def _write_manifest(
        self, *, file_count: int, row_count: int, incremental: bool = False
    ) -> None:
        data = {
            "version": PARQUET_VERSION,
            "file_count": file_count,
            "row_count": row_count,
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_incremental": incremental,
        }
        self.manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------- 读取 -------------------

    def load(self, code: str) -> pd.DataFrame | None:
        """加载单只股票的指标 DataFrame（带内存缓存）。

        注意：返回的对象会被全程持有；对短交互（K 线/诊断）合适，
        对批量回测请使用 load_no_cache 避免内存爆炸。
        """
        c = code.upper()
        if c in self._memory:
            return self._memory[c]
        df = self.load_no_cache(c)
        if df is not None:
            self._memory[c] = df
        return df

    def load_no_cache(self, code: str) -> pd.DataFrame | None:
        """直接读 Parquet，不缓存到内存。批量回测 / 一次性扫描时使用。"""
        path = self._parquet_path(code.upper())
        if not path.exists():
            return None
        return pd.read_parquet(path, engine="pyarrow")

    def load_many(self, codes: Iterable[str]) -> dict[str, pd.DataFrame]:
        out = {}
        for c in codes:
            df = self.load(c)
            if df is not None:
                out[c.upper()] = df
        return out

    def codes(self) -> list[str]:
        """返回所有已缓存的股票代码（按字母排序）。"""
        result: list[str] = []
        for market in ("sh", "sz"):
            mdir = self.cache_dir / market
            if not mdir.is_dir():
                continue
            for p in mdir.glob("*.parquet"):
                result.append(p.stem.upper())
        return sorted(result)

    # ------------------- 状态 -------------------

    def stats(self) -> CacheStats:
        files = list(self.cache_dir.rglob("*.parquet"))
        total_size = sum(p.stat().st_size for p in files)
        total_rows = 0
        if self.manifest_path.exists():
            try:
                meta = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                total_rows = int(meta.get("row_count", 0))
                last = meta.get("last_updated", "")
            except Exception:
                last = ""
        else:
            last = ""
        return CacheStats(
            total_files=len(files),
            total_rows=total_rows,
            total_size_mb=round(total_size / 1024 / 1024, 1),
            last_updated=last,
        )

    def exists(self, code: str) -> bool:
        return self._parquet_path(code).exists()

    def clear_memory(self) -> None:
        self._memory.clear()
