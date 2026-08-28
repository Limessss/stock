"""龙头周期全景图配置持久化。"""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.time_utils import utc_now
from ..models.sentiment import LeaderPanoramaConfig, LeaderPanoramaPreset

CONFIG_ID = "default"
MAX_INSTRUMENTS = 100


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


def list_presets(session: Session) -> list[LeaderPanoramaPreset]:
    """按最近更新优先列出已保存的区间方案。"""
    return list(
        session.scalars(
            select(LeaderPanoramaPreset).order_by(
                LeaderPanoramaPreset.updated_at.desc(),
                LeaderPanoramaPreset.created_at.desc(),
            )
        )
    )


def create_preset(
    session: Session,
    *,
    name: str,
    start_date: str,
    end_date: str,
    instruments: list[dict],
) -> LeaderPanoramaPreset:
    if start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")
    now = utc_now()
    preset = LeaderPanoramaPreset(
        id=str(uuid4()),
        name=name.strip(),
        start_date=start_date,
        end_date=end_date,
        instruments=normalize_instruments(instruments),
        created_at=now,
        updated_at=now,
    )
    session.add(preset)
    session.flush()
    return preset


def update_preset(
    session: Session,
    preset_id: str,
    *,
    name: str,
    start_date: str,
    end_date: str,
    instruments: list[dict],
) -> LeaderPanoramaPreset | None:
    if start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")
    preset = session.get(LeaderPanoramaPreset, preset_id)
    if preset is None:
        return None
    preset.name = name.strip()
    preset.start_date = start_date
    preset.end_date = end_date
    preset.instruments = normalize_instruments(instruments)
    preset.updated_at = utc_now()
    session.flush()
    return preset


def delete_preset(session: Session, preset_id: str) -> bool:
    preset = session.get(LeaderPanoramaPreset, preset_id)
    if preset is None:
        return False
    session.delete(preset)
    session.flush()
    return True
