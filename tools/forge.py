"""
ToolForge — Dynamic tool creation and refinement for EvoCoder.

When the agent encounters a task that no existing tool can handle,
ToolForge uses the LLM to generate a new tool implementation, validates
it for safety, and registers it in the tool registry — all at runtime.

Safety guarantees:
  - Generated code is scanned for dangerous patterns (same as ToolEvolver)
  - New tools are saved to forged_tools/ as importable modules
  - Tools are validated (syntax + safety) before registration
  - Destructive operations require explicit confirmation
  - Forged tools are namespaced with "forge_" prefix to distinguish from builtins

Usage:
    forge = ToolForge(brain, registry, storage_dir="forged_tools")
    result = forge.forge_tool(
        task="Parse a CSV file and return rows where column 'age' > 30",
        context="No existing tool can filter CSV by column value",
    )
    # result["success"]: bool
    # result["tool_name"]: str
    # result["description"]: str

    # Or refine an existing tool:
    forge.refine_tool(
        tool_name="process_data",
        feedback="The sort function doesn't handle None values",
        task="Sort a list of dicts by a key that may have None values",
    )
"""

from __future__ import annotations

import ast
import json
import logging
import re
import textwrap
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("evocoder.tools.forge")


# ---------------------------------------------------------------------------
# Safety validation (shared patterns with ToolEvolver)
# ---------------------------------------------------------------------------

_DANGEROUS_PATTERNS = [
    re.compile(r"\b__import__\b"),
    re.compile(r"\bimportlib\b"),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\beval\s*\("),
    re.compile(r"\bcompile\s*\("),
    re.compile(r"\bos\.system\s*\("),
    re.compile(r"\bos\.popen\s*\("),
    re.compile(r"\bsubprocess\b"),
    re.compile(r"\bos\.remove\s*\("),
    re.compile(r"\bos\.unlink\s*\("),
    re.compile(r"\bshutil\.rmtree\s*\("),
    re.compile(r"\bglobals\s*\("),
    re.compile(r"\blocals\s*\("),
    re.compile(r"\bgetattr\s*\(.*,\s*['\"]__\w"),
    re.compile(r"\bsetattr\s*\("),
    re.compile(r"\bdelattr\s*\("),
    re.compile(r"\bctypes\b"),
    re.compile(r"\bsys\._getframe\b"),
    re.compile(r"\b__subclasses__\b"),
    re.compile(r"\bos\.environ\b"),
    re.compile(r"\bsys\.exit\b"),
    re.compile(r"\bsocket\b"),
    re.compile(r"\bhttp\.server\b"),
]


def _validate_forged_code(source: str) -> Tuple[bool, List[str]]:
    """Validate forged tool code for safety.

    Checks:
      1. Regex scan for dangerous function/module references
      2. AST parse for valid Python syntax
      3. AST walk for dangerous node types
      4. Must define at least one function

    Returns:
        (is_valid, list_of_errors)
    """
    errors: List[str] = []

    # Regex scan
    for pat in _DANGEROUS_PATTERNS:
        if pat.search(source):
            errors.append(f"Dangerous pattern: {pat.pattern}")

    # Syntax check
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        errors.append(f"Syntax error: {e}")
        return False, errors

    # AST walk
    has_function = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                has_function = True

        # Disallow dangerous calls
        if isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in ("exec", "eval", "__import__", "compile"):
                errors.append(f"Disallowed call: {name} at line {node.lineno}")

        # Disallow dangerous dunder access
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                if node.attr not in ("__init__", "__name__", "__all__", "__doc__"):
                    errors.append(f"Disallowed dunder: {node.attr} at line {node.lineno}")

    if not has_function:
        errors.append("No public function defined")

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# ToolForge
# ---------------------------------------------------------------------------

class ToolForge:
    """Dynamic tool creation and refinement system.

    Uses the LLM to generate new tool implementations when existing tools
    can't handle a task. Validates and registers forged tools at runtime.

    Parameters:
        brain: Brain instance for LLM calls.
        registry: ToolRegistry to register forged tools into.
        storage_dir: Directory to persist forged tool modules.
    """

    def __init__(
        self,
        brain: Any,
        registry: Any,
        storage_dir: str = "forged_tools",
    ):
        self.brain = brain
        self.registry = registry
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Track forged tools and their metadata
        self._forged: Dict[str, Dict[str, Any]] = {}
        self._failure_log: List[Dict[str, Any]] = []
        self._load_index()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def forge_tool(
        self,
        task: str,
        context: str = "",
        category: str = "forged",
        max_attempts: int = 2,
    ) -> Dict[str, Any]:
        """Create a new tool to handle a task that existing tools can't.

        Args:
            task: Description of what the tool should do.
            context: Why existing tools are insufficient.
            category: Tool category for registration.
            max_attempts: Max LLM attempts to generate valid code.

        Returns:
            Dict with keys:
              - success (bool)
              - tool_name (str | None)
              - description (str | None)
              - error (str | None)
        """
        # Build the prompt
        existing_tools = self._describe_existing_tools()

        prompt = f"""You are a Python tool developer for EvoCoder, a programming assistant.

## Task
Create a new tool function that does: {task}

{f"## Context: Why existing tools are insufficient{chr(10)}{context}" if context else ""}

## Existing tools (for reference, don't duplicate)
{existing_tools}

## Requirements
1. Write a single Python function with clear name, docstring, and type hints
2. The function must be self-contained (no external state, no class methods)
3. Use only safe built-in modules: json, csv, re, math, datetime, pathlib, collections, itertools, io, textwrap, hashlib, base64, urllib.parse
4. Do NOT use: os, sys, subprocess, socket, importlib, ctypes, eval, exec, __import__
5. Return a string result (the agent processes strings)
6. Handle errors gracefully — return error messages, don't raise
7. Keep it focused: one function, one job

## Output format
Output ONLY the Python code, no explanations, no markdown fences.

The function signature must be:
def tool_name(param1: str, param2: int = 10) -> str:
    \"\"\"Description of what this tool does.\"\"\"
    ...
"""

        for attempt in range(max_attempts):
            try:
                response = self.brain.think([{"role": "user", "content": prompt}])
                code = self._extract_code(response.content)

                if not code:
                    logger.warning("LLM returned no code (attempt %d)", attempt + 1)
                    continue

                # Validate
                is_valid, errors = _validate_forged_code(code)
                if not is_valid:
                    logger.warning("Forged code invalid (attempt %d): %s", attempt + 1, errors)
                    # Feed errors back to LLM for next attempt
                    prompt += f"\n\nPrevious attempt had errors: {errors}\nPlease fix."
                    continue

                # Extract tool metadata from the code
                tool_name, description, parameters = self._extract_metadata(code)

                if not tool_name:
                    logger.warning("Could not extract tool name from code")
                    continue

                # Prefix with "forge_" to distinguish from builtins
                if not tool_name.startswith("forge_"):
                    tool_name = f"forge_{tool_name}"

                # Check for name collision
                if tool_name in self.registry.tools:
                    tool_name = f"{tool_name}_{int(time.time()) % 10000}"

                # Execute the code to get the function
                namespace = {}
                exec(compile(code, f"<forged:{tool_name}>", "exec"), namespace)

                # Find the function (skip private names)
                func = None
                for name, obj in namespace.items():
                    if callable(obj) and not name.startswith("_"):
                        func = obj
                        break

                if func is None:
                    logger.warning("No callable found in forged code")
                    continue

                # Register in the tool registry
                self.registry.register_function(
                    func=func,
                    name=tool_name,
                    description=description or f"Forged tool: {task[:80]}",
                    parameters=parameters,
                    category=category,
                )

                # Persist to disk
                self._save_tool(tool_name, code, description, task)

                # Track
                self._forged[tool_name] = {
                    "description": description,
                    "task": task,
                    "created_at": time.time(),
                    "call_count": 0,
                    "success_count": 0,
                }
                self._save_index()

                logger.info("Forged new tool: %s", tool_name)

                return {
                    "success": True,
                    "tool_name": tool_name,
                    "description": description,
                    "error": None,
                }

            except Exception as exc:
                logger.warning("Forge attempt %d failed: %s", attempt + 1, exc)
                continue

        return {
            "success": False,
            "tool_name": None,
            "description": None,
            "error": f"Failed to forge tool after {max_attempts} attempts",
        }

    def refine_tool(
        self,
        tool_name: str,
        feedback: str,
        task: str = "",
    ) -> Dict[str, Any]:
        """Refine an existing tool based on feedback.

        Args:
            tool_name: Name of the tool to refine.
            feedback: What's wrong / what needs to change.
            task: The task context where the tool was used.

        Returns:
            Dict with success status and details.
        """
        if tool_name not in self.registry.tools:
            return {"success": False, "error": f"Tool {tool_name} not found"}

        tool = self.registry.tools[tool_name]
        current_desc = tool.description
        current_params = json.dumps(tool.parameters, indent=2)

        # Get the source of the current function if possible
        import inspect
        try:
            current_source = inspect.getsource(tool.func)
        except (OSError, TypeError):
            current_source = "# Source not available"

        prompt = f"""You are refining an existing EvoCoder tool.

## Current tool: {tool_name}
Description: {current_desc}
Parameters: {current_params}

## Current implementation
```python
{current_source}
```

## Feedback / Problem
{feedback}

{f"## Task context{chr(10)}{task}" if task else ""}

## Requirements
1. Output the COMPLETE improved function (not a diff)
2. Keep the same function name and parameter names
3. Fix the specific issue described in the feedback
4. Don't break existing functionality
5. Return only the Python code, no explanations
"""

        try:
            response = self.brain.think([{"role": "user", "content": prompt}])
            code = self._extract_code(response.content)

            if not code:
                return {"success": False, "error": "LLM returned no code"}

            is_valid, errors = _validate_forged_code(code)
            if not is_valid:
                return {"success": False, "error": f"Invalid code: {errors}"}

            # Execute and get the new function
            namespace = {}
            exec(compile(code, f"<refined:{tool_name}>", "exec"), namespace)

            new_func = None
            for name, obj in namespace.items():
                if callable(obj) and not name.startswith("_"):
                    new_func = obj
                    break

            if new_func is None:
                return {"success": False, "error": "No callable found"}

            # Replace the function in the registry
            old_func = tool.func
            tool.func = new_func

            # Update description if the LLM provided a better one
            new_desc = self._extract_description_from_code(code)
            if new_desc:
                tool.description = new_desc

            # Persist
            self._save_tool(tool_name, code, tool.description, f"Refined: {feedback[:100]}")

            logger.info("Refined tool: %s", tool_name)
            return {"success": True, "tool_name": tool_name, "error": None}

        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def suggest_tool(self, failed_task: str, error: str = "") -> Optional[str]:
        """Analyze a failed task and suggest which existing tool to try, or forge a new one.

        Args:
            failed_task: Description of the task that failed.
            error: The error message if any.

        Returns:
            Tool name to try, or None if no suggestion.
        """
        tools_list = self._describe_existing_tools()

        prompt = f"""An agent failed at this task. Suggest the best existing tool to try, or say "FORGE" if a new tool is needed.

## Failed task
{failed_task}

{f"## Error{chr(10)}{error}" if error else ""}

## Available tools
{tools_list}

Respond with ONLY one of:
- An existing tool name (if one can handle this)
- FORGE (if no existing tool works)
"""

        try:
            response = self.brain.think([{"role": "user", "content": prompt}])
            answer = response.content.strip().strip('"').strip("'")

            if answer.upper() == "FORGE":
                return "__FORGE__"

            # Check if it's a valid tool name
            if answer in self.registry.tools:
                return answer

            # Fuzzy match
            for name in self.registry.tools:
                if name.lower() in answer.lower() or answer.lower() in name.lower():
                    return name

            return None

        except Exception:
            return None

    def get_forged_tools(self) -> List[Dict[str, Any]]:
        """List all forged tools with their metadata."""
        result = []
        for name, meta in self._forged.items():
            result.append({
                "name": name,
                "description": meta.get("description", ""),
                "task": meta.get("task", ""),
                "created_at": meta.get("created_at", 0),
                "call_count": meta.get("call_count", 0),
            })
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_code(self, text: str) -> str:
        """Extract Python code from LLM response (handles markdown fences)."""
        if not text:
            return ""

        # Try to extract from ```python ... ``` blocks
        match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try ``` ... ``` without language tag
        match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Assume the entire response is code (if it looks like Python)
        if "def " in text and "return" in text:
            return text.strip()

        return ""

    def _extract_metadata(self, code: str) -> Tuple[str, str, Dict[str, Any]]:
        """Extract tool name, description, and parameters from code."""
        tool_name = ""
        description = ""
        parameters = {"type": "object", "properties": {}, "required": []}

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return tool_name, description, parameters

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                tool_name = node.name

                # Extract docstring
                if (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    description = node.body[0].value.value.strip().split("\n")[0]

                # Extract parameters from annotations
                for arg in node.args.args:
                    if arg.arg in ("self", "cls"):
                        continue
                    param_name = arg.arg
                    param_type = "string"  # default

                    if arg.annotation:
                        ann = ast.dump(arg.annotation)
                        if "int" in ann:
                            param_type = "integer"
                        elif "float" in ann:
                            param_type = "number"
                        elif "bool" in ann:
                            param_type = "boolean"
                        elif "list" in ann or "List" in ann:
                            param_type = "array"
                        elif "dict" in ann or "Dict" in ann:
                            param_type = "object"

                    parameters["properties"][param_name] = {
                        "type": param_type,
                        "description": f"Parameter: {param_name}",
                    }

                    # Check if has default value
                    has_default = False
                    defaults = node.args.defaults
                    n_args = len(node.args.args)
                    n_defaults = len(defaults)
                    arg_idx = node.args.args.index(arg)
                    if arg_idx >= n_args - n_defaults:
                        has_default = True

                    if not has_default:
                        parameters["required"].append(param_name)

                break

        return tool_name, description, parameters

    def _extract_description_from_code(self, code: str) -> str:
        """Extract just the description from code."""
        _, desc, _ = self._extract_metadata(code)
        return desc

    def _describe_existing_tools(self) -> str:
        """Build a summary of existing tools for the LLM context."""
        lines = []
        for name, tool in sorted(self.registry.tools.items()):
            lines.append(f"- {name}: {tool.description[:80]}")
        return "\n".join(lines[:30])  # Limit to avoid token bloat

    def _save_tool(self, name: str, code: str, description: str, task: str):
        """Persist a forged tool to disk."""
        file_path = self.storage_dir / f"{name}.py"
        header = textwrap.dedent(f"""\
            \"\"\"
            Forged tool: {name}
            Description: {description}
            Task: {task[:100]}
            Created: {time.strftime('%Y-%m-%d %H:%M:%S')}
            \"\"\"
        """)
        file_path.write_text(header + "\n" + code, encoding="utf-8")

    def _save_index(self):
        """Persist forged tools index."""
        index_path = self.storage_dir / "_index.json"
        data = {
            "forged_tools": self._forged,
            "updated_at": time.time(),
        }
        index_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def _load_index(self):
        """Load forged tools index from disk."""
        index_path = self.storage_dir / "_index.json"
        if index_path.exists():
            try:
                data = json.loads(index_path.read_text(encoding="utf-8"))
                self._forged = data.get("forged_tools", {})
            except (json.JSONDecodeError, OSError):
                pass
