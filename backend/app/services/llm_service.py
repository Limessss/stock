"""OpenAI 兼容大模型调用。"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from openai import OpenAI

from .settings_service import get_llm_config

logger = logging.getLogger(__name__)


class LlmNotConfiguredError(RuntimeError):
    pass


def _client() -> OpenAI:
    cfg = get_llm_config()
    if not cfg.api_key.strip():
        raise LlmNotConfiguredError("未配置大模型 API Key，请先在系统设置中配置大模型提供商")
    return OpenAI(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        timeout=cfg.timeout,
    )


def is_llm_configured() -> bool:
    return bool(get_llm_config().api_key.strip())


def _extract_json(text: str) -> dict[str, Any]:
    """从模型回复中解析 JSON（兼容 markdown 代码块包裹）。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("大模型返回空内容")

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if code_block:
        try:
            parsed = json.loads(code_block.group(1).strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        snippet = text[start : end + 1]
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as e:
            raise ValueError(f"大模型返回非 JSON: {e}") from e

    preview = text[:200].replace("\n", " ")
    raise ValueError(f"大模型返回非 JSON，原始内容: {preview}")


def _create_completion(
    *,
    client: OpenAI,
    model: str,
    system: str,
    user: str,
    temperature: float,
    json_mode: bool,
    max_tokens: int | None = None,
) -> str:
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    resp = client.chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()


def chat_json(
    *,
    system: str,
    user: str,
    temperature: float = 0.2,
    max_tokens: int | None = 4096,
) -> dict[str, Any]:
    """调用大模型并解析 JSON 结果，兼容不支持 json_object 的 OpenAI 兼容接口。"""
    cfg = get_llm_config()
    client = _client()

    json_hint = "\n只输出一个合法的 JSON 对象，不要输出 markdown 代码块或其它说明文字。"
    attempts: list[tuple[str, bool]] = [
        (system, True),
        (system + json_hint, False),
    ]

    last_error: Exception | None = None
    last_content = ""

    for sys_prompt, json_mode in attempts:
        try:
            content = _create_completion(
                client=client,
                model=cfg.model,
                system=sys_prompt,
                user=user,
                temperature=temperature,
                json_mode=json_mode,
                max_tokens=max_tokens,
            )
            last_content = content
            if not content:
                logger.warning("LLM empty response (json_mode=%s, model=%s)", json_mode, cfg.model)
                continue
            return _extract_json(content)
        except ValueError as e:
            last_error = e
            logger.warning(
                "LLM JSON parse failed (json_mode=%s): %s",
                json_mode,
                last_content[:200],
            )
            continue
        except Exception as e:
            if json_mode:
                logger.warning("LLM json_mode request failed, will retry plain: %s", e)
                last_error = e
                continue
            raise

    if last_error:
        raise ValueError(str(last_error)) from last_error
    raise ValueError(
        "大模型返回空内容或非 JSON。"
        "请确认 Base URL / 模型名称正确，且该模型支持 Chat Completions。"
    )


def test_connection() -> dict[str, Any]:
    t0 = time.perf_counter()
    cfg = get_llm_config()
    client = _client()
    resp = client.chat.completions.create(
        model=cfg.model,
        max_tokens=16,
        messages=[{"role": "user", "content": "回复 OK"}],
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    reply = (resp.choices[0].message.content or "").strip()
    return {
        "ok": True,
        "latency_ms": elapsed_ms,
        "model": cfg.model,
        "reply": reply[:100],
    }
