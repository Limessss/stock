"""股票代码 → 名称（stock_names.json + 东财在线补全）。"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE: dict[str, str] | None = None
_mtime: float = 0.0
_lock = threading.Lock()
_names_path: Path | None = None
_pending_save = False


def _default_names_file() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root.parent / "data" / "cache" / "stock_names.json"


def set_names_file(path: Path) -> None:
    """由 backend 启动时注入 cache_dir 路径。"""
    global _names_path, _CACHE, _mtime
    with _lock:
        if _names_path != path:
            _names_path = path
            _CACHE = None
            _mtime = 0.0


def _names_file() -> Path:
    return _names_path or _default_names_file()


def _load() -> dict[str, str]:
    global _CACHE, _mtime
    path = _names_file()
    if not path.exists():
        return {}
    mtime = path.stat().st_mtime
    if _CACHE is not None and mtime == _mtime:
        return _CACHE
    with _lock:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            _CACHE = {str(k).upper(): str(v).strip() for k, v in raw.items()}
            _mtime = mtime
        except Exception:
            logger.warning("load stock_names.json failed: %s", path, exc_info=True)
            _CACHE = {}
    return _CACHE or {}


def _save_cache(data: dict[str, str]) -> None:
    global _CACHE, _mtime, _pending_save
    path = _names_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        path.write_text(
            json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _CACHE = dict(data)
        _mtime = path.stat().st_mtime
        _pending_save = False


def _secid(code: str) -> str:
    c = code.upper().replace("SH", "").replace("SZ", "")
    market = "1" if c.startswith("6") else "0"
    return f"{market}.{c}"


def fetch_name_from_eastmoney(code: str, *, timeout: float = 8.0) -> str:
    """东财行情接口补全名称（含部分退市/旧代码）。"""
    url = (
        "https://push2.eastmoney.com/api/qt/stock/get"
        f"?secid={_secid(code)}&fields=f58"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    # Windows 下 urllib 可能走系统代理导致东财连接失败
    prev = {
        k: os.environ.get(k)
        for k in ("NO_PROXY", "no_proxy", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
    }
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(k, None)
    try:
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                name = str(payload.get("data", {}).get("f58") or "").strip()
                return name
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
                if attempt == 0:
                    time.sleep(0.3)
                    continue
                logger.debug("eastmoney name fetch failed for %s: %s", code, e)
                return ""
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return ""


def enrich_stock_names(codes: list[str], *, persist: bool = True) -> dict[str, str]:
    """批量补全缺失名称，可选写回 stock_names.json。"""
    data = _load()
    out: dict[str, str] = {}
    changed = False
    for raw in codes:
        code = raw.upper()
        if data.get(code):
            out[code] = data[code]
            continue
        name = fetch_name_from_eastmoney(code)
        if name:
            data[code] = name
            out[code] = name
            changed = True
        else:
            out[code] = ""
        time.sleep(0.05)
    if persist and changed:
        _save_cache(data)
    return out


def get_stock_name(code: str, *, fetch_if_missing: bool = True) -> str:
    """返回股票中文名；本地无记录时可在线补全并缓存。"""
    key = code.upper()
    data = _load()
    name = data.get(key, "")
    if name or not fetch_if_missing:
        return name
    fetched = fetch_name_from_eastmoney(key)
    if fetched:
        data[key] = fetched
        _save_cache(data)
    return fetched


def total_names() -> int:
    return len(_load())
