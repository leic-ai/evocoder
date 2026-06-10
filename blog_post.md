# I Built a Coding Agent That Evolves Itself — Here's What I Learned

**TL;DR**: I built EvoCoder, a self-evolving programming agent that learns from every task. Its system prompt rewrites itself after failures, its error memory suggests fixes from past mistakes, and its tool library grows automatically by detecting usage patterns. 12K lines of Python, 34 tests, MIT license.

GitHub: https://github.com/leic-ai/evocoder

---

## The Problem

Every coding agent I've tried (Aider, Cursor, Continue) treats each session as independent. You fix the same import error 10 times, and it never learns. You always search_code → read_file → edit_file in the same pattern, and it never optimizes.

I wanted an agent that **gets better the more you use it**.

## What Makes EvoCoder Different

### 1. Self-Modifying System Prompt

Most agents have a static system prompt. EvoCoder's prompt evolves.

When the failure rate exceeds 30%, the `PromptEvolver` kicks in. It analyzes recent failures, consults the error memory and strategy memory, then proposes a revised system prompt. The new prompt is versioned — you can accept, reject, or roll back.

```
Task History → Failure Analysis → Prompt Evolution → Accept/Reject/Rollback
```

After 100 tasks, EvoCoder's system prompt is measurably different from task 1. It has learned your coding style, your common mistakes, and your preferred patterns.

### 2. Error Memory with Fix Suggestions

Every error is logged with context, attempted solution, and resolution. When a similar error appears later, EvoCoder suggests fixes from its experience.

```python
# ErrorMemory classifies errors by type and scores suggestions
hints = error_memory.suggest_fix("KeyError: 'user_id'")
# → [PitfallHint(error_type="KeyError", attempted_solution="Use .get() with default")]
```

This isn't just keyword matching — it uses semantic similarity (via ChromaDB vectors when available, keyword fallback otherwise).

### 3. Automatic Tool Generation

This is the feature I'm most proud of. The `ToolEvolver` observes tool call sequences using sliding-window sub-sequence analysis. When it detects a repetitive pattern (e.g., you always `search_code → read_file → edit_file`), it automatically generates a composite tool.

The generated tools are:
- Validated via regex scan + AST parse (no `exec`/`eval`/`__import__`)
- Saved as importable Python modules in `evolved_tools/`
- Immediately registered in the tool registry

After enough usage, your tool library grows autonomously.

### 4. 4-Layer Memory System

| Layer | Storage | Purpose |
|-------|---------|---------|
| L1: Conversation | In-memory ring buffer (200 msgs) | Current session context |
| L2: Working Memory | JSON file (24h TTL) | Session-scoped key-value context |
| L3: Long-Term | JSONL + ChromaDB vectors | Persistent experience store (5000 entries) |
| L4: User Profile | JSON files | Cross-session preferences and history |

### 5. SubAgent Delegation

Complex tasks are decomposed and delegated to specialized sub-agents:

```python
results = manager.delegate_parallel([
    ("Write unit tests for utils/parser.py", AgentType.CODE),
    ("Research the new requests 3.x API changes", AgentType.RESEARCH),
    ("Refactor the database connection pool", AgentType.CODE),
])
```

Each sub-agent has its own Brain, ToolRegistry, and iteration budget. Thread-safe with locks.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      EvoCoder Agent                      │
│                                                          │
│  ┌──────────────┐    ┌──────────────────────────────┐   │
│  │    Brain      │    │     SubAgentManager          │   │
│  │ (LLM Engine)  │    │  code|debug|research|file    │   │
│  │  - think()    │    └──────────────────────────────┘   │
│  │  - streaming  │                                       │
│  └──────┬───────┘    ┌──────────────────────────────┐   │
│         │            │     ToolRegistry (26 tools)   │   │
│         ▼            │  file|shell|git|http|web|     │   │
│  ┌──────────────┐    │  desktop|data|bg              │   │
│  │ 4-Layer Mem  │    └──────────────────────────────┘   │
│  │ L1: Conv Buf │                                       │
│  │ L2: Working  │    ┌──────────────────────────────┐   │
│  │ L3: LongTerm │    │   3-Layer Evolution System    │   │
│  │ L4: UserProfile│  │ L1: PromptEvolver             │   │
│  └──────────────┘    │ L2: StrategyMemory+ErrorMem   │   │
│                      │ L3: ToolEvolver               │   │
│                      └──────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
         │                    │                    │
    MiMo v2.5 Pro       ChromaDB Vectors      JSONL Disk
    (OpenAI-compatible)  (semantic search)     (persistence)
```

## Tech Stack

- **Python 3.11+** with type hints and dataclasses
- **OpenAI SDK** (works with MiMo, DeepSeek, or any compatible API)
- **ChromaDB** for vector similarity search
- **Rich** for terminal UI
- **WebSockets** for the GUI frontend
- **highlight.js** for syntax highlighting in the web UI

## What I Learned

1. **Self-evolution is real, but slow.** The agent doesn't get dramatically better after 10 tasks. After 100+, you start noticing it avoids past mistakes.

2. **Error memory is the most immediately useful feature.** Even without the full evolution system, just having "I've seen this error before, here's the fix" saves a lot of time.

3. **Tool generation is hard to validate safely.** The biggest challenge wasn't generating tools — it was making sure they don't run arbitrary code. Regex + AST + sandboxed import is the minimum.

4. **Context compression is critical.** Without mid-loop compression, the agent hits memory limits after 15+ iterations. We compress when messages exceed 40.

5. **The GUI matters more than I thought.** A web UI with syntax highlighting, code execution, and file browsing makes the agent 10x more usable than CLI-only.

## Try It

```bash
git clone https://github.com/leic-ai/evocoder.git
cd evocoder
pip install -r requirements.txt
cp .env.example .env
# Add your API key (MiMo or DeepSeek)
python cli.py
```

Or launch the web GUI:

```bash
python web_server.py
# Open http://localhost:8080
```

## What's Next

- [ ] VS Code extension
- [ ] More tool evolver patterns (currently only detects sequential patterns)
- [ ] Multi-model support (use fast model for simple tasks, powerful model for complex ones)
- [ ] Plugin system for custom evolution strategies

---

**GitHub**: https://github.com/leic-ai/evocoder

If you find this interesting, a star ⭐ goes a long way. If you want to contribute, check out [CONTRIBUTING.md](https://github.com/leic-ai/evocoder/blob/main/CONTRIBUTING.md).
