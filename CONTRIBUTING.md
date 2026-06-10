# Contributing to EvoCoder

Thanks for your interest in contributing! Here's how to get started.

## Setup

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/evocoder.git
cd evocoder

# Install dependencies
pip install -r requirements.txt

# Copy env template and add your API key
cp .env.example .env
# Edit .env and set DEEPSEEK_API_KEY=your_key_here

# Run smoke tests (no API key needed)
python -m pytest tests/test_smoke.py -v
```

## Running

```bash
# CLI mode
python cli.py

# Web server mode (WebSocket)
python web_server.py

# Desktop GUI mode
python desktop.py
```

## Project Structure

```
evocoder/
├── agent.py              # Main agent loop (run / run_stream)
├── agent_events/         # Event system for streaming output
├── brain/                # LLM engine (DeepSeek via OpenAI SDK)
├── evolution/            # 3-layer evolution system
│   ├── tracker.py        #   Task tracking & stats
│   ├── prompt_evolver.py #   Self-modifying system prompts
│   ├── error_memory.py   #   Failure tracking & fix suggestions
│   ├── strategy_memory.py#   Per-category strategy learning
│   ├── tool_evolver.py   #   Autonomous tool generation
│   └── user_prefs.py     #   Coding style learning
├── memory/               # 4-layer memory system
│   ├── store.py          #   Conversation + working + long-term
│   └── long_term.py      #   User profile & session history
├── tools/                # Tool registry & built-in tools
│   ├── registry.py       #   Registration, execution, OpenAI schema
│   ├── builtin.py        #   26 built-in tools
│   └── web_search.py     #   DuckDuckGo + Bing fallback
├── subagents/            # Sub-agent delegation system
├── tests/                # Test suite
└── web_server.py         # WebSocket API server
```

## Code Guidelines

- **Type hints**: Use them on all public functions
- **Docstrings**: Google style for all public methods
- **Error format**: `[ERR:CODE] message` for tool errors
- **Graceful degradation**: Optional deps (chromadb, pyautogui, pandas) must have try/except guards
- **Thread safety**: Use locks for shared mutable state

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run a specific test class
python -m pytest tests/test_smoke.py::TestErrorMemory -v

# Tests should NOT require an API key or network access
# Mock external dependencies in your tests
```

## Submitting Changes

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests: `python -m pytest tests/ -v`
5. Commit with a clear message
6. Open a PR against `master`

## Reporting Issues

- Include your Python version (`python --version`)
- Include the full error traceback
- Describe what you expected vs what happened
- Steps to reproduce
