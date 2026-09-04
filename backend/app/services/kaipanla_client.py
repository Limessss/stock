"""开盘啦可选数据源客户端。

该客户端只负责单次低频请求；是否允许请求以及缓存命中判断由 sentiment_service
统一控制，普通 GET API 不会调用这里。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from ..core.config import settings


class KaipanlaNotConfiguredError(RuntimeError):
    pass


@dataclass(frozen=True)
class EndpointRequest:
    name: str
    url: str
    body: dict[str, str]

    @property
    def public_params(self) -> dict[str, str]:
        secret_keys = {"UserID", "Token", "DeviceID"}
        return {key: value for key, value in self.body.items() if key not in secret_keys}


_LIVE_URL = "https://apphwhq.longhuvip.com/w1/api/index.php"
_LIVE_RANKING_URL = "https://apphq.longhuvip.com/w1/api/index.php"
_HISTORY_URL = "https://apphis.longhuvip.com/w1/api/index.php"


def is_configured() -> bool:
    return bool(settings.kaipanla_enabled and settings.kaipanla_device_id.strip())


def _base_body() -> dict[str, str]:
    body = {
        "PhoneOSNew": "1",
        "DeviceID": settings.kaipanla_device_id.strip(),
        "VerSion": settings.kaipanla_version,
        "Red": "0",
        "apiv": "w47",
    }
    if settings.kaipanla_user_id.strip():
        body["UserID"] = settings.kaipanla_user_id.strip()
    if settings.kaipanla_token.strip():
        body["Token"] = settings.kaipanla_token.strip()
    return body


def build_request(endpoint: str, trade_date: str) -> EndpointRequest:
    if endpoint in {"sector_strength", "sector_weakness"}:
        is_current = trade_date == datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
        body = {
            "Order": "1" if endpoint == "sector_strength" else "0",
            "a": "RealRankingInfo",
            "st": "30",
            "c": "ZhiShuRanking",
            "PhoneOSNew": "1",
            "DeviceID": settings.kaipanla_device_id.strip(),
            "VerSion": "5.22.0.6",
            "Index": "0",
            "Date": trade_date,
            "apiv": "w43",
            "Type": "1",
            "ZSType": "7",
        }
        if is_current:
            body.pop("Date")
            body["apiv"] = "w21"
            body["IsZZ"] = "0"
            return EndpointRequest(endpoint, _LIVE_RANKING_URL, body)
        return EndpointRequest(endpoint, _HISTORY_URL, body)

    body = _base_body()
    if endpoint == "limit_ladder":
        body.update({"a": "GetZhangTingTianTi_W47", "c": "FuPanLa"})
        return EndpointRequest(endpoint, _LIVE_URL, body)
    if endpoint == "limit_reasons":
        body.update(
            {
                "a": "GetPlateInfo_w38",
                "c": "HisLimitResumption",
                "st": "100",
                "Index": "0",
                "Date": trade_date,
            }
        )
        return EndpointRequest(endpoint, _HISTORY_URL, body)
    if endpoint == "new_high_groups":
        body.update({"a": "GroupCount_w28", "c": "StockNewHigh", "Type": "0_0_0_0_0"})
        return EndpointRequest(endpoint, _LIVE_URL, body)
    if endpoint == "highlights":
        body.update(
            {"a": "GetPMSL_PMLD", "c": "FuPanLa", "st": "30", "Index": "0"}
        )
        return EndpointRequest(endpoint, _LIVE_URL, body)
    raise ValueError(f"unknown kaipanla endpoint: {endpoint}")


def _decode_payload(value: Any) -> Any:
    decoded = value
    for _ in range(3):
        if not isinstance(decoded, str):
            break
        text = decoded.strip()
        if not text:
            return {}
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return {"text": decoded}
    return decoded


def fetch(endpoint: str, trade_date: str) -> tuple[EndpointRequest, Any]:
    if not is_configured():
        raise KaipanlaNotConfiguredError("开盘啦数据源未启用或缺少 DeviceID")
    request = build_request(endpoint, trade_date)
    user_agent = (
        "Dalvik/2.1.0 (Linux; U; Android 14; 25098PN5AC Build/UQ1A.240205.05262019)"
        if endpoint in {"sector_strength", "sector_weakness"}
        else "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Mobile Safari/537.36"
    )
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://apppage.longhuvip.com",
        "Referer": "https://apppage.longhuvip.com/",
        "X-Requested-With": "com.aiyu.kaipanla",
        "User-Agent": user_agent,
    }
    with httpx.Client(timeout=settings.kaipanla_timeout, follow_redirects=True) as client:
        response = client.post(request.url, data=request.body, headers=headers)
        response.raise_for_status()
        try:
            payload: Any = response.json()
        except ValueError:
            payload = response.text
    return request, _decode_payload(payload)


def payload_has_data(payload: Any) -> bool:
    if isinstance(payload, list):
        return len(payload) > 0
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in {"errcode", "error", "message", "msg"}:
                continue
            if isinstance(value, list) and value:
                return True
            if isinstance(value, dict) and payload_has_data(value):
                return True
        return False
    return bool(payload)


def payload_error(payload: Any) -> str:
    """提取 HTTP 200 响应中的业务错误，避免将参数错误误判为空数据。"""
    if not isinstance(payload, dict):
        return ""
    code = payload.get("errcode")
    if code not in (None, "", 0, "0"):
        message = payload.get("errmsg") or payload.get("message") or "接口业务错误"
        return f"errcode={code}: {message}"
    error = payload.get("error")
    return str(error).strip() if error else ""
