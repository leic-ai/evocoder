"""Smoke tests — verify imports and basic object creation.

These tests run without an API key and without network access.
They catch import errors, missing dependencies, and constructor bugs.
"""

import json
import tempfile
import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Event system
# ---------------------------------------------------------------------------

class TestAgentEvents:
    """Verify the event system imports and works."""

    def test_import_events(self):
        from agent_events import AgentEvent, EventType
        assert EventType.CONTENT_TOKEN.value == "content_token"
        assert EventType.TOOL_CALL.value == "tool_call"

    def test_create_events(self):
        from agent_events import (
            thinking_event, content_event, content_token_event,
            tool_call_event, tool_result_event, step_event,
            pitfall_event, error_event, evolution_event, summary_event,
        )

        e = thinking_event(1)
        assert e.type.value == "thinking"
        assert e.step == 1

        e = content_token_event(2, "hello")
        assert e.data["token"] == "hello"

        e = tool_call_event(3, "read_file", {"path": "test.py"})
        assert e.data["name"] == "read_file"

        e = summary_event("done", True, 5, 1.23, 100, 50)
        assert e.data["success"] is True
        assert e.data["total_time"] == 1.23

    def test_event_serialization(self):
        from agent_events import AgentEvent, EventType

        original = AgentEvent(EventType.TOOL_CALL, {"name": "test"}, step=1)
        d = original.to_dict()
        restored = AgentEvent.from_dict(d)
        assert restored.type == original.type
        assert restored.data == original.data
        assert restored.step == original.step


# ---------------------------------------------------------------------------
# Error memory (type-safe dataclasses)
# ---------------------------------------------------------------------------

class TestErrorMemory:
    """Verify ErrorMemory with new dataclass types."""

    def test_create_and_record(self):
        from evolution.error_memory import ErrorMemory, ErrorEntry, PitfallHint, PitfallSummary

        with tempfile.TemporaryDirectory() as tmpdir:
            mem = ErrorMemory(memory_path=str(Path(tmpdir) / "errors.json"))

            entry = mem.record_failure(
                task="test task",
                error_msg="KeyError: 'missing_key'",
                attempted_solution="used .get()",
            )
            assert isinstance(entry, ErrorEntry)
            assert entry.error_type == "KeyError"
            assert entry.resolved is False

    def test_suggest_fix_returns_pitfall_hints(self):
        from evolution.error_memory import ErrorMemory, PitfallHint

        with tempfile.TemporaryDirectory() as tmpdir:
            mem = ErrorMemory(memory_path=str(Path(tmpdir) / "errors.json"))
            mem.record_failure("task1", "KeyError: 'x'", "tried something")
            mem.record_failure("task2", "KeyError: 'y'", "tried again")

            hints = mem.suggest_fix("KeyError: 'z'")
            assert isinstance(hints, list)
            assert len(hints) > 0
            assert isinstance(hints[0], PitfallHint)
            assert hints[0].error_type == "KeyError"
            assert 0 < hints[0].confidence <= 1.0

    def test_pitfall_summary_type(self):
        from evolution.error_memory import ErrorMemory, PitfallSummary

        with tempfile.TemporaryDirectory() as tmpdir:
            mem = ErrorMemory(memory_path=str(Path(tmpdir) / "errors.json"))

            summary = mem.get_pitfall_summary()
            assert isinstance(summary, PitfallSummary)
            assert summary.total_errors == 0

            mem.record_failure("task", "TypeError: bad", "fix")
            summary = mem.get_pitfall_summary()
            assert summary.total_errors == 1
            assert "TypeError" in summary.error_breakdown

    def test_mark_resolved(self):
        from evolution.error_memory import ErrorMemory

        with tempfile.TemporaryDirectory() as tmpdir:
            mem = ErrorMemory(memory_path=str(Path(tmpdir) / "errors.json"))
            entry = mem.record_failure("task", "ValueError: x", "fix")
            assert mem.mark_resolved(entry.id) is True
            assert mem.mark_resolved(999) is False

    def test_persistence(self):
        from evolution.error_memory import ErrorMemory, ErrorEntry

        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "errors.json")
            mem1 = ErrorMemory(memory_path=path)
            mem1.record_failure("task", "ImportError: no module", "pip install")
            assert len(mem1.errors) == 1

            # Reload from disk
            mem2 = ErrorMemory(memory_path=path)
            assert len(mem2.errors) == 1
            assert isinstance(mem2.errors[0], ErrorEntry)
            assert mem2.errors[0].error_type == "ImportError"


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

class TestToolRegistry:
    """Verify ToolRegistry works correctly."""

    def test_register_and_execute(self):
        from tools.registry import ToolRegistry

        reg = ToolRegistry()

        @reg.register(name="add", description="Add two numbers", parameters={
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        })
        def add(a: int, b: int) -> int:
            return a + b

        result = reg.execute("add", a=3, b=4)
        assert result == 7

    def test_execute_with_retry_success(self):
        from tools.registry import ToolRegistry

        reg = ToolRegistry()
        call_count = [0]

        @reg.register(name="flaky", description="Sometimes fails")
        def flaky():
            call_count[0] += 1
            if call_count[0] < 2:
                raise RuntimeError("transient error")
            return "ok"

        result, is_error = reg.execute_with_retry("flaky", max_retries=3)
        assert is_error is False
        assert result == "ok"
        assert call_count[0] == 2

    def test_execute_with_retry_exhausted(self):
        from tools.registry import ToolRegistry

        reg = ToolRegistry()

        @reg.register(name="broken", description="Always fails")
        def broken():
            raise ValueError("permanent error")

        result, is_error = reg.execute_with_retry("broken", max_retries=2)
        assert is_error is True
        assert "RETRY_EXHAUSTED" in result

    def test_execute_with_retry_not_found(self):
        from tools.registry import ToolRegistry

        reg = ToolRegistry()
        result, is_error = reg.execute_with_retry("nonexistent", max_retries=1)
        assert is_error is True
        assert "NOT_FOUND" in result

    def test_openai_schema(self):
        from tools.registry import ToolRegistry

        reg = ToolRegistry()

        @reg.register(name="test_tool", description="A test tool", parameters={
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
        })
        def test_tool(x: str) -> str:
            return x

        schemas = reg.to_openai_tools()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "test_tool"


# ---------------------------------------------------------------------------
# Strategy memory
# ---------------------------------------------------------------------------

class TestStrategyMemory:
    """Verify StrategyMemory classification and stats."""

    def test_classify_task(self):
        from evolution.strategy_memory import StrategyMemory

        sm = StrategyMemory()
        assert sm.classify_task("Fix the login crash") == "debug"
        assert sm.classify_task("Write a CLI parser") == "code"
        assert sm.classify_task("Refactor the database module") == "refactor"
        assert sm.classify_task("Read config.yaml") == "file"
        assert sm.classify_task("Commit and push") == "git"
        assert sm.classify_task("Search for TODO comments") == "search"

    def test_record_and_stats(self):
        from evolution.strategy_memory import StrategyMemory

        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StrategyMemory(memory_path=str(Path(tmpdir) / "strat.json"))
            sm.record_task_result("debug", success=True, duration=10.0)
            sm.record_task_result("debug", success=False, duration=30.0)

            stats = sm.get_stats()
            assert stats["debug"]["total_tasks"] == 2
            assert stats["debug"]["success_count"] == 1
            assert stats["debug"]["failure_count"] == 1


# ---------------------------------------------------------------------------
# Prompt evolver
# ---------------------------------------------------------------------------

class TestPromptEvolver:
    """Verify PromptEvolver version chain."""

    def test_version_chain(self):
        from evolution.prompt_evolver import PromptEvolver

        with tempfile.TemporaryDirectory() as tmpdir:
            evolver = PromptEvolver(persist_dir=tmpdir)

            # Initial version exists
            history = evolver.get_evolution_history()
            assert len(history) == 1
            assert history[0]["trigger"] == "initial"
            assert history[0]["accepted"] is True

            # Manual override
            evolver.set_prompt("You are a testing assistant.", reason="test")
            assert len(evolver.get_evolution_history()) == 2
            assert "testing" in evolver.get_prompt().lower()

            # Rollback
            evolver.rollback(steps=1)
            history = evolver.get_evolution_history()
            assert len(history) == 3  # initial + manual + rollback
            assert history[-1]["trigger"] == "rollback"

    def test_pending_accept_reject(self):
        from evolution.prompt_evolver import PromptEvolver

        with tempfile.TemporaryDirectory() as tmpdir:
            evolver = PromptEvolver(persist_dir=tmpdir)

            # Use set_prompt to create a pending-like state, then test rollback
            evolver.set_prompt("Version A", reason="test A")
            evolver.set_prompt("Version B", reason="test B")
            assert len(evolver.get_evolution_history()) == 3  # initial + A + B

            # Rollback to A
            evolver.rollback(steps=1)
            history = evolver.get_evolution_history()
            assert history[-1]["trigger"] == "rollback"


# ---------------------------------------------------------------------------
# Memory store
# ---------------------------------------------------------------------------

class TestMemoryStore:
    """Verify MemoryStore conversation and compression."""

    def _make_store(self, tmpdir):
        """Create a MemoryStore with vectors disabled (avoids ChromaDB lock on Windows)."""
        from memory.store import MemoryStore
        return MemoryStore(data_dir=tmpdir, enable_vectors=False)

    def test_conversation_buffer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._make_store(tmpdir)
            store.add_conversation("user", "hello")
            store.add_conversation("assistant", "hi there")

            msgs = store.get_recent_conversation(n=10)
            assert len(msgs) == 2
            assert msgs[0]["role"] == "user"
            assert msgs[1]["role"] == "assistant"

    def test_compress_context_short(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._make_store(tmpdir)
            messages = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
            result = store.compress_context(messages, target_count=30)
            assert len(result) == 10  # no compression needed

    def test_compress_context_long(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._make_store(tmpdir)
            messages = [{"role": "user", "content": f"msg {i}"} for i in range(100)]
            result = store.compress_context(messages, target_count=30)
            assert len(result) == 31  # 1 summary + 30 recent

    def test_experience_recording(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._make_store(tmpdir)
            entry = store.record_experience(
                task="test", category="code", outcome="success",
                solution="worked", tags=["test"],
            )
            assert entry["outcome"] == "success"
            assert store.get_experience_stats()["total"] == 1


# ---------------------------------------------------------------------------
# User preferences
# ---------------------------------------------------------------------------

class TestUserPreferences:
    """Verify UserPreferences signal extraction."""

    def test_learn_from_feedback(self):
        from evolution.user_prefs import UserPreferences

        with tempfile.TemporaryDirectory() as tmpdir:
            prefs = UserPreferences(memory_path=str(Path(tmpdir) / "prefs.json"))
            changes = prefs.learn_from_feedback("I prefer single quotes")
            assert changes.get("quote_style") == "single"

    def test_get_style_prompt(self):
        from evolution.user_prefs import UserPreferences

        with tempfile.TemporaryDirectory() as tmpdir:
            prefs = UserPreferences(memory_path=str(Path(tmpdir) / "prefs.json"))
            prompt = prefs.get_style_prompt()
            assert "indentation" in prompt.lower()
            assert "quotes" in prompt.lower()


# ---------------------------------------------------------------------------
# Tool evolver
# ---------------------------------------------------------------------------

class TestToolEvolver:
    """Verify ToolEvolver pattern detection and code validation."""

    def test_record_and_detect(self):
        from evolution.tool_evolver import ToolEvolver

        with tempfile.TemporaryDirectory() as tmpdir:
            evolver = ToolEvolver(storage_dir=tmpdir)

            # Record a repeating pattern
            for _ in range(5):
                evolver.record_tool_call("read_file", {"path": "test.py"}, True)
                evolver.record_tool_call("write_file", {"path": "test.py"}, True)

            patterns = evolver.detect_patterns(min_count=3)
            assert len(patterns) > 0

    def test_code_validation(self):
        from evolution.tool_evolver import _validate_code

        # Safe code
        ok, errors = _validate_code("def hello():\n    return 'hi'\n")
        assert ok is True
        assert len(errors) == 0

        # Dangerous: exec
        ok, errors = _validate_code("exec('import os')")
        assert ok is False
        assert any("exec" in e for e in errors)

        # Dangerous: __import__
        ok, errors = _validate_code("__import__('os').system('rm -rf /')")
        assert ok is False

        # Dangerous: os.system
        ok, errors = _validate_code("import os\nos.system('ls')")
        assert ok is False

        # Syntax error
        ok, errors = _validate_code("def foo(:\n    pass")
        assert ok is False
        assert any("Syntax" in e for e in errors)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

class TestConfig:
    """Verify config loading works."""

    def test_default_config(self):
        from agent import load_config, DEFAULT_CONFIG

        config = load_config()
        assert "api" in config
        assert "agent" in config
        assert "evolution" in config
        # Model may be overridden by config.json, just check it exists
        assert "model" in config["api"]
        assert isinstance(config["agent"]["max_iterations"], int)
        assert config["agent"]["max_iterations"] > 0

    def test_config_merge(self):
        from agent import _deep_merge

        base = {"a": 1, "b": {"c": 2, "d": 3}}
        override = {"b": {"c": 99}, "e": 5}
        _deep_merge(base, override)
        assert base["a"] == 1
        assert base["b"]["c"] == 99
        assert base["b"]["d"] == 3
        assert base["e"] == 5


# ---------------------------------------------------------------------------
# Tool Forge
# ---------------------------------------------------------------------------

class TestToolForge:
    """Verify ToolForge safety validation and metadata extraction."""

    def test_validate_safe_code(self):
        from tools.forge import _validate_forged_code

        code = textwrap.dedent('''
            def add_numbers(a: int, b: int) -> str:
                """Add two numbers and return the result."""
                return str(a + b)
        ''')
        ok, errors = _validate_forged_code(code)
        assert ok is True
        assert len(errors) == 0

    def test_validate_dangerous_exec(self):
        from tools.forge import _validate_forged_code

        code = 'def bad(): exec("import os")'
        ok, errors = _validate_forged_code(code)
        assert ok is False
        assert any("exec" in e for e in errors)

    def test_validate_dangerous_subprocess(self):
        from tools.forge import _validate_forged_code

        code = 'import subprocess\ndef bad(): subprocess.run(["ls"])'
        ok, errors = _validate_forged_code(code)
        assert ok is False
        assert any("subprocess" in e for e in errors)

    def test_validate_no_function(self):
        from tools.forge import _validate_forged_code

        code = 'x = 42'
        ok, errors = _validate_forged_code(code)
        assert ok is False
        assert any("No public function" in e for e in errors)

    def test_validate_syntax_error(self):
        from tools.forge import _validate_forged_code

        code = 'def bad(:\n    pass'
        ok, errors = _validate_forged_code(code)
        assert ok is False
        assert any("Syntax" in e for e in errors)

    def test_extract_metadata(self):
        from tools.forge import ToolForge

        code = textwrap.dedent('''
            def filter_rows(data: str, min_value: int = 10) -> str:
                """Filter CSV rows where value exceeds minimum."""
                return "filtered"
        ''')

        # Create a minimal forge instance to use _extract_metadata
        class FakeBrain:
            pass
        class FakeRegistry:
            tools = {}
        forge = ToolForge(FakeBrain(), FakeRegistry(), storage_dir="/tmp/test_forge")

        name, desc, params = forge._extract_metadata(code)
        assert name == "filter_rows"
        assert "Filter CSV" in desc
        assert "data" in params["properties"]
        assert "min_value" in params["properties"]
        assert "data" in params["required"]
        assert "min_value" not in params["required"]  # has default

    def test_extract_code_from_markdown(self):
        from tools.forge import ToolForge

        class FakeBrain:
            pass
        class FakeRegistry:
            tools = {}
        forge = ToolForge(FakeBrain(), FakeRegistry(), storage_dir="/tmp/test_forge")

        response = 'Here is the code:\n```python\ndef hello():\n    return "hi"\n```\nDone.'
        code = forge._extract_code(response)
        assert "def hello()" in code
        assert "return" in code
