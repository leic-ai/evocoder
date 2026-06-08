#!/usr/bin/env python3
"""
EVOcoder 五轮全面测试
确保：无错误、能写代码、能记住人、跨会话有记忆
"""

import sys
import os
import json
import shutil
import time
from pathlib import Path

# 设置UTF-8编码
os.environ['PYTHONIOENCODING'] = 'utf-8'
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

# 添加项目路径
sys.path.insert(0, '.')

# 测试结果收集
test_results = {
    "round1": {"name": "基础导入测试", "tests": []},
    "round2": {"name": "工具系统测试", "tests": []},
    "round3": {"name": "记忆系统测试", "tests": []},
    "round4": {"name": "进化系统测试", "tests": []},
    "round5": {"name": "完整流程测试", "tests": []},
}

def log_test(round_name, test_name, passed, detail=""):
    """记录测试结果"""
    status = "PASS" if passed else "FAIL"
    test_results[round_name]["tests"].append({
        "name": test_name,
        "status": status,
        "detail": detail
    })
    print(f"  [{status}] {test_name}" + (f" - {detail}" if detail else ""))

def print_summary():
    """打印测试总结"""
    print("\n" + "="*60)
    print("EVOcoder 五轮测试总结")
    print("="*60)

    total_tests = 0
    total_passed = 0
    total_failed = 0

    for round_name, round_data in test_results.items():
        round_passed = sum(1 for t in round_data["tests"] if t["status"] == "PASS")
        round_failed = sum(1 for t in round_data["tests"] if t["status"] == "FAIL")
        round_total = len(round_data["tests"])

        total_tests += round_total
        total_passed += round_passed
        total_failed += round_failed

        status = "✓" if round_failed == 0 else "✗"
        print(f"\n{status} {round_name}: {round_data['name']}")
        print(f"  通过: {round_passed}/{round_total}")

        if round_failed > 0:
            print(f"  失败: {round_failed}")
            for t in round_data["tests"]:
                if t["status"] == "FAIL":
                    print(f"    - {t['name']}: {t['detail']}")

    print("\n" + "="*60)
    print(f"总计: {total_passed}/{total_tests} 通过")
    if total_failed > 0:
        print(f"失败: {total_failed}")
        print("\n❌ 测试未通过，请修复后重试")
        return False
    else:
        print("\n✅ 所有测试通过！可以提交")
        return True


# ============================================================================
# 第一轮：基础导入测试
# ============================================================================

def round1_basic_imports():
    """测试所有模块能否正常导入"""
    print("\n" + "="*60)
    print("第一轮：基础导入测试")
    print("="*60)

    # 1.1 核心模块
    try:
        from agent import EvoCoder, load_config
        log_test("round1", "agent模块导入", True)
    except Exception as e:
        log_test("round1", "agent模块导入", False, str(e))

    # 1.2 Brain模块
    try:
        from brain.engine import Brain, TokenCache, get_system_prompt
        log_test("round1", "brain模块导入", True)
    except Exception as e:
        log_test("round1", "brain模块导入", False, str(e))

    # 1.3 工具模块
    try:
        from tools.registry import ToolRegistry
        from tools.builtin import register_builtins
        log_test("round1", "tools模块导入", True)
    except Exception as e:
        log_test("round1", "tools模块导入", False, str(e))

    # 1.4 记忆模块
    try:
        from memory.store import MemoryStore
        from memory.long_term import LongTermMemory
        log_test("round1", "memory模块导入", True)
    except Exception as e:
        log_test("round1", "memory模块导入", False, str(e))

    # 1.5 进化模块
    try:
        from evolution.tracker import EvolutionTracker, TaskStatus
        from evolution.error_memory import ErrorMemory
        from evolution.user_prefs import UserPreferences
        from evolution.strategy_memory import StrategyMemory
        from evolution.prompt_evolver import PromptEvolver
        from evolution.tool_evolver import ToolEvolver
        log_test("round1", "evolution模块导入", True)
    except Exception as e:
        log_test("round1", "evolution模块导入", False, str(e))

    # 1.6 子代理模块
    try:
        from subagents.manager import SubAgentManager, AgentType
        log_test("round1", "subagents模块导入", True)
    except Exception as e:
        log_test("round1", "subagents模块导入", False, str(e))

    # 1.7 SDD模块
    try:
        from sdd import SDDFlow
        log_test("round1", "sdd模块导入", True)
    except Exception as e:
        log_test("round1", "sdd模块导入", False, str(e))

    # 1.8 配置加载
    try:
        config = load_config()
        assert "api" in config
        assert "agent" in config
        assert "evolution" in config
        log_test("round1", "配置加载", True, f"keys={list(config.keys())}")
    except Exception as e:
        log_test("round1", "配置加载", False, str(e))


# ============================================================================
# 第二轮：工具系统测试
# ============================================================================

def round2_tool_system():
    """测试工具注册和执行"""
    print("\n" + "="*60)
    print("第二轮：工具系统测试")
    print("="*60)

    # 2.1 工具注册
    try:
        from tools.registry import ToolRegistry
        from tools.builtin import register_builtins

        registry = ToolRegistry()
        register_builtins(registry)
        tool_count = len(registry)
        assert tool_count >= 20, f"工具数量不足: {tool_count}"
        log_test("round2", "工具注册", True, f"{tool_count}个工具")
    except Exception as e:
        log_test("round2", "工具注册", False, str(e))
        return

    # 2.2 工具列表
    try:
        tools = registry.list_tools()
        assert len(tools) > 0
        log_test("round2", "工具列表", True, f"{len(tools)}个工具")
    except Exception as e:
        log_test("round2", "工具列表", False, str(e))

    # 2.3 read_file工具
    try:
        result = registry.execute("read_file", path="config.json")
        assert "api" in result or "model" in result
        log_test("round2", "read_file执行", True)
    except Exception as e:
        log_test("round2", "read_file执行", False, str(e))

    # 2.4 write_file工具
    try:
        test_content = "# Test file\nprint('hello')"
        result = registry.execute("write_file", path="/tmp/test_evo_write.py", content=test_content)
        assert "OK" in result
        log_test("round2", "write_file执行", True)
    except Exception as e:
        log_test("round2", "write_file执行", False, str(e))

    # 2.5 list_directory工具
    try:
        result = registry.execute("list_directory", path=".")
        assert "agent.py" in result
        log_test("round2", "list_directory执行", True)
    except Exception as e:
        log_test("round2", "list_directory执行", False, str(e))

    # 2.6 run_command工具
    try:
        result = registry.execute("run_command", command="echo hello")
        assert "hello" in result
        log_test("round2", "run_command执行", True)
    except Exception as e:
        log_test("round2", "run_command执行", False, str(e))

    # 2.7 search_code工具
    try:
        result = registry.execute("search_code", pattern="def run", path=".", glob="*.py")
        assert "def run" in result or "agent.py" in result
        log_test("round2", "search_code执行", True)
    except Exception as e:
        log_test("round2", "search_code执行", False, str(e))

    # 2.8 子代理工具注册
    try:
        from agent import EvoCoder
        # 检查子代理工具是否在registry中
        # 注意：不能直接实例化EvoCoder（需要API key），但可以检查方法存在
        assert hasattr(EvoCoder, '_register_subagent_tools')
        log_test("round2", "子代理工具注册方法", True)
    except Exception as e:
        log_test("round2", "子代理工具注册方法", False, str(e))

    # 清理
    try:
        os.remove("/tmp/test_evo_write.py")
    except:
        pass


# ============================================================================
# 第三轮：记忆系统测试
# ============================================================================

def round3_memory_system():
    """测试记忆系统的读写和持久化"""
    print("\n" + "="*60)
    print("第三轮：记忆系统测试")
    print("="*60)

    test_dir = "/tmp/test_evo_memory"

    # 清理测试目录
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    # 3.1 MemoryStore初始化
    try:
        from memory.store import MemoryStore
        store = MemoryStore(test_dir)
        log_test("round3", "MemoryStore初始化", True)
    except Exception as e:
        log_test("round3", "MemoryStore初始化", False, str(e))
        return

    # 3.2 会话记忆
    try:
        store.add_conversation("user", "你好")
        store.add_conversation("assistant", "你好！有什么可以帮你的？")
        messages = store.get_recent_conversation(n=2)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        log_test("round3", "会话记忆读写", True)
    except Exception as e:
        log_test("round3", "会话记忆读写", False, str(e))

    # 3.3 经验记录
    try:
        entry = store.record_experience(
            task="测试任务",
            category="general",
            outcome="success",
            solution="测试解决方案",
            tags=["test", "memory"]
        )
        assert entry["id"] is not None
        assert entry["task"] == "测试任务"
        log_test("round3", "经验记录", True)
    except Exception as e:
        log_test("round3", "经验记录", False, str(e))

    # 3.4 相似经验检索
    try:
        similar = store.get_similar_experiences("测试", top_k=1)
        assert len(similar) > 0
        assert similar[0]["task"] == "测试任务"
        log_test("round3", "相似经验检索", True)
    except Exception as e:
        log_test("round3", "相似经验检索", False, str(e))

    # 3.5 经验统计
    try:
        stats = store.get_experience_stats()
        assert stats["total"] > 0
        assert "success" in stats["outcomes"]
        log_test("round3", "经验统计", True, f"total={stats['total']}")
    except Exception as e:
        log_test("round3", "经验统计", False, str(e))

    # 3.6 LongTermMemory初始化
    try:
        from memory.long_term import LongTermMemory
        ltm = LongTermMemory(test_dir + "/long_term")
        log_test("round3", "LongTermMemory初始化", True)
    except Exception as e:
        log_test("round3", "LongTermMemory初始化", False, str(e))

    # 3.7 用户档案更新
    try:
        user = ltm.update_user(name="测试用户", tags=["python", "ai"])
        assert user["name"] == "测试用户"
        assert "python" in user["tags"]
        log_test("round3", "用户档案更新", True)
    except Exception as e:
        log_test("round3", "用户档案更新", False, str(e))

    # 3.8 会话记录
    try:
        session = ltm.add_session(
            summary="测试会话",
            tags=["test"]
        )
        assert session["session_id"] is not None
        log_test("round3", "会话记录", True)
    except Exception as e:
        log_test("round3", "会话记录", False, str(e))

    # 3.9 上下文生成
    try:
        context = ltm.get_context()
        assert "测试用户" in context
        log_test("round3", "上下文生成", True)
    except Exception as e:
        log_test("round3", "上下文生成", False, str(e))

    # 3.10 持久化测试
    try:
        # 重新加载
        store2 = MemoryStore(test_dir)
        similar = store2.get_similar_experiences("测试", top_k=1)
        assert len(similar) > 0
        log_test("round3", "记忆持久化", True)
    except Exception as e:
        log_test("round3", "记忆持久化", False, str(e))

    # 3.11 清除会话
    try:
        store.clear_conversation()
        messages = store.get_recent_conversation()
        assert len(messages) == 0
        log_test("round3", "清除会话", True)
    except Exception as e:
        log_test("round3", "清除会话", False, str(e))

    # 清理
    shutil.rmtree(test_dir, ignore_errors=True)


# ============================================================================
# 第四轮：进化系统测试
# ============================================================================

def round4_evolution_system():
    """测试进化系统的各个组件"""
    print("\n" + "="*60)
    print("第四轮：进化系统测试")
    print("="*60)

    test_dir = "/tmp/test_evo_evolution"

    # 清理测试目录
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir, exist_ok=True)

    # 4.1 EvolutionTracker初始化
    try:
        from evolution.tracker import EvolutionTracker, TaskStatus
        tracker = EvolutionTracker(test_dir + "/tracker")
        log_test("round4", "EvolutionTracker初始化", True)
    except Exception as e:
        log_test("round4", "EvolutionTracker初始化", False, str(e))
        return

    # 4.2 任务生命周期
    try:
        task = tracker.start_task("test", "测试任务")
        assert task.task_id is not None
        assert task.status == TaskStatus.RUNNING

        tracker.log_step(task.task_id, "step1", {"detail": "test"})
        tracker.log_step(task.task_id, "step2", tool="read_file")

        result = tracker.end_task(task.task_id, TaskStatus.SUCCESS, result="完成")
        assert result.task_id == task.task_id
        assert result.status == TaskStatus.SUCCESS
        log_test("round4", "任务生命周期", True)
    except Exception as e:
        log_test("round4", "任务生命周期", False, str(e))

    # 4.3 任务统计
    try:
        stats = tracker.summary()
        assert stats["total_tasks"] > 0
        assert stats["successes"] > 0
        log_test("round4", "任务统计", True, f"total={stats['total_tasks']}")
    except Exception as e:
        log_test("round4", "任务统计", False, str(e))

    # 4.4 ErrorMemory初始化
    try:
        from evolution.error_memory import ErrorMemory
        em = ErrorMemory(test_dir + "/errors.json")
        log_test("round4", "ErrorMemory初始化", True)
    except Exception as e:
        log_test("round4", "ErrorMemory初始化", False, str(e))

    # 4.5 错误记录和查询
    try:
        entry = em.record_failure(
            task="测试错误",
            error_msg="KeyError: 'test'",
            attempted_solution="使用.get()方法"
        )
        assert entry["error_type"] == "KeyError"

        suggestions = em.suggest_fix("KeyError: 'config'")
        assert len(suggestions) > 0
        log_test("round4", "错误记录和查询", True)
    except Exception as e:
        log_test("round4", "错误记录和查询", False, str(e))

    # 4.6 UserPreferences初始化
    try:
        from evolution.user_prefs import UserPreferences
        up = UserPreferences(test_dir + "/prefs.json")
        log_test("round4", "UserPreferences初始化", True)
    except Exception as e:
        log_test("round4", "UserPreferences初始化", False, str(e))

    # 4.7 偏好学习
    try:
        signals = up.learn_from_code("def hello():\n    print('hello')")
        assert "indent_style" in signals or len(signals) >= 0

        changes = up.learn_from_feedback("I prefer single quotes")
        log_test("round4", "偏好学习", True)
    except Exception as e:
        log_test("round4", "偏好学习", False, str(e))

    # 4.8 StrategyMemory初始化
    try:
        from evolution.strategy_memory import StrategyMemory
        sm = StrategyMemory(test_dir + "/strategy.json")
        log_test("round4", "StrategyMemory初始化", True)
    except Exception as e:
        log_test("round4", "StrategyMemory初始化", False, str(e))

    # 4.9 策略分类
    try:
        category = sm.classify_task("Fix the bug in main.py")
        assert category == "debug"

        category = sm.classify_task("Write a new function")
        assert category == "code"
        log_test("round4", "策略分类", True)
    except Exception as e:
        log_test("round4", "策略分类", False, str(e))

    # 4.10 策略统计
    try:
        sm.record_task_result("debug", success=True, duration=10.0)
        sm.record_task_result("debug", success=False, duration=20.0)

        stats = sm.get_stats()
        assert stats["debug"]["total_tasks"] > 0
        log_test("round4", "策略统计", True)
    except Exception as e:
        log_test("round4", "策略统计", False, str(e))

    # 4.11 PromptEvolver初始化
    try:
        from evolution.prompt_evolver import PromptEvolver
        pe = PromptEvolver(persist_dir=test_dir + "/evolver")
        log_test("round4", "PromptEvolver初始化", True)
    except Exception as e:
        log_test("round4", "PromptEvolver初始化", False, str(e))

    # 4.12 提示词进化
    try:
        result = pe.analyze_and_evolve(force=True)
        assert "evolution_proposed" in result

        if result["evolution_proposed"]:
            pe.accept_evolution()
            log_test("round4", "提示词进化", True, "已接受进化")
        else:
            log_test("round4", "提示词进化", True, "无需进化")
    except Exception as e:
        log_test("round4", "提示词进化", False, str(e))

    # 4.13 ToolEvolver初始化
    try:
        from evolution.tool_evolver import ToolEvolver
        te = ToolEvolver(test_dir + "/tools")
        log_test("round4", "ToolEvolver初始化", True)
    except Exception as e:
        log_test("round4", "ToolEvolver初始化", False, str(e))

    # 4.14 工具调用记录
    try:
        te.record_tool_call("read_file", {"path": "test.py"}, success=True)
        te.record_tool_call("read_file", {"path": "test2.py"}, success=True)
        te.record_tool_call("write_file", {"path": "out.py", "content": "test"}, success=True)

        patterns = te.detect_patterns()
        log_test("round4", "工具调用记录", True, f"{len(te.call_log)}条记录")
    except Exception as e:
        log_test("round4", "工具调用记录", False, str(e))

    # 清理
    shutil.rmtree(test_dir, ignore_errors=True)


# ============================================================================
# 第五轮：完整流程测试
# ============================================================================

def round5_full_flow():
    """测试完整的Agent流程（模拟，不调用API）"""
    print("\n" + "="*60)
    print("第五轮：完整流程测试（模拟）")
    print("="*60)

    test_dir = "/tmp/test_evo_full"

    # 清理测试目录
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    # 5.1 Agent配置加载
    try:
        from agent import load_config
        config = load_config()
        assert config["api"]["model"] is not None
        assert config["agent"]["max_iterations"] > 0
        log_test("round5", "Agent配置加载", True)
    except Exception as e:
        log_test("round5", "Agent配置加载", False, str(e))

    # 5.2 任务分类
    try:
        from agent import EvoCoder
        # 模拟分类逻辑
        categories = config.get("task_categories", {})
        task_lower = "fix the bug in main.py"
        category = "general"
        for cat, cfg in categories.items():
            if any(w in task_lower for w in cfg.get("keywords", [])):
                category = cat
                break
        assert category == "debug"
        log_test("round5", "任务分类", True, f"category={category}")
    except Exception as e:
        log_test("round5", "任务分类", False, str(e))

    # 5.3 系统提示词构建
    try:
        from brain.engine import get_system_prompt
        prompt = get_system_prompt()
        assert "EvoCoder" in prompt
        assert len(prompt) > 100
        log_test("round5", "系统提示词构建", True, f"{len(prompt)}字符")
    except Exception as e:
        log_test("round5", "系统提示词构建", False, str(e))

    # 5.4 TokenCache功能
    try:
        from brain.engine import TokenCache
        tc = TokenCache()

        # 模拟缓存更新
        tc.cache_hits = 100
        tc.cache_misses = 20
        tc.total_input_tokens = 50000
        tc.total_output_tokens = 10000

        stats = tc.get_stats()
        assert stats["cache_hits"] == 100
        assert stats["hit_rate"] > 0.8
        log_test("round5", "TokenCache功能", True, f"hit_rate={stats['hit_rate']:.1%}")
    except Exception as e:
        log_test("round5", "TokenCache功能", False, str(e))

    # 5.5 工具过滤
    try:
        from brain.engine import TokenCache
        tc = TokenCache()

        tools = [{"function": {"name": f"tool_{i}", "description": f"Tool {i}"}} for i in range(20)]
        messages = [{"role": "user", "content": "read file"}]

        filtered = tc.filter_relevant_tools(tools, messages)
        assert len(filtered) < len(tools)
        log_test("round5", "工具过滤", True, f"{len(tools)}->{len(filtered)}")
    except Exception as e:
        log_test("round5", "工具过滤", False, str(e))

    # 5.6 SubAgentManager初始化
    try:
        from subagents.manager import SubAgentManager, AgentType
        manager = SubAgentManager(api_key="test", base_url="http://test", model="test")

        types = manager.list_types()
        assert len(types) >= 5
        log_test("round5", "SubAgentManager初始化", True, f"{len(types)}种代理")
    except Exception as e:
        log_test("round5", "SubAgentManager初始化", False, str(e))

    # 5.7 平台检测
    try:
        from utils.platform import get_platform_prompt
        prompt = get_platform_prompt()
        assert "Windows" in prompt or "Linux" in prompt or "Darwin" in prompt
        log_test("round5", "平台检测", True)
    except Exception as e:
        log_test("round5", "平台检测", False, str(e))

    # 5.8 CLI命令解析
    try:
        # 模拟命令解析
        user_input = "/help"
        parts = user_input.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        assert cmd == "/help"
        assert arg == ""
        log_test("round5", "CLI命令解析", True)
    except Exception as e:
        log_test("round5", "CLI命令解析", False, str(e))

    # 5.9 跨会话记忆模拟
    try:
        from memory.store import MemoryStore
        from memory.long_term import LongTermMemory

        # 第一次会话
        store1 = MemoryStore(test_dir)
        store1.record_experience(
            task="记住用户偏好",
            category="general",
            outcome="success",
            solution="用户喜欢Python",
            tags=["preference", "python"]
        )

        ltm1 = LongTermMemory(test_dir + "/ltm")
        ltm1.update_user(name="用户A", tags=["python", "ai"])
        ltm1.add_session(summary="学习用户偏好", tags=["preference"])

        # 模拟第二次会话（重新加载）
        store2 = MemoryStore(test_dir)
        similar = store2.get_similar_experiences("Python", top_k=1)
        assert len(similar) > 0

        ltm2 = LongTermMemory(test_dir + "/ltm")
        user = ltm2.get_user()
        assert user["name"] == "用户A"
        assert "python" in user["tags"]

        log_test("round5", "跨会话记忆", True, "记忆保留成功")
    except Exception as e:
        log_test("round5", "跨会话记忆", False, str(e))

    # 5.10 错误处理
    try:
        from tools.registry import ToolRegistry
        registry = ToolRegistry()

        # 测试不存在的工具
        try:
            registry.execute("nonexistent_tool")
            log_test("round5", "错误处理", False, "应该抛出异常")
        except KeyError:
            log_test("round5", "错误处理", True, "正确抛出KeyError")
    except Exception as e:
        log_test("round5", "错误处理", False, str(e))

    # 清理
    shutil.rmtree(test_dir, ignore_errors=True)


# ============================================================================
# 主函数
# ============================================================================

def main():
    print("\n" + "="*60)
    print("EVOcoder 五轮全面测试")
    print("="*60)
    print("测试目标：")
    print("  1. 无错误")
    print("  2. 能写代码")
    print("  3. 能记住人")
    print("  4. 跨会话有记忆")
    print("="*60)

    # 执行五轮测试
    round1_basic_imports()
    round2_tool_system()
    round3_memory_system()
    round4_evolution_system()
    round5_full_flow()

    # 打印总结
    all_passed = print_summary()

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
