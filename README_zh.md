# EvoCoder v0.7.0

> 🌐 [English](README.md) | 中文

一个**会自我进化**的编程 Agent，基于 **MiMo v2.5 Pro**（兼容 OpenAI API）。EvoCoder 会从每次任务中学习——优化系统提示词、记住过去的错误、适应你的编码风格，甚至从使用模式中自动生成新的复合工具。用得越多，它越强。

> **v0.7.0**: 支持 MiMo API、修复内存溢出、语法高亮、代码运行、文件浏览器

```
                        ████████████
                  ██████████████████████████
              ██████████████████████████████████
          ░░██████████████████████████████████████░░
        ░░░░████████████████████████████████████████░░
  ░░░░░░░░░░████████████████████████████████████████████░░
░░░░░░░░░░░░██████████████████████████████████████████████
  ░░░░░░░░██████████████████████████████████████████████
      ░░░░██████████████████████████████████████████
          ████████████████████████████████████████

███████  ██    ██  ██████   CODER
██       ██    ██ ██
█████    ██    ██ ██   ███
██        ██  ██  ██    ██
███████   ████    ██████       v0.7.0
```

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🧬 **自进化系统提示词** | 失败率超过 30% 时自动分析原因并重写 prompt，支持版本回滚 |
| 🧠 **4 层记忆系统** | 对话缓冲 → 工作记忆 → 长期经验（向量检索）→ 用户画像 |
| 🔧 **自动工具生成** | 检测重复的工具调用模式，自动生成新的复合工具 |
| 🐛 **错误记忆** | 记录每个错误的上下文和修复方案，下次遇到类似问题自动建议 |
| 🤖 **子 Agent 委派** | 将复杂任务拆分给专门的子 Agent（代码/调试/研究/文件）并行执行 |
| 🖥️ **Web GUI** | 语法高亮、代码运行、文件浏览器、流式输出 |
| 📊 **26 个内置工具** | 文件/Shell/Git/HTTP/桌面自动化/数据处理/Web 搜索 |

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入 MIMO_API_KEY=你的key
# 从 https://platform.xiaomimimo.com 获取
```

也支持 DeepSeek：

```bash
# 在 .env 中设置 DEEPSEEK_API_KEY 即可切换
```

### 3. 运行

```bash
# 命令行版
python cli.py

# Web GUI 版
python web_server.py
# 浏览器打开 http://localhost:8080
```

---

## 🏗️ 架构

```
+=====================================================================+
|                          EvoCoder Agent                              |
|                                                                      |
|  +--------------------+     +------------------------------------+   |
|  |     Brain          |     |        SubAgentManager             |   |
|  | (LLM 推理引擎)     |     |  code | debug | research | file    |   |
|  |  - think()         |     +------------------------------------+   |
|  |  - think_stream()  |              |                               |
|  |  - TokenCache      |              v                               |
|  +--------+-----------+     +------------------------------------+   |
|           |                 |       ToolRegistry (26 工具)        |   |
|           v                 |  file | shell | git | http | web   |   |
|  +--------------------+     |  desktop | data | bg               |   |
|  |   4 层记忆系统      |     +------------------------------------+   |
|  |                    |                                               |
|  | L1: 对话缓冲       |     +------------------------------------+   |
|  |     (环形缓冲区)   |     |      3 层进化系统                   |   |
|  | L2: 工作记忆       |     |                                    |   |
|  |     (会话 KV)      |     | L1: PromptEvolver                  |   |
|  | L3: 长期记忆       |     |     (自修改系统提示词)              |   |
|  |     (JSONL+向量)   |     | L2: StrategyMemory + ErrorMemory   |   |
|  | L4: 用户画像       |     |     (任务感知学习)                  |   |
|  |     (跨会话)       |     | L3: ToolEvolver                    |   |
|  +--------------------+     |     (自动工具生成)                  |   |
|                             +------------------------------------+   |
+=====================================================================+
         |                    |                    |
    MiMo v2.5 Pro       ChromaDB 向量库        JSONL 磁盘
    (兼容 OpenAI API)    (语义搜索)            (持久化)
```

---

## 📋 命令列表

| 命令 | 说明 |
|------|------|
| `/help` | 显示所有可用命令 |
| `/ask` | 提问通用问题 |
| `/code` | 根据描述生成代码 |
| `/debug` | 调试错误或堆栈跟踪 |
| `/file` | 读取、写入或编辑文件 |
| `/git` | Git 操作（status, diff, log, commit） |
| `/search` | 搜索 Web 或代码库 |
| `/tools` | 列出所有注册工具 |
| `/brain` | Brain 诊断和健康检查 |
| `/evolve` | 查看进化统计和 prompt 历史 |
| `/clear` | 清空对话历史 |
| `/quit` | 退出 EvoCoder |

---

## 🔧 内置工具（26 个）

| # | 类别 | 工具 | 说明 |
|---|------|------|------|
| 1 | **文件** | `read_file` | 读取文件内容，支持编码和行数限制 |
| 2 | **文件** | `write_file` | 写入文件，自动创建父目录 |
| 3 | **文件** | `edit_file` | 查找替换文件中的文本 |
| 4 | **Shell** | `run_command` | 执行 Shell 命令（跨平台） |
| 5 | **Shell** | `list_directory` | 列出文件/目录 |
| 6 | **Shell** | `search_code` | 正则搜索文件内容 |
| 7 | **Git** | `git_status` | 查看工作区状态 |
| 8 | **Git** | `git_diff` | 查看差异 |
| 9 | **Git** | `git_log` | 查看提交历史 |
| 10 | **Git** | `github` | 运行 GitHub CLI 命令 |
| 11 | **HTTP** | `http_get` | 发送 GET 请求 |
| 12 | **HTTP** | `http_post` | 发送 POST 请求 |
| 13 | **HTTP** | `parse_html` | 解析 HTML 提取文本/链接 |
| 14 | **桌面** | `screenshot` | 截屏 |
| 15 | **桌面** | `mouse_click` | 鼠标点击 |
| 16 | **桌面** | `mouse_move` | 移动鼠标 |
| 17 | **桌面** | `type_text` | 输入文本（支持中文） |
| 18 | **桌面** | `press_key` | 按键/组合键 |
| 19 | **数据** | `read_csv` | 读取 CSV |
| 20 | **数据** | `process_data` | 数据处理（排序/过滤/分组） |
| 21 | **数据** | `export_data` | 导出为 CSV/JSON/Markdown |
| 22 | **Web** | `web_search` | 搜索网页（DuckDuckGo + Bing） |
| 23 | **Web** | `web_fetch` | 获取网页内容 |
| 24 | **后台** | `start_background` | 后台运行命令 |
| 25 | **后台** | `check_background` | 检查后台任务状态 |
| 26 | **后台** | `stop_background` | 终止后台任务 |

> 工具可扩展 — 用 `@registry.register()` 注册自定义工具。

---

## 🧠 4 层记忆系统

| 层级 | 存储 | 用途 | 持久化 |
|------|------|------|--------|
| L1: 对话缓冲 | 内存环形缓冲区（200 条） | 当前会话上下文 | ❌ 仅会话 |
| L2: 工作记忆 | JSON 文件（24h TTL） | 当前任务的结构化上下文 | ✅ 跨重启 |
| L3: 长期记忆 | JSONL + ChromaDB 向量 | 记录每个任务的结果/错误/解决方案 | ✅ 永久 |
| L4: 用户画像 | JSON 文件 | 跨会话的偏好和历史 | ✅ 永久 |

---

## 🧬 3 层进化系统

这是 EvoCoder 的核心差异化——用得越多，它越强。

### 第 1 层：PromptEvolver（自修改系统提示词）

- 分析任务执行历史，检测失败模式
- 失败率 >30% 时触发进化
- 生成新版本的系统提示词
- 支持 accept/reject/rollback

### 第 2 层：StrategyMemory + ErrorMemory（任务感知学习）

- **StrategyMemory**: 按类别维护策略提示词（code/debug/refactor/file/git/search）
- **ErrorMemory**: 记录每个错误的上下文和修复方案，遇到类似问题自动建议

### 第 3 层：ToolEvolver（自动工具生成）

- 用滑动窗口检测重复的工具调用模式
- 自动生成 Python 包装函数链接现有工具
- 安全验证：正则扫描 + AST 解析 + 危险节点检测
- 保存为可导入的 Python 模块

---

## 📁 项目结构

```
EvoCoder/
├── agent.py              # Agent 主循环（感知→推理→行动→学习）
├── brain/engine.py       # LLM 推理引擎 + TokenCache
├── cli.py                # 命令行界面
├── web_server.py         # WebSocket 服务 + GUI 后端
├── gui/index.html        # Web GUI 前端
├── config.json           # 模型/Agent/进化配置
├── memory/               # 记忆系统
│   ├── store.py          # 3 层记忆（对话/工作/长期）
│   └── long_term.py      # 用户画像/会话历史/学习知识
├── evolution/            # 进化系统
│   ├── prompt_evolver.py # 系统提示词自进化
│   ├── error_memory.py   # 错误记忆 + 修复建议
│   ├── strategy_memory.py# 按类别策略记忆
│   └── tool_evolver.py   # 自动工具生成
├── tools/                # 工具系统
│   ├── registry.py       # 工具注册中心
│   ├── builtin.py        # 26 个内置工具
│   └── forge.py          # 工具安全验证
├── subagents/manager.py  # 子 Agent 委派
├── tests/                # 34 个测试
└── .evocoder/            # 运行时数据（自动创建）
```

---

## 🔑 设计决策

- **兼容 OpenAI API**: 默认使用 MiMo v2.5 Pro，可切换到 DeepSeek/OpenAI 等
- **优雅降级**: 可选依赖（ChromaDB/pandas/pyautogui）都有 try/except 保护
- **线程安全**: SubAgentManager 用锁保护共享状态
- **跨平台**: 自动检测 Windows/Linux/macOS，注入对应的 Shell 规则

---

## 📦 依赖

| 包 | 用途 |
|----|------|
| `openai` | LLM API 客户端 |
| `rich` | 终端 UI |
| `chromadb` | 向量搜索（可选） |
| `requests` | HTTP 请求 |
| `beautifulsoup4` | HTML 解析 |
| `pandas` | 数据处理（可选） |
| `pyautogui` | 桌面自动化（可选） |
| `python-dotenv` | .env 文件加载 |
| `gitpython` | Git 集成 |

---

## 📄 许可证

MIT

---

## 🤝 贡献

欢迎！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

如果觉得有用，点个 ⭐ Star 鼓励一下！
