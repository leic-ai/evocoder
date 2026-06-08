# EvoCoder v0.6.0

A self-evolving programming agent powered by **DeepSeek V4 Pro**. EvoCoder learns from every task it executes -- refining its system prompt, remembering past errors, adapting strategies to your coding style, and even generating new composite tools from usage patterns. The longer you use it, the better it gets.

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
███████   ████    ██████       v0.6.0
```

---

## Architecture

```
+=====================================================================+
|                          EvoCoder Agent                              |
|                                                                      |
|  +--------------------+     +------------------------------------+   |
|  |     Brain          |     |        SubAgentManager             |   |
|  | (LLM Engine)       |     |  code | debug | research | file    |   |
|  |  - think()         |     +------------------------------------+   |
|  |  - think_stream()  |              |                               |
|  |  - TokenCache      |              v                               |
|  +--------+-----------+     +------------------------------------+   |
|           |                 |       ToolRegistry (23 tools)      |   |
|           v                 |  file | shell | git | http | web   |   |
|  +--------------------+     |  desktop | data | bg               |   |
|  |   4-Layer Memory   |     +------------------------------------+   |
|  |                    |                                               |
|  | L1: Conversation   |     +------------------------------------+   |
|  |     (ring buffer)  |     |      3-Layer Evolution System      |   |
|  | L2: Working Memory |     |                                    |   |
|  |     (session KV)   |     | L1: PromptEvolver                  |   |
|  | L3: Long-Term      |     |     (self-modifying system prompt) |   |
|  |     (JSONL+Vector) |     | L2: StrategyMemory + ErrorMemory   |   |
|  | L4: User Profile   |     |     (task-aware learning)          |   |
|  |     (cross-session)|     | L3: ToolEvolver                    |   |
|  +--------------------+     |     (autonomous tool generation)   |   |
|                             +------------------------------------+   |
+=====================================================================+
         |                    |                    |
         v                    v                    v
   DeepSeek V4 Pro      ChromaDB Vectors      JSONL Disk
   (OpenAI-compatible)  (semantic search)     (persistence)
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set your API key

```bash
cp .env.example .env
# Edit .env and set DEEPSEEK_API_KEY=your_key_here
```

Or export directly:

```bash
export DEEPSEEK_API_KEY=sk-xxxxxxxx
```

### 3. Configure (optional)

Edit `config.json` to adjust model, timeouts, and evolution thresholds:

```json
{
  "api": {
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-v4-pro",
    "max_retries": 3,
    "timeout": 120
  },
  "agent": {
    "max_iterations": 25,
    "workspace": ".evocoder"
  },
  "evolution": {
    "failure_threshold": 3,
    "auto_accept_confidence": 0.7
  }
}
```

### 4. Run

```bash
python evo_splash.py
```

---

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all available commands |
| `/ask` | Ask a general question |
| `/code` | Generate code from a description |
| `/debug` | Debug an error or traceback |
| `/file` | Read, write, or edit files |
| `/git` | Git operations (status, diff, log, commit) |
| `/search` | Search the web or codebase |
| `/tools` | List all registered tools |
| `/brain` | Brain diagnostics and health check |
| `/evolve` | View evolution stats and prompt history |
| `/clear` | Clear conversation history |
| `/quit` | Exit EvoCoder |

---

## Built-in Tools (23)

| # | Category | Tool | Description |
|---|----------|------|-------------|
| 1 | **file** | `read_file` | Read file contents with encoding and line limits |
| 2 | **file** | `write_file` | Write content to file, auto-creates parent dirs |
| 3 | **file** | `edit_file` | Find-and-replace exact text in a file |
| 4 | **shell** | `run_command` | Execute shell command (cmd.exe or bash, platform-aware) |
| 5 | **shell** | `list_directory` | List files/dirs with type and size |
| 6 | **shell** | `search_code` | Regex search across files with glob filtering |
| 7 | **git** | `git_status` | Show working tree status |
| 8 | **git** | `git_diff` | Show staged or unstaged diff |
| 9 | **git** | `git_log` | Show recent commit history |
| 10 | **git** | `github` | Run GitHub CLI (`gh`) commands |
| 11 | **http** | `http_get` | Send HTTP GET request |
| 12 | **http** | `http_post` | Send HTTP POST with JSON/form body |
| 13 | **http** | `parse_html` | Parse HTML and extract text, links, or meta tags |
| 14 | **desktop** | `screenshot` | Capture screen to image file |
| 15 | **desktop** | `mouse_click` | Click at coordinates (left/right/middle) |
| 16 | **desktop** | `mouse_move` | Move mouse cursor without clicking |
| 17 | **desktop** | `type_text` | Type text (CJK-aware via clipboard paste) |
| 18 | **desktop** | `press_key` | Press key or key combo (e.g. `ctrl+c`) |
| 19 | **data** | `read_csv` | Read CSV with delimiter and row limits |
| 20 | **data** | `process_data` | Process CSV/JSON: head, tail, describe, sort, filter, groupby |
| 21 | **data** | `export_data` | Export data to CSV, JSON, or Markdown |
| 22 | **web** | `web_search` | Search the web (DuckDuckGo + Bing fallback) |
| 23 | **web** | `web_fetch` | Fetch web page and extract text/links/meta |
| 24 | **bg** | `start_background` | Run a command in the background |
| 25 | **bg** | `check_background` | Check background job status |
| 26 | **bg** | `stop_background` | Terminate a background job |

> The tool registry is extensible -- register custom tools with `@registry.register()`.

---

## 4-Layer Memory System

EvoCoder maintains persistent memory across four complementary layers:

### L1: Conversation Buffer (Short-Term)

- **Storage**: In-memory ring buffer (deque, 200 messages max)
- **Purpose**: Maintains context within a session
- **Persistence**: None (session only)

### L2: Working Memory (Session-Scoped)

- **Storage**: JSON file (`working_memory.json`)
- **Purpose**: Structured key-value context for the current task
- **Persistence**: Survives restarts, 24-hour TTL per entry
- **Keys**: `current_task`, `error_context`, `active_file`, etc.

### L3: Long-Term Experience Store

- **Storage**: JSONL file (`experiences.jsonl`) + ChromaDB vector collection
- **Purpose**: Records every task outcome (success/failure/partial) with solution, errors, tags, and duration
- **Retrieval**: Semantic vector search (ChromaDB) with keyword fallback
- **Capacity**: Up to 5000 entries with automatic pruning

### L4: User Profile (Cross-Session)

- **Storage**: Three JSON files (`user.json`, `history.json`, `learned.json`)
- **Purpose**: Remembers who you are, your session history, and accumulated knowledge
- **Features**:
  - Visit tracking and personalised greetings
  - Session log (last 20 sessions with summaries)
  - Learned facts: preferences, corrections, habits
  - Easter egg: tag "ugly-whale" for a surprise

---

## 3-Layer Evolution System

The core differentiator -- EvoCoder improves itself over time through three complementary evolution layers:

### Layer 1: PromptEvolver (Self-Modifying System Prompt)

- **What it does**: Analyses task execution history, detects failure patterns, and proposes evolved system prompts
- **Triggers**: High failure rate (>30%), high error rate (>20%), hotspot categories
- **Mechanism**: Versioned prompt chain with accept/reject/rollback lifecycle
- **Integration**: Consults ErrorMemory, StrategyMemory, and UserPreferences before proposing changes

```
Task History --> Analysis --> Failure Patterns --> Evolved Prompt
                                                      |
                                              [accept / reject / rollback]
```

### Layer 2: StrategyMemory + ErrorMemory (Task-Aware Learning)

**StrategyMemory**:
- Maintains per-category strategy prompts (code, debug, refactor, file, git, search)
- Classifies tasks by keyword scoring
- Records outcomes and accumulates "learned tips" per strategy
- Tips are appended to future strategy prompts automatically

**ErrorMemory**:
- Logs every error with task context, attempted solution, and file/line info
- Classifies errors by type (SyntaxError, KeyError, ImportError, etc.)
- Suggests fixes by matching against past failures (type + keyword + substring scoring)
- Generates actionable tips for recurring error patterns

### Layer 3: ToolEvolver (Autonomous Tool Generation)

- **What it does**: Observes tool usage patterns, detects repetitive call sequences, and synthesises new composite tools
- **Detection**: Sliding-window sub-sequence analysis with configurable frequency threshold
- **Generation**: Builds Python wrapper functions that chain existing tools
- **Validation**: Multi-layer safety check (regex scan, AST parse, dangerous node detection, no `exec`/`eval`/`__import__`)
- **Persistence**: Saved as importable Python modules in `evolved_tools/`

---

## Project Structure

```
EvoCoder/
|-- .env.example              # API key template
|-- .gitignore
|-- config.json               # Model, agent, and evolution config
|-- requirements.txt           # Python dependencies
|-- evo_splash.py             # Splash screen (Rich console + whale art)
|-- test_api.py               # API connectivity test
|-- test_gap.py               # Gap test
|
|-- brain/
|   |-- __init__.py
|   |-- engine.py             # Brain (LLM engine), TokenCache, TokenUsage
|
|-- evolution/
|   |-- __init__.py
|   |-- tracker.py            # EvolutionTracker: task lifecycle + stats
|   |-- prompt_evolver.py     # PromptEvolver: self-modifying prompts
|   |-- error_memory.py       # ErrorMemory: failure tracking + fix suggestions
|   |-- strategy_memory.py    # StrategyMemory: per-category strategies
|   |-- tool_evolver.py       # ToolEvolver: autonomous tool generation
|   |-- user_prefs.py         # UserPreferences: coding style learning
|
|-- memory/
|   |-- __init__.py
|   |-- store.py              # MemoryStore: 3-tier memory (conversation, working, long-term)
|   |-- long_term.py          # LongTermMemory: user profile, sessions, learned facts
|
|-- tools/
|   |-- __init__.py
|   |-- registry.py           # ToolRegistry + Tool: registration, execution, OpenAI schema
|   |-- builtin.py            # 23+ built-in tools across 8 categories
|   |-- web_search.py         # WebSearcher: DuckDuckGo + Bing fallback
|
|-- subagents/
|   |-- __init__.py
|   |-- manager.py            # SubAgentManager: delegation, parallel execution
|
|-- utils/
|   |-- __init__.py
|   |-- platform.py           # Platform detection, path normalization
|
|-- .evocoder/                # Runtime data (auto-created)
|   |-- cache/                # TokenCache (prompt/response SHA-256 cache)
|   |-- memory/               # MemoryStore + LongTermMemory data
|   |   |-- chroma_db/        # ChromaDB vector store
|   |   |-- experiences.jsonl # Long-term experience log
|   |   |-- working_memory.json
|   |   |-- user.json         # User profile
|   |   |-- history.json      # Session history
|   |   |-- learned.json      # Accumulated knowledge
|   |-- evolution/            # Evolution data
|   |   |-- task_history.jsonl
|   |   |-- prompt_versions.json
|   |   |-- strategy_memory.json
|   |   |-- error_memory.json
|   |   |-- user_prefs.json
|   |-- evolved_tools/        # Auto-generated composite tools
|   |-- prompts/              # Prompt snapshots
|   |-- records/              # Execution records
|
|-- blog_system/              # (planned)
|-- finetune/                 # (planned)
|-- superpowers/              # (planned)
```

---

## Key Design Decisions

**OpenAI-compatible API**: Uses the `openai` Python SDK pointed at DeepSeek's endpoint. Swap to any OpenAI-compatible provider by changing `base_url` in `config.json`.

**Graceful degradation**: Every optional dependency (ChromaDB, pandas, pyautogui, Pillow) is handled with try/except -- the agent works with just `openai` and `rich`, losing only vector search, data processing, desktop automation, and screenshot capture.

**Thread-safety**: SubAgentManager uses locks for shared state and serializes Brain API calls when agents share an API key.

**Cross-platform**: Platform detection in `utils/platform.py` injects OS-specific shell rules into every sub-agent's system prompt. Built-in tools use `cmd.exe` on Windows, `bash` elsewhere.

**Error format**: All tool errors use the standard format `[ERR:CODE] message` for consistent parsing.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `openai` | LLM API client (DeepSeek V4 Pro) |
| `rich` | Terminal UI (splash screen, tables, panels) |
| `prompt_toolkit` | Interactive input |
| `chromadb` | Vector similarity search (optional) |
| `requests` | HTTP requests |
| `beautifulsoup4` + `lxml` | HTML parsing |
| `pandas` + `openpyxl` | Data processing (optional) |
| `pyautogui` + `pyperclip` | Desktop automation (optional) |
| `python-dotenv` | `.env` file loading |
| `gitpython` | Git integration |

---

## License

MIT
