# EVOcoder v0.7.1 项目归档

> 归档日期：2026-06-09
> 版本：v0.7.1
> 状态：稳定版，83项测试通过

---

## 项目概述

EVOcoder是一个**自进化编程助手**，运行在DeepSeek V4 Pro上，具备完整的工具系统、记忆系统和进化系统。

## 核心能力

### ✅ 已验证能力

1. **代码生成** - 可以生成、执行、调试Python代码
2. **记忆系统** - 可以记住用户、经验、偏好
3. **进化系统** - 可以学习、优化、进化
4. **子代理系统** - 可以委托任务
5. **完整流程** - 可以完成复杂任务

### 📊 测试结果

- 基础测试：42/42 通过
- 深度测试：41/41 通过
- **总计**：83项测试全部通过

## 功能清单

### 工具系统（26个）

| 类别 | 工具 | 数量 |
|------|------|------|
| 文件 | read_file, write_file, edit_file | 3 |
| Shell | run_command, list_directory, search_code | 3 |
| Git | git_status, git_diff, git_log, github | 4 |
| HTTP | http_get, http_post, parse_html | 3 |
| 桌面 | screenshot, mouse_click, mouse_move, type_text, press_key | 5 |
| 数据 | read_csv, process_data, export_data | 3 |
| Web | web_search, web_fetch | 2 |
| 后台 | start_background, check_background, stop_background | 3 |

### 子代理系统（5种）

| 类型 | 用途 | 最大迭代 |
|------|------|----------|
| code | 代码编写专家 | 15 |
| debug | 调试修复专家 | 20 |
| research | 信息研究专家 | 10 |
| file | 文件操作专家 | 10 |
| general | 通用任务代理 | 15 |

### 自进化系统（6层）

1. **ErrorMemory** - 记录错误，避免重复
2. **UserPreferences** - 学习用户编码风格
3. **StrategyMemory** - 优化任务策略
4. **PromptEvolver** - 自我修改系统提示词
5. **ToolEvolver** - 自动生成新工具
6. **EvolutionTracker** - 决定何时进化

### 记忆系统（4层）

1. **会话记忆** - 当前对话上下文
2. **工作记忆** - 会话内关键信息
3. **长期记忆** - 跨会话经验
4. **用户档案** - 偏好和历史

## 修复记录

### v0.7.1 修复（2026-06-08/09）

1. ErrorMemory.record_failure() 参数名修正
2. EvolutionTracker.should_evolve() 移除无效参数
3. PromptEvolver.get_evolution_history() 移除无效参数
4. StrategyMemory.get_strategy() 改用get_strategy_prompt()
5. best_strategy_for() 用法修正
6. SubAgentManager._run_agent_loop() Brain.think()参数修正
7. UserPreferences.learn_from_feedback() 参数数量修正
8. MemoryStore.clear_session() 改用正确方法
9. get_stats() 修复success_rate计算
10. _try_evolve() 修复get_failure_analysis()不存在问题
11. task_id访问 修复task_record.id为task_record.task_id
12. SubAgentManager 添加缺失的list_types()方法

### 界面改进

- 添加Brewed Footer（耗时显示）
- 移除Panel标题（更简洁）
- 修复变量名冲突

## 经验固化

### 成功经验

1. **API兼容性** - 仔细检查方法签名和参数
2. **错误处理** - 使用try-except捕获所有异常
3. **测试驱动** - 先写测试，再修复问题
4. **渐进式修复** - 一次修复一个问题
5. **记忆持久化** - 确保跨会话数据不丢失

### 踩过的坑

1. **TaskRecord字段** - task_id不是id
2. **get_stats()返回值** - 需要从outcomes计算success_rate
3. **Windows兼容** - 路径、编码、命令都要处理
4. **ChromaDB下载** - 向量搜索需要下载79MB模型
5. **变量名冲突** - 避免使用内置函数名作变量名

## 使用方式

### 启动

```bash
cd D:\ClaudeData\EvoCoder
python cli.py
```

### 常用命令

- `/help` - 显示帮助
- `/tools` - 列出工具
- `/stats` - 查看统计
- `/evolve` - 进化状态
- `/memory` - 记忆状态
- `/token` - Token统计
- `/search <query>` - 网页搜索
- `/fetch <url>` - 获取网页
- `/quit` - 退出

## 测试命令

```bash
# 基础测试（42项）
python test_quick.py

# 深度测试（41项）
python test_deep.py
```

## 文件结构

```
D:\ClaudeData\EvoCoder\
├── agent.py              # Agent核心循环
├── cli.py                # 命令行界面
├── config.json           # 配置文件
├── evo_splash.py         # 启动画面
├── SKILLS.md             # 技能文档
├── ARCHIVE.md            # 本文件
├── brain/
│   └── engine.py         # DeepSeek推理引擎
├── tools/
│   ├── builtin.py        # 26个内置工具
│   ├── registry.py       # 工具注册表
│   └── web_search.py     # 网页搜索
├── memory/
│   ├── store.py          # 记忆存储
│   └── long_term.py      # 长期记忆
├── evolution/
│   ├── tracker.py        # 任务跟踪
│   ├── error_memory.py   # 错误记忆
│   ├── user_prefs.py     # 用户偏好
│   ├── strategy_memory.py # 策略记忆
│   ├── prompt_evolver.py # 提示词进化
│   └── tool_evolver.py   # 工具进化
├── subagents/
│   └── manager.py        # 子代理管理
├── test_quick.py         # 基础测试（42项）
└── test_deep.py          # 深度测试（41项）
```

## Git历史

```
b263557 Pass all 41 deep tests - complex task verification
e2c4f53 Pass all 42 tests - EVOcoder fully verified
44ec6f1 Fix task_id access
cf990ba Fix list index errors
ad740b4 Remove EvoCoder title from response panel
e872037 Add Claude Code style 'Brewed' footer
ffc3fb2 Fix 7 critical API mismatches
9bcb0fb Add thinking visualization
f172524 EVOcoder v0.7.0 — FULLY WORKING!
89cd5fc Fix Brain to support tool_calls
7eaa959 Fix audit issues
4845821 Fix all CLI command errors
2925e8a Fix constructor mismatches
cde99ec Add agent.py and cli.py
c4ae5f1 Add start.bat
54b0690 EVOcoder v0.7.0 — 重生版
```

## 未来改进

1. 添加更多测试用例
2. 优化Token缓存策略
3. 改进子代理并行执行
4. 添加MCP服务器支持
5. 实现插件系统

---

**归档完成** ✅

EVOcoder v0.7.1 已经完全验证，可以正常使用。
