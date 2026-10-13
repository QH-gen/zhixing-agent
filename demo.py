"""一键演示脚本：无需 API Key 即可完整跑通「能说会做」全流程。

    python demo.py

脚本会依次演示：多轮对话记忆 → 天气查询（外部 API）→ 新增待办 →
查询清单 → 导出 Markdown 文件（落盘）→ 列出文件 → 计算，
并把每一次工具调用及其返回打印出来，可直接用于撰写实验报告/随笔。
"""
from __future__ import annotations

import json
import sys

import config
from core.agent import Agent, available_tools

SCRIPT = [
    "你好，你能做什么？",
    "我明天要去杭州，帮我看看天气，要不要带伞？",
    "帮我记一下：周三下午交软件工程实验报告，优先级高",
    "再记一条：周四上午十点小组会议",
    "看看我的待办清单",
    "把待办清单导出成 Markdown 文件",
    "列一下我现在有哪些文件",
    "算一下 128*37+56",
    "今天几号？",
]

LINE = "─" * 66


def main() -> int:
    mode = "大模型模式" if config.llm_enabled() else "规则模式（未配置 LLM_API_KEY，功能完全可用）"
    print(LINE)
    print(f"  {config.AGENT_NAME} · {config.AGENT_SLOGAN}   一键演示")
    print(f"  运行模式：{mode}")
    print(f"  已挂载工具 {len(available_tools())} 个")
    print(LINE)

    agent = Agent(session_id="demo")
    agent.memory.clear()
    # 每次演示都从干净状态开始，保证输出可复现（只清演示数据，不动其他文件）
    config.TODO_FILE.write_text("[]", encoding="utf-8")
    print("  （已重置演示用待办数据）")

    for index, utterance in enumerate(SCRIPT, 1):
        print(f"\n【第 {index} 轮】用户：{utterance}")
        result = agent.run(utterance)
        for step in result["steps"]:
            args = json.dumps(step["arguments"], ensure_ascii=False)
            print(f"   ↳ 工具调用 {step['tool']}({args})  -> {'成功' if step['ok'] else '失败'}")
            if step["result"] is not None:
                snippet = json.dumps(step["result"], ensure_ascii=False, default=str)
                print(f"     返回：{snippet[:150]}{'…' if len(snippet) > 150 else ''}")
            if not step["ok"]:
                print(f"     错误：{step['error']}")
        print(f"  知行：{result['reply']}")

    print("\n" + LINE)
    print(f"  演示结束。会话共 {agent.memory.turn_count()} 轮，记忆已持久化到 storage/sessions/demo.json")
    print("  下一步：python server.py 打开网页版体验语音输入输出")
    print(LINE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
