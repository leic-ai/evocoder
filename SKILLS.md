# EvoCoder Superpowers -- Skills Adaptation Guide

How Claude Code's core skills translate to EvoCoder's architecture. Each skill maps to EvoCoder's native tools, memory layers, and evolution system -- no external dependencies required.

---

## Tool Mapping: Claude Code -> EvoCoder

| Claude Code Capability | EvoCoder Equivalent | Tool(s) Used |
|---|---|---|
| `Read` (file) | Read file contents | `read_file` |
| `Write` (file) | Create/overwrite file | `write_file` |
| `Edit` (find-replace) | Exact text replacement | `edit_file` |
| `Bash` (shell) | Run command | `run_command` |
| `Glob` (file search) | List directory + pattern | `list_directory` + `search_code` |
| `Grep` (content search) | Regex search across files | `search_code` |
| `WebSearch` | Web search | `web_search` |
| `WebFetch` | Fetch page content | `web_fetch` |
| `TaskCreate/Update/List` | SubAgent task delegation | `SubAgentManager.delegate()` |
| `CronCreate` (scheduling) | Background process management | `start_background` / `check_background` |
| Git operations | Git status/diff/log | `git_status` / `git_diff` / `git_log` / `github` |
| Notebook editing | Direct file manipulation | `read_file` + `edit_file` |
| Desktop automation | GUI control | `screenshot` / `mouse_click` / `type_text` / `press_key` |
| Data processing | CSV/JSON analysis | `read_csv` / `process_data` / `export_data` |

---

## The 8 Skills

### 1. Writing Plans

> Before executing complex tasks, produce a structured plan. Break work into ordered steps, identify dependencies, and anticipate blockers.

**How EvoCoder does it:**

- Use `think_stream()` to reason through the task before touching any tool.
- Write the plan to a file via `write_file` (e.g. `.evocoder/plan.md`) so it persists across iterations.
- Use `read_file` to re-consult the plan mid-execution.
- Log each completed step to Working Memory (L2) for session-scoped tracking.
- Record the full plan and outcome to Long-Term Experience (L3) via `experiences.jsonl` for future retrieval.

**Pattern:**
```
1. think_stream("Analyze this task and produce a step-by-step plan")
2. write_file(".evocoder/plan.md", plan_content)
3. For each step:
     a. read_file(".evocoder/plan.md") -- re-orient
     b. Execute step via appropriate tool
     c. Update plan with completion status
4. Record outcome to experience store
```

**When to use:** Any task with 3+ steps, multi-file changes, or cross-module dependencies.

---

### 2. Systematic Debugging

> Diagnose bugs methodically: reproduce, isolate root cause, apply minimal fix, verify.

**How EvoCoder does it:**

- **Reproduce**: `run_command` to execute the failing code and capture the error.
- **Read**: `read_file` to inspect the source at the error location.
- **Search**: `search_code` to find all references to the failing function/class/variable.
- **Hypothesize**: `think_stream()` to reason about root cause, consulting ErrorMemory for similar past failures.
- **Fix**: `edit_file` to apply the minimal change.
- **Verify**: `run_command` to re-run and confirm the fix.
- **Learn**: The ErrorMemory (`error_memory.py`) automatically logs the error type, context, and fix for future suggestion.

**Pattern:**
```
1. run_command("python main.py") -- reproduce
2. ErrorMemory.suggest_fix(error_type, context) -- check past solutions
3. read_file(path_to_error_location)
4. search_code("def broken_function") -- find all usages
5. think_stream("Root cause analysis...")
6. edit_file(path, old_code, fixed_code)
7. run_command("python main.py") -- verify
```

**EvoCoder advantage:** ErrorMemory auto-classifies errors by type (SyntaxError, KeyError, ImportError, etc.) and scores fix suggestions by keyword + substring matching against all past failures. The more you debug, the faster it gets.

---

### 3. Self-Review

> After completing work, review it critically before declaring done. Check for correctness, edge cases, style, and completeness.

**How EvoCoder does it:**

- After writing code, use `read_file` to re-read the changed file(s).
- `search_code` to verify no broken references or unused imports remain.
- `run_command` to execute tests or linters (e.g. `python -m pytest`, `python -m py_compile`).
- `think_stream()` with a self-critique prompt: "Review the following changes for bugs, edge cases, and style issues."
- `git_diff` to review the exact changes before committing.
- Record the review outcome in StrategyMemory -- if self-review caught a real bug, add it as a "learned tip" for that task category.

**Pattern:**
```
1. read_file(changed_file) -- re-read what you wrote
2. search_code("import X") -- verify dependencies
3. run_command("python -m py_compile changed_file.py")
4. git_diff() -- review the full change set
5. think_stream("Self-review: check for [bugs/edge cases/style]")
6. StrategyMemory.add_tip(category, "tip learned from review")
```

**When to use:** Every code generation or modification task. Make it automatic, not optional.

---

### 4. Finishing Work

> Complete tasks cleanly: verify the goal is met, clean up temporary artifacts, report results, and commit if appropriate.

**How EvoCoder does it:**

- **Verify goal**: `think_stream("Does this output satisfy the original requirement?")` with the original task from conversation history.
- **Test**: `run_command` to run relevant tests or smoke checks.
- **Clean up**: `run_command` / `write_file` to remove temp files, debug logs, or scratch code.
- **Commit**: `git_status` -> `git_diff` -> `github(["commit", "-m", "message"])`.
- **Report**: Summarize what was done, what changed, and any caveats.
- **Record**: Log the completed task to Long-Term Experience (L3) with success status, duration, and tags.

**Pattern:**
```
1. think_stream("Does this satisfy the original requirement?")
2. run_command("python -m pytest tests/") -- verify
3. git_status() + git_diff() -- review changes
4. github(["add", "."]) + github(["commit", "-m", "..."])
5. Log to experiences.jsonl: {task, outcome: "success", duration, tags}
6. Clean up temp files
7. Final summary to user
```

**Key principle:** A task is not done until it is verified, cleaned up, and recorded.

---

### 5. Self-Evolution

> Learn from every task. Detect failure patterns, update strategies, evolve the system prompt, and generate new tools from usage patterns.

**How EvoCoder does it -- this is the core differentiator:**

**Layer 1 -- PromptEvolver:**
- After every task, EvolutionTracker records the outcome (success/failure/partial).
- When failure rate exceeds 30% or error rate exceeds 20%, PromptEvolver triggers.
- It analyses the task history, consults ErrorMemory and StrategyMemory, and proposes an evolved system prompt.
- The new prompt is versioned -- you can accept, reject, or roll back.

**Layer 2 -- StrategyMemory + ErrorMemory:**
- StrategyMemory maintains per-category strategy prompts (code, debug, refactor, file, git, search).
- Each strategy accumulates "learned tips" from past outcomes -- automatically appended to future prompts.
- ErrorMemory logs every error with context, attempted fix, and resolution. It suggests fixes for new errors by matching against the full history.

**Layer 3 -- ToolEvolver:**
- Observes tool call sequences across tasks using sliding-window sub-sequence analysis.
- When a repetitive pattern is detected (e.g. "always search_code then read_file then edit_file"), it generates a composite tool.
- New tools are validated (regex scan, AST parse, no exec/eval/import) and saved as importable Python modules in `evolved_tools/`.

**Pattern:**
```
1. Execute task normally
2. EvolutionTracker.record_task(task, outcome, duration, errors)
3. If failure_rate > threshold:
     PromptEvolver.analyze_and_propose()
     -> accept / reject / rollback
4. StrategyMemory.update_strategy(category, tips)
5. ErrorMemory.log_error(error_type, context, fix)
6. ToolEvolver.detect_patterns(tool_call_history)
     -> generate composite tool if pattern found
```

**EvoCoder advantage:** This is not a one-time setup. The evolution system runs continuously, silently, and compounds over time. After 100 tasks, EvoCoder's system prompt, strategies, error fixes, and tool library are all measurably better than at task 1.

---

### 6. Web Surfing

> Search the web, fetch pages, extract information, and integrate findings into the current task.

**How EvoCoder does it:**

- `web_search(query)` -- DuckDuckGo primary, Bing fallback. Returns title, URL, snippet.
- `web_fetch(url, extract="text"|"links"|"meta"|"all")` -- fetches and parses page content.
- `http_get(url)` -- raw HTTP GET for APIs or non-HTML endpoints.
- `http_post(url, body)` -- raw HTTP POST for API calls.
- `parse_html(html, extract)` -- BeautifulSoup-based extraction from raw HTML.

**Pattern:**
```
1. web_search("how to fix X in Python 3.12")
2. web_fetch(top_result_url, extract="text")
3. think_stream("Synthesize findings into actionable steps")
4. Apply findings via edit_file / write_file
```

**Advanced -- parallel research:**
```
SubAgentManager.delegate_parallel([
    ("Research X library API", AgentType.RESEARCH),
    ("Find Y error solutions on StackOverflow", AgentType.RESEARCH),
])
```

**Key tools:**
- `web_search` for discovery (DuckDuckGo + Bing redundancy)
- `web_fetch` for deep reading (extracts text, links, meta, or all)
- `parse_html` for processing raw HTML from `http_get` responses
- SubAgent `research` type for parallel, isolated research tasks

---

### 7. Tool Evolution

> When you notice repetitive tool patterns, create new composite tools that chain them together. The tool library should grow with usage.

**How EvoCoder does it:**

This is Layer 3 of the evolution system (`tool_evolver.py`), but you can also trigger it manually.

**Automatic (ToolEvolver):**
- Tracks all tool call sequences in a sliding window.
- Detects sub-sequences that repeat above a frequency threshold.
- Synthesizes a Python wrapper function that chains the detected tools.
- Validates: regex scan for dangerous patterns, AST parse, detection of `exec`/`eval`/`__import__`, sandboxed import test.
- Saves to `evolved_tools/` as an importable module.
- Registers the new tool in ToolRegistry so it's immediately available.

**Manual (custom tools):**
```python
# In your code or via run_command + write_file:
@registry.register(
    name="lint_and_fix",
    description="Run linter, parse errors, and auto-fix common issues.",
    parameters={...},
    category="code",
)
def lint_and_fix(path: str) -> str:
    result = run_command(f"python -m flake8 {path}")
    # parse errors, apply fixes...
    return result
```

**Pattern for detecting evolution opportunities:**
```
1. After 20+ tasks, review tool call history
2. look for repeated sequences:
   - search_code -> read_file -> edit_file (code navigation pattern)
   - web_search -> web_fetch -> think_stream (research pattern)
   - run_command -> read_file -> edit_file -> run_command (debug pattern)
3. Generate composite tool that encapsulates the pattern
4. Test on historical tasks before accepting
```

**EvoCoder advantage:** Tools evolve autonomously. You don't need to manually identify patterns -- the ToolEvolver does it by analyzing actual usage data.

---

### 8. Sub-Agent Delegation

> For complex tasks, delegate sub-tasks to specialized agents that work in isolation with their own context and tool sets.

**How EvoCoder does it:**

SubAgentManager (`subagents/manager.py`) provides isolated, specialized execution:

| Agent Type | Specialization | Tools | Max Iterations |
|---|---|---|---|
| `code` | Write, modify, refactor code | read/write/edit_file, run_command, search_code, git | 15 |
| `debug` | Diagnose and fix bugs | read/write/edit_file, run_command, search_code, git_diff/log | 20 |
| `research` | Web search, docs, info gathering | web_search, web_fetch, read_file, run_command, http_get | 10 |
| `file` | File system operations | read/write/edit_file, list_directory, search_code, run_command | 10 |
| `general` | Catch-all | All tools | 15 |

**Single delegation:**
```python
result = manager.delegate(
    "Fix the import error in auth/middleware.py",
    agent_type=AgentType.DEBUG,
    extra_context="The error started after the refactor on 2026-06-07.",
)
```

**Parallel delegation (fan-out):**
```python
results = manager.delegate_parallel([
    ("Write unit tests for utils/parser.py", AgentType.CODE),
    ("Research the new requests 3.x API changes", AgentType.RESEARCH),
    ("Refactor the database connection pool", AgentType.CODE),
])
```

**Key properties:**
- Each sub-agent gets its own Brain instance (isolated conversation context).
- Each sub-agent gets its own ToolRegistry (scoped to allowed tools).
- Platform prompt is injected automatically (OS-aware shell commands).
- Thread-safe: locks protect shared state, API calls serialized per key.
- Results include: output, error, iterations used, elapsed time, tool calls made.

**Pattern:**
```
1. Analyze the incoming task
2. If decomposable into independent sub-tasks:
     manager.delegate_parallel([(task1, type1), (task2, type2), ...])
3. If a single focused sub-task:
     manager.delegate(task, agent_type)
4. Collect SubAgentResult from each
5. Synthesize results and verify completeness
6. Record delegation outcomes for evolution tracking
```

**When to use:**
- Tasks with 2+ independent sub-tasks (parallelize with `delegate_parallel`)
- Deep debugging that needs isolated context (delegate to `debug` agent)
- Research-heavy tasks that need web access (delegate to `research` agent)
- Any task where the main agent's context is getting too large

---

## Skill Composition

These 8 skills are not isolated -- they compose naturally:

| Scenario | Skills Used |
|---|---|
| Fix a production bug | Systematic Debugging -> Self-Review -> Finishing Work |
| Add a new feature | Writing Plans -> Sub-Agent Delegation -> Self-Review -> Finishing Work |
| Research and implement an API | Web Surfing -> Writing Plans -> Self-Review -> Finishing Work |
| After 50 tasks, optimize workflow | Self-Evolution -> Tool Evolution |
| Complex multi-file refactor | Writing Plans -> Sub-Agent Delegation -> Systematic Debugging -> Self-Review -> Finishing Work |

The evolution system (Skill 5) runs in the background after every task, silently improving all other skills over time.
