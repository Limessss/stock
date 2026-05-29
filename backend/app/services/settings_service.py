"""系统设置持久化（大模型提供商等）。"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.config import settings

_lock = threading.Lock()
_cache: dict[str, Any] | None = None


def _settings_path() -> Path:
    return settings.cache_dir / "system_settings.json"


def _load_store() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = _settings_path()
    with _lock:
        if not path.exists():
            _cache = {}
            return _cache
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            _cache = raw if isinstance(raw, dict) else {}
        except (json.JSONDecodeError, OSError):
            _cache = {}
    return _cache or {}


def _save_store(data: dict[str, Any]) -> None:
    global _cache
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        _cache = dict(data)


@dataclass
class LlmConfig:
    base_url: str
    api_key: str
    model: str
    timeout: float


def _mask_api_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:3]}****{key[-4:]}"


def get_llm_config() -> LlmConfig:
    store = _load_store()
    llm = store.get("llm") if isinstance(store.get("llm"), dict) else {}
    return LlmConfig(
        base_url=str(llm.get("base_url") or settings.llm_base_url).rstrip("/"),
        api_key=str(llm.get("api_key") or settings.llm_api_key),
        model=str(llm.get("model") or settings.llm_model),
        timeout=float(llm.get("timeout") or settings.llm_timeout),
    )


def get_llm_config_public() -> dict[str, Any]:
    cfg = get_llm_config()
    return {
        "base_url": cfg.base_url,
        "model": cfg.model,
        "timeout": cfg.timeout,
        "api_key_masked": _mask_api_key(cfg.api_key),
        "configured": bool(cfg.api_key.strip()),
    }


def save_llm_config(
    *,
    base_url: str | None = None,
    model: str | None = None,
    timeout: float | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    store = dict(_load_store())
    llm = dict(store.get("llm") or {}) if isinstance(store.get("llm"), dict) else {}
    current = get_llm_config()

    if base_url is not None:
        llm["base_url"] = base_url.rstrip("/")
    if model is not None:
        llm["model"] = model
    if timeout is not None:
        llm["timeout"] = timeout
    if api_key is not None and api_key.strip():
        llm["api_key"] = api_key.strip()
    elif "api_key" not in llm and current.api_key:
        llm["api_key"] = current.api_key

    store["llm"] = llm
    _save_store(store)
    return get_llm_config_public()
