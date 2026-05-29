"""策略元信息与默认参数持久化。"""
from __future__ import annotations

import dataclasses
import json
import threading
from pathlib import Path
from typing import Any

from model.strategies import STRATEGIES

from ..core.config import settings

_lock = threading.Lock()
_cache: dict[str, Any] | None = None
_GLOBAL_KEY = "__global__"
_META_KEY = "meta"
_PARAMS_KEY = "params"
_FALLBACK_DEFAULT = "breakout_washout"


def _defaults_path() -> Path:
    return settings.cache_dir / "strategy_defaults.json"


def _load_raw_store() -> dict[str, Any]:
    global _cache
    path = _defaults_path()
    if _cache is not None:
        return _cache
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


def _save_raw_store(data: dict[str, Any]) -> None:
    global _cache
    path = _defaults_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        _cache = dict(data)


def _code_param_keys(name: str) -> set[str]:
    return set(get_code_defaults(name))


def _normalize_entry(name: str, raw: Any) -> dict[str, Any]:
    """兼容旧版：策略条目顶层直接是参数字典。"""
    if not isinstance(raw, dict):
        return {_META_KEY: {}, _PARAMS_KEY: {}}
    if _META_KEY in raw or _PARAMS_KEY in raw:
        meta = raw.get(_META_KEY) if isinstance(raw.get(_META_KEY), dict) else {}
        params = raw.get(_PARAMS_KEY) if isinstance(raw.get(_PARAMS_KEY), dict) else {}
        return {_META_KEY: dict(meta), _PARAMS_KEY: dict(params)}
    code_keys = _code_param_keys(name)
    legacy_params = {k: v for k, v in raw.items() if k in code_keys}
    if legacy_params:
        return {_META_KEY: {}, _PARAMS_KEY: legacy_params}
    return {_META_KEY: {}, _PARAMS_KEY: {}}


def _get_entry(name: str) -> dict[str, Any]:
    store = _load_raw_store()
    return _normalize_entry(name, store.get(name))


def _set_entry(name: str, entry: dict[str, Any]) -> None:
    store = dict(_load_raw_store())
    meta = entry.get(_META_KEY) or {}
    params = entry.get(_PARAMS_KEY) or {}
    if meta or params:
        store[name] = {_META_KEY: meta, _PARAMS_KEY: params}
    else:
        store.pop(name, None)
    _save_raw_store(store)


def _get_global() -> dict[str, Any]:
    store = _load_raw_store()
    raw = store.get(_GLOBAL_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _set_global(settings_map: dict[str, Any]) -> None:
    store = dict(_load_raw_store())
    if settings_map:
        store[_GLOBAL_KEY] = settings_map
    else:
        store.pop(_GLOBAL_KEY, None)
    _save_raw_store(store)


def get_code_defaults(name: str) -> dict[str, Any]:
    cls = STRATEGIES[name]
    params_cls = cls.params_cls
    out: dict[str, Any] = {}
    for f in dataclasses.fields(params_cls):
        if f.default is not dataclasses.MISSING:
            out[f.name] = f.default
        elif f.default_factory is not dataclasses.MISSING:  # type: ignore[attr-defined]
            out[f.name] = f.default_factory()
        else:
            out[f.name] = None
    return out


def get_code_label(name: str) -> str:
    return STRATEGIES[name].label


def get_code_description(name: str) -> str:
    return STRATEGIES[name].description


def get_custom_meta(name: str) -> dict[str, Any]:
    meta = _get_entry(name)[_META_KEY]
    out: dict[str, Any] = {}
    if isinstance(meta.get("label"), str) and meta["label"].strip():
        out["label"] = meta["label"].strip()
    if isinstance(meta.get("description"), str):
        out["description"] = meta["description"]
    return out


def get_effective_label(name: str) -> str:
    custom = get_custom_meta(name).get("label")
    return custom if custom else get_code_label(name)


def get_effective_description(name: str) -> str:
    if "description" in get_custom_meta(name):
        return str(get_custom_meta(name)["description"])
    return get_code_description(name)


def has_custom_meta(name: str) -> bool:
    return bool(get_custom_meta(name))


def get_custom_defaults(name: str) -> dict[str, Any]:
    params = _get_entry(name)[_PARAMS_KEY]
    code_keys = _code_param_keys(name)
    return {k: v for k, v in params.items() if k in code_keys}


def get_effective_defaults(name: str) -> dict[str, Any]:
    return {**get_code_defaults(name), **get_custom_defaults(name)}


def has_custom_defaults(name: str) -> bool:
    return bool(get_custom_defaults(name))


def get_default_strategy_name() -> str:
    preferred = _get_global().get("default_strategy")
    if isinstance(preferred, str) and preferred in STRATEGIES:
        return preferred
    if _FALLBACK_DEFAULT in STRATEGIES:
        return _FALLBACK_DEFAULT
    return next(iter(STRATEGIES))


def set_default_strategy(name: str) -> None:
    if name not in STRATEGIES:
        raise ValueError(f"未知策略: {name}")
    global_settings = dict(_get_global())
    global_settings["default_strategy"] = name
    _set_global(global_settings)


def is_default_strategy(name: str) -> bool:
    return get_default_strategy_name() == name


def resolve_strategy_params(name: str, params: dict[str, Any] | None) -> dict[str, Any]:
    base = get_effective_defaults(name)
    if not params:
        return base
    valid = set(base.keys())
    merged = dict(base)
    for k, v in params.items():
        if k in valid:
            merged[k] = v
    return merged


def _coerce_param(value: Any, template: Any) -> Any:
    t = type(template)
    if t is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)
    if t is int:
        return int(value)
    if t is float:
        return float(value)
    return value


def validate_strategy_params(name: str, params: dict[str, Any]) -> dict[str, Any]:
    code_defaults = get_code_defaults(name)
    unknown = set(params) - set(code_defaults)
    if unknown:
        raise ValueError(f"未知参数: {sorted(unknown)}")
    out: dict[str, Any] = {}
    for key, value in params.items():
        try:
            out[key] = _coerce_param(value, code_defaults[key])
        except (TypeError, ValueError) as e:
            raise ValueError(f"参数 {key} 类型错误: {e}") from e
    return out


def save_strategy_meta(
    name: str,
    *,
    label: str | None = None,
    description: str | None = None,
    is_default: bool | None = None,
) -> None:
    if name not in STRATEGIES:
        raise ValueError(f"未知策略: {name}")

    entry = _get_entry(name)
    meta = dict(entry[_META_KEY])

    if label is not None:
        text = label.strip()
        if text and text != get_code_label(name):
            meta["label"] = text
        else:
            meta.pop("label", None)

    if description is not None:
        if description != get_code_description(name):
            meta["description"] = description
        else:
            meta.pop("description", None)

    entry[_META_KEY] = meta
    _set_entry(name, entry)

    if is_default is True:
        set_default_strategy(name)
    elif is_default is False and is_default_strategy(name):
        set_default_strategy(_FALLBACK_DEFAULT)


def save_strategy_defaults(name: str, params: dict[str, Any]) -> dict[str, Any]:
    if name not in STRATEGIES:
        raise ValueError(f"未知策略: {name}")
    validated = validate_strategy_params(name, params)
    entry = _get_entry(name)
    entry[_PARAMS_KEY] = validated
    _set_entry(name, entry)
    return get_effective_defaults(name)


def save_strategy_config(
    name: str,
    *,
    label: str | None = None,
    description: str | None = None,
    is_default: bool | None = None,
    params: dict[str, Any] | None = None,
) -> None:
    if label is not None or description is not None or is_default is not None:
        save_strategy_meta(
            name,
            label=label,
            description=description,
            is_default=is_default,
        )
    if params is not None:
        save_strategy_defaults(name, params)


def reset_strategy_meta(name: str) -> None:
    if name not in STRATEGIES:
        raise ValueError(f"未知策略: {name}")
    entry = _get_entry(name)
    entry[_META_KEY] = {}
    _set_entry(name, entry)


def reset_strategy_defaults(name: str) -> None:
    if name not in STRATEGIES:
        raise ValueError(f"未知策略: {name}")
    entry = _get_entry(name)
    entry[_PARAMS_KEY] = {}
    _set_entry(name, entry)


def reset_strategy_all(name: str) -> None:
    if name not in STRATEGIES:
        raise ValueError(f"未知策略: {name}")
    store = dict(_load_raw_store())
    store.pop(name, None)
    _save_raw_store(store)
    if is_default_strategy(name):
        global_settings = dict(_get_global())
        global_settings.pop("default_strategy", None)
        _set_global(global_settings)


def dataclass_to_schema(params_cls: type, defaults: dict[str, Any]) -> dict[str, Any]:
    if not dataclasses.is_dataclass(params_cls):
        return {}
    out: dict[str, Any] = {}
    for f in dataclasses.fields(params_cls):
        t = f.type
        type_name = t.__name__ if hasattr(t, "__name__") else str(t)
        out[f.name] = {
            "type": type_name,
            "default": defaults.get(f.name),
        }
    return out


def build_strategy_info(name: str) -> dict[str, Any]:
    cls = STRATEGIES[name]
    effective = get_effective_defaults(name)
    schema = dataclass_to_schema(cls.params_cls, effective)
    return {
        "name": name,
        "label": get_effective_label(name),
        "code_label": get_code_label(name),
        "description": get_effective_description(name),
        "code_description": get_code_description(name),
        "param_count": len(schema),
        "params_schema": schema,
        "has_custom_defaults": has_custom_defaults(name),
        "has_custom_meta": has_custom_meta(name),
        "is_default": is_default_strategy(name),
    }


def build_strategy_detail(name: str) -> dict[str, Any]:
    cls = STRATEGIES[name]
    code_defaults = get_code_defaults(name)
    effective = get_effective_defaults(name)
    info = build_strategy_info(name)
    return {
        **info,
        "features": list(cls.features),
        "tier_rules": list(cls.tier_rules),
        "default_params": effective,
        "code_defaults": code_defaults,
    }


def build_strategy_list() -> dict[str, Any]:
    return {
        "strategies": [build_strategy_info(name) for name in STRATEGIES],
        "default_strategy": get_default_strategy_name(),
    }
