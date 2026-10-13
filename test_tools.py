"""工具层与智能体的自动化测试。

    python -m unittest test_tools -v

测试不依赖网络（天气用例允许离线兜底），也不依赖大模型 Key。
"""
from __future__ import annotations

import json
import shutil
import unittest
from datetime import datetime, timedelta

import config
from core.agent import Agent
from core.memory import SessionMemory
from tools import call_tool, tool_names, todo_tools

SANDBOX = config.WORKSPACE_DIR


class ToolRegistryTest(unittest.TestCase):
    def test_all_tools_registered(self):
        expected = {
            "todo_add", "todo_list", "todo_done", "todo_remove",
            "weather_query",
            "file_write", "file_read", "file_list",
            "calculator", "current_time",
        }
        self.assertEqual(expected, set(tool_names()))

    def test_unknown_tool_returns_error_not_exception(self):
        outcome = call_tool("not_exist_tool", {})
        self.assertFalse(outcome["ok"])
        self.assertIn("未知工具", outcome["error"])

    def test_bad_arguments_are_caught(self):
        outcome = call_tool("calculator", {"wrong_param": 1})
        self.assertFalse(outcome["ok"])


class CalculatorTest(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(call_tool("calculator", {"expression": "128*37+56"})["result"]["result"], 4792)

    def test_functions_and_constants(self):
        self.assertEqual(call_tool("calculator", {"expression": "sqrt(144)"})["result"]["result"], 12)

    def test_rejects_malicious_expression(self):
        outcome = call_tool("calculator", {"expression": "__import__('os').system('echo hi')"})
        self.assertFalse(outcome["ok"])


class TodoTest(unittest.TestCase):
    def setUp(self):
        self.backup = config.TODO_FILE.read_text(encoding="utf-8") if config.TODO_FILE.exists() else None
        config.TODO_FILE.write_text("[]", encoding="utf-8")

    def tearDown(self):
        if self.backup is None:
            config.TODO_FILE.unlink(missing_ok=True)
        else:
            config.TODO_FILE.write_text(self.backup, encoding="utf-8")

    def test_add_list_done_remove(self):
        added = call_tool("todo_add", {"text": "交实验报告", "priority": "high"})["result"]
        self.assertEqual(added["added"]["priority"], "high")
        todo_id = added["added"]["id"]

        listed = call_tool("todo_list", {"status": "pending"})["result"]
        self.assertEqual(listed["count"], 1)

        done = call_tool("todo_done", {"todo_id": str(todo_id)})["result"]
        self.assertIn("已完成", done["message"])

        self.assertEqual(call_tool("todo_list", {"status": "pending"})["result"]["count"], 0)
        call_tool("todo_remove", {"todo_id": str(todo_id)})
        self.assertEqual(call_tool("todo_list", {"status": "all"})["result"]["count"], 0)


class FileSandboxTest(unittest.TestCase):
    def tearDown(self):
        shutil.rmtree(SANDBOX / "_test", ignore_errors=True)

    def test_write_read_list(self):
        call_tool("file_write", {"path": "_test/sample.md", "content": "# hello"})
        read = call_tool("file_read", {"path": "_test/sample.md"})["result"]
        self.assertIn("hello", read["content"])
        listing = call_tool("file_list", {"subdir": "_test"})["result"]
        self.assertGreaterEqual(listing["count"], 1)

    def test_path_traversal_is_blocked(self):
        outcome = call_tool("file_write", {"path": "../../evil.txt", "content": "x"})
        self.assertFalse(outcome["ok"])
        self.assertIn("越界", str(outcome.get("error")))


class WeatherTest(unittest.TestCase):
    def test_returns_structured_data(self):
        result = call_tool("weather_query", {"city": "杭州"})["result"]
        self.assertEqual(result["city"], "杭州")
        self.assertIn("current", result)
        self.assertIsInstance(result["forecast"], list)
        self.assertTrue(result["advice"])


class MemoryTest(unittest.TestCase):
    def test_persist_and_reload(self):
        memory = SessionMemory("unittest-memory")
        memory.clear()
        memory.append("user", "你好")
        memory.append("assistant", "你好，我是知行")
        reloaded = SessionMemory("unittest-memory")
        self.assertEqual(reloaded.turn_count(), 1)
        self.assertEqual(len(reloaded.history()), 2)
        self.assertEqual(reloaded.history()[0]["role"], "user")
        reloaded.clear()


class DueParsingTest(unittest.TestCase):
    """相对时间解析：让规则模式也能理解“周三”“明天”。"""

    def test_absolute_date(self):
        self.assertEqual(todo_tools.resolve_due("2026-10-15 交报告"), "2026-10-15")

    def test_chinese_date(self):
        self.assertEqual(todo_tools.resolve_due("10月20日交报告"), "2026-10-20")

    def test_relative_days(self):
        today = datetime.now()
        self.assertEqual(todo_tools.resolve_due("明天开会"), (today + timedelta(days=1)).strftime("%Y-%m-%d"))
        self.assertEqual(todo_tools.resolve_due("后天交作业"), (today + timedelta(days=2)).strftime("%Y-%m-%d"))

    def test_weekday(self):
        expected = (datetime.now() + timedelta(days=(2 - datetime.now().weekday()) % 7)).strftime("%Y-%m-%d")
        self.assertEqual(todo_tools.resolve_due("周三下午交报告"), expected)

    def test_de_xia_zhou_is_not_next_week(self):
        """回归：'帮我记一下周三...' 里的 '一下周三' 不能被误读成 '下周三'。"""
        today = datetime.now()
        expected = (today + timedelta(days=(2 - today.weekday()) % 7)).strftime("%Y-%m-%d")
        self.assertEqual(todo_tools.resolve_due("帮我记一下周三下午交实验报告"), expected)
        self.assertEqual(todo_tools.resolve_due("帮我记一下：周三下午交实验报告"), expected)

    def test_next_week_prefix(self):
        today = datetime.now()
        expected = (today + timedelta(days=(7 - today.weekday()) + 2)).strftime("%Y-%m-%d")
        self.assertEqual(todo_tools.resolve_due("下周三交报告"), expected)

    def test_no_time_expression(self):
        self.assertEqual(todo_tools.resolve_due("买牛奶"), "")

    def test_strip_meta(self):
        self.assertEqual(todo_tools.strip_meta("周三交报告，优先级高"), "周三交报告")


class IntentDisambiguationTest(unittest.TestCase):
    """回归：查询意图绝不能被误判成新增。

    背景：曾有 bug —— 用户问「现在有什么待办」，因为“待办”同时是新增关键词，
    智能体凭空建出一条叫「现在有什么待办」的垃圾待办。
    """

    QUERY_PHRASES = [
        "现在有什么待办", "我有什么待办", "有没有待办", "查看待办",
        "看看我的待办清单", "待办有哪些", "还有什么任务", "我的任务有哪些",
        "待办清单", "我的任务",
    ]

    ADD_PHRASES = [
        "帮我记一下明天开会", "再记一条：买牛奶", "加一条 交实验报告",
        "别忘了我周五要交作业", "帮我记一下购物清单",
    ]

    def setUp(self):
        self.backup = config.TODO_FILE.read_text(encoding="utf-8") if config.TODO_FILE.exists() else None
        config.TODO_FILE.write_text("[]", encoding="utf-8")
        self.agent = Agent("unittest-intent")
        self.agent.memory.clear()

    def tearDown(self):
        if self.backup is None:
            config.TODO_FILE.unlink(missing_ok=True)
        else:
            config.TODO_FILE.write_text(self.backup, encoding="utf-8")

    def test_query_phrases_route_to_list_and_create_nothing(self):
        for phrase in self.QUERY_PHRASES:
            with self.subTest(phrase=phrase):
                self.agent.memory.clear()
                config.TODO_FILE.write_text("[]", encoding="utf-8")
                result = self.agent.run(phrase)
                self.assertEqual(result["steps"][0]["tool"], "todo_list", f"「{phrase}」应走查询")
                total = call_tool("todo_list", {"status": "all"})["result"]["count"]
                self.assertEqual(total, 0, f"「{phrase}」不应新增任何待办，实际新增了 {total} 条")

    def test_add_phrases_still_add(self):
        for phrase in self.ADD_PHRASES:
            with self.subTest(phrase=phrase):
                self.agent.memory.clear()
                config.TODO_FILE.write_text("[]", encoding="utf-8")
                result = self.agent.run(phrase)
                self.assertEqual(result["steps"][0]["tool"], "todo_add", f"「{phrase}」应走新增")
                self.assertEqual(call_tool("todo_list", {"status": "all"})["result"]["count"], 1)

    def test_question_shaped_todo_is_rejected(self):
        result = self.agent.run("记一下：还有什么没做？")
        # 命中强疑问信号「什么」，应走查询而非新增
        self.assertEqual(result["steps"][0]["tool"], "todo_list")


class RuleAgentTest(unittest.TestCase):
    """无 API Key 时，规则模式也必须能正确路由到工具。"""

    def setUp(self):
        self.agent = Agent("unittest-agent")
        self.agent.memory.clear()

    def test_weather_routing(self):
        result = self.agent.run("北京今天天气怎么样？")
        self.assertTrue(result["steps"])
        self.assertEqual(result["steps"][0]["tool"], "weather_query")

    def test_calculator_routing(self):
        result = self.agent.run("算一下 12*12")
        self.assertEqual(result["steps"][0]["tool"], "calculator")
        self.assertIn("144", result["reply"])

    def test_export_todo_to_file(self):
        result = self.agent.run("把待办清单导出成 Markdown 文件")
        self.assertEqual(result["steps"][0]["tool"], "file_write")
        target = SANDBOX / "待办清单.md"
        self.assertTrue(target.exists())
        target.unlink(missing_ok=True)

    def test_multi_turn_memory_grows(self):
        self.agent.run("你好")
        self.agent.run("今天几号")
        self.assertGreaterEqual(self.agent.memory.turn_count(), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
