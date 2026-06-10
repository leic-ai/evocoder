"""
SubAgentManager for EvoCoder

Manages specialized sub-agents that handle delegated tasks in isolation.
Each agent type has its own system prompt, tool set, and iteration budget.

Agent types:
  code     — Generate, modify, and refactor code
  debug    — Diagnose and fix bugs, analyze stack traces
  research — Web search, documentation lookup, information gathering
  file     — File system operations, reading, writing, organizing
  general  — Catch-all for tasks that don't fit other categories

Key features:
  - delegate() creates a sub-agent with its own Brain + ToolRegistry
  - delegate_parallel() fans out independent tasks via ThreadPoolExecutor
  - _run_agent_loop() injects platform prompt into every sub-agent system prompt
  - Thread-safe: _lock guards shared state, _brain_lock serializes API calls
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

from brain.engine import Brain
from tools.registry import ToolRegistry
from tools.builtin import register_builtins
from utils.platform import get_platform_prompt

logger = logging.getLogger("evocoder.subagents")


# ---------------------------------------------------------------------------
# Agent type definitions
# ---------------------------------------------------------------------------

class AgentType(str, Enum):
    """Enumeration of available sub-agent specializations."""
    CODE = "code"
    DEBUG = "debug"
    RESEARCH = "research"
    FILE = "file"
    GENERAL = "general"


# Agent configuration: system_prompt, allowed tool names, max_iterations
_AGENT_CONFIGS: Dict[AgentType, Dict[str, Any]] = {
    AgentType.CODE: {
        "system_prompt": (
            "You are a specialized coding sub-agent inside EvoCoder.\n"
            "Your job is to write, modify, and refactor code.\n"
            "Think step-by-step before writing code. Prefer clean, well-structured solutions.\n"
            "When modifying existing code, read it first to understand the context.\n"
            "Use the provided tools to read files, write files, and run commands.\n"
            "Report your work concisely: what you did, any issues encountered, and the result.\n"
        ),
        "tools": [
            "read_file", "write_file", "edit_file",
            "run_command", "list_directory", "search_code",
            "git_status", "git_diff",
        ],
        "max_iterations": 15,
    },
    AgentType.DEBUG: {
        "system_prompt": (
            "You are a specialized debugging sub-agent inside EvoCoder.\n"
            "Your job is to diagnose bugs, analyze errors, and fix them.\n"
            "Start by reading relevant code and error messages.\n"
            "Form a hypothesis, verify it, then apply the minimal fix.\n"
            "Use shell commands to reproduce issues when needed.\n"
            "Report: root cause, fix applied, and verification result.\n"
        ),
        "tools": [
            "read_file", "write_file", "edit_file",
            "run_command", "list_directory", "search_code",
            "git_diff", "git_log",
        ],
        "max_iterations": 20,
    },
    AgentType.RESEARCH: {
        "system_prompt": (
            "You are a specialized research sub-agent inside EvoCoder.\n"
            "Your job is to gather information: search the web, fetch pages,\n"
            "read documentation, and summarize findings.\n"
            "Be thorough but concise. Cite sources with URLs.\n"
            "Return structured findings that the parent agent can act on.\n"
        ),
        "tools": [
            "web_search", "web_fetch", "read_file",
            "run_command", "http_get",
        ],
        "max_iterations": 10,
    },
    AgentType.FILE: {
        "system_prompt": (
            "You are a specialized file-operations sub-agent inside EvoCoder.\n"
            "Your job is to read, write, organize, and manage files and directories.\n"
            "Be careful with destructive operations — confirm file existence before overwriting.\n"
            "Report what files you touched and any errors encountered.\n"
        ),
        "tools": [
            "read_file", "write_file", "edit_file",
            "list_directory", "search_code",
            "run_command",
        ],
        "max_iterations": 10,
    },
    AgentType.GENERAL: {
        "system_prompt": (
            "You are a general-purpose sub-agent inside EvoCoder.\n"
            "You have access to all available tools. Handle the delegated task\n"
            "methodically: break it into steps, execute them, and report results.\n"
            "If the task is ambiguous, make reasonable assumptions and state them.\n"
        ),
        "tools": [
            "read_file", "write_file", "edit_file",
            "run_command", "list_directory", "search_code",
            "web_search", "web_fetch", "http_get",
            "git_status", "git_diff", "git_log",
        ],
        "max_iterations": 15,
    },
}


# ---------------------------------------------------------------------------
# SubAgentResult
# ---------------------------------------------------------------------------

@dataclass
class SubAgentResult:
    """Outcome of a single sub-agent delegation."""

    agent_id: str
    agent_type: AgentType
    task: str
    success: bool
    output: str
    error: Optional[str] = None
    iterations_used: int = 0
    elapsed_seconds: float = 0.0
    tool_calls_made: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        """One-line summary for logging."""
        status = "OK" if self.success else "FAIL"
        return (
            f"[{self.agent_id}] {self.agent_type.value} | {status} | "
            f"{self.iterations_used} iters, {self.elapsed_seconds:.1f}s | "
            f"{self.task[:60]}..."
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict for logging or persistence."""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type.value,
            "task": self.task,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "iterations_used": self.iterations_used,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "tool_calls_made": self.tool_calls_made,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# SubAgentManager
# ---------------------------------------------------------------------------

class SubAgentManager:
    """
    Creates and manages sub-agents for task delegation.

    Thread-safety:
      - `_lock` protects shared mutable state (active_agents, result_log).
      - `_brain_lock` serializes API calls when Brain instances share the
        same API key (rate-limit protection).

    Usage::

        manager = SubAgentManager()

        # Single delegation
        result = manager.delegate("Fix the import error in main.py", agent_type=AgentType.DEBUG)

        # Parallel delegation
        results = manager.delegate_parallel([
            ("Analyze the auth module", AgentType.RESEARCH),
            ("Write unit tests for utils.py", AgentType.CODE),
        ])
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        max_workers: int = 4,
        verbose: bool = False,
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._max_workers = max_workers
        self._verbose = verbose

        # Thread-safe shared state
        self._lock = Lock()
        self._brain_lock = Lock()  # serializes Brain API calls
        self._active_agents: Dict[str, str] = {}  # agent_id -> task
        self._result_log: List[SubAgentResult] = []

        logger.info(
            "SubAgentManager initialized (max_workers=%d, model=%s)",
            max_workers, model or "default",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def delegate(
        self,
        task: str,
        agent_type: AgentType = AgentType.GENERAL,
        extra_context: Optional[str] = None,
        max_iterations: Optional[int] = None,
        tools_filter: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SubAgentResult:
        """
        Delegate a task to a single sub-agent and wait for the result.

        Args:
            task: Natural language description of what the sub-agent should do.
            agent_type: Which specialization to use.
            extra_context: Additional context injected into the system prompt.
            max_iterations: Override the default iteration budget.
            tools_filter: Restrict to a subset of the agent's default tools.
            metadata: Arbitrary metadata attached to the result.

        Returns:
            SubAgentResult with the outcome.
        """
        agent_id = self._make_agent_id(agent_type)
        config = _AGENT_CONFIGS[agent_type]

        with self._lock:
            self._active_agents[agent_id] = task

        result = self._run_agent_loop(
            agent_id=agent_id,
            agent_type=agent_type,
            task=task,
            system_prompt=config["system_prompt"],
            allowed_tools=tools_filter or config["tools"],
            max_iterations=max_iterations or config["max_iterations"],
            extra_context=extra_context,
            metadata=metadata or {},
        )

        with self._lock:
            self._active_agents.pop(agent_id, None)
            self._result_log.append(result)

        if self._verbose:
            logger.info(result.summary)

        return result

    def delegate_parallel(
        self,
        tasks: List[tuple],
        extra_context: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[SubAgentResult]:
        """
        Delegate multiple independent tasks in parallel.

        Args:
            tasks: List of (task_description, AgentType) tuples.
            extra_context: Shared context injected into every sub-agent.
            metadata: Shared metadata attached to every result.

        Returns:
            List of SubAgentResult, one per task, in submission order.
        """
        if not tasks:
            return []

        results: List[SubAgentResult] = [None] * len(tasks)  # type: ignore[list-item]

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            future_to_idx = {
                pool.submit(
                    self.delegate,
                    task=task_desc,
                    agent_type=agent_type,
                    extra_context=extra_context,
                    metadata=metadata,
                ): idx
                for idx, (task_desc, agent_type) in enumerate(tasks)
            }

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    task_desc, agent_type = tasks[idx]
                    results[idx] = SubAgentResult(
                        agent_id=f"failed_{idx}",
                        agent_type=agent_type,
                        task=task_desc,
                        success=False,
                        output="",
                        error=f"Sub-agent execution failed: {exc}",
                        metadata=metadata or {},
                    )

        return results

    @property
    def active_agents(self) -> Dict[str, str]:
        """Snapshot of currently running agents (agent_id -> task)."""
        with self._lock:
            return dict(self._active_agents)

    @property
    def result_log(self) -> List[SubAgentResult]:
        """All completed sub-agent results from this manager instance."""
        with self._lock:
            return list(self._result_log)

    def stats(self) -> Dict[str, Any]:
        """Aggregate statistics over all completed delegations."""
        with self._lock:
            results = list(self._result_log)

        total = len(results)
        if total == 0:
            return {"total": 0, "success": 0, "failure": 0, "by_type": {}}

        by_type: Dict[str, Dict[str, Any]] = {}
        for r in results:
            t = r.agent_type.value
            if t not in by_type:
                by_type[t] = {"count": 0, "success": 0, "total_iterations": 0, "total_seconds": 0.0}
            by_type[t]["count"] += 1
            if r.success:
                by_type[t]["success"] += 1
            by_type[t]["total_iterations"] += r.iterations_used
            by_type[t]["total_seconds"] += r.elapsed_seconds

        return {
            "total": total,
            "success": sum(1 for r in results if r.success),
            "failure": sum(1 for r in results if not r.success),
            "active": len(self._active_agents),
            "by_type": by_type,
        }

    def list_types(self) -> List[Dict[str, Any]]:
        """List available sub-agent types and their capabilities."""
        types = []
        for agent_type, config in _AGENT_CONFIGS.items():
            types.append({
                "name": agent_type.value,
                "description": config["system_prompt"].split("\n")[0][:60],
                "tools_count": len(config["tools"]),
                "max_iterations": config["max_iterations"],
                "icon": {"code": "💻", "debug": "🔍", "research": "📚", "file": "📁", "general": "🔧"}.get(agent_type.value, "🤖"),
            })
        return types

    # ------------------------------------------------------------------
    # Internal: agent loop
    # ------------------------------------------------------------------

    def _run_agent_loop(
        self,
        agent_id: str,
        agent_type: AgentType,
        task: str,
        system_prompt: str,
        allowed_tools: List[str],
        max_iterations: int,
        extra_context: Optional[str],
        metadata: Dict[str, Any],
    ) -> SubAgentResult:
        """
        Execute the think-act-observe loop for a sub-agent.

        Uses native OpenAI tool_calls for reliable tool execution.
        Creates an isolated Brain + ToolRegistry, injects the platform prompt,
        and runs up to max_iterations rounds of LLM reasoning + tool execution.
        """
        import json as _json
        start_time = time.time()

        # Build the full system prompt with platform awareness
        full_system_prompt = self._build_system_prompt(
            system_prompt, extra_context
        )

        # Create isolated Brain for this sub-agent
        brain = Brain(
            api_key=self._api_key,
            base_url=self._base_url,
            model=self._model,
            system_prompt=full_system_prompt,
        )

        # Create tool registry scoped to allowed tools
        registry = ToolRegistry()
        register_builtins(registry)
        tool_schemas = [
            registry.get(name).to_openai_schema()
            for name in allowed_tools
            if registry.get(name) is not None
        ]

        # The initial prompt: the task itself
        current_prompt = (
            f"=== DELEGATED TASK ({agent_type.value}) ===\n"
            f"{task}\n\n"
            f"Use the available tools to complete this task. "
            f"When done, provide a final summary of what you accomplished."
        )

        iterations_used = 0
        tool_calls_made = 0
        last_output = ""
        error_msg: Optional[str] = None

        try:
            messages = [{"role": "user", "content": current_prompt}]

            for iteration in range(1, max_iterations + 1):
                iterations_used = iteration

                # Think: get LLM response with native tool_calls
                with self._brain_lock:
                    response = brain.think(
                        messages,
                        tools=tool_schemas if tool_schemas else None,
                    )

                response_text = response.content if hasattr(response, 'content') else str(response)
                last_output = response_text

                # Use native tool_calls (not regex parsing)
                if hasattr(response, 'tool_calls') and response.tool_calls:
                    # Append assistant message with tool calls
                    messages.append({
                        "role": "assistant",
                        "content": response_text,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in response.tool_calls
                        ],
                    })

                    # Execute each tool call and append results
                    for tc in response.tool_calls:
                        tool_name = tc.function.name
                        try:
                            tool_args = _json.loads(tc.function.arguments)
                        except _json.JSONDecodeError:
                            tool_args = {"raw": tc.function.arguments}

                        try:
                            result = registry.execute(tool_name, **tool_args)
                        except Exception as tool_exc:
                            result = f"[ERR:{type(tool_exc).__name__}] {tool_exc}"

                        tool_calls_made += 1

                        # Append as tool role message
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": str(result)[:4000],
                        })
                else:
                    # No tool calls = agent is done
                    break

        except Exception as exc:
            error_msg = str(exc)
            logger.error("Sub-agent %s error: %s", agent_id, exc)

        elapsed = time.time() - start_time
        success = error_msg is None and iterations_used <= max_iterations

        return SubAgentResult(
            agent_id=agent_id,
            agent_type=agent_type,
            task=task,
            success=success,
            output=last_output,
            error=error_msg,
            iterations_used=iterations_used,
            elapsed_seconds=round(elapsed, 2),
            tool_calls_made=tool_calls_made,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Internal: system prompt construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_system_prompt(
        agent_prompt: str,
        extra_context: Optional[str],
    ) -> str:
        """
        Assemble the full system prompt for a sub-agent.

        Injects the platform prompt so sub-agents are OS-aware, and appends
        any extra context provided by the caller.
        """
        platform_prompt = get_platform_prompt()

        parts = [
            agent_prompt.rstrip(),
            "",
            "---",
            platform_prompt.rstrip(),
        ]

        if extra_context:
            parts.extend([
                "",
                "---",
                "ADDITIONAL CONTEXT:",
                extra_context.rstrip(),
            ])

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Internal: helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_agent_id(agent_type: AgentType) -> str:
        """Generate a unique agent ID like 'code_a3f2b1'."""
        short_id = uuid.uuid4().hex[:6]
        return f"{agent_type.value}_{short_id}"

    def __repr__(self) -> str:
        with self._lock:
            active = len(self._active_agents)
            total = len(self._result_log)
        return f"SubAgentManager(active={active}, completed={total})"
