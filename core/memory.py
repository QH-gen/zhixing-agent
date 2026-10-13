"""多轮对话记忆（加分项 1）。

两层设计：
* records —— 完整记录，含工具调用轨迹，仅供前端回显；
* history() —— 干净的 user/assistant 交替消息，供大模型消费。

工具调用过程中的中间消息一律不写入长期记忆，避免会话被截断时
出现「有 tool 消息、没有对应 assistant.tool_calls」的非法序列。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import config


def _safe_id(session_id: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_\-]", "_", str(session_id or "default"))[:60]
    return cleaned or "default"


class SessionMemory:
    def __init__(self, session_id: str = "default", max_records: int | None = None):
        self.session_id = _safe_id(session_id)
        self.max_records = max_records or config.MEMORY_TURNS
        self.path: Path = config.SESSION_DIR / f"{self.session_id}.json"
        self.records: List[Dict[str, Any]] = self._load()

    # ---------- 持久化 ----------
    def _load(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            records = payload.get("records", []) if isinstance(payload, dict) else payload
            return records if isinstance(records, list) else []
        except json.JSONDecodeError:
            return []

    def _flush(self) -> None:
        payload = {
            "session_id": self.session_id,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "turn_count": len([r for r in self.records if r.get("role") == "user"]),
            "records": self.records[-200:],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 读写 ----------
    def append(self, role: str, content: str, steps: List[Dict[str, Any]] | None = None,
               mode: str = "") -> Dict[str, Any]:
        record = {
            "role": role,
            "content": content,
            "ts": datetime.now().strftime("%H:%M:%S"),
        }
        if steps:
            record["steps"] = steps
        if mode:
            record["mode"] = mode
        self.records.append(record)
        self._flush()
        return record

    def history(self, turns: int | None = None) -> List[Dict[str, str]]:
        """返回最近 N 轮、role 只有 user/assistant 的干净消息列表。"""
        limit = (turns or self.max_records) * 2
        clean = [
            {"role": r["role"], "content": r.get("content") or ""}
            for r in self.records
            if r.get("role") in ("user", "assistant")
        ]
        return clean[-limit:]

    def turn_count(self) -> int:
        return len([r for r in self.records if r.get("role") == "user"])

    def clear(self) -> None:
        self.records = []
        self._flush()

    def summary(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_count": self.turn_count(),
            "records": len(self.records),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    @staticmethod
    def list_sessions() -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for file in sorted(config.SESSION_DIR.glob("*.json")):
            try:
                payload = json.loads(file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            result.append(
                {
                    "session_id": payload.get("session_id", file.stem),
                    "turn_count": payload.get("turn_count", 0),
                    "updated_at": payload.get("updated_at", ""),
                }
            )
        return result
