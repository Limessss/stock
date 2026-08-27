"""龙头周期全景图配置持久化。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..core.time_utils import utc_now
from ..models.sentiment import LeaderPanoramaConfig

CONFIG_ID = "default"
MAX_INSTRUMENTS = 16


def normalize_instruments(instruments: list[dict]) -> list[dict[str, str]]:
    """规范化证券代码并按首次出现去重，保留用户排序。"""
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in instruments[:MAX_INSTRUMENTS]:
        code = str(item.get("code", "")).strip().upper()
        name = str(item.get("name", "")).strip()
        item_type = "index" if item.get("type") == "index" else "stock"
        if not code or not name or code in seen:
            continue
        seen.add(code)
        result.append({"code": code, "name": name, "type": item_type})
    return result


def get_config(session: Session) -> LeaderPanoramaConfig | None:
    return session.get(LeaderPanoramaConfig, CONFIG_ID)


def save_config(session: Session, instruments: list[dict]) -> LeaderPanoramaConfig:
    config = get_config(session)
    now = utc_now()
    normalized = normalize_instruments(instruments)
    if config is None:
        config = LeaderPanoramaConfig(
            id=CONFIG_ID,
            instruments=normalized,
            created_at=now,
            updated_at=now,
        )
        session.add(config)
    else:
        config.instruments = normalized
        config.updated_at = now
    session.flush()
    return config
