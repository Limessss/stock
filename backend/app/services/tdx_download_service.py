"""通达信官方日线包下载与本地缓存衔接。

只在用户显式触发时访问通达信：先请求一次轻量更新信息，远端版本变化时
下载 ``hsjday.zip``，安全解压到现有 raw 目录，最后启动 Parquet 增量构建。
状态查询只读内存和本地 manifest，不访问网络。
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from model.data.adjustment import adjustment_paths, parse_gbbq_to_cache
from model.data.tdx_parser import raw_last_date

from ..core.config import settings
from .cache_service import get_build_status, start_build

TDX_INFO_URL = "https://data.tdx.com.cn/vipdoc/_hsjdayinfo.js"
TDX_ZIP_URL = "https://data.tdx.com.cn/vipdoc/hsjday.zip"
GBBQ_ZIP_URL = "http://www.tdx.com.cn/products/data/data/dbf/gbbq.zip"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

DOWNLOAD_DIR = settings.data_dir / "downloads" / "tdx"
ZIP_PATH = DOWNLOAD_DIR / "hsjday.zip"
GBBQ_ZIP_PATH = DOWNLOAD_DIR / "gbbq.zip"
GBBQ_RAW_PATH = DOWNLOAD_DIR / "gbbq"
MANIFEST_PATH = DOWNLOAD_DIR / "manifest.json"


@dataclass
class TdxDownloadStatus:
    running: bool = False
    stage: str = "idle"
    done: int = 0
    total: int = 0
    unit: str = "files"
    started_at: float = 0.0
    finished_at: float = 0.0
    error: str | None = None
    remote_time: str = ""
    remote_size: str = ""
    downloaded: bool = False
    extracted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    gbbq_downloaded: bool = False
    gbbq_events: int = 0
    gbbq_updated_at: str = ""

    @property
    def elapsed_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.finished_at or time.time()
        return round(end - self.started_at, 2)

    @property
    def progress_pct(self) -> float:
        if not self.total:
            return 0.0
        return round(min(100.0, self.done / self.total * 100), 2)


_status = TdxDownloadStatus()
_lock = threading.Lock()


def _ensure_dirs() -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for market in ("sh", "sz"):
        (settings.raw_dir / market / "lday").mkdir(parents=True, exist_ok=True)  # type: ignore[operator]


def _read_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_manifest(data: dict[str, Any]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = MANIFEST_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(MANIFEST_PATH)


def _match_js_value(text: str, name: str) -> str:
    match = re.search(rf'{name}\s*=\s*"([^"]*)"', text)
    return match.group(1) if match else ""


def fetch_remote_info() -> dict[str, str]:
    """读取轻量更新信息；每次显式同步最多调用一次。"""
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.tdx.com.cn/article/vipdata.html"}
    with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
        response = client.get(TDX_INFO_URL)
        response.raise_for_status()
    text = response.text
    return {
        "url": TDX_ZIP_URL,
        "size": _match_js_value(text, "HSJDAY_SOFT_SIZE"),
        "update_time": _match_js_value(text, "HSJDAY_SOFT_TIME"),
    }


def _last_raw_date() -> str:
    index_path = settings.raw_dir / "sh" / "lday" / "sh000001.day"  # type: ignore[operator]
    return raw_last_date(index_path) or ""


def status_payload() -> dict[str, Any]:
    manifest = _read_manifest()
    _, gbbq_meta_path = adjustment_paths(settings.cache_dir)  # type: ignore[arg-type]
    try:
        gbbq_meta = json.loads(gbbq_meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        gbbq_meta = {}
    payload = asdict(_status)
    payload.update(
        {
            "progress_pct": _status.progress_pct,
            "elapsed_seconds": _status.elapsed_seconds,
            "remote_time": _status.remote_time or str(manifest.get("remote_time", "")),
            "remote_size": _status.remote_size or str(manifest.get("remote_size", "")),
            "last_raw_date": _last_raw_date(),
            "raw_dir": str(settings.raw_dir),
            "download_path": str(ZIP_PATH),
            "source_url": TDX_ZIP_URL,
            "gbbq_events": _status.gbbq_events or int(gbbq_meta.get("event_count", 0)),
            "gbbq_updated_at": _status.gbbq_updated_at
            or str(gbbq_meta.get("parsed_at", "")),
            "gbbq_source_url": GBBQ_ZIP_URL,
            "gbbq_download_path": str(GBBQ_ZIP_PATH),
        }
    )
    return payload


def start_sync(*, force_download: bool = False) -> bool:
    """启动一次后台同步；下载任务和 Parquet 构建互斥。"""
    if not _lock.acquire(blocking=False):
        return False
    try:
        if _status.running or get_build_status().running:
            return False
        _reset_status()
        thread = threading.Thread(
            target=_run_sync,
            args=(force_download,),
            daemon=True,
            name="tdx-official-sync",
        )
        thread.start()
        return True
    finally:
        _lock.release()


def _reset_status() -> None:
    global _status
    _status = TdxDownloadStatus(running=True, stage="checking", started_at=time.time())


def _run_sync(force_download: bool) -> None:
    try:
        _ensure_dirs()
        remote = fetch_remote_info()
        _status.remote_time = remote["update_time"]
        _status.remote_size = remote["size"]
        manifest = _read_manifest()
        same_remote = bool(
            ZIP_PATH.exists()
            and zipfile.is_zipfile(ZIP_PATH)
            and remote["update_time"]
            and remote["update_time"] == str(manifest.get("remote_time", ""))
        )

        if force_download or not same_remote:
            _download_zip()
            _status.downloaded = True
            _extract_zip(ZIP_PATH)
        else:
            _status.stage = "using-local-data"

        gbbq_info = _sync_gbbq(force_download=force_download)
        _write_manifest(
            {
                "source": "tdx-official",
                "zip_url": TDX_ZIP_URL,
                "remote_time": remote["update_time"],
                "remote_size": remote["size"],
                "zip_size_bytes": ZIP_PATH.stat().st_size if ZIP_PATH.exists() else 0,
                "last_raw_date": _last_raw_date(),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "gbbq_url": GBBQ_ZIP_URL,
                "gbbq_etag": gbbq_info.get("etag", ""),
                "gbbq_last_modified": gbbq_info.get("last_modified", ""),
                "gbbq_size_bytes": int(gbbq_info.get("content_length") or 0),
            }
        )
        _run_incremental_build()
        _status.stage = "done"
    except Exception as exc:  # noqa: BLE001 - 后台任务必须落状态
        _status.stage = "error"
        _status.error = f"{type(exc).__name__}: {exc}"
    finally:
        _status.running = False
        _status.finished_at = time.time()


def _download_zip() -> None:
    _status.stage = "downloading"
    _status.unit = "bytes"
    _status.done = 0
    _status.total = 0
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.tdx.com.cn/article/vipdata.html"}
    temp_path = ZIP_PATH.with_suffix(".zip.part")
    temp_path.unlink(missing_ok=True)
    try:
        with httpx.stream(
            "GET",
            TDX_ZIP_URL,
            headers=headers,
            timeout=httpx.Timeout(60, read=120),
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            _status.total = int(response.headers.get("Content-Length") or 0)
            with temp_path.open("wb") as file:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    file.write(chunk)
                    _status.done += len(chunk)
        if not zipfile.is_zipfile(temp_path):
            raise RuntimeError("通达信服务器未返回有效 ZIP 文件")
        temp_path.replace(ZIP_PATH)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _fetch_gbbq_info() -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.tdx.com.cn/"}
    with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
        response = client.head(GBBQ_ZIP_URL)
        response.raise_for_status()
    return {
        "etag": response.headers.get("ETag", ""),
        "last_modified": response.headers.get("Last-Modified", ""),
        "content_length": response.headers.get("Content-Length", ""),
    }


def _download_gbbq_zip() -> None:
    _status.stage = "downloading-gbbq"
    _status.unit = "bytes"
    _status.done = 0
    _status.total = 0
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.tdx.com.cn/"}
    temp_path = GBBQ_ZIP_PATH.with_suffix(".zip.part")
    temp_path.unlink(missing_ok=True)
    try:
        with httpx.stream(
            "GET",
            GBBQ_ZIP_URL,
            headers=headers,
            timeout=httpx.Timeout(30, read=90),
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            _status.total = int(response.headers.get("Content-Length") or 0)
            with temp_path.open("wb") as file:
                for chunk in response.iter_bytes(chunk_size=512 * 1024):
                    if chunk:
                        file.write(chunk)
                        _status.done += len(chunk)
        if not zipfile.is_zipfile(temp_path):
            raise RuntimeError("通达信服务器未返回有效 GBBQ ZIP")
        temp_path.replace(GBBQ_ZIP_PATH)
        _status.gbbq_downloaded = True
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _extract_gbbq() -> None:
    with zipfile.ZipFile(GBBQ_ZIP_PATH) as archive:
        try:
            member = archive.getinfo("gbbq")
        except KeyError as exc:
            raise RuntimeError("GBBQ ZIP 中缺少 gbbq 数据文件") from exc
        temp_path = GBBQ_RAW_PATH.with_suffix(".tmp")
        temp_path.unlink(missing_ok=True)
        try:
            with archive.open(member) as source, temp_path.open("wb") as destination:
                shutil.copyfileobj(source, destination, length=512 * 1024)
            temp_path.replace(GBBQ_RAW_PATH)
        finally:
            temp_path.unlink(missing_ok=True)


def _sync_gbbq(*, force_download: bool) -> dict[str, str]:
    """每次显式同步仅 HEAD 一次；版本变化才下载并重建事件缓存。"""
    manifest = _read_manifest()
    try:
        remote = _fetch_gbbq_info()
    except Exception:
        if not GBBQ_ZIP_PATH.exists():
            raise
        remote = {
            "etag": str(manifest.get("gbbq_etag", "")),
            "last_modified": str(manifest.get("gbbq_last_modified", "")),
            "content_length": str(GBBQ_ZIP_PATH.stat().st_size),
        }
    _status.gbbq_updated_at = remote.get("last_modified", "")
    same_remote = bool(
        GBBQ_ZIP_PATH.exists()
        and zipfile.is_zipfile(GBBQ_ZIP_PATH)
        and remote.get("etag")
        and remote.get("etag") == str(manifest.get("gbbq_etag", ""))
    )
    if force_download or not same_remote:
        _download_gbbq_zip()
    if _status.gbbq_downloaded or not GBBQ_RAW_PATH.exists():
        _extract_gbbq()

    events_path, meta_path = adjustment_paths(settings.cache_dir)  # type: ignore[arg-type]
    needs_parse = _status.gbbq_downloaded or not events_path.exists() or not meta_path.exists()
    if needs_parse:
        _status.stage = "parsing-gbbq"
        _status.unit = "records"
        _status.done = 0
        _status.total = 0
        parsed = parse_gbbq_to_cache(
            GBBQ_RAW_PATH,
            settings.cache_dir,  # type: ignore[arg-type]
            source_meta=remote,
        )
        _status.gbbq_events = int(parsed.get("event_count", 0))
    else:
        try:
            parsed = json.loads(meta_path.read_text(encoding="utf-8"))
            _status.gbbq_events = int(parsed.get("event_count", 0))
        except (OSError, json.JSONDecodeError):
            _status.gbbq_events = 0
    return remote


def _extract_zip(zip_path: Path) -> None:
    _status.stage = "extracting"
    _status.unit = "files"
    _status.done = 0
    _status.extracted = 0
    name_pattern = re.compile(r"^(sh|sz)(\d{6})\.day$", re.IGNORECASE)
    with zipfile.ZipFile(zip_path) as archive:
        members = []
        for member in archive.infolist():
            name = Path(member.filename.replace("\\", "/")).name.lower()
            if name_pattern.match(name):
                members.append((member, name))
        if not members:
            raise RuntimeError("通达信 ZIP 中没有找到沪深日线文件")
        _status.total = len(members)
        for member, name in members:
            market = name[:2]
            target = settings.raw_dir / market / "lday" / name  # type: ignore[operator]
            target.parent.mkdir(parents=True, exist_ok=True)
            temp_target = target.with_suffix(".day.tmp")
            try:
                with archive.open(member) as source, temp_target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                temp_target.replace(target)
                _status.extracted += 1
            finally:
                temp_target.unlink(missing_ok=True)
                _status.done += 1


def _run_incremental_build() -> None:
    _status.stage = "building-cache"
    _status.unit = "files"
    _status.done = 0
    _status.total = 0
    if not start_build(incremental=True):
        raise RuntimeError("已有 Parquet 缓存构建任务正在运行")
    while True:
        build = get_build_status()
        _status.done = build.done
        _status.total = build.total
        _status.updated = build.updated
        _status.skipped = build.skipped
        _status.failed = build.failed
        if not build.running:
            if build.error:
                raise RuntimeError(f"Parquet 增量构建失败：{build.error}")
            return
        time.sleep(0.5)
