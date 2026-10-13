"""HTTP 服务：为前端提供 API，并托管静态页面。

只用 Python 标准库 http.server，不引入 FastAPI/Flask，
保证「克隆下来 → python server.py → 打开浏览器」三步可跑。
"""
from __future__ import annotations

import json
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

import config
import tools as tool_pkg
from core.agent import Agent, available_tools
from core.llm import health_check
from core.memory import SessionMemory

WEB_DIR = Path(__file__).resolve().parent / "web"

_AGENTS: Dict[str, Agent] = {}


def get_agent(session_id: str) -> Agent:
    if session_id not in _AGENTS:
        _AGENTS[session_id] = Agent(session_id)
    return _AGENTS[session_id]


class Handler(BaseHTTPRequestHandler):
    server_version = "ZhiXing/1.0"

    # ---------------- 基础工具 ----------------
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        print(f"[知行] {self.address_string()} {fmt % args}")

    # ---------------- GET ----------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            return self._serve_file(WEB_DIR / "index.html", "text/html; charset=utf-8")

        if path == "/api/status":
            return self._json(
                {
                    "agent": config.AGENT_NAME,
                    "slogan": config.AGENT_SLOGAN,
                    "mode": config.runtime_mode(),
                    "model": config.LLM_MODEL,
                    "base_url": config.LLM_BASE_URL,
                    "tool_count": len(available_tools()),
                    "tools": available_tools(),
                }
            )

        if path == "/api/todos":
            outcome = tool_pkg.call_tool("todo_list", {"status": "all"})
            return self._json(outcome.get("result") or {"items": []})

        if path == "/api/files":
            outcome = tool_pkg.call_tool("file_list", {})
            return self._json(outcome.get("result") or {"files": []})

        if path == "/api/history":
            session_id = (query.get("session_id") or ["default"])[0]
            memory = SessionMemory(session_id)
            return self._json({"session_id": memory.session_id, "records": memory.records})

        if path == "/api/sessions":
            return self._json({"sessions": SessionMemory.list_sessions()})

        if path == "/api/health":
            return self._json(health_check() if config.llm_enabled() else {"ok": False, "error": "未配置 LLM_API_KEY"})

        return self._json({"error": f"未知路径：{path}"}, 404)

    # ---------------- POST ----------------
    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        payload = self._read_json()
        session_id = str(payload.get("session_id") or "default")

        if path == "/api/chat":
            message = str(payload.get("message") or "")
            if not message.strip():
                return self._json({"error": "消息不能为空"}, 400)
            return self._json(get_agent(session_id).run(message))

        if path == "/api/reset":
            get_agent(session_id).memory.clear()
            return self._json({"ok": True, "message": "会话已清空"})

        return self._json({"error": f"未知路径：{path}"}, 404)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    # ---------------- 静态文件 ----------------
    def _serve_file(self, file_path: Path, content_type: str) -> None:
        if not file_path.exists():
            return self._json({"error": f"文件不存在：{file_path.name}"}, 404)
        self._send(200, file_path.read_bytes(), content_type)


def main() -> None:
    server = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    url = f"http://{config.HOST}:{config.PORT}/"
    mode = "大模型模式" if config.llm_enabled() else "规则模式（未配置 LLM_API_KEY）"
    print("=" * 62)
    print(f"  {config.AGENT_NAME} · {config.AGENT_SLOGAN}")
    print(f"  运行模式：{mode}")
    print(f"  已注册工具：{len(available_tools())} 个 -> {', '.join(available_tools())}")
    print(f"  访问地址：{url}")
    print("  Ctrl+C 停止服务")
    print("=" * 62)
    if not os.getenv("ZX_NO_BROWSER"):
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[知行] 服务已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
