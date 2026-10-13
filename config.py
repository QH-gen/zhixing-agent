"""全局配置。

所有可变参数集中在 .env 中，代码里不出现任何密钥。
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
WORKSPACE_DIR = STORAGE_DIR / "workspace"
SESSION_DIR = STORAGE_DIR / "sessions"
TODO_FILE = STORAGE_DIR / "todos.json"

for _dir in (STORAGE_DIR, WORKSPACE_DIR, SESSION_DIR):
    _dir.mkdir(parents=True, exist_ok=True)


def _load_env(path: Path) -> None:
    """极简 .env 解析器：KEY=VALUE，支持 # 注释。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(BASE_DIR / ".env")
_load_env(BASE_DIR / ".env.local")

# ---- 大模型（任意 OpenAI 兼容接口：DeepSeek / 通义 / 智谱 / Kimi / 本地 Ollama）----
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or "https://api.deepseek.com/v1"
LLM_MODEL = os.getenv("LLM_MODEL") or "deepseek-chat"
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE") or "0.3")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT") or "60")

# ---- 智能体行为 ----
MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS") or "6")
MEMORY_TURNS = int(os.getenv("MEMORY_TURNS") or "12")

# ---- Web 服务 ----
HOST = os.getenv("HOST") or "127.0.0.1"
PORT = int(os.getenv("PORT") or "8848")

AGENT_NAME = "知行 ZhiXing"
AGENT_SLOGAN = "会说，也会做"

# ---- 天气服务 ----
WEATHER_TIMEOUT = int(os.getenv("WEATHER_TIMEOUT") or "10")


def llm_enabled() -> bool:
    """是否配置了大模型密钥。未配置时智能体自动退回规则模式。"""
    return bool(LLM_API_KEY.strip())


def runtime_mode() -> str:
    return "llm" if llm_enabled() else "rules"
