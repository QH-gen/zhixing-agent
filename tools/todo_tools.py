"""待办管理工具：智能体的「记忆型行动」能力。

数据落在 storage/todos.json，结构：
[{"id": 1, "text": "...", "due": "2026-10-15", "priority": "high",
  "status": "pending", "created_at": "2026-10-13 22:10:01"}]
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List

import config
from .registry import tool

PRIORITY_LABEL = {"high": "高", "normal": "中", "low": "低"}
PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}


def _load() -> List[Dict[str, Any]]:
    if not config.TODO_FILE.exists():
        return []
    try:
        data = json.loads(config.TODO_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _save(items: List[Dict[str, Any]]) -> None:
    config.TODO_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _next_id(items: List[Dict[str, Any]]) -> int:
    return max((int(i.get("id", 0)) for i in items), default=0) + 1


def _normalize_priority(value: str) -> str:
    value = (value or "").strip().lower()
    mapping = {
        "high": "high", "高": "high", "紧急": "high", "重要": "high", "p0": "high",
        "low": "low", "低": "low", "不急": "low",
        "normal": "normal", "中": "normal", "普通": "normal", "medium": "normal",
    }
    return mapping.get(value, "normal")


def _find(items: List[Dict[str, Any]], todo_id: Any) -> Dict[str, Any] | None:
    try:
        target = int(todo_id)
    except (TypeError, ValueError):
        # 也支持用文本模糊匹配，方便自然语言调用
        keyword = str(todo_id).strip()
        for item in items:
            if keyword and keyword in item.get("text", ""):
                return item
        return None
    for item in items:
        if int(item.get("id", 0)) == target:
            return item
    return None


def _format(items: List[Dict[str, Any]], title: str) -> str:
    if not items:
        return f"{title}：暂无记录。"
    lines = [f"{title}（共 {len(items)} 条）："]
    for item in items:
        mark = "x" if item.get("status") == "done" else " "
        due = f" · 截止 {item['due']}" if item.get("due") else ""
        pr = PRIORITY_LABEL.get(item.get("priority", "normal"), "中")
        lines.append(f"- [{mark}] #{item['id']} {item['text']}（优先级：{pr}{due}）")
    return "\n".join(lines)


@tool(
    name="todo_add",
    description="新增一条待办事项。当用户说“记一下”“提醒我”“帮我加个任务”时调用。",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "待办内容，例如“交软件工程实验报告”"},
            "due": {"type": "string", "description": "截止时间，建议格式 YYYY-MM-DD；不确定就留空"},
            "priority": {
                "type": "string",
                "enum": ["high", "normal", "low"],
                "description": "优先级，默认 normal",
            },
        },
        "required": ["text"],
    },
)
def todo_add(text: str, due: str = "", priority: str = "normal") -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("待办内容不能为空")
    items = _load()
    item = {
        "id": _next_id(items),
        "text": text,
        "due": (due or "").strip(),
        "priority": _normalize_priority(priority),
        "status": "pending",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    items.append(item)
    _save(items)
    return {
        "added": item,
        "total_pending": len([i for i in items if i.get("status") != "done"]),
        "message": f"已添加待办 #{item['id']}：{text}",
    }


@tool(
    name="todo_list",
    description="查看待办清单。当用户询问“我有哪些任务”“看看待办”时调用。",
    parameters={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pending", "done", "all"],
                "description": "筛选状态，默认 pending（未完成）",
            }
        },
        "required": [],
    },
)
def todo_list(status: str = "pending") -> Dict[str, Any]:
    items = _load()
    status = (status or "pending").strip().lower()
    if status == "pending":
        view = [i for i in items if i.get("status") != "done"]
        label = "未完成待办"
    elif status == "done":
        view = [i for i in items if i.get("status") == "done"]
        label = "已完成待办"
    else:
        view = list(items)
        label = "全部待办"
    view.sort(key=lambda i: (PRIORITY_ORDER.get(i.get("priority", "normal"), 1), i.get("due") or "9999"))
    return {
        "count": len(view),
        "items": view,
        "markdown": _format(view, label),
        "hint": "如需导出到文件，可调用 file_write 写入待办清单.md",
    }


@tool(
    name="todo_done",
    description="把某条待办标记为已完成。需要用户给出待办编号或关键词。",
    parameters={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string", "description": "待办编号（如 3）或内容关键词"},
        },
        "required": ["todo_id"],
    },
)
def todo_done(todo_id: str) -> Dict[str, Any]:
    items = _load()
    item = _find(items, todo_id)
    if item is None:
        return {"ok": False, "message": f"没找到待办「{todo_id}」，请先用 todo_list 查看清单。"}
    item["status"] = "done"
    item["done_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save(items)
    return {"message": f"已完成待办 #{item['id']}：{item['text']}", "item": item}


@tool(
    name="todo_remove",
    description="删除某条待办事项（误记录或已作废时使用）。",
    parameters={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string", "description": "待办编号（如 3）或内容关键词"},
        },
        "required": ["todo_id"],
    },
)
def todo_remove(todo_id: str) -> Dict[str, Any]:
    items = _load()
    item = _find(items, todo_id)
    if item is None:
        return {"ok": False, "message": f"没找到待办「{todo_id}」，请先用 todo_list 查看清单。"}
    items = [i for i in items if int(i.get("id", 0)) != int(item["id"])]
    _save(items)
    return {"message": f"已删除待办 #{item['id']}：{item['text']}"}


def todos_as_markdown() -> str:
    """供 file_tools 导出使用。"""
    items = _load()
    pending = sorted(
        [i for i in items if i.get("status") != "done"],
        key=lambda i: (PRIORITY_ORDER.get(i.get("priority", "normal"), 1), i.get("due") or "9999"),
    )
    done = [i for i in items if i.get("status") == "done"]
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 我的待办清单",
        "",
        f"> 由「知行 ZhiXing」智能体于 {stamp} 自动生成",
        "",
        f"## 未完成（{len(pending)} 条）",
        "",
    ]
    if pending:
        lines += [
            "| # | 事项 | 优先级 | 截止 |",
            "|---|------|--------|------|",
        ]
        for i in pending:
            lines.append(
                f"| {i['id']} | {i['text']} | {PRIORITY_LABEL.get(i.get('priority','normal'),'中')} | {i.get('due') or '—'} |"
            )
    else:
        lines.append("_全部完成，好耶。_")
    lines += ["", f"## 已完成（{len(done)} 条）", ""]
    if done:
        for i in done:
            lines.append(f"- ~~{i['text']}~~（{i.get('done_at', '')}）")
    else:
        lines.append("_暂无_")
    lines.append("")
    return "\n".join(lines)


WEEKDAY_ZH = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
              "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6}


def resolve_due(text: str) -> str:
    """把自然语言里的时间表达解析为 YYYY-MM-DD。

    支持：2026-10-15 / 2026年10月15日 / 10月15日 / 今天 / 明天 / 后天 /
    大后天 / 周三 / 星期三 / 下周三。解析不出来就返回空字符串，
    由调用方（大模型）决定是否追问。
    """
    text = text or ""
    now = datetime.now()

    match = re.search(r"(\d{4})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})", text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    match = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", text)
    if match:
        return f"{now.year}-{int(match.group(1)):02d}-{int(match.group(2)):02d}"

    offset = None
    if "大后天" in text:
        offset = 3
    elif "后天" in text:
        offset = 2
    elif "明天" in text or "明日" in text:
        offset = 1
    elif "今天" in text or "今日" in text or "今晚" in text:
        offset = 0

    if offset is None:
        # 注意：必须用负向后顾排除「记一下周三」里的“下”。
        # 否则 "一下周三" 会被误读成 "下周三"，日期整整差一周。
        pattern = (
            r"(?:(?<![一以留剩了过再])(下|本|这)(?:个)?)?"
            r"(?:周|星期|礼拜)\s*([一二三四五六日天1-7])"
        )
        match = re.search(pattern, text)
        if not match:
            return ""
        prefix = match.group(1) or ""
        target = WEEKDAY_ZH.get(match.group(2))
        if target is None:
            return ""
        if prefix == "下":
            # 「下周三」= 下周的周三：先到下一个周一，再加星期偏移
            offset = (7 - now.weekday()) + target
        else:
            # 「周三」「本周三」= 距今最近的那个周三
            offset = (target - now.weekday()) % 7

    return (now + timedelta(days=offset)).strftime("%Y-%m-%d")


_META_PATTERNS = (
    r"[,，;；、]?\s*优先级\s*[:：]?\s*(?:是)?\s*(?:高|中|低|普通|紧急|重要|normal|high|low)",
    r"[,，;；、]?\s*(?:高|中|低|紧急|重要)\s*优先级",
    r"[,，;；、]?\s*(?:要|标记为|标为)\s*(?:高|中|低)\s*",
)


def strip_meta(text: str) -> str:
    """从待办正文里剔除“优先级高”这类元信息，让清单更干净。"""
    cleaned = text or ""
    for pattern in _META_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" ，,。;；、:：")
