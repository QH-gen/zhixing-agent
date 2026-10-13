"""工具注册表。

设计要点：工具函数与「谁在调用它」完全解耦。
同一份注册表同时服务三个消费方：
  1. 智能体主循环（导出 OpenAI function calling 的 tools schema）
  2. MCP Server（导出 MCP 协议的 inputSchema）
  3. 单元自测 / demo 脚本（直接 call_tool）
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

_REGISTRY: Dict[str, Dict[str, Any]] = {}


def tool(name: str, description: str, parameters: Dict[str, Any]) -> Callable:
    """把一个普通 Python 函数注册为智能体可调用的工具。"""

    def decorator(fn: Callable) -> Callable:
        if name in _REGISTRY:
            raise ValueError(f"工具名重复：{name}")
        _REGISTRY[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "func": fn,
        }
        return fn

    return decorator


def all_tools() -> List[Dict[str, Any]]:
    return list(_REGISTRY.values())


def tool_names() -> List[str]:
    return list(_REGISTRY.keys())


def openai_tools_schema() -> List[Dict[str, Any]]:
    """转换为 OpenAI Chat Completions 的 tools 参数格式。"""
    return [
        {
            "type": "function",
            "function": {
                "name": item["name"],
                "description": item["description"],
                "parameters": item["parameters"],
            },
        }
        for item in _REGISTRY.values()
    ]


def mcp_tools_schema() -> List[Dict[str, Any]]:
    """转换为 MCP 协议的 Tool 定义（name / description / inputSchema）。"""
    return [
        {
            "name": item["name"],
            "description": item["description"],
            "inputSchema": item["parameters"],
        }
        for item in _REGISTRY.values()
    ]


def call_tool(name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """执行工具，永不抛异常——错误以 ok=False 的形式回传给模型，让它自行纠正。"""
    if name not in _REGISTRY:
        return {"ok": False, "error": f"未知工具：{name}，可用工具：{', '.join(tool_names())}"}
    args = arguments or {}
    try:
        result = _REGISTRY[name]["func"](**args)
        return {"ok": True, "tool": name, "result": result}
    except TypeError as exc:
        return {"ok": False, "tool": name, "error": f"参数不匹配：{exc}"}
    except Exception as exc:  # noqa: BLE001 - 兜底，保证智能体不会崩
        return {"ok": False, "tool": name, "error": f"{type(exc).__name__}: {exc}"}
