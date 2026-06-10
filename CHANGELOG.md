# Changelog

All notable changes to EvoCoder will be documented in this file.

## [0.7.0] - 2026-06-09

### Added
- **Type-safe dataclasses**: `ErrorEntry`, `PitfallHint`, `PitfallSummary` replace raw dicts in ErrorMemory
- **True token-level streaming**: `Agent.run_stream()` uses `brain.think_stream()` for real-time output
- **Event system**: `AgentEvent` + `EventType` enum with 11 event types for structured streaming
- **Tool retry with LLM correction**: `ToolRegistry.execute_with_retry()` — auto-retries failed tools, optionally asks LLM to fix args
- **LLM-driven prompt evolution**: `PromptEvolver._llm_reflect_and_rewrite()` — uses LLM to analyze failures and rewrite system prompt
- **Context compression**: `MemoryStore.compress_context()` — LLM-powered conversation summarization when history exceeds 50 messages
- **SubAgent native tool_calls**: Rewrote `_run_agent_loop()` to use OpenAI native tool_calls instead of regex parsing
- **Smoke tests**: 27 pytest tests covering all core modules (no API key required)
- **MIT License**: Added LICENSE file
- **AgentEvents package**: `agent_events/` with event types and convenience constructors

### Changed
- `ErrorMemory.suggest_fix()` now returns `List[PitfallHint]` (was `List[dict]`)
- `ErrorMemory.get_pitfall_summary()` now returns `PitfallSummary` (was `dict`)
- `ErrorMemory.record_failure()` now returns `ErrorEntry` (was `dict`)
- `Brain.__init__()` removed unused `**kwargs` parameter
- CLI uses `run_stream()` for real-time token display via `sys.stdout.write()`
- Web server rewritten to use `run_stream()` directly (removed monkey-patching)
- `.gitignore` expanded for IDE, OS, test, and build artifacts
- `requirements.txt` reorganized with optional dependency comments and `pytest`

### Removed
- `_extract_and_execute_tools()` regex-based tool parsing (replaced by native tool_calls)
- `_is_task_complete()` heuristic (no longer needed)
- `_tmp_read.py` temporary file

## [0.6.0] - 2026-06-08

### Added
- DeepSeek V4 Pro integration with 1M context window
- SDD (Specification-Driven Development) workflow engine
- Web search tool for real-time information retrieval
- Expanded tool suite to 23 tools total
- Enhanced GUI with DeepSeek GUI fusion architecture

### Changed
- Upgraded LLM backend from v0.5 to DeepSeek V4 Pro
- Improved context management for large codebases
- Refined tool registration and discovery mechanism

## [0.5.0] - 2026-05-xx

### Added
- Tool evolution system with automatic capability expansion
- Cross-session memory persistence
- Dynamic tool creation and refinement
- Session state management

### Changed
- Enhanced tool execution pipeline
- Improved error handling and recovery

## [0.4.0] - 2026-04-xx

### Added
- Initial EvoCoder architecture
- Core agent framework
- Basic tool integration system
- Project scaffolding and configuration
