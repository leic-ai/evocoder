Title: I built a coding agent that rewrites its own system prompt, generates new tools from usage patterns, and learns from every error

Body:

I've been frustrated that every coding agent treats each session as independent — you fix the same error 10 times and it never learns.

So I built EvoCoder: https://github.com/leic-ai/evocoder

What makes it different:

**Self-evolving system prompt** — When failure rate exceeds 30%, the agent analyzes what went wrong and proposes a revised system prompt. You can accept/reject/roll back. After 100 tasks, the prompt is measurably different.

**Error memory with fix suggestions** — Every error is logged with context. When a similar error appears later, it suggests fixes from past experience. Uses ChromaDB vectors for semantic matching.

**Automatic tool generation** — Observes your tool call patterns (e.g., you always search → read → edit) and generates composite tools automatically. Validated via AST parse + regex scan, no exec/eval.

**4-layer memory** — Conversation buffer → working memory → long-term experience store (JSONL + vectors) → user profile.

**SubAgent delegation** — Parallel task execution with specialized agents (code, debug, research, file).

12K lines of Python, 34 tests, MIT license. Works with MiMo, DeepSeek, or any OpenAI-compatible API.

Would love feedback on the architecture. The tool evolver is the part I'm most uncertain about — how do you safely validate auto-generated code?
