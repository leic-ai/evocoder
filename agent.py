"""Agent — EvoCoder core loop

Brain thinks -> picks tool -> Tools execute -> Memory saves
  -> 3-layer evolution checks -> self-reflect -> repeat
"""

import json
from pathlib import Path
from brain import Brain
from memory import MemoryStore
from tools import ToolRegistry, register_builtins
from evolution import (
    EvolutionTracker, PromptEvolver,
    ErrorMemory, UserPreferences, StrategyMemory,
    ToolEvolver,
)
from memory.long_term import LongTermMemory
from sdd import SDDFlow
from subagents.manager import SubAgentManager


APP_ROOT = Path(__file__).resolve().parent


DEFAULT_CONFIG = {
    "api": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
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
        self.memory = MemoryStore(data_dir=f"{self.workspace}/memory")
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
        if pitfall_summary:
            sections.append(pitfall_summary)

        # Layer 2: User preferences
        style_prompt = self.user_prefs.get_style_prompt()
        if style_prompt and self.user_prefs.prefs["task_count"] > 0:
            sections.append(style_prompt)

        # Layer 3: Task strategy
        strategy_prompt = self.strategy_memory.get_strategy_prompt(category)
        if strategy_prompt:
            sections.append(strategy_prompt)

        # Evolved prompt override (if exists)
        evolved = self.evolver.get_prompt(category)
        if evolved:
            sections.append(f"[Evolved prompt for {category}]\n{evolved}")

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
            messages = [{"role": "user", "content": prompt}]
            response = self.brain.think(messages, tools=None)
            return {"reflection": response.content, "success": success}
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
        """Execute one full Agent loop with 3-layer evolution."""
        self.long_term.update_user()
        category = self._classify_task(user_input)
        system_prompt = self._build_system_prompt(category)
        self.brain.system_prompt = system_prompt

        prompt_version = f"v{len(self.evolver.get_evolution_history(category))}"
        task_id = self.tracker.start_task(
            task=user_input, category=category, prompt_version=prompt_version,
        )

        strategy = self.strategy_memory.get_strategy(category)
        self.memory.add_message("user", user_input)

        experiences = self.memory.get_similar_experiences(user_input)
        context_prefix = ""
        if experiences:
            context_prefix = "\n\n[Related experience]\n"
            for exp in experiences[:3]:
                status = "[OK]" if exp["success"] else "[FAIL]"
                context_prefix += f"{status} {exp['task']} -> {exp.get('error', 'success')}\n"

        messages = self.memory.get_messages()
        if context_prefix:
            messages[-1] = {"role": "user", "content": messages[-1]["content"] + context_prefix}

        tools = self.registry.to_openai_tools()

        iteration = 0
        final_response = ""
        error_msg = ""
        all_tool_calls = []

        while iteration < self.max_iterations:
            iteration += 1

            response = self.brain.think(messages, tools if tools else None)

            if not response.tool_calls:
                final_response = response.content or ""
                self.memory.add_message("assistant", final_response)
                self.tracker.log_step(
                    step=iteration, action="final_response",
                    result=final_response[:500], success=True,
                )
                break

            print(f"\n{'─'*50}")
            print(f"  [Step {iteration}]")
            print(f"{'─'*50}")
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

                hint = self.error_memory.suggest_fix(json.dumps(tool_args))
                if hint:
                    print(f"  [Pitfall Warning] Known issue: {hint['error_type']} -> {hint['fix'][:80]}")

                print(f"  >> Tool: {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:100]})")

                result = self.registry.execute(tool_name, tool_args)
                is_error = result.startswith("[ERR:")

                if len(result) > 4000:
                    result = result[:4000] + "\n...(truncated)"

                print(f"  >> Result: {result[:200]}{'...' if len(result) > 200 else ''}")

                if is_error:
                    code_for_memory = tool_args.get("content") or tool_args.get("new_string") or json.dumps(tool_args)
                    self.error_memory.record_failure(
                        code_snippet=code_for_memory[:300],
                        error_msg=result,
                        fix_applied="",
                        task=user_input[:200],
                    )

                self.tool_evolver.record_tool_call(tool_name, tool_args, not is_error)

                self.tracker.log_step(
                    step=iteration, action="tool_call",
                    tool_name=tool_name, tool_args=tool_args,
                    result=result, success=not is_error,
                    error=result if is_error else "",
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        else:
            final_response = "[WARN] Max iterations reached. Task may be incomplete."
            error_msg = "max_iterations_reached"
            self.memory.add_message("assistant", final_response)

        success = not error_msg and "[WARN]" not in final_response

        tools_used = list(set(all_tool_calls))
        self.memory.save_experience(
            task=user_input, result=final_response[:500],
            success=success, tools_used=tools_used, error=error_msg,
        )

        self.tracker.end_task(success=success, final_response=final_response, error=error_msg)

        self.strategy_memory.record_task_result(
            task_type=category, success=success,
            iterations=iteration, tools_used=tools_used,
            strategy_used=strategy,
        )

        if not success or (self.strategy_memory.stats.get(category, {}).get("total", 0) % 5 == 0):
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

        if not success and self.tracker.should_evolve(category, self.evo_threshold):
            print(f"\n  [Evolution] {category} tasks failed consecutively, analyzing...")
            self._try_evolve(category)

        patterns = self.tool_evolver.detect_patterns()
        if patterns:
            print(f"\n  [Tool Evolution] Detected {len(patterns)} patterns!")
            for p in patterns:
                print(f"    - {p['pattern']}")

        self.long_term.add_session(
            summary=f"[{category}] {user_input[:100]} → {final_response[:100]}",
            topics=[category],
            memorable=user_input[:100] if success else None,
        )
        self.long_term.save_all()

        return final_response

    def _try_evolve(self, category: str):
        failures = self.tracker.get_failure_analysis(category, limit=10)
        if not failures:
            return
        current_prompt = self._build_system_prompt(category)
        result = self.evolver.analyze_and_evolve(category, current_prompt, failures)
        if result:
            confidence = result.get("confidence", 0)
            if confidence >= self.evo_confidence:
                self.evolver.accept_evolution(category)
                print(f"  [Evolution] Auto-accepted (confidence: {confidence:.0%})")
            else:
                print(f"  [Evolution] Pending review (confidence: {confidence:.0%})")

    def get_stats(self) -> dict:
        tools = self.registry.list_tools()
        exp_stats = self.memory.get_experience_stats()

        return {
            "tools": tools,
            "total_experiences": exp_stats.get("total", 0),
            "success_rate": exp_stats.get("success_rate", 0),
            "pitfall_count": len(self.error_memory.errors),
            "user_task_count": self.user_prefs.prefs.get("task_count", 0),
            "strategy_stats": self.strategy_memory.get_stats(),
            "subagent_stats": self.subagents.stats(),
        }

    def get_evolution_status(self) -> dict:
        categories = list(self.config.get("task_categories", {}).keys()) + ["general"]
        status = {}
        for cat in categories:
            history = self.evolver.get_evolution_history(cat)
            stats = self.strategy_memory.stats.get(cat, {})
            total = stats.get("total", 0)
            success = stats.get("success", 0)
            status[cat] = {
                "versions": len(history),
                "has_evolved": any(h["status"] == "accepted" for h in history),
                "strategy": self.strategy_memory.get_strategy(cat).get("approach", "default"),
                "total_tasks": total,
                "success_rate": success / total if total > 0 else 0,
            }
        return status
