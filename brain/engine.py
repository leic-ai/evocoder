"""
Brain Engine for EvoCoder

Core LLM interaction layer with:
- TokenCache: SHA-256 based prompt/response caching to avoid redundant API calls
- Brain: Main reasoning engine with think() and think_stream() methods
- Automatic retry with exponential backoff
- Token usage tracking
- Tool-aware prompt construction
"""

import os
import sys
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Union
from dataclasses import dataclass, field
from threading import Lock

from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("evocoder.brain")


# ---------------------------------------------------------------------------
# System prompt with platform awareness
# ---------------------------------------------------------------------------

_BASE_SYSTEM_PROMPT = """You are EvoCoder, a self-evolving programming assistant powered by DeepSeek.
You are NOT Claude, NOT GPT. You run on DeepSeek V4 Pro with 1M context window.
You can help users with programming tasks by calling tools.

Rules:
1. Analyze the task first, then decide which tool to call
2. Call one tool at a time, get the result, then decide the next step
3. If the task is complete, reply to the user directly without calling more tools
4. On error, analyze the cause and try to fix it. Don't give up.
5. Be honest about your capabilities. Don't claim to be other AI models.

IMPORTANT - Long-running commands:
- Use `run_command` for quick commands (ls, cat, grep, etc.)
- Use `start_background` for servers, web apps, or any long-running process
- NEVER use `run_command` to start a server - it will block forever!
- After starting a background process, use `check_background` to verify it's running
- Use `stop_background` to stop a background process when done
"""


def get_system_prompt() -> str:
    """Get system prompt with platform info injected."""
    try:
        from utils.platform import get_platform_prompt
        return _BASE_SYSTEM_PROMPT + "\n\n" + get_platform_prompt()
    except ImportError:
        return _BASE_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Token tracking
# ---------------------------------------------------------------------------

@dataclass
class TokenUsage:
    """Tracks cumulative token usage across calls."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_hits: int = 0
    api_calls: int = 0

    def record(self, prompt: int, completion: int) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion
        self.api_calls += 1

    def record_cache_hit(self) -> None:
        self.cache_hits += 1

    @property
    def savings_ratio(self) -> float:
        total = self.api_calls + self.cache_hits
        if total == 0:
            return 0.0
        return self.cache_hits / total

    def summary(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "api_calls": self.api_calls,
            "cache_hits": self.cache_hits,
            "cache_savings_ratio": round(self.savings_ratio, 3),
        }


# ---------------------------------------------------------------------------
# TokenCache — SHA-256 prompt/response cache
# ---------------------------------------------------------------------------

class TokenCache:
    """
    Persistent disk cache mapping prompt hashes to cached responses.

    Cache key = SHA-256 of (model + system_prompt + messages JSON + temperature).
    Stored as individual JSON files under a cache directory so entries survive
    restarts and can be inspected / pruned manually.
    """

    def __init__(
        self,
        cache_dir: Union[str, Path] = ".evocoder/cache",
        max_entries: int = 2000,
        ttl_hours: float = 72.0,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self.ttl_seconds = ttl_hours * 3600
        self._mem_cache: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()

        # Pre-load hot entries into memory (last-modified first, capped)
        self._warm_memory()

    # ---- key generation ---------------------------------------------------

    @staticmethod
    def _make_key(
        model: str,
        system_prompt: str,
        messages: List[Dict[str, str]],
        temperature: float,
        tools_json: str = "",
    ) -> str:
        """Deterministic SHA-256 key for a given request configuration."""
        payload = json.dumps(
            {
                "model": model,
                "system": system_prompt,
                "messages": messages,
                "temperature": temperature,
                "tools": tools_json,
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # ---- disk I/O ----------------------------------------------------------

    def _entry_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _warm_memory(self, limit: int = 200) -> None:
        """Load most recent entries into in-memory cache."""
        try:
            entries = sorted(
                self.cache_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:limit]
            for p in entries:
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    self._mem_cache[p.stem] = data
                except (json.JSONDecodeError, OSError):
                    continue
        except OSError:
            pass

    # ---- public API --------------------------------------------------------

    def get(
        self,
        model: str,
        system_prompt: str,
        messages: List[Dict[str, str]],
        temperature: float,
        tools_json: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Return cached response dict or None on miss / expiry.

        The returned dict has keys: content, finish_reason, usage.
        """
        key = self._make_key(model, system_prompt, messages, temperature, tools_json)

        # Fast path: in-memory
        with self._lock:
            if key in self._mem_cache:
                entry = self._mem_cache[key]
                if not self._is_expired(entry):
                    return entry["response"]
                # expired — fall through to delete
                del self._mem_cache[key]

        # Slow path: disk
        path = self._entry_path(key)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        if self._is_expired(data):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None

        with self._lock:
            self._mem_cache[key] = data
        return data["response"]

    def put(
        self,
        model: str,
        system_prompt: str,
        messages: List[Dict[str, str]],
        temperature: float,
        response: Dict[str, Any],
        tools_json: str = "",
    ) -> None:
        """Store a response in the cache (memory + disk)."""
        key = self._make_key(model, system_prompt, messages, temperature, tools_json)
        entry = {
            "key": key,
            "created_at": time.time(),
            "model": model,
            "response": response,
        }

        with self._lock:
            self._mem_cache[key] = entry
            # Evict oldest if over limit
            if len(self._mem_cache) > self.max_entries:
                oldest_key = min(
                    self._mem_cache,
                    key=lambda k: self._mem_cache[k].get("created_at", 0),
                )
                self._mem_cache.pop(oldest_key, None)

        # Write to disk asynchronously-safe (atomic-ish)
        path = self._entry_path(key)
        try:
            path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            logger.warning("Cache write failed for %s: %s", key[:12], exc)

    def clear(self) -> int:
        """Delete all cache entries. Returns count removed."""
        count = 0
        with self._lock:
            self._mem_cache.clear()
        for p in self.cache_dir.glob("*.json"):
            try:
                p.unlink()
                count += 1
            except OSError:
                continue
        return count

    def prune(self) -> int:
        """Remove expired entries. Returns count removed."""
        removed = 0
        now = time.time()
        with self._lock:
            expired_keys = [
                k for k, v in self._mem_cache.items()
                if self._is_expired(v)
            ]
            for k in expired_keys:
                del self._mem_cache[k]

        for p in self.cache_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if self._is_expired(data):
                    p.unlink(missing_ok=True)
                    removed += 1
            except (json.JSONDecodeError, OSError):
                continue
        return removed

    @property
    def size(self) -> int:
        """Number of entries currently on disk."""
        return len(list(self.cache_dir.glob("*.json")))

    # ---- internals ---------------------------------------------------------

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        created = entry.get("created_at", 0)
        return (time.time() - created) > self.ttl_seconds


# ---------------------------------------------------------------------------
# Brain — main reasoning engine
# ---------------------------------------------------------------------------

class Brain:
    """
    EvoCoder reasoning engine.

    Wraps the DeepSeek (or OpenAI-compatible) API with:
    - Persistent prompt/response caching via TokenCache
    - Automatic retry with exponential backoff
    - Streaming and non-streaming completion
    - Token usage tracking
    - Tool-aware message construction
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        timeout: float = 120.0,
        enable_cache: bool = True,
        cache_dir: str = ".evocoder/cache",
        system_prompt: str = "",
    ):
        # Resolve config: explicit args > env vars > config.json defaults
        config = self._load_config()

        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or config.get("base_url", "https://api.deepseek.com")
        self.model = model or config.get("model", "deepseek-chat")
        self.max_retries = max_retries or config.get("max_retries", 3)
        self.retry_delay = retry_delay or config.get("retry_delay", 2.0)
        self.timeout = timeout or config.get("timeout", 120.0)

        self.system_prompt = system_prompt

        # OpenAI-compatible client
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

        # Cache
        self.cache_enabled = enable_cache
        self.cache = TokenCache(cache_dir=cache_dir) if enable_cache else None

        # Usage tracking
        self.usage = TokenUsage()

        # Conversation history (auto-appended across think calls)
        self.history: List[Dict[str, str]] = []

        logger.info(
            "Brain initialized: model=%s, base_url=%s, cache=%s",
            self.model, self.base_url, "ON" if self.cache_enabled else "OFF",
        )

    # ---- config loading ----------------------------------------------------

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        """Load config.json from project root if present."""
        config_path = Path(__file__).resolve().parent.parent / "config.json"
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                return data.get("api", {})
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    # ---- message construction ----------------------------------------------

    def _build_messages(
        self,
        prompt: str,
        context: Optional[List[Dict[str, str]]] = None,
        system_override: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Build the full message list for an API call.

        Order: system prompt -> context/history -> current prompt.
        """
        messages: List[Dict[str, str]] = []

        # System prompt
        sys_content = system_override or self.system_prompt
        if sys_content:
            messages.append({"role": "system", "content": sys_content})

        # Context or persistent history
        if context is not None:
            messages.extend(context)
        elif self.history:
            messages.extend(self.history)

        # Current user prompt
        messages.append({"role": "user", "content": prompt})

        return messages

    def _build_tools_json(self, tools: Optional[List[Dict[str, Any]]] = None) -> str:
        """Serialize tools list to a stable JSON string for cache keys."""
        if not tools:
            return ""
        return json.dumps(tools, sort_keys=True, ensure_ascii=True)

    # ---- core: think (non-streaming) ---------------------------------------

    def think(
        self,
        prompt: str,
        *,
        context: Optional[List[Dict[str, str]]] = None,
        system_override: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[List[Dict[str, Any]]] = None,
        remember: bool = True,
        use_cache: bool = True,
    ) -> str:
        """
        Send a prompt to the LLM and return the complete response text.

        Args:
            prompt: The user message / question.
            context: Explicit message list (overrides self.history for this call).
            system_override: Temporarily replace the system prompt.
            temperature: Sampling temperature (0.0–2.0).
            max_tokens: Max tokens in the completion.
            tools: OpenAI-compatible tool definitions (function calling).
            remember: If True, append this exchange to self.history.
            use_cache: If True, consult and populate the token cache.

        Returns:
            The assistant's response text as a string.
        """
        messages = self._build_messages(prompt, context, system_override)
        tools_json = self._build_tools_json(tools)

        # --- cache check ---
        if use_cache and self.cache_enabled and self.cache:
            cached = self.cache.get(
                self.model, self.system_prompt, messages, temperature, tools_json
            )
            if cached is not None:
                self.usage.record_cache_hit()
                logger.debug("Cache HIT for prompt (len=%d)", len(prompt))
                result_text = cached.get("content", "")
                if remember:
                    self.history.append({"role": "user", "content": prompt})
                    self.history.append({"role": "assistant", "content": result_text})
                return result_text

        # --- API call with retry ---
        response = self._call_api(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            stream=False,
        )

        # Extract content
        choice = response.choices[0]
        result_text = choice.message.content or ""

        # Track usage
        if response.usage:
            self.usage.record(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )

        # --- store in cache ---
        if use_cache and self.cache_enabled and self.cache:
            self.cache.put(
                self.model,
                self.system_prompt,
                messages,
                temperature,
                {"content": result_text, "finish_reason": choice.finish_reason},
                tools_json,
            )

        # --- persist to history ---
        if remember:
            self.history.append({"role": "user", "content": prompt})
            self.history.append({"role": "assistant", "content": result_text})

        return result_text

    # ---- core: think_stream (streaming) ------------------------------------

    def think_stream(
        self,
        prompt: str,
        *,
        context: Optional[List[Dict[str, str]]] = None,
        system_override: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[List[Dict[str, Any]]] = None,
        remember: bool = True,
    ) -> Generator[str, None, None]:
        """
        Send a prompt to the LLM and yield response tokens as they arrive.

        Streaming responses are NOT cached (the full text is unknown until
        the stream completes).  If you need caching, use think() instead.

        Args:
            prompt: The user message / question.
            context: Explicit message list (overrides self.history for this call).
            system_override: Temporarily replace the system prompt.
            temperature: Sampling temperature (0.0–2.0).
            max_tokens: Max tokens in the completion.
            tools: OpenAI-compatible tool definitions (function calling).
            remember: If True, append this exchange to self.history.

        Yields:
            Incremental text chunks (str) as the model produces them.
        """
        messages = self._build_messages(prompt, context, system_override)

        # Streaming does not use cache (partial responses cannot be replayed)
        stream = self._call_api(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            stream=True,
        )

        collected: List[str] = []
        prompt_tokens = 0
        completion_tokens = 0

        for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            if delta.content:
                collected.append(delta.content)
                yield delta.content

            # Accumulate usage from final chunk if present
            if chunk.usage:
                prompt_tokens = chunk.usage.prompt_tokens or 0
                completion_tokens = chunk.usage.completion_tokens or 0

        # Track usage
        if prompt_tokens or completion_tokens:
            self.usage.record(prompt_tokens, completion_tokens)

        # Persist full response to history
        full_text = "".join(collected)
        if remember:
            self.history.append({"role": "user", "content": prompt})
            self.history.append({"role": "assistant", "content": full_text})

    # ---- API call with retry -----------------------------------------------

    def _call_api(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]],
        stream: bool,
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
        """
        Execute an API call with exponential-backoff retry.

        Returns ChatCompletion for non-streaming, or a generator of
        ChatCompletionChunk for streaming.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs: Dict[str, Any] = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": stream,
                }
                if tools:
                    kwargs["tools"] = tools

                response = self.client.chat.completions.create(**kwargs)
                return response

            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "API call attempt %d/%d failed: %s",
                    attempt, self.max_retries, exc,
                )
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    time.sleep(delay)

        raise RuntimeError(
            f"API call failed after {self.max_retries} attempts: {last_exc}"
        ) from last_exc

    # ---- conversation management -------------------------------------------

    def clear_history(self) -> None:
        """Wipe conversation history."""
        self.history.clear()

    def set_system_prompt(self, prompt: str) -> None:
        """Update the system prompt for subsequent calls."""
        self.system_prompt = prompt

    def get_history(self) -> List[Dict[str, str]]:
        """Return a copy of the current conversation history."""
        return list(self.history)

    def trim_history(self, max_turns: int = 20) -> int:
        """
        Keep only the last `max_turns` exchanges (user+assistant pairs).
        Returns number of messages removed.
        """
        max_messages = max_turns * 2  # each turn = user + assistant
        if len(self.history) <= max_messages:
            return 0
        removed = len(self.history) - max_messages
        self.history = self.history[-max_messages:]
        return removed

    # ---- diagnostics -------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """
        Quick connectivity test. Returns status dict.
        """
        start = time.time()
        try:
            result = self.think(
                "Reply with exactly: OK",
                remember=False,
                use_cache=False,
                max_tokens=10,
            )
            latency = time.time() - start
            return {
                "status": "ok",
                "model": self.model,
                "base_url": self.base_url,
                "latency_ms": round(latency * 1000, 1),
                "response_preview": result[:50],
            }
        except Exception as exc:
            return {
                "status": "error",
                "model": self.model,
                "base_url": self.base_url,
                "error": str(exc),
            }

    def stats(self) -> Dict[str, Any]:
        """Return brain statistics including usage and cache info."""
        info: Dict[str, Any] = {
            "model": self.model,
            "base_url": self.base_url,
            "system_prompt_length": len(self.system_prompt),
            "history_length": len(self.history),
            "usage": self.usage.summary(),
        }
        if self.cache:
            info["cache"] = {
                "enabled": True,
                "entries": self.cache.size,
                "cache_dir": str(self.cache.cache_dir),
            }
        else:
            info["cache"] = {"enabled": False}
        return info

    def __repr__(self) -> str:
        return (
            f"Brain(model={self.model!r}, "
            f"history={len(self.history)}, "
            f"api_calls={self.usage.api_calls}, "
            f"cache_hits={self.usage.cache_hits})"
        )
