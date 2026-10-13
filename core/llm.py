"""OpenAI 兼容的大模型客户端。

只用标准库 urllib 实现，不依赖 openai SDK —— 作业演示环境零安装即可跑通。
兼容 DeepSeek / 通义千问 / 智谱 GLM / Kimi / 本地 Ollama 等任何
提供 /chat/completions 的服务。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List

import config


class LLMError(RuntimeError):
    """大模型调用异常，统一收敛成这一种，便于上层降级。"""


def chat_completion(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    if not config.llm_enabled():
        raise LLMError("未配置 LLM_API_KEY")

    url = config.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    payload: Dict[str, Any] = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "temperature": config.LLM_TEMPERATURE,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.LLM_API_KEY}",
            "User-Agent": "zhixing-agent/1.0",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=config.LLM_TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:400]
        raise LLMError(f"模型接口返回 HTTP {exc.code}：{detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"无法连接模型服务（{config.LLM_BASE_URL}）：{exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise LLMError(f"模型请求超时或网络异常：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise LLMError(f"模型返回内容不是合法 JSON：{exc}") from exc

    try:
        return body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"模型返回结构异常：{str(body)[:300]}") from exc


def health_check() -> Dict[str, Any]:
    """探活：确认密钥与模型可用，供前端状态栏展示。"""
    try:
        message = chat_completion([{"role": "user", "content": "回复两个字：就绪"}])
        return {"ok": True, "reply": (message.get("content") or "").strip()[:50]}
    except LLMError as exc:
        return {"ok": False, "error": str(exc)}
