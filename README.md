# 知行 ZhiXing · 会说也会做的个人事务智能体

> 软件工程《AI 智能体构建》小组作业
> 一个既能**自然语言对话（能说）**，又能**调用工具真正落地办事（会做）**的 AI Agent。

「知行」取自「知行合一」——知是理解，行是执行。名字本身就说明了这个智能体的两端：
一端是**语言理解**，一端是**工具执行**。

---

## 一、它到底能做什么

| 能力域 | 典型说法 | 背后的工具 |
|--------|----------|-----------|
| 待办管理 | “帮我记一下周三下午交实验报告，优先级高” | `todo_add` / `todo_list` / `todo_done` / `todo_remove` |
| 天气出行 | “杭州明天要带伞吗” | `weather_query`（调用 wttr.in 公开接口） |
| 文件处理 | “把待办清单导出成 Markdown 文件” | `file_write` / `file_read` / `file_list` |
| 计算与时间 | “算一下 128\*37+56”“今天几号” | `calculator` / `current_time` |

**共 10 个工具。** 智能体自己决定该调用哪个、传什么参数。

## 二、四大加分项，一个不落

| 加分项 | 实现方式 | 位置 |
|--------|----------|------|
| 多轮对话记忆 | 会话按 `session_id` 持久化到 JSON，重启后自动恢复 | `core/memory.py` |
| 语音输入 / 输出 | 浏览器 Web Speech API：麦克风转文字 + 回答自动播报 | `web/index.html` |
| 外部 API / 数据库交互 | wttr.in 实时天气 JSON 接口；待办数据以 JSON 库形式持久化 | `tools/weather_tools.py` |
| 简洁前端界面 | 单页聊天工作台，含工具调用可视化卡片与待办/文件侧栏 | `web/index.html` |

另外还额外做到：**工具调用全过程可视化**、**MCP 协议导出**、**零依赖可运行**。

## 三、快速开始

```bash
# 1. 进入项目
cd zhixing-agent

# 2. 启动 Web 版（核心功能零依赖，无需 pip install）
python server.py
#    浏览器会自动打开 http://127.0.0.1:8848/

# 3.（可选）配置大模型，从规则模式升级为大模型模式
cp .env.example .env      # Windows: copy .env.example .env
#    编辑 .env，填入 LLM_API_KEY 即可
```

> **没有 API Key 也能完整跑通。** 未配置密钥时，智能体自动切换到内置的规则模式，
> 所有工具、多轮记忆、前端界面、语音功能照常可用。这样保证了课堂演示绝不翻车。

### 其他三种运行方式

```bash
python demo.py                    # 一键演示 9 轮完整对话，打印每次工具调用
python cli.py                     # 命令行交互（支持 /tools /reset /exit）
pip install mcp && python mcp_server.py   # 把 10 个工具暴露为标准 MCP Server
python -m unittest test_tools -v  # 运行 26 项自动化测试
```

## 四、支持的模型

任何提供 OpenAI 兼容 `/chat/completions` 接口的服务都能直接用（改 `.env` 即可）：

| 服务 | LLM_BASE_URL | LLM_MODEL |
|------|--------------|-----------|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 阿里云百炼 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 本地 Ollama | `http://localhost:11434/v1` | `qwen2.5:7b` |

## 五、项目结构

```
zhixing-agent/
├── config.py            配置中心：读 .env，统一管理路径与参数
├── tools/               【会做】工具层
│   ├── registry.py       工具注册表 —— 一处定义，三端复用
│   ├── todo_tools.py     待办管理（含自然语言时间解析）
│   ├── weather_tools.py  天气查询（外部 API + 离线兜底）
│   ├── file_tools.py     文件读写（沙箱隔离，防路径穿越）
│   └── util_tools.py     计算器（AST 白名单求值）+ 当前时间
├── core/                【说 + 决策】智能体内核
│   ├── agent.py          主循环：ReAct 式「理解→调用→回填→回答」
│   ├── llm.py            OpenAI 兼容客户端（纯标准库 urllib）
│   └── memory.py         多轮对话记忆（JSON 持久化）
├── web/index.html       前端界面（聊天 + 语音 + 工具卡片 + 侧栏）
├── server.py            HTTP 服务（标准库 http.server）
├── cli.py / demo.py     命令行与演示脚本
├── mcp_server.py        MCP Server 封装
├── test_tools.py        26 项自动化测试
└── storage/             运行时数据（待办、会话、沙箱文件）
```

## 六、它是怎么跑起来的

```
用户输入
   │
   ▼
┌──────────────────────────────────────────────┐
│  core/agent.py  智能体主循环                  │
│                                              │
│  ① 组装消息 = 系统提示词 + 历史记忆 + 本次输入  │
│  ② 交给大模型，同时把 10 个工具的 schema 一起给它 │
│  ③ 模型返回 tool_calls？                      │
│        ├─ 是 → 执行工具 → 结果回填 → 回到 ②    │
│        └─ 否 → 直接输出自然语言回答             │
└──────────────────────────────────────────────┘
   │
   ▼
工具注册表 tools/registry.py
   │
   ├──> 内置主循环（function calling）
   ├──> MCP Server（stdio，供 Claude/Cursor 等外部客户端调用）
   └──> 自动化测试
```

**关键设计：工具只定义一次。** 同一份注册表同时导出三种 schema
（OpenAI function calling / MCP inputSchema / 直接调用），
所以工具层的改动会自动同步到所有消费端。这是本项目最值得讲的一点。

## 七、安全设计

- **文件沙箱**：所有文件读写被限制在 `storage/workspace/`，通过 `resolve()` + 前缀校验
  阻断 `../../` 路径穿越（`test_tools.py::test_path_traversal_is_blocked` 覆盖）。
- **无 eval 计算器**：`calculator` 用 `ast` 节点白名单求值，拒绝 `__import__('os').system(...)`
  这类注入（有对应测试）。
- **错误不中断**：工具执行异常统一转成 `{"ok": false, "error": ...}` 回传给模型，
  模型可自行纠正参数重试，而不是让整个智能体崩掉。
- **密钥不入库**：`.env` 已加入 `.gitignore`，仓库内只保留 `.env.example`。

## 八、与作业要求的对应关系

| 作业要求 | 本项目落点 |
|----------|-----------|
| 推荐使用 MCP 框架或兼容框架 | 工具层可直接导出为 MCP Server；主循环用 OpenAI function calling（兼容框架） |
| 能说：自然语言对话 | Web / CLI 双入口，多轮上下文 |
| 会做：执行操作或调用工具 | 10 个工具，覆盖 API 调用、文件读写、数据持久化 |
| 多轮对话记忆（加分） | `core/memory.py`，JSON 持久化 + 重启恢复 |
| 语音输入/输出（加分） | `web/index.html` Web Speech API |
| 外部 API/数据库交互（加分） | wttr.in 实时接口 + JSON 数据库 |
| 前端界面（加分） | `web/index.html` 聊天工作台 |

## 九、GitHub

代码提交至本小组第一次团队作业创建的公共仓库（见博客园随笔中的链接说明）。

## 十、许可

本项目为课程作业，仅供学习交流使用。
