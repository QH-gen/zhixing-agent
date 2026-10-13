"""把知行智能体的全部工具暴露为一个标准 MCP Server（stdio 传输）。

这意味着同一套工具能力，既能被本项目内置的智能体主循环调用，
也能被 Claude Desktop、Cursor、WorkBuddy 等任意 MCP 客户端复用。

安装依赖：
    pip install mcp

手动测试：
    python mcp_server.py        # 之后向 stdin 写 JSON-RPC 消息

Claude Desktop 配置（claude_desktop_config.json）：
{
  "mcpServers": {
    "zhixing": {
      "command": "python",
      "args": ["<项目绝对路径>/mcp_server.py"]
    }
  }
}
"""
from __future__ import annotations

import asyncio
import json
import sys

import tools as tool_pkg

try:
    from mcp import types
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
except ImportError:  # pragma: no cover
    print("[知行] 未安装官方 MCP SDK。请先执行：pip install mcp", file=sys.stderr)
    raise SystemExit(1)

server = Server("zhixing-tools")


@server.list_tools()
async def list_tools() -> list:
    """复用工具注册表 —— 工具只定义一次，多端复用。"""
    return [types.Tool(**item) for item in tool_pkg.mcp_tools_schema()]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list:
    outcome = tool_pkg.call_tool(name, arguments or {})
    text = json.dumps(outcome, ensure_ascii=False, default=str)
    return [types.TextContent(type="text", text=text)]


async def main() -> None:
    print(f"[知行] MCP Server 已启动，暴露 {len(tool_pkg.tool_names())} 个工具："
          f"{', '.join(tool_pkg.tool_names())}", file=sys.stderr)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
