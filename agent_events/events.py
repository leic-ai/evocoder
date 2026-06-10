"""
AgentEvent — Event types for EvoCoder streaming output.

Used by Agent.run_stream() to yield structured events as the agent
thinks, calls tools, and produces results. Enables real-time UI updates
instead of blocking until completion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class EventType(Enum):
    """Types of events emitted during agent execution."""

    # Agent is thinking (before LLM call)
    THINKING = "thinking"

    # A single token from the LLM (real-time streaming)
    CONTENT_TOKEN = "content_token"

    # LLM produced complete text content (non-streaming fallback)
    CONTENT = "content"

    # Agent is about to call a tool
    TOOL_CALL = "tool_call"

    # Tool execution completed
    TOOL_RESULT = "tool_result"

    # A full step (iteration) completed
    STEP = "step"

    # Pitfall warning from error memory
    PITFALL_WARNING = "pitfall_warning"

    # Error occurred during execution
    ERROR = "error"

    # Evolution system triggered
    EVOLUTION = "evolution"

    # Final summary of the run
    SUMMARY = "summary"

    # Context compression happened
    COMPRESSED = "compressed"


@dataclass
class AgentEvent:
    """A single event emitted during agent execution.

    Attributes:
        type: The kind of event.
        data: Event-specific payload (varies by type).
        step: The iteration step number (0-based).
    """

    type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    step: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict for JSON transport."""
        return {
            "type": self.type.value,
            "data": self.data,
            "step": self.step,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AgentEvent":
        """Deserialize from a dict."""
        return cls(
            type=EventType(d["type"]),
            data=d.get("data", {}),
            step=d.get("step", 0),
        )


# ── Convenience constructors ──────────────────────────────────────────

def thinking_event(step: int, message: str = "Thinking...") -> AgentEvent:
    """Agent is about to think."""
    return AgentEvent(EventType.THINKING, {"message": message}, step=step)


def content_event(step: int, text: str) -> AgentEvent:
    """LLM produced complete text content."""
    return AgentEvent(EventType.CONTENT, {"text": text}, step=step)


def content_token_event(step: int, token: str) -> AgentEvent:
    """A single token from the LLM (real-time streaming)."""
    return AgentEvent(EventType.CONTENT_TOKEN, {"token": token}, step=step)


def tool_call_event(step: int, name: str, args: Dict[str, Any]) -> AgentEvent:
    """Agent is calling a tool."""
    return AgentEvent(EventType.TOOL_CALL, {"name": name, "args": args}, step=step)


def tool_result_event(step: int, name: str, result: str, is_error: bool = False) -> AgentEvent:
    """Tool execution completed."""
    return AgentEvent(
        EventType.TOOL_RESULT,
        {"name": name, "result": result, "is_error": is_error},
        step=step,
    )


def step_event(step: int, elapsed: float, tools_called: int) -> AgentEvent:
    """A full iteration step completed."""
    return AgentEvent(
        EventType.STEP,
        {"elapsed_seconds": round(elapsed, 2), "tools_called": tools_called},
        step=step,
    )


def pitfall_event(step: int, error_type: str, hint: str) -> AgentEvent:
    """Warning from error memory about a known pitfall."""
    return AgentEvent(
        EventType.PITFALL_WARNING,
        {"error_type": error_type, "hint": hint},
        step=step,
    )


def error_event(step: int, message: str, error_type: str = "unknown") -> AgentEvent:
    """An error occurred."""
    return AgentEvent(
        EventType.ERROR,
        {"message": message, "error_type": error_type},
        step=step,
    )


def evolution_event(category: str, action: str, details: str = "") -> AgentEvent:
    """Evolution system triggered."""
    return AgentEvent(
        EventType.EVOLUTION,
        {"category": category, "action": action, "details": details},
        step=0,
    )


def summary_event(
    result: str,
    success: bool,
    total_steps: int,
    total_time: float,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> AgentEvent:
    """Final summary of the agent run."""
    return AgentEvent(
        EventType.SUMMARY,
        {
            "result": result,
            "success": success,
            "total_steps": total_steps,
            "total_time": round(total_time, 2),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "speed": round(tokens_out / total_time, 1) if total_time > 0 else 0,
        },
        step=total_steps,
    )
