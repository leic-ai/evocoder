"""Brain — EvoCoder inference engine

Calls DeepSeek API for thinking, planning, tool selection.
DeepSeek V4 Pro is compatible with OpenAI API format, so we use the openai SDK.

Token optimization inspired by KUN runtime (DeepSeek GUI).
"""

import json
import time
import hashlib
from openai import OpenAI
from utils.platform import get_platform_prompt


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
        return _BASE_SYSTEM_PROMPT + "\n\n" + get_platform_prompt()
    except ImportError:
        return _BASE_SYSTEM_PROMPT


class TokenCache:
    """Token缓存优化器 — 借鉴KUN运行时"""

    def __init__(self):
        self.prefix_hash = None
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.saved_tokens = 0

    def update_prefix(self, system_prompt: str):
        new_hash = hashlib.md5(system_prompt.encode()).hexdigest()
        changed = self.prefix_hash != new_hash
        self.prefix_hash = new_hash
        return changed

    def filter_relevant_tools(self, tools: list[dict], messages: list[dict]) -> list[dict]:
        if not tools or len(tools) <= 5:
            return tools
        recent_text = ""
        for msg in messages[-3:]:
            if isinstance(msg.get("content"), str):
                recent_text += msg["content"] + " "
        scored_tools = []
        for tool in tools:
            name = tool.get("function", {}).get("name", "")
            desc = tool.get("function", {}).get("description", "")
            score = 0
            keywords = recent_text.lower().split()
            for kw in keywords:
                if kw in name.lower() or kw in desc.lower():
                    score += 1
            scored_tools.append((score, tool))
        scored_tools.sort(key=lambda x: -x[0])
        keep = min(15, max(5, len(tools) // 2))
        filtered = [t[1] for t in scored_tools[:keep]]
        self.saved_tokens += (len(tools) - len(filtered)) * 50
        return filtered

    def update_stats(self, response):
        if hasattr(response, 'usage') and response.usage:
            self.total_input_tokens += response.usage.prompt_tokens or 0
            self.total_output_tokens += response.usage.completion_tokens or 0
            if hasattr(response.usage, 'prompt_cache_hit_tokens'):
                self.cache_hits += response.usage.prompt_cache_hit_tokens or 0
            if hasattr(response.usage, 'prompt_cache_miss_tokens'):
                self.cache_misses += response.usage.prompt_cache_miss_tokens or 0

    def get_stats(self) -> dict:
        total = self.cache_hits + self.cache_misses
        hit_rate = self.cache_hits / total if total > 0 else 0
        saved_cost = (self.cache_hits * 0.0000015)
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": hit_rate,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "saved_tokens": self.saved_tokens,
            "saved_cost": saved_cost,
        }


class Brain:
    """DeepSeek inference engine with retry logic and token optimization"""

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com",
                 model: str = "deepseek-chat", system_prompt: str | None = None,
                 max_retries: int = 3, retry_delay: float = 2.0, timeout: int = 120,
                 **kwargs):
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self.model = model
        self.system_prompt = system_prompt or get_system_prompt()
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.token_cache = TokenCache()
        self.token_cache.update_prefix(self.system_prompt)

    def think(self, messages: list[dict], tools: list[dict] | None = None) -> object:
        """Send conversation to DeepSeek, return response object with .content and .tool_calls"""
        self.token_cache.update_prefix(self.system_prompt)
        filtered_tools = tools
        if tools:
            filtered_tools = self.token_cache.filter_relevant_tools(tools, messages)
        kwargs = {
            "model": self.model,
            "messages": [{"role": "system", "content": self.system_prompt}] + messages,
            "temperature": 0.1,
        }
        if filtered_tools:
            kwargs["tools"] = filtered_tools
            kwargs["tool_choice"] = "auto"

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(**kwargs)
                self.token_cache.update_stats(response)
                return response.choices[0].message
            except Exception as e:
                last_error = e
                error_type = type(e).__name__
                if "AuthenticationError" in error_type or "401" in str(e):
                    raise
                wait = self.retry_delay * (2 ** attempt)
                if "RateLimitError" in error_type or "429" in str(e):
                    wait *= 2
                if attempt < self.max_retries - 1:
                    print(f"  [Brain] API error ({error_type}), retrying in {wait:.1f}s...")
                    time.sleep(wait)
        raise last_error

    def think_stream(self, messages: list[dict], tools: list[dict] | None = None):
        """Stream response from DeepSeek. Yields chunks."""
        self.token_cache.update_prefix(self.system_prompt)
        filtered_tools = tools
        if tools:
            filtered_tools = self.token_cache.filter_relevant_tools(tools, messages)
        kwargs = {
            "model": self.model,
            "messages": [{"role": "system", "content": self.system_prompt}] + messages,
            "temperature": 0.1,
            "stream": True,
        }
        if filtered_tools:
            kwargs["tools"] = filtered_tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        full_content = ""
        tool_calls = {}
        for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue
            if delta.content:
                full_content += delta.content
                yield {"type": "content", "text": delta.content}
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {"id": tc.id or "", "function": {"name": "", "arguments": ""}}
                    if tc.id:
                        tool_calls[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls[idx]["function"]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls[idx]["function"]["arguments"] += tc.function.arguments
        final_calls = [tool_calls[i] for i in sorted(tool_calls.keys())]
        yield {"type": "done", "content": full_content, "tool_calls": final_calls}
