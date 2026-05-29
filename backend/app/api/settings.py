"""系统设置 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.settings import LlmConfigPublic, LlmConfigUpdate, LlmTestResponse
from ..services.llm_service import LlmNotConfiguredError, test_connection
from ..services.settings_service import get_llm_config_public, save_llm_config

router = APIRouter()


@router.get("/settings/llm", response_model=LlmConfigPublic)
def get_llm_settings() -> LlmConfigPublic:
    return LlmConfigPublic(**get_llm_config_public())


@router.put("/settings/llm", response_model=LlmConfigPublic)
def update_llm_settings(body: LlmConfigUpdate) -> LlmConfigPublic:
    payload = save_llm_config(
        base_url=body.base_url,
        model=body.model,
        timeout=body.timeout,
        api_key=body.api_key,
    )
    return LlmConfigPublic(**payload)


@router.post("/settings/llm/test", response_model=LlmTestResponse)
def test_llm_settings() -> LlmTestResponse:
    try:
        result = test_connection()
    except LlmNotConfiguredError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"连接失败: {e}") from e
    return LlmTestResponse(**result)
