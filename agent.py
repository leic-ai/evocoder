"""Agent — EvoCoder core loop

The main agent orchestrates the think-act-learn cycle:

1. **Perceive**: Load user input + recall relevant memories + project context
2. **Think**: LLM reasons about the task, selects tools
3. **Act**: Execute tools, collect results
4. **Learn**: Record outcomes, evolve prompts, update strategies

Two execution modes:
  - `run()`         — synchronous, returns final response
  - `run_stream()`  — generator, yields AgentEvent objects for real-time streaming

Memory safety:
  - Tool results are truncated to 2000 chars to prevent context overflow
  - Messages are compressed mid-loop when count exceeds 40
  - Conversation buffer is a ring buffer (deque, 200 max)

Evolution integration:
  - EvolutionTracker records every task outcome
  - PromptEvolver triggers on high failure rates
  - ErrorMemory suggests fixes for known error patterns
  - ToolEvolver detects repetitive tool patterns and generates composite tools
"""

import json
import time as _time_module
from pathlib import Path
from brain import Brain
from memory import MemoryStore
from tools import ToolRegistry, register_builtins
from tools.forge import ToolForge
from tools.scoreboard import ToolScoreboard
from evolution import (
    EvolutionTracker, PromptEvolver,
    ErrorMemory, UserPreferences, StrategyMemory,
    ToolEvolver,
)
from evolution.verifier import EvolutionVerifier
from memory.long_term import LongTermMemory
from sdd import SDDFlow
from subagents.manager import SubAgentManager


APP_ROOT = Path(__file__).resolve().parent


DEFAULT_CONFIG = {
    "api": {
        "base_url": "https://api.xiaomimimo.com/v1",
        "model": "mimo-v2.5-pro",
        "max_retries": 3,
        "retry_delay": 2,
        "timeout": 120,
    },
    "agent": {
        "max_iterations": 25,
        "workspace": ".evocoder",
    },
    "evolution": {
        "failure_threshold": 3,
        "auto_accept_confidence": 0.7,
    },
    "task_categories": {
        "code": {"keywords": ["write", "code", "function", "class", "implement", "create", "build", "script"]},
        "debug": {"keywords": ["bug", "error", "fix", "exception", "traceback", "crash", "fail"]},
        "refactor": {"keywords": ["refactor", "optimize", "improve", "rewrite", "clean", "performance"]},
        "file": {"keywords": ["read", "file", "view", "show", "list", "directory", "open"]},
        "git": {"keywords": ["git", "commit", "push", "pull", "branch", "merge", "status"]},
        "search": {"keywords": ["search", "find", "grep", "look", "locate", "where"]},
    },
}


def load_config(workspace: str = ".evocoder") -> dict:
    config = DEFAULT_CONFIG.copy()
    for path in [Path(workspace) / "config.json", APP_ROOT / "config.json"]:
        if path.exists():
            try:
                user_config = json.loads(path.read_text(encoding="utf-8"))
                _deep_merge(config, user_config)
                break
            except Exception:
                pass
    return config


def _deep_merge(base: dict, override: dict):
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


class EvoCoder:
    """Self-evolving programming agent with 3-layer evolution"""

    def __init__(self, api_key: str, base_url: str = None, model: str = None,
                 workspace: str = None, config: dict = None):
        self.config = config or load_config(workspace or ".evocoder")
        api_cfg = self.config["api"]
        agent_cfg = self.config["agent"]

        base_url = base_url or api_cfg["base_url"]
        model = model or api_cfg["model"]
        self.workspace = workspace or agent_cfg["workspace"]

        self.brain = Brain(
            api_key=api_key, base_url=base_url, model=model,
            max_retries=api_cfg.get("max_retries", 3),
            retry_delay=api_cfg.get("retry_delay", 2),
            timeout=api_cfg.get("timeout", 120),
        )
        self.memory = MemoryStore(data_dir=f"{self.workspace}/memory", enable_vectors=False)
        self.registry = ToolRegistry()
        register_builtins(self.registry)
        self.max_iterations = agent_cfg["max_iterations"]

        # ── Evolution System ──
        evo_cfg = self.config["evolution"]
        evo_dir = f"{self.workspace}/evolution"
        self.tracker = EvolutionTracker(history_dir=evo_dir)

        # Layer 1: Error pitfall memory
        self.error_memory = ErrorMemory(memory_path=f"{self.workspace}/error_memory.json")

        # Layer 2: User preference learning
        self.user_prefs = UserPreferences(memory_path=f"{self.workspace}/user_prefs.json")

        # Layer 3: Task strategy optimization
        self.strategy_memory = StrategyMemory(memory_path=f"{self.workspace}/strategy_memory.json")

        # Prompt evolution (depends on layers 1-3)
        self.evolver = PromptEvolver(
            tracker=self.tracker,
            error_memory=self.error_memory,
            strategy_memory=self.strategy_memory,
            user_prefs=self.user_prefs,
            brain=self.brain,
            persist_dir=evo_dir,
        )
        self.evo_threshold = evo_cfg["failure_threshold"]
        self.evo_confidence = evo_cfg["auto_accept_confidence"]

        # ── Long-term Memory ──
        self.long_term = LongTermMemory(data_dir=f"{self.workspace}/memory")

        # ── Tool Evolution ──
        self.tool_evolver = ToolEvolver(
            storage_dir=f"{self.workspace}/evolved_tools",
        )

        # ── Tool Forge (dynamic tool creation) ──
        self.tool_forge = ToolForge(
            brain=self.brain,
            registry=self.registry,
            storage_dir=f"{self.workspace}/forged_tools",
        )

        # ── Tool Scoreboard (performance tracking) ──
        self.scoreboard = ToolScoreboard(
            data_dir=f"{self.workspace}/scoreboard",
        )

        # ── Evolution Verifier (closes the evolution loop) ──
        self.verifier = EvolutionVerifier(
            tracker=self.tracker,
            prompt_evolver=self.evolver,
            scoreboard=self.scoreboard,
            strategy_memory=self.strategy_memory,
            data_dir=evo_dir,
        )

        # ── SDD Flow ──
        self.sdd = SDDFlow(
            api_key=api_key, base_url=base_url,
            model=model, workspace=self.workspace,
        )

        # ── SubAgent System ──
        self.subagents = SubAgentManager(
            api_key=api_key, base_url=base_url, model=model,
        )
        self._register_subagent_tools()
        self._register_forge_tools()

    def _register_subagent_tools(self):
        """Register sub-agent delegation tools."""

        def delegate_to_subagent(agent_type: str, task: str) -> str:
            result = self.subagents.delegate(agent_type, task)
            return result

        def delegate_parallel(delegations: str) -> str:
            try:
                tasks = json.loads(delegations)
            except json.JSONDecodeError as e:
                return f"[ERR:JSON_ERROR] {e}"
            results = self.subagents.delegate_parallel(tasks)
            return json.dumps(results, ensure_ascii=False, indent=2)

        def list_subagent_types() -> str:
            types = self.subagents.list_types()
            lines = []
            for t in types:
                lines.append(f"  {t['icon']} {t['name']}: {t['description']}")
            return "\n".join(lines)

        self.registry.register_function(
            func=delegate_to_subagent,
            name="delegate_to_subagent",
            description="Delegate a subtask to a specialized sub-agent. Types: code, debug, research, file, general.",
            parameters={
                "type": "object",
                "properties": {
                    "agent_type": {"type": "string", "description": "Sub-agent type", "enum": ["code", "debug", "research", "file", "general"]},
                    "task": {"type": "string", "description": "Task to delegate"},
                },
                "required": ["agent_type", "task"],
            },
            category="subagent",
        )

        self.registry.register_function(
            func=delegate_parallel,
            name="delegate_parallel",
            description="Delegate multiple tasks to sub-agents in parallel. Input: JSON array of {agent_type, task}.",
            parameters={
                "type": "object",
                "properties": {
                    "delegations": {"type": "string", "description": "JSON array of {agent_type, task}"},
                },
                "required": ["delegations"],
            },
            category="subagent",
        )

        self.registry.register_function(
            func=list_subagent_types,
            name="list_subagent_types",
            description="List available sub-agent types and their capabilities.",
            parameters={"type": "object", "properties": {}, "required": []},
            category="subagent",
        )

    def _register_forge_tools(self):
        """Register tool forging capabilities."""

        def forge_tool(task: str, context: str = "") -> str:
            """Create a new tool at runtime when no existing tool can handle the task."""
            result = self.tool_forge.forge_tool(task=task, context=context)
            if result["success"]:
                return json.dumps({
                    "status": "created",
                    "tool_name": result["tool_name"],
                    "description": result["description"],
                }, ensure_ascii=False)
            return f"[ERR:FORGE_FAILED] {result['error']}"

        def refine_tool(tool_name: str, feedback: str, task: str = "") -> str:
            """Improve an existing tool based on usage feedback."""
            result = self.tool_forge.refine_tool(
                tool_name=tool_name, feedback=feedback, task=task,
            )
            if result["success"]:
                return json.dumps({
                    "status": "refined",
                    "tool_name": result["tool_name"],
                }, ensure_ascii=False)
            return f"[ERR:REFINE_FAILED] {result['error']}"

        def list_forged_tools() -> str:
            """List all dynamically forged tools."""
            tools = self.tool_forge.get_forged_tools()
            if not tools:
                return "No forged tools yet."
            lines = []
            for t in tools:
                lines.append(f"  - {t['name']}: {t['description'][:60]}")
            return "\n".join(lines)

        self.registry.register_function(
            func=forge_tool,
            name="forge_tool",
            description=(
                "Create a new tool at runtime when no existing tool can handle the task. "
                "Use this when you need a capability that doesn't exist yet."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "What the tool should do"},
                    "context": {"type": "string", "description": "Why existing tools are insufficient"},
                },
                "required": ["task"],
            },
            category="forge",
        )

        self.registry.register_function(
            func=refine_tool,
            name="refine_tool",
            description=(
                "Improve an existing tool based on feedback. "
                "Use when a tool works but has issues (wrong output, missing edge cases, etc.)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string", "description": "Name of the tool to refine"},
                    "feedback": {"type": "string", "description": "What's wrong and what needs to change"},
                    "task": {"type": "string", "description": "Task context where the tool was used"},
                },
                "required": ["tool_name", "feedback"],
            },
            category="forge",
        )

        self.registry.register_function(
            func=list_forged_tools,
            name="list_forged_tools",
            description="List all dynamically forged tools.",
            parameters={"type": "object", "properties": {}, "required": []},
            category="forge",
        )

    def _classify_task(self, task: str) -> str:
        category = self.strategy_memory.classify_task(task)
        if category != "general":
            return category
        task_lower = task.lower()
        categories = self.config.get("task_categories", {})
        for cat, cfg in categories.items():
            if any(w in task_lower for w in cfg.get("keywords", [])):
                return cat
        return "general"

    def _build_system_prompt(self, category: str) -> str:
        """Build system prompt with all evolution layers injected."""
        sections = []

        # Base prompt (from brain)
        from brain.engine import get_system_prompt
        sections.append(get_system_prompt())

        # Long-term memory context
        memory_context = self.long_term.get_context()
        if memory_context:
            sections.append(memory_context)

        # Load skills if available
        skills_path = APP_ROOT / "SKILLS.md"
        if skills_path.exists():
            try:
                skills_content = skills_path.read_text(encoding="utf-8")
                if len(skills_content) < 3000:
                    sections.append(f"[Skills]\n{skills_content}")
                else:
                    lines = skills_content.split("\n")
                    compact = []
                    in_table = False
                    for line in lines:
                        if "## Skill" in line or "### Rules" in line or "### Process" in line:
                            compact.append(line)
                        elif line.startswith("| ") and "Tool" in line:
                            in_table = True
                            compact.append(line)
                        elif in_table and line.startswith("|"):
                            compact.append(line)
                        elif in_table and not line.startswith("|"):
                            in_table = False
                        elif "The Iron Law" in line or "NO FIXES" in line:
                            compact.append(line)
                    sections.append("[Skills - Key Rules]\n" + "\n".join(compact[:30]))
            except Exception:
                pass

        # Layer 1: Pitfall warnings
        pitfall_summary = self.error_memory.get_pitfall_summary()
        if pitfall_summary and pitfall_summary.total_errors > 0:
            lines = [f"[Known Pitfalls - {pitfall_summary.total_errors} errors recorded]"]
            for etype, count in pitfall_summary.error_breakdown.items():
                lines.append(f"  - {etype}: {count} occurrences")
            for tip in pitfall_summary.tips[:3]:
                lines.append(f"  - Tip: {tip}")
            sections.append("\n".join(lines))

        # Layer 2: User preferences
        style_prompt = self.user_prefs.get_style_prompt()
        if style_prompt and self.user_prefs.prefs["task_count"] > 0:
            sections.append(style_prompt)

        # Layer 3: Task strategy
        strategy_prompt = self.strategy_memory.get_strategy_prompt(category)
        if strategy_prompt:
            sections.append(f"[Task Strategy - {category}]\n{strategy_prompt}")

        # Tool performance context (helps LLM choose better tools)
        scoreboard_context = self.scoreboard.get_context_for_llm(category)
        if scoreboard_context:
            sections.append(scoreboard_context)

        # Evolved prompt override (if exists)
        evolved = self.evolver.get_prompt(include_style=False)
        if evolved:
            sections.append(f"[Evolved System Prompt]\n{evolved}")

        return "\n\n".join(sections)

    def _self_reflect(self, task: str, code_generated: str, success: bool,
                      error: str = "") -> dict:
        feedback = "succeeded" if success else f"failed: {error}"
        prompt = f"""You are reflecting on your own performance as a programming assistant.

Task: {task}
Result: {feedback}
Code/output generated (excerpt): {code_generated[:500]}

Answer in this exact format:
SUCCESS_PATTERN: <what worked well, if anything>
ERROR_PATTERN: <what went wrong, if anything>
IMPROVEMENT: <how to do better next time>
PITFALL: <error type>|<code feature>|<correct fix> (only if failed)"""

        try:
            response = self.brain.think(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            return {"reflection": content, "success": success}
        except Exception:
            return {"reflection": "", "success": success}

    def _parse_reflection(self, text: str) -> dict:
        result = {"success_pattern": "", "error_pattern": "", "improvement": "", "pitfall": ""}
        if not text:
            return result
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("SUCCESS_PATTERN:"):
                result["success_pattern"] = line[len("SUCCESS_PATTERN:"):].strip()
            elif line.startswith("ERROR_PATTERN:"):
                result["error_pattern"] = line[len("ERROR_PATTERN:"):].strip()
            elif line.startswith("IMPROVEMENT:"):
                result["improvement"] = line[len("IMPROVEMENT:"):].strip()
            elif line.startswith("PITFALL:"):
                result["pitfall"] = line[len("PITFALL:"):].strip()
        return result

    def run(self, user_input: str) -> str:
        """Execute one full Agent loop with 3-layer evolution.

        Flow:
          1. Classify task → build system prompt with category-specific strategy
          2. Recall similar past experiences for context
          3. Loop up to max_iterations:
             a. LLM thinks → picks tool(s)
             b. Execute tools → append results to messages
             c. Compress context if messages > 40 (prevents MemoryError)
             d. If no tool calls → final response
          4. Record outcome → trigger evolution if failure threshold met

        Args:
            user_input: The user's task description.

        Returns:
            The agent's final text response.
        """
        self.long_term.update_user()
        category = self._classify_task(user_input)
        system_prompt = self._build_system_prompt(category)
        self.brain.system_prompt = system_prompt

        prompt_version = f"v{len(self.evolver.get_evolution_history())}"
        task_record = self.tracker.start_task(
            category=category, description=user_input,
        )
        task_id = task_record.task_id

        # Get strategy prompt for this category
        strategy_prompt = self.strategy_memory.get_strategy_prompt(category)
        self.memory.add_conversation("user", user_input)

        experiences = self.memory.get_similar_experiences(user_input)
        context_prefix = ""
        if experiences:
            context_prefix = "\n\n[Related experience]\n"
            for exp in experiences[:3]:
                outcome = exp.get("outcome", "unknown")
                status = "[OK]" if outcome == "success" else "[FAIL]"
                context_prefix += f"{status} {exp.get('task', 'N/A')} -> {outcome}\n"

        messages = self.memory.get_recent_conversation()

        # Compress context if conversation is too long
        if len(messages) > 50:
            messages = self.memory.compress_context(
                messages, target_count=30, brain=self.brain
            )

        if context_prefix:
            messages[-1] = {"role": "user", "content": messages[-1]["content"] + context_prefix}

        tools = self.registry.to_openai_tools()

        iteration = 0
        final_response = ""
        error_msg = ""
        all_tool_calls = []
        total_think_time = 0.0
        total_tokens_in = 0
        total_tokens_out = 0

        while iteration < self.max_iterations:
            iteration += 1
            import time as _time

            # Thinking visualization
            print(f"\n{'─'*50}")
            print(f"  [Step {iteration}] 🤔 Thinking...")
            start_think = _time.time()

            response = self.brain.think(messages, tools if tools else None)

            think_time = _time.time() - start_think
            total_think_time += think_time

            # Track tokens from response
            if hasattr(response, '_usage'):
                total_tokens_in += response._usage.get('prompt_tokens', 0)
                total_tokens_out += response._usage.get('completion_tokens', 0)

            if not response.tool_calls:
                final_response = response.content or ""
                self.memory.add_conversation("assistant", final_response)
                self.tracker.log_step(
                    task_id=task_id, action="final_response",
                    details={"result": final_response[:500]},
                )
                break

            print(f"{'─'*50}")
            print(f"  [Step {iteration}] ⚡ Thought in {think_time:.1f}s")
            if response.content:
                print(f"  >> {response.content[:200]}")

            messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    } for tc in response.tool_calls
                ],
            })

            for tc in response.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {"raw": tc.function.arguments}
                all_tool_calls.append(tool_name)

                hints = self.error_memory.suggest_fix(json.dumps(tool_args))
                if hints:
                    hint = hints[0]
                    print(f"  [Pitfall Warning] Known issue: {hint.error_type} -> {hint.attempted_solution[:80]}")

                print(f"  >> Tool: {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:100]})")

                result, is_error = self.registry.execute_with_retry(
                    tool_name, self.brain, max_retries=2, **tool_args
                )

                if len(result) > 2000:
                    result = result[:2000] + "\n...(truncated)"

                print(f"  >> Result: {result[:200]}{'...' if len(result) > 200 else ''}")

                if is_error:
                    code_for_memory = tool_args.get("content") or tool_args.get("new_string") or json.dumps(tool_args)
                    self.error_memory.record_failure(
                        task=user_input[:200],
                        error_msg=result,
                        attempted_solution=code_for_memory[:300],
                    )

                    # Suggest forging a new tool if this one is RETRY_EXHAUSTED
                    if "RETRY_EXHAUSTED" in result:
                        forge_hint = (
                            f"\n[Hint: Tool '{tool_name}' failed after retries. "
                            f"You can call forge_tool() to create a new tool for this task, "
                            f"or try a different approach.]"
                        )
                        result = result + forge_hint

                self.tool_evolver.record_tool_call(tool_name, tool_args, not is_error)

                # Record to scoreboard for adaptive tool selection
                self.scoreboard.record(
                    tool_name=tool_name,
                    success=not is_error,
                    duration_ms=0,  # duration tracked at higher level
                    category=category,
                    error=result[:200] if is_error else "",
                    task=user_input[:100],
                )

                self.tracker.log_step(
                    task_id=task_id, action="tool_call",
                    details={"tool_name": tool_name, "tool_args": tool_args, "result": result[:500]},
                    tool=tool_name, is_error=is_error,
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

            # 循环内压缩：消息太多时压缩旧消息，防止内存溢出
            if len(messages) > 40:
                messages = self.memory.compress_context(
                    messages, target_count=25, brain=self.brain
                )

        else:
            final_response = "[WARN] Max iterations reached. Task may be incomplete."
            error_msg = "max_iterations_reached"
            self.memory.add_conversation("assistant", final_response)

        success = not error_msg and "[WARN]" not in final_response

        tools_used = list(set(all_tool_calls))
        self.memory.record_experience(
            task=user_input,
            category=category,
            outcome="success" if success else "failure",
            solution=final_response[:500],
            errors=[error_msg] if error_msg else None,
            tags=tools_used,
        )

        from evolution.tracker import TaskStatus
        status = TaskStatus.SUCCESS if success else TaskStatus.FAILURE
        self.tracker.end_task(task_id=task_id, status=status, result=final_response[:500])

        self.strategy_memory.record_task_result(
            category=category, success=success,
            task_description=user_input[:200],
        )

        strategy_stats = self.strategy_memory.get_stats()
        if not success or (strategy_stats.get(category, {}).get("total_tasks", 0) % 5 == 0):
            print(f"\n  [Self-Reflect] Analyzing performance...")
            reflection = self._self_reflect(user_input, final_response, success, error_msg)
            parsed = self._parse_reflection(reflection.get("reflection", ""))

            if parsed["pitfall"]:
                parts = parsed["pitfall"].split("|")
                if len(parts) >= 3:
                    self.error_memory.record_failure(
                        code_snippet=final_response[:200],
                        error_msg=parts[0],
                        fix_applied=parts[2],
                        task=user_input[:200],
                    )

            if success and final_response:
                self.user_prefs.learn_from_code(final_response)

        if not success and self.tracker.should_evolve():
            print(f"\n  [Evolution] {category} tasks need evolution, analyzing...")
            self._try_evolve(category)

        patterns = self.tool_evolver.detect_patterns()
        if patterns:
            print(f"\n  [Tool Evolution] Detected {len(patterns)} patterns!")
            for p in patterns:
                print(f"    - {p['pattern']}")

        self.long_term.add_session(
            summary=f"[{category}] {user_input[:100]} → {final_response[:100]}",
            tags=[category],
        )

        # Print summary with thinking time and token usage
        print(f"\n{'─'*50}")
        print(f"  📊 Summary")
        print(f"  ⏱️  Think time: {total_think_time:.1f}s")
        print(f"  📥 Tokens in: {total_tokens_in:,}")
        print(f"  📤 Tokens out: {total_tokens_out:,}")
        if total_think_time > 0:
            print(f"  ⚡ Speed: {total_tokens_out/total_think_time:.0f} tok/s")
        print(f"{'─'*50}")

        return final_response

    def run_stream(self, user_input: str):
        """Execute one full Agent loop with true token-level streaming.

        Uses brain.think_stream() to yield individual tokens in real-time,
        then processes tool calls after the full response is assembled.

        Usage:
            for event in agent.run_stream("Write a fibonacci function"):
                if event.type == EventType.CONTENT_TOKEN:
                    print(event.data["token"], end="", flush=True)
                elif event.type == EventType.TOOL_CALL:
                    print(f"\\n  Calling {event.data['name']}...")
        """
        from agent_events import (
            EventType, thinking_event, content_event, content_token_event,
            tool_call_event, tool_result_event, step_event, pitfall_event,
            error_event, evolution_event, summary_event,
        )
        import time as _time

        self.long_term.update_user()
        category = self._classify_task(user_input)
        system_prompt = self._build_system_prompt(category)
        self.brain.system_prompt = system_prompt

        task_record = self.tracker.start_task(
            category=category, description=user_input,
        )
        task_id = task_record.task_id

        self.memory.add_conversation("user", user_input)

        experiences = self.memory.get_similar_experiences(user_input)
        context_prefix = ""
        if experiences:
            context_prefix = "\n\n[Related experience]\n"
            for exp in experiences[:3]:
                outcome = exp.get("outcome", "unknown")
                status = "[OK]" if outcome == "success" else "[FAIL]"
                context_prefix += f"{status} {exp.get('task', 'N/A')} -> {outcome}\n"

        messages = self.memory.get_recent_conversation()

        # Compress context if conversation is too long
        if len(messages) > 50:
            messages = self.memory.compress_context(
                messages, target_count=30, brain=self.brain
            )

        if context_prefix:
            messages[-1] = {"role": "user", "content": messages[-1]["content"] + context_prefix}

        tools = self.registry.to_openai_tools()

        iteration = 0
        final_response = ""
        error_msg = ""
        all_tool_calls = []
        total_think_time = 0.0
        total_tokens_in = 0
        total_tokens_out = 0
        start_time = _time.time()

        while iteration < self.max_iterations:
            iteration += 1

            yield thinking_event(iteration)

            # ── True token-level streaming via think_stream() ──
            start_think = _time.time()
            full_content = ""
            tool_calls_data = []

            try:
                for chunk in self.brain.think_stream(messages, tools if tools else None):
                    if chunk["type"] == "content":
                        token = chunk["text"]
                        full_content += token
                        total_tokens_out += 1
                        yield content_token_event(iteration, token)

                    elif chunk["type"] == "done":
                        full_content = chunk.get("content", full_content)
                        tool_calls_data = chunk.get("tool_calls", [])
            except Exception as llm_err:
                yield error_event(iteration, f"LLM error: {type(llm_err).__name__}: {llm_err}")
                final_response = f"[ERROR] LLM call failed: {llm_err}"
                error_msg = str(llm_err)
                break

            think_time = _time.time() - start_think
            total_think_time += think_time

            # Estimate tokens (rough: 1 token ≈ 4 chars)
            total_tokens_out = len(full_content) // 4

            # Yield complete content event for consumers that prefer full text
            if full_content:
                yield content_event(iteration, full_content)

            # No tool calls = final response
            if not tool_calls_data:
                final_response = full_content
                self.memory.add_conversation("assistant", final_response)
                self.tracker.log_step(
                    task_id=task_id, action="final_response",
                    details={"result": final_response[:500]},
                )
                break

            # Build tool_calls objects for message history
            parsed_tool_calls = []
            for tc_data in tool_calls_data:
                tc_id = tc_data.get("id", "")
                tc_func = tc_data.get("function", {})
                tc_name = tc_func.get("name", "")
                tc_args_str = tc_func.get("arguments", "{}")

                # Wrap in a simple object for consistent access
                class _ToolCall:
                    def __init__(self, id, name, arguments):
                        self.id = id
                        self.function = type('F', (), {'name': name, 'arguments': arguments})()

                parsed_tool_calls.append(_ToolCall(tc_id, tc_name, tc_args_str))

            # Append assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": full_content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    } for tc in parsed_tool_calls
                ],
            })

            # Execute tool calls
            for tc in parsed_tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {"raw": tc.function.arguments}
                all_tool_calls.append(tool_name)

                # Pitfall warning
                try:
                    hints = self.error_memory.suggest_fix(json.dumps(tool_args))
                    if hints:
                        hint = hints[0]
                        yield pitfall_event(iteration, hint.error_type, hint.attempted_solution[:100])
                except Exception:
                    pass  # non-critical

                yield tool_call_event(iteration, tool_name, tool_args)

                try:
                    result, is_error = self.registry.execute_with_retry(
                        tool_name, self.brain, max_retries=2, **tool_args
                    )
                except Exception as tool_err:
                    result = f"[ERR:TOOL_EXCEPTION] {type(tool_err).__name__}: {tool_err}"
                    is_error = True

                if len(result) > 2000:
                    result = result[:2000] + "\n...(truncated)"

                yield tool_result_event(iteration, tool_name, result[:500], is_error)

                if is_error:
                    try:
                        code_for_memory = tool_args.get("content") or tool_args.get("new_string") or json.dumps(tool_args)
                        self.error_memory.record_failure(
                            task=user_input[:200],
                            error_msg=result,
                            attempted_solution=code_for_memory[:300],
                        )
                    except Exception:
                        pass  # non-critical

                    if "RETRY_EXHAUSTED" in result:
                        result += (
                            f"\n[Hint: Tool '{tool_name}' failed after retries. "
                            f"You can call forge_tool() to create a new tool for this task, "
                            f"or try a different approach.]"
                        )

                try:
                    self.tool_evolver.record_tool_call(tool_name, tool_args, not is_error)
                    self.scoreboard.record(
                        tool_name=tool_name,
                        success=not is_error,
                        duration_ms=0,
                        category=category,
                        error=result[:200] if is_error else "",
                        task=user_input[:100],
                    )
                except Exception:
                    pass  # non-critical

                try:
                    self.tracker.log_step(
                        task_id=task_id, action="tool_call",
                        details={"tool_name": tool_name, "tool_args": tool_args, "result": result[:500]},
                        tool=tool_name, is_error=is_error,
                    )
                except Exception:
                    pass  # non-critical

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

            # 循环内压缩：消息太多时压缩旧消息，防止内存溢出
            if len(messages) > 40:
                messages = self.memory.compress_context(
                    messages, target_count=25, brain=self.brain
                )

            yield step_event(iteration, think_time, len(parsed_tool_calls))

        else:
            final_response = "[WARN] Max iterations reached. Task may be incomplete."
            error_msg = "max_iterations_reached"
            self.memory.add_conversation("assistant", final_response)

        success = not error_msg and "[WARN]" not in final_response

        # Post-run: record experience, evolution, etc. (all non-critical, wrapped)
        tools_used = list(set(all_tool_calls))

        try:
            self.memory.record_experience(
                task=user_input,
                category=category,
                outcome="success" if success else "failure",
                solution=final_response[:500],
                errors=[error_msg] if error_msg else None,
                tags=tools_used,
            )
        except Exception as e:
            logger.warning("Failed to record experience: %s", e)

        try:
            from evolution.tracker import TaskStatus
            status = TaskStatus.SUCCESS if success else TaskStatus.FAILURE
            self.tracker.end_task(task_id=task_id, status=status, result=final_response[:500])
        except Exception as e:
            logger.warning("Failed to end task: %s", e)

        try:
            self.strategy_memory.record_task_result(
                category=category, success=success,
                task_description=user_input[:200],
            )
        except Exception as e:
            logger.warning("Failed to record strategy: %s", e)

        # Self-reflect on failure or periodically
        try:
            strategy_stats = self.strategy_memory.get_stats()
            if not success or (strategy_stats.get(category, {}).get("total_tasks", 0) % 5 == 0):
                reflection = self._self_reflect(user_input, final_response, success, error_msg)
                parsed = self._parse_reflection(reflection.get("reflection", ""))

                if parsed["pitfall"]:
                    parts = parsed["pitfall"].split("|")
                    if len(parts) >= 3:
                        self.error_memory.record_failure(
                            code_snippet=final_response[:200],
                            error_msg=parts[0],
                            fix_applied=parts[2],
                            task=user_input[:200],
                        )

                if success and final_response:
                    self.user_prefs.learn_from_code(final_response)
        except Exception as e:
            logger.warning("Failed to self-reflect: %s", e)

        # Evolution check
        try:
            if not success and self.tracker.should_evolve():
                yield evolution_event(category, "analyzing", "Tasks need evolution")
                self._try_evolve(category)
        except Exception as e:
            logger.warning("Failed to evolve: %s", e)

        # Tool evolution patterns
        patterns = self.tool_evolver.detect_patterns()
        if patterns:
            yield evolution_event("tools", "patterns_detected", f"{len(patterns)} patterns")

        self.long_term.add_session(
            summary=f"[{category}] {user_input[:100]} → {final_response[:100]}",
            tags=[category],
        )

        total_time = _time.time() - start_time
        yield summary_event(
            result=final_response,
            success=success,
            total_steps=iteration,
            total_time=total_time,
            tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
        )

    def _try_evolve(self, category: str):
        # Check pending verifications first
        self._check_pending_verifications()

        # Get failed tasks from tracker
        failed_tasks = self.tracker.failed_tasks(n=10)
        if not failed_tasks:
            return

        # Convert to analysis format
        failures = []
        for task in failed_tasks:
            failures.append({
                "task": task.description,
                "category": task.category,
                "errors": task.errors,
                "tools_used": task.tools_used,
            })

        current_prompt = self._build_system_prompt(category)
        result = self.evolver.analyze_and_evolve(force=False)
        if result and result.get("evolution_proposed"):
            # Snapshot before accepting evolution
            version_id = result.get("version_id", "unknown")
            self.verifier.snapshot(f"prompt_{version_id}")

            # Auto-accept if confidence is high enough
            if version_id:
                self.evolver.accept_evolution(version_id)
                print(f"  [Evolution] Auto-accepted new prompt version")
            else:
                print(f"  [Evolution] Proposed changes pending review")

    def _check_pending_verifications(self):
        """Check and verify pending evolution snapshots."""
        pending = self.verifier.get_pending_verifications()
        for label in pending:
            # Only verify snapshots that are old enough (at least 5 tasks later)
            snap = self.verifier._snapshots.get(label)
            if not snap:
                continue

            # Check if enough tasks have passed since the snapshot
            current_rate, total, _, _, _ = self._get_current_performance()
            tasks_since = total - snap.total_tasks
            if tasks_since < self.verifier.min_tasks:
                continue

            result = self.verifier.verify(label)
            if result.action == "rollback":
                print(f"  [Evolution] Rolling back '{label}': {result.reason}")
                self.verifier.auto_rollback(label)
            elif result.action == "keep":
                print(f"  [Evolution] Verified '{label}': {result.reason}")

    def _get_current_performance(self) -> tuple:
        """Get current performance metrics."""
        try:
            summary = self.tracker.summary() if hasattr(self.tracker, 'summary') else {}
            categories = summary.get("categories", {})
            total = sum(d.get("total_tasks", 0) for d in categories.values() if isinstance(d, dict))
            success = sum(d.get("success_count", 0) for d in categories.values() if isinstance(d, dict))
            failure = total - success
            rate = success / total if total > 0 else 0.0
            return rate, total, success, failure, 0.0
        except Exception:
            return 0.0, 0, 0, 0, 0.0

    def get_stats(self) -> dict:
        tools = self.registry.list_tools()
        exp_stats = self.memory.get_experience_stats()

        # Calculate success rate from outcomes
        outcomes = exp_stats.get("outcomes", {})
        total_tasks = exp_stats.get("total", 0)
        success_count = outcomes.get("success", 0)
        success_rate = success_count / total_tasks if total_tasks > 0 else 0

        return {
            "tools": tools,
            "total_experiences": total_tasks,
            "success_rate": success_rate,
            "pitfall_count": len(self.error_memory.errors),
            "user_task_count": self.user_prefs.prefs.get("task_count", 0),
            "strategy_stats": self.strategy_memory.get_stats(),
            "subagent_stats": self.subagents.stats(),
        }

    def get_evolution_status(self) -> dict:
        categories = list(self.config.get("task_categories", {}).keys()) + ["general"]
        status = {}
        # Get all evolution history
        all_history = self.evolver.get_evolution_history()
        # Get strategy stats
        strategy_stats = self.strategy_memory.get_stats()

        for cat in categories:
            # Filter history for this category
            cat_history = [h for h in all_history if h.get("analysis", {}).get("category") == cat]
            stats = strategy_stats.get(cat, {})
            total = stats.get("total_tasks", 0)
            success = stats.get("success_count", 0)
            status[cat] = {
                "versions": len(cat_history),
                "has_evolved": any(h.get("accepted", False) for h in cat_history),
                "strategy": self.strategy_memory.get_strategy_prompt(cat)[:50] if self.strategy_memory.get_strategy_prompt(cat) else "default",
                "total_tasks": total,
                "success_rate": success / total if total > 0 else 0,
            }
        return status
