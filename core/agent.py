"""智能体主循环。

一句话概括：把「用户输入 → 意图理解 → 工具调用 → 结果回填 → 自然语言回答」
这个 ReAct 式闭环，用 200 行讲清楚。

两种运行模式：
* llm   —— 有 API Key 时走大模型 function calling，自主决策调用哪些工具；
* rules —— 没有 Key 或接口不可用时，退化为关键词规则路由，保证演示不中断。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

import config
import tools as tool_pkg
from tools import todo_tools, weather_tools

from .llm import LLMError, chat_completion
from .memory import SessionMemory

SYSTEM_PROMPT = """你是「知行 ZhiXing」，一名大学生个人事务智能助理，名字取自“知行合一”——既要会说，也要会做。

# 你可以调用的工具
- 待办管理：todo_add（新增）、todo_list（查看）、todo_done（完成）、todo_remove（删除）
- 天气出行：weather_query（查询实时天气与三天预报）
- 文件处理：file_write（写入）、file_read（读取）、file_list（列目录）——仅限 storage/workspace 沙箱
- 通用：calculator（算术计算）、current_time（获取当前时间）

# 工作原则
1. 先判断意图。需要真实数据或需要产生副作用（写文件、改待办）时，必须调用工具，绝不凭想象编造数据。
2. 涉及“今天、明天、这周、下周三”等相对时间时，先调用 current_time 拿到准确日期。
3. 用户要求导出/保存时，用 file_write 真正落盘，并告诉用户保存的文件名。
4. 工具返回 ok=false 时，读懂错误原因并自行调整参数重试一次；仍失败就如实告知用户。
5. 用户只是打招呼或问“你能做什么”时，直接用文字回答，不要调用工具。
6. 用中文回答，条理清晰，适度使用 Markdown 列表和加粗；不要输出思考过程，只给结论和必要说明。
7. 涉及用户隐私或沙箱外的文件操作，礼貌拒绝并说明原因。

# 输出风格
简洁、直接、有温度。先给结果，再给建议。不要复述工具返回的原始 JSON。"""


def _tool_step(name: str, args: Dict[str, Any], outcome: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tool": name,
        "arguments": args,
        "ok": bool(outcome.get("ok", True)),
        "result": outcome.get("result"),
        "error": outcome.get("error"),
    }


def _run_tool(name: str, args: Dict[str, Any], steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    outcome = tool_pkg.call_tool(name, args)
    steps.append(_tool_step(name, args, outcome))
    return outcome


class Agent:
    """知行智能体。每个实例绑定一个会话，天然具备多轮记忆。"""

    def __init__(self, session_id: str = "default"):
        self.memory = SessionMemory(session_id)
        self.session_id = self.memory.session_id
        self.last_error: str | None = None

    # ------------------------------------------------------------------
    # 对外唯一入口
    # ------------------------------------------------------------------
    def run(self, user_input: str) -> Dict[str, Any]:
        user_input = (user_input or "").strip()
        if not user_input:
            return {"reply": "我在，请说说需要我做什么？", "steps": [], "mode": "noop", "error": None}

        steps: List[Dict[str, Any]] = []
        self.last_error = None
        self.memory.append("user", user_input)

        if config.llm_enabled():
            try:
                reply = self._run_llm(steps)
                mode = "llm"
            except LLMError as exc:
                self.last_error = str(exc)
                reply = self._run_rules(user_input, steps)
                mode = "rules-fallback"
        else:
            reply = self._run_rules(user_input, steps)
            mode = "rules"

        self.memory.append("assistant", reply, steps=steps, mode=mode)
        return {
            "reply": reply,
            "steps": steps,
            "mode": mode,
            "error": self.last_error,
            "session_id": self.session_id,
            "turn_count": self.memory.turn_count(),
        }

    # ------------------------------------------------------------------
    # 模式一：大模型 function calling
    # ------------------------------------------------------------------
    def _run_llm(self, steps: List[Dict[str, Any]]) -> str:
        schemas = tool_pkg.openai_tools_schema()
        messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self.memory.history())

        for _ in range(config.MAX_TOOL_ROUNDS):
            message = chat_completion(messages, schemas)
            tool_calls = message.get("tool_calls") or []

            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    **({"tool_calls": tool_calls} if tool_calls else {}),
                }
            )

            if not tool_calls:
                content = (message.get("content") or "").strip()
                return content or "（模型没有返回内容，请再说一次）"

            for call in tool_calls:
                function = call.get("function") or {}
                name = function.get("name") or ""
                raw_args = function.get("arguments") or "{}"
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args) if raw_args.strip() else {}
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = raw_args if isinstance(raw_args, dict) else {}

                outcome = _run_tool(name, args, steps)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": json.dumps(outcome, ensure_ascii=False, default=str),
                    }
                )

        return "这个任务需要来回好几步，我先停一下。你可以把需求拆得更具体一点，我们一步步来完成。"

    # ------------------------------------------------------------------
    # 模式二：规则兜底（无 API Key 也能完整演示）
    # ------------------------------------------------------------------
    def _run_rules(self, text: str, steps: List[Dict[str, Any]]) -> str:
        decision = _rule_route(text)
        if decision is None:
            return _HELP_REPLY

        name, args = decision
        outcome = _run_tool(name, args, steps)
        if not outcome.get("ok"):
            return f"执行「{name}」时出了问题：{outcome.get('error') or outcome.get('result')}"
        return _render_rule_reply(name, args, outcome.get("result") or {})


# ----------------------------------------------------------------------
# 规则路由
# ----------------------------------------------------------------------
_WEATHER_KEYS = ("天气", "气温", "温度", "下雨", "降雨", "冷不冷", "热不热", "穿什么", "带伞", "出行建议")
_EXPORT_KEYS = ("导出", "保存成", "保存为", "写成文件", "生成文件", "存成", "落盘", "整理成文件")
_FILE_LIST_KEYS = ("有哪些文件", "文件列表", "列一下文件", "看看文件", "我的文件", "都有什么文件")
_DONE_KEYS = ("完成", "做完了", "搞定了", "已办", "办完了")
_REMOVE_KEYS = ("删除", "删掉", "取消任务", "去掉这条", "移除")
_READ_KEYS = ("读", "打开", "查看文件", "看一下文件", "显示文件")

# ---- 待办域：查询与新增必须严格区分，否则「现在有什么待办」会被误建成待办 ----
# 只要出现以下任一词，就说明用户在聊待办
_TODO_DOMAIN_KEYS = ("待办", "任务", "清单", "todo", "to-do")

# 强疑问信号：命中即判定为「查询」，优先级高于一切写操作
_QUERY_HINTS = ("什么", "哪些", "多少", "几个", "有没有", "查看", "看看", "看下", "看一下",
                "列出", "列一下", "显示", "还有什么", "还有哪些", "情况", "怎么样", "咋样",
                "如何", "要做", "进度")

# 弱信号：单独出现时倾向「查询」，但会被明确的写入动词覆盖
# 例：「待办清单」→ 查询；「帮我记一下购物清单」→ 新增
_WEAK_QUERY_KEYS = ("清单", "列表", "待办", "任务")

# 明确的写入动词：没有这些词，绝不新增待办
_ADD_VERBS = ("记一下", "记一条", "记个", "再记", "记录一下", "记录", "提醒我", "帮我记",
              "帮我加", "新增", "添加", "加个任务", "加一条", "加上", "顺便记", "也记",
              "别忘了", "安排", "计划", "规划", "待办事项")

_HELP_REPLY = (
    "我是**知行 ZhiXing**，会说也会做。目前能帮你办这几件事：\n\n"
    "1. **待办管理** —— “帮我记一下明天下午交实验报告” / “现在有什么待办”\n"
    "2. **天气与出行** —— “杭州明天天气怎么样，要带伞吗”\n"
    "3. **文件处理** —— “把待办清单导出成 Markdown 文件” / “列一下我的文件”\n"
    "4. **计算与时间** —— “算一下 128*37+56” / “今天几号了”\n\n"
    "直接说需求就行，我会自己决定该调用哪个工具。"
)


def _priority_of(text: str) -> str:
    if re.search(r"(高优先|优先级\s*[:：]?\s*(?:是)?\s*高|优先\s*高|紧急|重要|很急|马上|p0|high)", text, re.IGNORECASE):
        return "high"
    if re.search(r"(低优先|优先级\s*[:：]?\s*(?:是)?\s*低|优先\s*低|不急|随便|有空|low)", text, re.IGNORECASE):
        return "low"
    return "normal"


_LEAD_PATTERN = (
    r"^(帮我|请|麻烦|再|顺便|也|然后)?\s*"
    r"(记一下|记录一下|记录|记一条|记个|提醒我|新增|添加一条|添加|帮我加|加个任务|加一条|加上|安排一下|安排)"
    r"\s*[:：,，。]?\s*"
)


def _strip_lead(text: str) -> str:
    cleaned = re.sub(_LEAD_PATTERN, "", text).strip(" ：:,，。")
    return cleaned or text


def _is_question(text: str) -> bool:
    """待办正文如果是问句，说明用户其实是在提问，不该被建成待办。"""
    body = (text or "").strip()
    if body.endswith(("?", "？")):
        return True
    # 极短的纯疑问短语，例如“有什么待办”“哪些任务”
    return len(body) <= 10 and any(hint in body for hint in _QUERY_HINTS)


def _rule_route(text: str) -> Tuple[str, Dict[str, Any]] | None:
    raw = (text or "").strip()
    if not raw:
        return None

    if any(k in raw for k in _WEATHER_KEYS):
        return "weather_query", {"city": weather_tools.resolve_city(raw) or "北京"}

    if any(k in raw for k in _FILE_LIST_KEYS):
        return "file_list", {}

    if any(k in raw for k in _EXPORT_KEYS):
        path = "待办清单.md" if any(k in raw for k in ("待办", "任务", "清单")) else "知行记录.md"
        content = (
            todo_tools.todos_as_markdown()
            if path == "待办清单.md"
            else f"# 知行记录\n\n> 原始需求：{raw}\n"
        )
        return "file_write", {"path": path, "content": content}

    if any(k in raw for k in _READ_KEYS) and ("文件" in raw or re.search(r"\.(md|txt|json|csv)", raw)):
        match = re.search(r"([\w\u4e00-\u9fa5\-/]+\.(?:md|txt|json|csv))", raw)
        if match:
            return "file_read", {"path": match.group(1)}

    # ---------- 待办域：查询与新增必须严格区分 ----------
    # 教训：「现在有什么待办」里的“待办”若只按关键词匹配新增，就会凭空建出一条
    # 叫「现在有什么待办」的垃圾待办。所以判定顺序必须是：
    # 强查询 > 删除 > 完成 > 新增 > 弱查询。
    # 另外「删除/完成」只有在带序号（第2条、#3）时才算待办操作，
    # 避免「删除文件 a.md」被误判成删待办。
    has_index = bool(re.search(r"#\s*\d+|\d+\s*条|\d+\s*号", raw))
    in_todo_domain = (
        any(k in raw for k in _TODO_DOMAIN_KEYS)
        or any(k in raw for k in _ADD_VERBS)
        or (has_index and (any(k in raw for k in _REMOVE_KEYS) or any(k in raw for k in _DONE_KEYS)))
    )
    if in_todo_domain:
        # 1) 强疑问信号 → 一律走查询，绝不新增
        if any(k in raw for k in _QUERY_HINTS):
            return "todo_list", {}

        # 2) 删除
        if any(k in raw for k in _REMOVE_KEYS):
            match = re.search(r"#?\s*(\d+)", raw)
            return "todo_remove", {"todo_id": match.group(1) if match else raw}

        # 3) 标记完成
        if any(k in raw for k in _DONE_KEYS):
            match = re.search(r"#?\s*(\d+)", raw)
            if match:
                return "todo_done", {"todo_id": match.group(1)}

        # 4) 新增：必须同时有明确写入动词，且内容不能是问句
        if any(k in raw for k in _ADD_VERBS):
            body = todo_tools.strip_meta(_strip_lead(raw))
            if body and not _is_question(body):
                return "todo_add", {
                    "text": body,
                    "due": todo_tools.resolve_due(raw),
                    "priority": _priority_of(raw),
                }

        # 5) 只有弱信号（如“待办清单”）→ 当查询处理
        if any(k in raw for k in _WEAK_QUERY_KEYS):
            return "todo_list", {}

        # 6) 既不是查询也不是明确的新增 → 不猜，交给默认回复引导用户说清楚
        return None

    if any(k in raw for k in ("计算", "算一下", "算算", "等于多少", "是多少")) or re.fullmatch(
        r"[\d\s.+\-*/()%×÷^]+", raw
    ):
        expression = re.sub(r"(帮我|请|计算一下|计算|算一下|算算|等于多少|是多少|结果|等于)", "", raw)
        expression = expression.strip(" \t?？=＝")
        if expression:
            return "calculator", {"expression": expression}

    if any(k in raw for k in ("几点", "几号", "今天", "日期", "时间", "星期")):
        return "current_time", {}

    return None


def _render_rule_reply(name: str, args: Dict[str, Any], result: Dict[str, Any]) -> str:
    if name == "weather_query":
        lines = [
            f"**{result.get('city', args.get('city', ''))}天气**",
            "",
            f"- 实况：{result['current']['desc']}，{result['current']['temp']}℃（体感 {result['current']['feels_like']}℃）",
            f"- 湿度 {result['current']['humidity']}% · 风速 {result['current']['wind']} km/h {result['current'].get('wind_dir', '')}",
            "",
            "**未来三天**",
            "",
            "| 日期 | 天气 | 气温 | 降雨概率 |",
            "|------|------|------|----------|",
        ]
        for day in result.get("forecast", []):
            lines.append(
                f"| {day['date']} | {day['desc']} | {day['min']}~{day['max']}℃ | {day['rain_chance']}% |"
            )
        lines += ["", f"> {result.get('advice', '')}", "", f"_数据来源：{result.get('source', '未知')}_"]
        return "\n".join(lines)

    if name == "todo_add":
        item = result.get("added", {})
        return (
            f"已经记下了 ✅\n\n"
            f"- 内容：**{item.get('text', '')}**\n"
            f"- 编号：#{item.get('id')}\n"
            f"- 优先级：{item.get('priority')}\n"
            f"- 截止：{item.get('due') or '未设置'}\n\n"
            f"当前还有 **{result.get('total_pending', 0)}** 条待办未完成。"
        )

    if name == "todo_list":
        return result.get("markdown", "暂无待办。")

    if name in ("todo_done", "todo_remove"):
        return result.get("message", "操作完成。")

    if name == "file_write":
        return (
            f"已保存到沙箱文件：`{result.get('path')}`（{result.get('action')}，{result.get('bytes')} 字节）\n\n"
            f"内容预览：\n\n```\n{(result.get('preview') or '')[:300]}\n```"
        )

    if name == "file_read":
        return f"`{result.get('path')}` 共 {result.get('chars')} 字符" + (
            "（已截断）" if result.get("truncated") else ""
        ) + f"：\n\n```\n{result.get('content', '')}\n```"

    if name == "file_list":
        return f"沙箱目录下共 {result.get('count', 0)} 个文件：\n\n{result.get('markdown', '')}"

    if name == "calculator":
        return f"计算完成：**{result.get('message', '')}**"

    if name == "current_time":
        return (
            f"现在是 **{result.get('date')} {result.get('weekday')}**，时间 {result.get('datetime')}\n\n"
            f"- 明天：{result.get('tomorrow')}\n- 一周后：{result.get('week_later')}"
        )

    return json.dumps(result, ensure_ascii=False, default=str)


def available_tools() -> List[str]:
    return tool_pkg.tool_names()
