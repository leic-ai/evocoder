"""
Built-in Tools for EvoCoder

Registers all core tools across categories:
  file     - read_file, write_file, edit_file
  shell    - run_command, list_directory, search_code
  git      - git_status, git_diff, git_log, github
  http     - http_get, http_post, parse_html
  desktop  - screenshot, mouse_click, mouse_move, type_text, press_key
  data     - read_csv, process_data, export_data
  web      - web_search, web_fetch
  bg       - start_background, check_background, stop_background

Error format: f"[ERR:{code}] {msg}"
Shell descriptions are dynamic based on platform (cmd.exe vs bash).
"""

from __future__ import annotations

import csv
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .registry import ToolRegistry


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

_IS_WINDOWS = sys.platform == "win32"
_SHELL_EXE = "cmd.exe" if _IS_WINDOWS else "bash"
_SHELL_NAME = "cmd.exe" if _IS_WINDOWS else "bash"


def _err(code: str, msg: str) -> str:
    """Standard error format: [ERR:{code}] {msg}"""
    return f"[ERR:{code}] {msg}"


def _posix(path: str) -> str:
    """Convert path to forward-slash POSIX form for cross-platform consistency."""
    return Path(path).as_posix()


def _find_gh() -> str:
    """Locate the gh CLI executable, falling back to PATH lookup."""
    gh = shutil.which("gh")
    if gh:
        return gh
    # Common install locations on Windows
    if _IS_WINDOWS:
        for candidate in [
            r"C:\Program Files\GitHub CLI\gh.exe",
            r"C:\Program Files (x86)\GitHub CLI\gh.exe",
        ]:
            if os.path.isfile(candidate):
                return candidate
    return "gh"  # hope it's on PATH


# ---------------------------------------------------------------------------
# Background process store
# ---------------------------------------------------------------------------

_bg_processes: Dict[str, subprocess.Popen] = {}
_bg_state: Dict[str, int] = {"counter": 0}


# ---------------------------------------------------------------------------
# Registration entry point
# ---------------------------------------------------------------------------

def register_builtins(registry: ToolRegistry) -> None:
    """Register all built-in tools on the given *registry*."""

    # ==================================================================
    # FILE OPERATIONS
    # ==================================================================

    @registry.register(
        name="read_file",
        description="Read the contents of a file. Returns the text content or an error.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path."},
                "encoding": {"type": "string", "description": "File encoding (default utf-8)."},
                "max_lines": {"type": "integer", "description": "Maximum lines to read (default: all)."},
            },
            "required": ["path"],
        },
        category="file",
    )
    def read_file(path: str, encoding: str = "utf-8", max_lines: int = 0) -> str:
        p = Path(path)
        if not p.exists():
            return _err("FILE_NOT_FOUND", f"File not found: {path}")
        if not p.is_file():
            return _err("NOT_A_FILE", f"Not a file: {path}")
        try:
            text = p.read_text(encoding=encoding, errors="replace")
            if max_lines > 0:
                lines = text.splitlines(keepends=True)
                text = "".join(lines[:max_lines])
            return text
        except Exception as exc:
            return _err("READ_FAIL", str(exc))

    @registry.register(
        name="write_file",
        description="Write content to a file. Creates parent directories if needed. Overwrites existing files.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write."},
                "content": {"type": "string", "description": "Content to write."},
                "encoding": {"type": "string", "description": "File encoding (default utf-8)."},
            },
            "required": ["path", "content"],
        },
        category="file",
    )
    def write_file(path: str, content: str, encoding: str = "utf-8") -> str:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding=encoding)
            return f"OK: wrote {len(content)} chars to {path}"
        except Exception as exc:
            return _err("WRITE_FAIL", str(exc))

    @registry.register(
        name="edit_file",
        description="Replace exact occurrences of old_string with new_string in a file. Uses errors='replace' for safe encoding handling.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to edit."},
                "old_string": {"type": "string", "description": "Exact text to find."},
                "new_string": {"type": "string", "description": "Replacement text."},
                "replace_all": {"type": "boolean", "description": "Replace all occurrences (default false)."},
            },
            "required": ["path", "old_string", "new_string"],
        },
        category="file",
    )
    def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        p = Path(path)
        if not p.exists():
            return _err("FILE_NOT_FOUND", f"File not found: {path}")
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            if old_string not in text:
                return _err("NOT_FOUND", f"old_string not found in {path}")
            if not replace_all:
                count = text.count(old_string)
                if count > 1:
                    return _err("AMBIGUOUS", f"old_string appears {count} times; set replace_all=true or provide more context")
                text = text.replace(old_string, new_string, 1)
            else:
                occurrences = text.count(old_string)
                text = text.replace(old_string, new_string)
                p.write_text(text, encoding="utf-8")
                return f"OK: replaced {occurrences} occurrence(s) in {path}"
            p.write_text(text, encoding="utf-8")
            return f"OK: replaced 1 occurrence in {path}"
        except Exception as exc:
            return _err("EDIT_FAIL", str(exc))

    # ==================================================================
    # SHELL OPERATIONS
    # ==================================================================

    _shell_cmd_desc = (
        f"Run a shell command in {_SHELL_NAME}. "
        f"{'Uses cmd.exe /c on Windows.' if _IS_WINDOWS else 'Uses bash -c.'} "
        f"Sets PYTHONIOENCODING=utf-8. Returns stdout+stderr. "
        f"Use timeout parameter to limit execution time (default 30s)."
    )

    @registry.register(
        name="run_command",
        description=_shell_cmd_desc,
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to execute."},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)."},
                "cwd": {"type": "string", "description": "Working directory (optional)."},
            },
            "required": ["command"],
        },
        category="shell",
    )
    def run_command(command: str, timeout: int = 30, cwd: Optional[str] = None) -> str:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        shell_args = ["cmd.exe", "/c", command] if _IS_WINDOWS else ["bash", "-c", command]
        try:
            proc = subprocess.run(
                shell_args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=env,
                errors="replace",
            )
            parts: List[str] = []
            if proc.stdout:
                parts.append(proc.stdout.rstrip())
            if proc.stderr:
                parts.append(f"[stderr]\n{proc.stderr.rstrip()}")
            if proc.returncode != 0:
                parts.append(f"[exit code: {proc.returncode}]")
            return "\n".join(parts) if parts else "(no output)"
        except subprocess.TimeoutExpired:
            return _err("TIMEOUT", f"Command timed out after {timeout}s")
        except Exception as exc:
            return _err("EXEC_FAIL", str(exc))

    @registry.register(
        name="list_directory",
        description="List files and directories at the given path. Shows type (file/dir), size, and name.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path (default: current directory)."},
                "show_hidden": {"type": "boolean", "description": "Include hidden files (default false)."},
            },
        },
        category="shell",
    )
    def list_directory(path: str = ".", show_hidden: bool = False) -> str:
        d = Path(path)
        if not d.exists():
            return _err("DIR_NOT_FOUND", f"Directory not found: {path}")
        if not d.is_dir():
            return _err("NOT_A_DIR", f"Not a directory: {path}")
        try:
            entries: List[str] = []
            for item in sorted(d.iterdir()):
                if not show_hidden and item.name.startswith("."):
                    continue
                kind = "dir " if item.is_dir() else "file"
                size = ""
                if item.is_file():
                    try:
                        sz = item.stat().st_size
                        if sz < 1024:
                            size = f"{sz}B"
                        elif sz < 1024 * 1024:
                            size = f"{sz / 1024:.1f}KB"
                        else:
                            size = f"{sz / (1024 * 1024):.1f}MB"
                    except OSError:
                        size = "?"
                entries.append(f"[{kind}] {size:>8s}  {item.name}")
            return "\n".join(entries) if entries else "(empty directory)"
        except Exception as exc:
            return _err("LIST_FAIL", str(exc))

    @registry.register(
        name="search_code",
        description="Search for a regex pattern in files under a directory. Uses POSIX-style paths in output. Returns matching lines with file path and line number.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for."},
                "path": {"type": "string", "description": "Directory to search in (default: current directory)."},
                "glob": {"type": "string", "description": "Glob filter, e.g. '*.py' (default: all files)."},
                "max_results": {"type": "integer", "description": "Maximum matches to return (default 50)."},
            },
            "required": ["pattern"],
        },
        category="shell",
    )
    def search_code(pattern: str, path: str = ".", glob: str = "*", max_results: int = 50) -> str:
        import re
        d = Path(path)
        if not d.exists():
            return _err("DIR_NOT_FOUND", f"Directory not found: {path}")
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return _err("BAD_REGEX", f"Invalid regex: {exc}")
        results: List[str] = []
        try:
            for fpath in d.rglob(glob):
                if not fpath.is_file():
                    continue
                # Skip binary-like files by size
                try:
                    if fpath.stat().st_size > 2_000_000:
                        continue
                except OSError:
                    continue
                try:
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for lineno, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        results.append(f"{fpath.as_posix()}:{lineno}: {line.rstrip()}")
                        if len(results) >= max_results:
                            return "\n".join(results)
        except Exception as exc:
            return _err("SEARCH_FAIL", str(exc))
        return "\n".join(results) if results else "(no matches)"

    # ==================================================================
    # GIT OPERATIONS
    # ==================================================================

    @registry.register(
        name="git_status",
        description="Show git working tree status (short format).",
        parameters={
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Repository root (optional)."},
            },
        },
        category="git",
    )
    def git_status(cwd: Optional[str] = None) -> str:
        try:
            proc = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True, text=True, timeout=15, cwd=cwd, errors="replace",
            )
            return proc.stdout.strip() if proc.stdout.strip() else "(clean working tree)"
        except FileNotFoundError:
            return _err("GIT_NOT_FOUND", "git is not installed or not on PATH")
        except Exception as exc:
            return _err("GIT_FAIL", str(exc))

    @registry.register(
        name="git_diff",
        description="Show git diff. By default shows unstaged changes; pass staged=true for staged changes.",
        parameters={
            "type": "object",
            "properties": {
                "staged": {"type": "boolean", "description": "Show staged diff (default false)."},
                "file": {"type": "string", "description": "Specific file to diff (optional)."},
                "cwd": {"type": "string", "description": "Repository root (optional)."},
            },
        },
        category="git",
    )
    def git_diff(staged: bool = False, file: Optional[str] = None, cwd: Optional[str] = None) -> str:
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--staged")
        if file:
            cmd.append(file)
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, cwd=cwd, errors="replace",
            )
            return proc.stdout if proc.stdout.strip() else "(no changes)"
        except FileNotFoundError:
            return _err("GIT_NOT_FOUND", "git is not installed or not on PATH")
        except Exception as exc:
            return _err("GIT_FAIL", str(exc))

    @registry.register(
        name="git_log",
        description="Show recent git log entries. Default 10 entries, one-line format.",
        parameters={
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "Number of entries (default 10)."},
                "cwd": {"type": "string", "description": "Repository root (optional)."},
            },
        },
        category="git",
    )
    def git_log(count: int = 10, cwd: Optional[str] = None) -> str:
        try:
            proc = subprocess.run(
                ["git", "log", f"--oneline", f"-{count}"],
                capture_output=True, text=True, timeout=15, cwd=cwd, errors="replace",
            )
            return proc.stdout.strip() if proc.stdout.strip() else "(no commits)"
        except FileNotFoundError:
            return _err("GIT_NOT_FOUND", "git is not installed or not on PATH")
        except Exception as exc:
            return _err("GIT_FAIL", str(exc))

    @registry.register(
        name="github",
        description=f"Run a GitHub CLI (gh) command. Finds gh.exe automatically. Example args: ['pr', 'list'] or ['issue', 'view', '1'].",
        parameters={
            "type": "object",
            "properties": {
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Arguments to pass to gh (e.g. ['pr', 'list']).",
                },
                "cwd": {"type": "string", "description": "Working directory (optional)."},
            },
            "required": ["args"],
        },
        category="git",
    )
    def github(args: List[str], cwd: Optional[str] = None) -> str:
        gh_exe = _find_gh()
        try:
            proc = subprocess.run(
                [gh_exe] + args,
                capture_output=True, text=True, timeout=30, cwd=cwd, errors="replace",
            )
            parts: List[str] = []
            if proc.stdout:
                parts.append(proc.stdout.rstrip())
            if proc.stderr:
                parts.append(f"[stderr]\n{proc.stderr.rstrip()}")
            if proc.returncode != 0:
                parts.append(f"[exit code: {proc.returncode}]")
            return "\n".join(parts) if parts else "(no output)"
        except FileNotFoundError:
            return _err("GH_NOT_FOUND", "GitHub CLI (gh) not found. Install from https://cli.github.com/")
        except Exception as exc:
            return _err("GH_FAIL", str(exc))

    # ==================================================================
    # HTTP OPERATIONS
    # ==================================================================

    @registry.register(
        name="http_get",
        description="Send an HTTP GET request. Returns status code, headers, and body text.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch."},
                "headers": {"type": "object", "description": "Optional request headers."},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 15)."},
            },
            "required": ["url"],
        },
        category="http",
    )
    def http_get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 15) -> str:
        try:
            import requests
            resp = requests.get(url, headers=headers, timeout=timeout)
            body = resp.text[:20000]  # cap to avoid flooding context
            return f"[{resp.status_code}]\n{body}"
        except ImportError:
            return _err("DEPS_MISSING", "requests library not installed. Run: pip install requests")
        except Exception as exc:
            return _err("HTTP_FAIL", str(exc))

    @registry.register(
        name="http_post",
        description="Send an HTTP POST request with a JSON or form body. Returns status code and response body.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to POST to."},
                "body": {"type": "string", "description": "Request body (JSON string or form data)."},
                "content_type": {"type": "string", "description": "Content-Type header (default application/json)."},
                "headers": {"type": "object", "description": "Additional headers."},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 15)."},
            },
            "required": ["url", "body"],
        },
        category="http",
    )
    def http_post(
        url: str,
        body: str,
        content_type: str = "application/json",
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 15,
    ) -> str:
        try:
            import requests
            hdrs = {"Content-Type": content_type}
            if headers:
                hdrs.update(headers)
            resp = requests.post(url, data=body.encode("utf-8"), headers=hdrs, timeout=timeout)
            return f"[{resp.status_code}]\n{resp.text[:20000]}"
        except ImportError:
            return _err("DEPS_MISSING", "requests library not installed. Run: pip install requests")
        except Exception as exc:
            return _err("HTTP_FAIL", str(exc))

    @registry.register(
        name="parse_html",
        description="Parse HTML and extract text, links, or meta tags using BeautifulSoup.",
        parameters={
            "type": "object",
            "properties": {
                "html": {"type": "string", "description": "Raw HTML string to parse."},
                "extract": {
                    "type": "string",
                    "enum": ["text", "links", "meta", "title"],
                    "description": "What to extract: text (default), links, meta, or title.",
                },
            },
            "required": ["html"],
        },
        category="http",
    )
    def parse_html(html: str, extract: str = "text") -> str:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return _err("DEPS_MISSING", "beautifulsoup4 not installed. Run: pip install beautifulsoup4 lxml")
        try:
            soup = BeautifulSoup(html, "lxml")
            if extract == "title":
                tag = soup.find("title")
                return tag.get_text(strip=True) if tag else "(no title)"
            if extract == "links":
                links: List[str] = []
                for a in soup.find_all("a", href=True):
                    text = a.get_text(strip=True) or "(no text)"
                    links.append(f"{text} -> {a['href']}")
                return "\n".join(links[:100]) if links else "(no links)"
            if extract == "meta":
                metas: List[str] = []
                for tag in soup.find_all("meta"):
                    name = tag.get("name") or tag.get("property", "")
                    content = tag.get("content", "")
                    if name and content:
                        metas.append(f"{name}: {content}")
                return "\n".join(metas) if metas else "(no meta tags)"
            # default: text
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)[:15000]
        except Exception as exc:
            return _err("PARSE_FAIL", str(exc))

    # ==================================================================
    # DESKTOP AUTOMATION
    # ==================================================================

    @registry.register(
        name="screenshot",
        description="Capture a screenshot. Saves to the given path (default: screenshot.png in cwd). Returns the saved path.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Output file path (default: screenshot.png)."},
            },
        },
        category="desktop",
    )
    def screenshot(path: str = "screenshot.png") -> str:
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(path)
            return f"OK: screenshot saved to {path} ({img.size[0]}x{img.size[1]})"
        except ImportError:
            return _err("DEPS_MISSING", "Pillow not installed. Run: pip install Pillow")
        except Exception as exc:
            return _err("SCREENSHOT_FAIL", str(exc))

    @registry.register(
        name="mouse_click",
        description="Move mouse to (x, y) and click. button=left/right/middle.",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate."},
                "y": {"type": "integer", "description": "Y coordinate."},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Mouse button (default left)."},
            },
            "required": ["x", "y"],
        },
        category="desktop",
    )
    def mouse_click(x: int, y: int, button: str = "left") -> str:
        try:
            import pyautogui
            pyautogui.click(x, y, button=button)
            return f"OK: clicked {button} at ({x}, {y})"
        except ImportError:
            return _err("DEPS_MISSING", "pyautogui not installed. Run: pip install pyautogui")
        except Exception as exc:
            return _err("CLICK_FAIL", str(exc))

    @registry.register(
        name="mouse_move",
        description="Move the mouse cursor to (x, y) without clicking.",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate."},
                "y": {"type": "integer", "description": "Y coordinate."},
                "duration": {"type": "number", "description": "Move duration in seconds (default 0.2)."},
            },
            "required": ["x", "y"],
        },
        category="desktop",
    )
    def mouse_move(x: int, y: int, duration: float = 0.2) -> str:
        try:
            import pyautogui
            pyautogui.moveTo(x, y, duration=duration)
            return f"OK: moved to ({x}, {y})"
        except ImportError:
            return _err("DEPS_MISSING", "pyautogui not installed. Run: pip install pyautogui")
        except Exception as exc:
            return _err("MOVE_FAIL", str(exc))

    @registry.register(
        name="type_text",
        description="Type text using keyboard. For Chinese/CJK text, uses pyperclip to paste via clipboard since pyautogui cannot handle non-ASCII input directly.",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type."},
                "interval": {"type": "number", "description": "Seconds between keystrokes (default 0.02)."},
            },
            "required": ["text"],
        },
        category="desktop",
    )
    def type_text(text: str, interval: float = 0.02) -> str:
        try:
            # Detect non-ASCII (Chinese/CJK etc.) and use clipboard paste
            if any(ord(c) > 127 for c in text):
                import pyperclip
                import pyautogui
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "v")
                return f"OK: pasted {len(text)} chars via clipboard (CJK detected)"
            else:
                import pyautogui
                pyautogui.typewrite(text, interval=interval)
                return f"OK: typed {len(text)} chars"
        except ImportError as exc:
            return _err("DEPS_MISSING", f"Missing dependency: {exc}. Run: pip install pyautogui pyperclip")
        except Exception as exc:
            return _err("TYPE_FAIL", str(exc))

    @registry.register(
        name="press_key",
        description="Press a keyboard key or key combination. E.g. key='enter' or key='ctrl+c'.",
        parameters={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name or combo separated by '+', e.g. 'enter', 'ctrl+c', 'alt+tab'."},
            },
            "required": ["key"],
        },
        category="desktop",
    )
    def press_key(key: str) -> str:
        try:
            import pyautogui
            parts = [k.strip() for k in key.split("+")]
            if len(parts) == 1:
                pyautogui.press(parts[0])
            else:
                pyautogui.hotkey(*parts)
            return f"OK: pressed '{key}'"
        except ImportError:
            return _err("DEPS_MISSING", "pyautogui not installed. Run: pip install pyautogui")
        except Exception as exc:
            return _err("KEY_FAIL", str(exc))

    # ==================================================================
    # DATA OPERATIONS
    # ==================================================================

    @registry.register(
        name="read_csv",
        description="Read a CSV file and return rows as text. Supports delimiter and max_rows options.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to CSV file."},
                "delimiter": {"type": "string", "description": "Field delimiter (default ',')."},
                "max_rows": {"type": "integer", "description": "Max rows to return (default 100)."},
                "encoding": {"type": "string", "description": "File encoding (default utf-8)."},
            },
            "required": ["path"],
        },
        category="data",
    )
    def read_csv(path: str, delimiter: str = ",", max_rows: int = 100, encoding: str = "utf-8") -> str:
        p = Path(path)
        if not p.exists():
            return _err("FILE_NOT_FOUND", f"CSV not found: {path}")
        try:
            with open(p, "r", encoding=encoding, errors="replace", newline="") as f:
                reader = csv.reader(f, delimiter=delimiter)
                rows: List[str] = []
                for i, row in enumerate(reader):
                    if i >= max_rows:
                        rows.append(f"... (truncated at {max_rows} rows)")
                        break
                    rows.append(delimiter.join(row))
                return "\n".join(rows) if rows else "(empty CSV)"
        except Exception as exc:
            return _err("CSV_FAIL", str(exc))

    @registry.register(
        name="process_data",
        description="Process tabular data (CSV/JSON). Operations: head, tail, describe, sort, filter, groupby. Returns text output.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to data file (CSV or JSON)."},
                "operation": {
                    "type": "string",
                    "enum": ["head", "tail", "describe", "sort", "filter", "groupby"],
                    "description": "Processing operation.",
                },
                "column": {"type": "string", "description": "Column name for sort/filter/groupby."},
                "value": {"type": "string", "description": "Filter value (for filter operation)."},
                "n": {"type": "integer", "description": "Number of rows for head/tail (default 10)."},
                "ascending": {"type": "boolean", "description": "Sort ascending (default true)."},
            },
            "required": ["path", "operation"],
        },
        category="data",
    )
    def process_data(
        path: str,
        operation: str,
        column: Optional[str] = None,
        value: Optional[str] = None,
        n: int = 10,
        ascending: bool = True,
    ) -> str:
        p = Path(path)
        if not p.exists():
            return _err("FILE_NOT_FOUND", f"Data file not found: {path}")

        try:
            import pandas as pd
        except ImportError:
            return _err("DEPS_MISSING", "pandas not installed. Run: pip install pandas")

        try:
            if p.suffix.lower() == ".json":
                df = pd.read_json(p)
            else:
                df = pd.read_csv(p)

            if operation == "head":
                return df.head(n).to_string()
            if operation == "tail":
                return df.tail(n).to_string()
            if operation == "describe":
                return df.describe(include="all").to_string()
            if operation == "sort":
                if not column:
                    return _err("MISSING_PARAM", "sort requires 'column' parameter")
                return df.sort_values(column, ascending=ascending).head(n).to_string()
            if operation == "filter":
                if not column or value is None:
                    return _err("MISSING_PARAM", "filter requires 'column' and 'value' parameters")
                mask = df[column].astype(str).str.contains(value, case=False, na=False)
                return df[mask].head(n).to_string()
            if operation == "groupby":
                if not column:
                    return _err("MISSING_PARAM", "groupby requires 'column' parameter")
                grouped = df.groupby(column).size().reset_index(name="count")
                return grouped.sort_values("count", ascending=False).to_string()
            return _err("BAD_OP", f"Unknown operation: {operation}")
        except Exception as exc:
            return _err("DATA_FAIL", str(exc))

    @registry.register(
        name="export_data",
        description="Export data from CSV/JSON to another format (csv, json, markdown).",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Source data file path."},
                "output_path": {"type": "string", "description": "Output file path."},
                "format": {"type": "string", "enum": ["csv", "json", "markdown"], "description": "Output format."},
                "max_rows": {"type": "integer", "description": "Max rows to export (default all)."},
            },
            "required": ["path", "output_path", "format"],
        },
        category="data",
    )
    def export_data(path: str, output_path: str, format: str, max_rows: int = 0) -> str:
        p = Path(path)
        if not p.exists():
            return _err("FILE_NOT_FOUND", f"Source file not found: {path}")
        try:
            import pandas as pd
        except ImportError:
            return _err("DEPS_MISSING", "pandas not installed. Run: pip install pandas")
        try:
            if p.suffix.lower() == ".json":
                df = pd.read_json(p)
            else:
                df = pd.read_csv(p)

            if max_rows > 0:
                df = df.head(max_rows)

            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)

            if format == "csv":
                df.to_csv(out, index=False)
            elif format == "json":
                df.to_json(out, orient="records", force_ascii=False, indent=2)
            elif format == "markdown":
                out.write_text(df.to_markdown(index=False), encoding="utf-8")
            else:
                return _err("BAD_FORMAT", f"Unknown format: {format}")

            return f"OK: exported {len(df)} rows to {output_path} ({format})"
        except Exception as exc:
            return _err("EXPORT_FAIL", str(exc))

    # ==================================================================
    # WEB OPERATIONS
    # ==================================================================

    # Create a shared WebSearcher instance
    _searcher_instance: Any = None

    def _get_searcher() -> Any:
        nonlocal _searcher_instance
        if _searcher_instance is None:
            from .web_search import WebSearcher
            _searcher_instance = WebSearcher()
        return _searcher_instance

    @registry.register(
        name="web_search",
        description="Search the web using DuckDuckGo (primary) with Bing fallback. Returns results with title, URL, and snippet.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "max_results": {"type": "integer", "description": "Max results (default 10)."},
            },
            "required": ["query"],
        },
        category="web",
    )
    def web_search(query: str, max_results: int = 10) -> str:
        try:
            searcher = _get_searcher()
            results = searcher.search(query, max_results=max_results)
            if not results:
                return "(no results)"
            lines: List[str] = []
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. [{r.title}]({r.url})")
                if r.snippet:
                    lines.append(f"   {r.snippet}")
            return "\n".join(lines)
        except ImportError:
            return _err("DEPS_MISSING", "requests/bs4 not installed. Run: pip install requests beautifulsoup4 lxml")
        except Exception as exc:
            return _err("SEARCH_FAIL", str(exc))

    @registry.register(
        name="web_fetch",
        description="Fetch a web page and extract its text content, links, and meta info.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch."},
                "extract": {
                    "type": "string",
                    "enum": ["text", "links", "meta", "all"],
                    "description": "What to extract (default text).",
                },
                "max_chars": {"type": "integer", "description": "Max characters to return (default 8000)."},
            },
            "required": ["url"],
        },
        category="web",
    )
    def web_fetch(url: str, extract: str = "text", max_chars: int = 8000) -> str:
        try:
            searcher = _get_searcher()
            page = searcher.fetch_page(url)
            if extract == "links":
                lines = [f"{l['text']} -> {l['href']}" for l in page.links[:50]]
                return "\n".join(lines) if lines else "(no links)"
            if extract == "meta":
                lines = [f"{k}: {v}" for k, v in page.meta.items()]
                return "\n".join(lines) if lines else "(no meta)"
            if extract == "all":
                parts = [f"Title: {page.title}", "", page.text[:max_chars]]
                if page.links:
                    parts.append("\n--- Links ---")
                    for l in page.links[:30]:
                        parts.append(f"  {l['text']} -> {l['href']}")
                if page.meta:
                    parts.append("\n--- Meta ---")
                    for k, v in page.meta.items():
                        parts.append(f"  {k}: {v}")
                return "\n".join(parts)
            # default: text
            return page.text[:max_chars]
        except ImportError:
            return _err("DEPS_MISSING", "requests/bs4 not installed. Run: pip install requests beautifulsoup4 lxml")
        except Exception as exc:
            return _err("FETCH_FAIL", str(exc))

    # ==================================================================
    # BACKGROUND PROCESSES
    # ==================================================================

    @registry.register(
        name="start_background",
        description=f"Start a command in the background ({_SHELL_NAME}). Returns a job ID for later check/stop.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to run in background."},
                "cwd": {"type": "string", "description": "Working directory (optional)."},
            },
            "required": ["command"],
        },
        category="bg",
    )
    def start_background(command: str, cwd: Optional[str] = None) -> str:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        shell_args = ["cmd.exe", "/c", command] if _IS_WINDOWS else ["bash", "-c", command]
        try:
            proc = subprocess.Popen(
                shell_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
            _bg_state["counter"] += 1
            job_id = f"bg_{_bg_state['counter']}"
            _bg_processes[job_id] = proc
            return f"OK: started background job '{job_id}' (pid={proc.pid})"
        except Exception as exc:
            return _err("BG_START_FAIL", str(exc))

    @registry.register(
        name="check_background",
        description="Check the status of a background job. Returns stdout/stderr if finished, or 'running' status.",
        parameters={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID from start_background."},
                "wait": {"type": "boolean", "description": "Wait for completion (default false)."},
            },
            "required": ["job_id"],
        },
        category="bg",
    )
    def check_background(job_id: str, wait: bool = False) -> str:
        proc = _bg_processes.get(job_id)
        if proc is None:
            return _err("JOB_NOT_FOUND", f"Unknown job: {job_id}")
        try:
            if wait:
                stdout, stderr = proc.communicate(timeout=60)
            else:
                ret = proc.poll()
                if ret is None:
                    return f"[{job_id}] running (pid={proc.pid})"
                stdout, stderr = proc.communicate()
            out = stdout.decode("utf-8", errors="replace") if stdout else ""
            err = stderr.decode("utf-8", errors="replace") if stderr else ""
            parts = [f"[{job_id}] finished (exit={proc.returncode})"]
            if out.strip():
                parts.append(out.rstrip())
            if err.strip():
                parts.append(f"[stderr]\n{err.rstrip()}")
            return "\n".join(parts)
        except subprocess.TimeoutExpired:
            return f"[{job_id}] still running (timeout waiting)"
        except Exception as exc:
            return _err("BG_CHECK_FAIL", str(exc))

    @registry.register(
        name="stop_background",
        description="Stop (terminate) a background job by its job ID.",
        parameters={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID from start_background."},
            },
            "required": ["job_id"],
        },
        category="bg",
    )
    def stop_background(job_id: str) -> str:
        proc = _bg_processes.get(job_id)
        if proc is None:
            return _err("JOB_NOT_FOUND", f"Unknown job: {job_id}")
        try:
            if proc.poll() is not None:
                del _bg_processes[job_id]
                return f"[{job_id}] already finished (exit={proc.returncode})"
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
            del _bg_processes[job_id]
            return f"OK: stopped '{job_id}'"
        except Exception as exc:
            return _err("BG_STOP_FAIL", str(exc))
