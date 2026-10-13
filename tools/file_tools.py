"""文件处理工具：体现智能体「会做」——真正落到磁盘上的副作用。

安全设计：所有文件操作被强制限制在 storage/workspace 沙箱目录内，
通过 resolve() + 前缀校验阻断 `../` 路径穿越，避免智能体误改用户文件。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import config
from .registry import tool

SANDBOX = config.WORKSPACE_DIR


def _resolve(relative_path: str) -> Path:
    if not relative_path or not str(relative_path).strip():
        raise ValueError("路径不能为空")
    candidate = (SANDBOX / str(relative_path).strip()).resolve()
    root = SANDBOX.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("路径越界：仅允许操作 storage/workspace 目录内的文件")
    return candidate


@tool(
    name="file_write",
    description="在沙箱目录 storage/workspace 内创建或修改文本文件。用户说“导出”“保存成文件”“写个 Markdown”时调用。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对路径，例如“待办清单.md”“notes/周报.md”"},
            "content": {"type": "string", "description": "文件内容（纯文本或 Markdown）"},
            "append": {"type": "boolean", "description": "true 表示追加而不是覆盖，默认 false"},
        },
        "required": ["path", "content"],
    },
)
def file_write(path: str, content: str, append: bool = False) -> Dict[str, Any]:
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    mode = "a" if append else "w"
    with target.open(mode, encoding="utf-8") as handle:
        handle.write(content if content is not None else "")
    size = target.stat().st_size
    return {
        "path": str(target.relative_to(SANDBOX)).replace("\\", "/"),
        "action": "已追加" if append else ("已覆盖" if existed else "已新建"),
        "bytes": size,
        "preview": (content or "")[:200],
        "message": f"{'追加' if append else '写入'}成功：{target.name}（{size} 字节）",
    }


@tool(
    name="file_read",
    description="读取沙箱目录 storage/workspace 内的文本文件内容。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对路径，例如“待办清单.md”"},
            "max_chars": {"type": "integer", "description": "最多读取字符数，默认 2000"},
        },
        "required": ["path"],
    },
)
def file_read(path: str, max_chars: int = 2000) -> Dict[str, Any]:
    target = _resolve(path)
    if not target.exists():
        return {"ok": False, "message": f"文件不存在：{path}。可先调用 file_list 查看已有文件。"}
    text = target.read_text(encoding="utf-8", errors="ignore")
    limit = max(100, int(max_chars or 2000))
    return {
        "path": str(target.relative_to(SANDBOX)).replace("\\", "/"),
        "chars": len(text),
        "truncated": len(text) > limit,
        "content": text[:limit],
    }


@tool(
    name="file_list",
    description="列出沙箱目录 storage/workspace 内的文件清单。",
    parameters={
        "type": "object",
        "properties": {
            "subdir": {"type": "string", "description": "子目录，留空表示根目录"},
        },
        "required": [],
    },
)
def file_list(subdir: str = "") -> Dict[str, Any]:
    root = _resolve(subdir) if subdir else SANDBOX
    if not root.exists():
        return {"ok": False, "message": f"目录不存在：{subdir}"}
    files: List[Dict[str, Any]] = []
    for item in sorted(root.rglob("*")):
        if not item.is_file():
            continue
        relative = item.relative_to(SANDBOX)
        # 跳过 .gitkeep 之类的隐藏占位文件，避免干扰用户
        if any(part.startswith(".") for part in relative.parts):
            continue
        files.append(
            {
                "path": str(relative).replace("\\", "/"),
                "bytes": item.stat().st_size,
            }
        )
    return {
        "count": len(files),
        "files": files,
        "markdown": "\n".join(f"- `{f['path']}`（{f['bytes']} 字节）" for f in files) or "_暂无文件_",
    }
