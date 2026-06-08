"""
Tool Registry for EvoCoder

Manages registration, discovery, and execution of tools.
Each Tool wraps a callable with metadata, tracks usage stats,
and can serialize itself to OpenAI function-calling schema.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class Tool:
    """A registered tool: its callable, metadata, and live stats."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        func: Callable,
        category: str = "general",
    ):
        self.name = name
        self.description = description
        # JSON Schema "properties" dict  (or full param spec)
        self.parameters: Dict[str, Any] = parameters
        self.func = func
        self.category = category

        # live counters
        self.call_count: int = 0
        self.error_count: int = 0

    # -- execution ----------------------------------------------------------

    def execute(self, **kwargs: Any) -> Any:
        """Call the underlying function and update counters."""
        self.call_count += 1
        try:
            return self.func(**kwargs)
        except Exception:
            self.error_count += 1
            raise

    # -- OpenAI schema ------------------------------------------------------

    def to_openai_schema(self) -> Dict[str, Any]:
        """Return an OpenAI function-calling tool descriptor."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    # -- helpers ------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Plain dict snapshot (for logging / export)."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": self.parameters,
            "call_count": self.call_count,
            "error_count": self.error_count,
        }

    def __repr__(self) -> str:
        return (
            f"Tool({self.name!r}, calls={self.call_count}, "
            f"errors={self.error_count})"
        )


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """
    Central registry that holds Tool instances.

    Typical usage::

        registry = ToolRegistry()

        @registry.register(description="Read a file", category="file")
        def read_file(path: str) -> str:
            ...

        result = registry.execute("read_file", path="foo.txt")
        openai_tools = registry.to_openai_tools()
    """

    def __init__(self) -> None:
        # name -> Tool   (public attribute kept for backward compat)
        self.tools: Dict[str, Tool] = {}

    # -- registration -------------------------------------------------------

    def register(
        self,
        name: Optional[str] = None,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        category: str = "general",
    ) -> Callable:
        """
        Decorator that registers a function as a tool.

        If *parameters* is ``None`` the schema is inferred from the
        function's type annotations and defaults.
        """

        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_params = parameters if parameters is not None else _infer_parameters(func)
            tool_desc = description or (func.__doc__ or "").strip()

            self.tools[tool_name] = Tool(
                name=tool_name,
                description=tool_desc,
                parameters=tool_params,
                func=func,
                category=category,
            )
            return func

        return decorator

    def register_function(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        category: str = "general",
    ) -> Tool:
        """Register a function directly (not as a decorator).  Returns the Tool."""
        tool_name = name or func.__name__
        tool_params = parameters if parameters is not None else _infer_parameters(func)
        tool_desc = description or (func.__doc__ or "").strip()

        tool = Tool(
            name=tool_name,
            description=tool_desc,
            parameters=tool_params,
            func=func,
            category=category,
        )
        self.tools[tool_name] = tool
        return tool

    # -- execution ----------------------------------------------------------

    def execute(self, name: str, **kwargs: Any) -> Any:
        """Look up *name* and run its tool.  Raises ``KeyError`` if missing."""
        if name not in self.tools:
            raise KeyError(f"Tool {name!r} not found in registry")
        return self.tools[name].execute(**kwargs)

    # -- OpenAI integration -------------------------------------------------

    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """Return a list of OpenAI function-calling tool descriptors."""
        return [tool.to_openai_schema() for tool in self.tools.values()]

    # -- discovery ----------------------------------------------------------

    def list_tools(self) -> List[str]:
        """Return sorted list of registered tool names."""
        return sorted(self.tools.keys())

    def get(self, name: str) -> Optional[Tool]:
        """Return the Tool for *name*, or ``None``."""
        return self.tools.get(name)

    # -- dunder helpers -----------------------------------------------------

    def __len__(self) -> int:
        return len(self.tools)

    def __contains__(self, name: str) -> bool:
        return name in self.tools

    def __iter__(self):
        return iter(self.tools.values())

    def __repr__(self) -> str:
        return f"ToolRegistry({len(self.tools)} tools)"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_PYTYPE_TO_JSON: Dict[str, str] = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
}


def _infer_parameters(func: Callable) -> Dict[str, Any]:
    """
    Build a JSON-Schema ``parameters`` object from a function signature.

    Returns a dict with ``type``, ``properties``, ``required`` keys.
    """
    sig = inspect.signature(func)
    properties: Dict[str, Any] = {}
    required: List[str] = []

    for pname, param in sig.parameters.items():
        if pname == "self":
            continue

        # map Python annotation to JSON type
        json_type = "string"
        if param.annotation is not inspect.Parameter.empty:
            type_name = getattr(param.annotation, "__name__", str(param.annotation))
            json_type = _PYTYPE_TO_JSON.get(type_name, "string")

        prop: Dict[str, Any] = {"type": json_type}
        properties[pname] = prop

        if param.default is inspect.Parameter.empty:
            required.append(pname)

    schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema
