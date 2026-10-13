"""命令行交互界面。

用法：
    python cli.py
命令：
    /tools   查看已挂载工具
    /reset   清空当前会话记忆
    /exit    退出
"""
from __future__ import annotations

import json
import sys

import config
from core.agent import Agent, available_tools


def _banner() -> None:
    mode = "大模型模式" if config.llm_enabled() else "规则模式（未配置 LLM_API_KEY）"
    print("=" * 62)
    print(f"  {config.AGENT_NAME} · {config.AGENT_SLOGAN}")
    print(f"  运行模式：{mode}    模型：{config.LLM_MODEL}")
    print(f"  已挂载工具 {len(available_tools())} 个：{', '.join(available_tools())}")
    print("  输入 /tools 看工具，/reset 清空记忆，/exit 退出")
    print("=" * 62)


def main() -> int:
    _banner()
    agent = Agent(session_id="cli")
    if agent.memory.turn_count():
        print(f"[提示] 已恢复会话记忆，历史 {agent.memory.turn_count()} 轮。\n")

    while True:
        try:
            text = input("你   > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[知行] 再见。")
            return 0

        if not text:
            continue
        if text in ("/exit", "/quit", "exit", "quit", "退出"):
            print("[知行] 再见。")
            return 0
        if text == "/reset":
            agent.memory.clear()
            print("[知行] 会话记忆已清空。")
            continue
        if text == "/tools":
            for item in available_tools():
                print("  -", item)
            continue

        result = agent.run(text)

        for step in result["steps"]:
            flag = "OK " if step["ok"] else "ERR"
            print(f"  [{flag}] 调用工具 {step['tool']}({json.dumps(step['arguments'], ensure_ascii=False)})")

        print(f"\n知行 > {result['reply']}")
        if result.get("error"):
            print(f"  (大模型不可用，已降级为规则模式：{result['error']})")
        print()


if __name__ == "__main__":
    sys.exit(main())
