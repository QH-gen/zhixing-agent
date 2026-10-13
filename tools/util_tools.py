"""通用工具：计算器与当前时间。

计算器用 ast 白名单求值，不使用 eval，避免任意代码执行；
当前时间工具让模型能正确理解“今天/明天/这周”等相对时间。
"""
from __future__ import annotations

import ast
import math
import operator
from datetime import datetime, timedelta
from typing import Any, Dict

from .registry import tool

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_ALLOWED_NAMES = {"pi": math.pi, "e": math.e, "abs": abs, "round": round,
                  "sqrt": math.sqrt, "log": math.log, "sin": math.sin, "cos": math.cos}
_MAX_POWER = 1000


def _eval(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("只支持数字常量")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_POWER:
            raise ValueError("指数过大，已拒绝计算")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Name) and node.id in _ALLOWED_NAMES:
        return _ALLOWED_NAMES[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_NAMES:
        if not callable(_ALLOWED_NAMES[node.func.id]):
            raise ValueError("该名称不可调用")
        return _ALLOWED_NAMES[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError("表达式包含不支持的语法")


@tool(
    name="calculator",
    description="计算数学表达式，例如“128*37+56”“sqrt(144)”。当用户需要算术、百分比、单位换算时调用。",
    parameters={
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "数学表达式，仅支持 + - * / // % ** 与括号、sqrt/log/sin/cos/pi/e"},
        },
        "required": ["expression"],
    },
)
def calculator(expression: str) -> Dict[str, Any]:
    expr = (expression or "").strip().replace("^", "**").replace("×", "*").replace("÷", "/")
    if not expr:
        raise ValueError("表达式不能为空")
    if len(expr) > 200:
        raise ValueError("表达式过长")
    tree = ast.parse(expr, mode="eval")
    value = _eval(tree)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return {"expression": expr, "result": value, "message": f"{expr} = {value}"}


@tool(
    name="current_time",
    description="获取当前日期、时间与星期。处理“今天/明天/这周”等相对时间前应先调用。",
    parameters={"type": "object", "properties": {}, "required": []},
)
def current_time() -> Dict[str, Any]:
    now = datetime.now()
    weekday = "一二三四五六日"[now.weekday()]
    return {
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "weekday": f"星期{weekday}",
        "tomorrow": (now + timedelta(days=1)).strftime("%Y-%m-%d"),
        "week_later": (now + timedelta(days=7)).strftime("%Y-%m-%d"),
        "iso_year_week": now.strftime("%G-W%V"),
    }
